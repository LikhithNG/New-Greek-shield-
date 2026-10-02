#!/usr/bin/env python3
"""
Logistics & Temporal Agent - Manages timing and execution feasibility
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.core.base_agent import BaseAgent
from datetime import datetime


class LogisticsAgent(BaseAgent):
    """
    Logistics Agent - The Scheduler
    Filters contracts by time constraints and liquidity
    """
    
    def __init__(self):
        super().__init__(
            agent_name="LogisticsAgent",
            agent_role="Logistics & Temporal Management",
            use_llm=False  # Uses rule-based logic for speed
        )
        
        # Liquidity thresholds
        self.min_volume = 10
        self.min_open_interest = 50
    
    def validate_input(self, context: dict) -> bool:
        """Validate required inputs"""
        required = ['ticker', 'strategy']
        for field in required:
            if field not in context:
                self.logger.error(f"Missing required field: {field}")
                return False
        return True
    
    def execute(self, context: dict) -> dict:
        """
        Main logistics execution
        
        Args:
            context: {
                'ticker': 'AAPL',
                'strategy': strategy_dict from StrategyAgent
            }
        """
        ticker = context['ticker']
        strategy = context['strategy']
        
        self.log_action("Logistics analysis started", {'ticker': ticker})
        
        # Fetch all available contracts
        all_contracts = self._fetch_available_contracts(ticker)
        
        # Filter by temporal constraints (DTE)
        temporal_filtered = self._apply_temporal_filters(all_contracts, strategy)
        
        # Filter by liquidity
        liquid_contracts = self._apply_liquidity_filters(temporal_filtered)
        
        # Check feasibility
        feasibility = self._check_feasibility(liquid_contracts, strategy)
        
        return {
            'available_contracts': len(all_contracts),
            'temporal_filtered': len(temporal_filtered),
            'liquid_contracts': len(liquid_contracts),
            'feasible': feasibility['is_feasible'],
            'feasibility_report': feasibility,
            'filtered_contracts': liquid_contracts[:50]  # Top 50 for review
        }
    
    def _fetch_available_contracts(self, ticker: str) -> list:
        """Fetch all available option contracts from Snowflake"""
        
        query = """
        SELECT 
            CONTRACT_SYMBOL,
            STRIKE,
            EXPIRY,
            OPTION_TYPE,
            DTE,
            LAST_PRICE,
            BID,
            ASK,
            VOLUME,
            OPEN_INTEREST,
            IMPLIED_VOL,
            UNDERLYING_PRICE
        FROM OPTIONS_SNAPSHOT
        WHERE SYMBOL = %s
        AND SNAPSHOT_TS >= CURRENT_TIMESTAMP() - INTERVAL '1 DAY'
        AND DTE > 0
        ORDER BY EXPIRY, STRIKE
        LIMIT 500
        """
        
        try:
            results = self.query_snowflake(query, (ticker,))
            self.logger.info(f"✅ Fetched {len(results)} contracts from Snowflake")
            return results
        
        except Exception as e:
            # Re-raise: an empty list would be indistinguishable from
            # "no contracts available" and report a false infeasibility.
            self.logger.error(f"Failed to fetch contracts: {e}")
            raise
    
    def _apply_temporal_filters(self, contracts: list, strategy: dict) -> list:
        """Filter contracts based on time constraints (DTE)"""
        
        min_dte = strategy.get('recommended_dte_min', 7)
        max_dte = strategy.get('recommended_dte_max', 60)
        
        filtered = []
        
        for contract in contracts:
            dte = contract.get('DTE', 0)
            
            if min_dte <= dte <= max_dte:
                # Add temporal metadata
                contract['days_until_expiry'] = dte
                contract['is_weekly'] = dte <= 7
                contract['is_monthly'] = 21 <= dte <= 35
                
                filtered.append(contract)
        
        self.log_action("Temporal filtering applied", {
            'min_dte': min_dte,
            'max_dte': max_dte,
            'contracts_remaining': len(filtered)
        })
        
        return filtered
    
    def _apply_liquidity_filters(self, contracts: list) -> list:
        """Filter contracts by liquidity metrics"""
        
        liquid = []
        
        for contract in contracts:
            volume = int(contract.get('VOLUME', 0) or 0)
            oi = int(contract.get('OPEN_INTEREST', 0) or 0)
            bid = float(contract.get('BID', 0) or 0)
            ask = float(contract.get('ASK', 0) or 0)
            
            # Calculate bid-ask spread
            if ask > 0:
                spread_pct = float((ask - bid) / ask)
            else:
                spread_pct = 1.0  # Flag as illiquid
            
            # Apply liquidity filters
            is_liquid = (
                volume >= self.min_volume and
                oi >= self.min_open_interest and
                spread_pct <= 0.10  # Max 10% spread
            )
            
            if is_liquid:
                contract['bid_ask_spread_pct'] = spread_pct
                contract['liquidity_score'] = self._calculate_liquidity_score(volume, oi, spread_pct)
                liquid.append(contract)
        
        self.log_action("Liquidity filtering applied", {
            'min_volume': self.min_volume,
            'min_oi': self.min_open_interest,
            'contracts_remaining': len(liquid)
        })
        
        return liquid
    
    def _calculate_liquidity_score(self, volume: int, oi: int, spread_pct: float) -> float:
        """Calculate liquidity score (0-100)"""
        
        volume_score = min(volume / 1000 * 40, 40)
        oi_score = min(oi / 5000 * 40, 40)
        spread_score = max(0, (0.05 - spread_pct) / 0.05 * 20)
        
        return round(volume_score + oi_score + spread_score, 2)
    
    def _check_feasibility(self, contracts: list, strategy: dict) -> dict:
        """Check if strategy is feasible with available contracts"""
        
        if not contracts or len(contracts) < 5:
            return {
                'is_feasible': False,
                'reason': 'Insufficient liquid contracts available',
                'total_contracts': len(contracts),
                'suggestions': ['Widen time horizon', 'Adjust liquidity requirements']
            }
        
        # Check if we have both calls and puts if needed
        calls = [c for c in contracts if c['OPTION_TYPE'] == 'CALL']
        puts = [c for c in contracts if c['OPTION_TYPE'] == 'PUT']
        
        # Check strike distribution
        strikes = sorted(set(c['STRIKE'] for c in contracts))
        
        feasibility = {
            'is_feasible': True,
            'total_contracts': len(contracts),
            'calls_available': len(calls),
            'puts_available': len(puts),
            'unique_strikes': len(strikes),
            'warnings': [],
            'suggestions': []
        }
        
        # Add warnings if needed
        if len(calls) < 5:
            feasibility['warnings'].append('Limited call options available')
        
        if len(puts) < 5:
            feasibility['warnings'].append('Limited put options available')
        
        if len(strikes) < 10:
            feasibility['warnings'].append('Limited strike selection')
        
        self.log_action("Feasibility checked", feasibility)
        
        return feasibility


if __name__ == "__main__":
    print("\n" + "="*70)
    print("TESTING LOGISTICS AGENT")
    print("="*70)
    
    agent = LogisticsAgent()
    
    # Mock strategy from Strategy Agent
    strategy = {
        'name': 'bull_call_spread',
        'recommended_dte_min': 14,
        'recommended_dte_max': 45
    }
    
    context = {
        'ticker': 'AAPL',
        'strategy': strategy
    }
    
    result = agent.safe_execute(context)
    
    print(f"\nSuccess: {result['success']}")
    if result['success']:
        print(f"\nAvailable Contracts: {result['available_contracts']}")
        print(f"After Temporal Filter: {result['temporal_filtered']}")
        print(f"After Liquidity Filter: {result['liquid_contracts']}")
        print(f"Feasible: {result['feasible']}")
        print(f"\nFeasibility:")
        feas = result['feasibility_report']
        print(f"  Calls: {feas.get('calls_available', 0)}")
        print(f"  Puts: {feas.get('puts_available', 0)}")
        print(f"  Strikes: {feas.get('unique_strikes', 0)}")
    
    print("\n✅ Logistics Agent test complete!")