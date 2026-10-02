#!/usr/bin/env python3
"""
Strategy & Discovery Agent - AI-Powered Market Analysis
Analyzes goals, market conditions, and recommends optimal strategies
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.core.base_agent import BaseAgent
import pandas as pd
from datetime import datetime


class StrategyAgent(BaseAgent):
    """
    Strategy Agent - The AI Planner
    Uses LLM to reason about market conditions and recommend strategies
    """
    
    def __init__(self):
        super().__init__(
            agent_name="StrategyAgent",
            agent_role="AI-Powered Strategy Discovery & Planning",
            use_llm=True  # Enable AI reasoning
        )
        
        # Risk profiles
        self.risk_profiles = {
            'conservative': {
                'max_delta_exposure': 50,
                'max_gamma_risk': 0.03,
                'max_theta_decay_daily': 50,
                'min_dte': 14,
                'description': 'Low risk - focuses on stability'
            },
            'moderate': {
                'max_delta_exposure': 150,
                'max_gamma_risk': 0.06,
                'max_theta_decay_daily': 150,
                'min_dte': 7,
                'description': 'Balanced risk-reward'
            },
            'aggressive': {
                'max_delta_exposure': 300,
                'max_gamma_risk': 0.10,
                'max_theta_decay_daily': 300,
                'min_dte': 3,
                'description': 'High risk - seeks maximum returns'
            }
        }
    
    def validate_input(self, context: dict) -> bool:
        """Validate required inputs"""
        required = ['ticker', 'budget', 'risk_profile']
        for field in required:
            if field not in context:
                self.logger.error(f"Missing required field: {field}")
                return False
        
        if context['risk_profile'] not in self.risk_profiles:
            self.logger.error(f"Invalid risk profile: {context['risk_profile']}")
            return False
        
        return True
    
    def execute(self, context: dict) -> dict:
        """
        Main strategy execution with AI reasoning
        
        Args:
            context: {
                'ticker': 'AAPL',
                'budget': 5000,
                'risk_profile': 'moderate',
                'goal': 'bullish' | 'bearish' | 'neutral' | 'volatility'
            }
        """
        ticker = context['ticker']
        budget = context['budget']
        risk_profile = context['risk_profile']
        goal = context.get('goal', 'neutral')
        
        self.log_action("Strategy analysis started", {
            'ticker': ticker,
            'budget': budget,
            'risk_profile': risk_profile,
            'goal': goal
        })
        
        # Get current market data
        market_data = self._analyze_market_conditions(ticker)
        
        # Get risk constraints
        constraints = self.risk_profiles[risk_profile]
        
        # Analyze portfolio risk
        portfolio_risk = self._analyze_portfolio_risk(ticker)
        
        # Use AI to determine strategy
        strategy = self._ai_determine_strategy(goal, market_data, constraints, budget)
        
        # Generate AI-powered recommendations
        recommendations = self._ai_generate_recommendations(
            strategy, market_data, portfolio_risk, constraints
        )
        
        # Calculate risk score
        risk_score = self._calculate_risk_score(portfolio_risk, constraints)
        
        return {
            'strategy': strategy,
            'recommendations': recommendations,
            'constraints': constraints,
            'market_analysis': market_data,
            'portfolio_risk': portfolio_risk,
            'risk_score': risk_score
        }
    
    def _analyze_market_conditions(self, ticker: str) -> dict:
        """Analyze current market conditions from Snowflake"""
        
        # Fixed query - properly aggregated
        query = """
        SELECT 
            MAX(UNDERLYING_PRICE) as underlying_price,
            AVG(IMPLIED_VOL) as avg_iv,
            MAX(IMPLIED_VOL) as max_iv,
            MIN(IMPLIED_VOL) as min_iv,
            COUNT(*) as total_contracts,
            AVG(VOLUME) as avg_volume,
            AVG(OPEN_INTEREST) as avg_oi
        FROM OPTIONS_SNAPSHOT
        WHERE SYMBOL = %s
        AND SNAPSHOT_TS >= CURRENT_TIMESTAMP() - INTERVAL '1 DAY'
        GROUP BY SYMBOL
        """
        
        # Failures propagate so safe_execute reports them instead of the
        # agent recommending a strategy against placeholder market data.
        try:
            results = self.query_snowflake(query, (ticker,))
        except Exception as e:
            self.logger.error(f"Market analysis failed: {e}")
            raise RuntimeError(f"Market data query failed for {ticker}: {e}") from e
        
        if not results:
            raise ValueError(f"No market data for {ticker} in OPTIONS_SNAPSHOT in the last day")
        
        data = results[0]
        
        underlying_price = float(data.get('UNDERLYING_PRICE') or 0)
        if underlying_price <= 0:
            raise ValueError(f"Missing underlying price for {ticker} in OPTIONS_SNAPSHOT")
        
        # Determine IV regime
        avg_iv = float(data.get('AVG_IV') or 0.30)
        if avg_iv < 0.20:
            iv_regime = 'low'
        elif avg_iv < 0.40:
            iv_regime = 'normal'
        else:
            iv_regime = 'high'
        
        # Determine liquidity
        avg_volume = float(data.get('AVG_VOLUME') or 0)
        if avg_volume > 1000:
            liquidity = 'high'
        elif avg_volume > 100:
            liquidity = 'moderate'
        else:
            liquidity = 'low'
        
        market_data = {
            'underlying_price': underlying_price,
            'avg_iv': avg_iv,
            'iv_regime': iv_regime,
            'liquidity': liquidity,
            'total_contracts': int(data.get('TOTAL_CONTRACTS') or 0),
            'avg_volume': int(avg_volume)
        }
        
        self.update_state('market_data', market_data)
        self.logger.info(f"Market data: Price=${market_data['underlying_price']:.2f}, IV={market_data['avg_iv']:.1%}, Contracts={market_data['total_contracts']}")
        return market_data
    
    def _analyze_portfolio_risk(self, ticker: str) -> dict:
        """Get current portfolio risk from Snowflake"""
        
        # This will fail gracefully if the tables don't exist yet
        try:
            query = """
            SELECT 
                NET_DELTA,
                NET_GAMMA,
                NET_THETA,
                NET_VEGA,
                N_CONTRACTS,
                N_ITM,
                N_OTM
            FROM PROCESSED.DAILY_RISK_SUMMARY
            WHERE TICKER = %s
            ORDER BY ASOF_DATE DESC
            LIMIT 1
            """
            
            results = self.query_snowflake(query, (ticker,))
            
            if not results:
                return {
                    'net_delta': 0,
                    'net_gamma': 0,
                    'net_theta': 0,
                    'net_vega': 0,
                    'total_positions': 0,
                    'risk_level': 'none'
                }
            
            data = results[0]
            
            portfolio_risk = {
                'net_delta': float(data['NET_DELTA'] or 0),
                'net_gamma': float(data['NET_GAMMA'] or 0),
                'net_theta': float(data['NET_THETA'] or 0),
                'net_vega': float(data['NET_VEGA'] or 0),
                'total_positions': int(data['N_CONTRACTS'] or 0)
            }
            
            # Calculate risk level
            if abs(portfolio_risk['net_delta']) > 200 or abs(portfolio_risk['net_gamma']) > 0.08:
                portfolio_risk['risk_level'] = 'high'
            elif abs(portfolio_risk['net_delta']) > 100 or abs(portfolio_risk['net_gamma']) > 0.04:
                portfolio_risk['risk_level'] = 'moderate'
            else:
                portfolio_risk['risk_level'] = 'low'
            
            return portfolio_risk
        
        except Exception as e:
            self.logger.warning(f"Portfolio risk query failed (table may not exist): {e}")
            # 'unknown' (not 'none') so a failed lookup is never read as "no risk"
            return {
                'net_delta': 0,
                'net_gamma': 0,
                'net_theta': 0,
                'net_vega': 0,
                'total_positions': 0,
                'risk_level': 'unknown',
                'error': str(e)
            }
    
    def _ai_determine_strategy(self, goal: str, market_data: dict, 
                              constraints: dict, budget: float) -> dict:
        """Use AI to determine optimal strategy"""
        
        if not self.use_llm:
            # Fallback to rule-based
            return self._rule_based_strategy(goal, market_data['iv_regime'])
        
        prompt = f"""You are an expert options trader. Analyze this situation and recommend the best strategy.

GOAL: {goal}
BUDGET: ${budget:,.2f}
RISK PROFILE: {constraints['description']}

MARKET CONDITIONS:
- Stock: ${market_data['underlying_price']:.2f}
- Average IV: {market_data['avg_iv']:.1%} ({market_data['iv_regime']} volatility regime)
- Liquidity: {market_data['liquidity']}
- Contracts available: {market_data['total_contracts']}

CONSTRAINTS:
- Max Delta: {constraints['max_delta_exposure']}
- Max Gamma: {constraints['max_gamma_risk']}
- Max Theta decay: ${constraints['max_theta_decay_daily']}/day
- Minimum DTE: {constraints['min_dte']} days

Based on this, what options strategy do you recommend?

Respond with JSON containing:
{{
  "strategy_name": "name of strategy",
  "rationale": "why this strategy fits the goal and conditions",
  "key_risks": ["risk1", "risk2"],
  "expected_outcome": "what to expect",
  "recommended_dte_min": number,
  "recommended_dte_max": number
}}"""
        
        try:
            response = self.ask_llm_json(prompt, system="You are an expert options trading advisor.")
            
            self.set_confidence('strategy', 85, ['AI reasoning with market data'])
            
            return {
                'name': response.get('strategy_name', 'long_call'),
                'goal': goal,
                'iv_regime': market_data['iv_regime'],
                'rationale': response.get('rationale', ''),
                'key_risks': response.get('key_risks', []),
                'expected_outcome': response.get('expected_outcome', ''),
                'recommended_dte_min': response.get('recommended_dte_min', constraints['min_dte']),
                'recommended_dte_max': response.get('recommended_dte_max', constraints['min_dte'] + 30),
                'ai_powered': True
            }
        
        except Exception as e:
            self.logger.warning(f"AI strategy determination failed: {e}, using rule-based")
            return self._rule_based_strategy(goal, market_data['iv_regime'])
    
    def _rule_based_strategy(self, goal: str, iv_regime: str) -> dict:
        """Fallback rule-based strategy"""
        
        strategies = {
            'bullish': {
                'low': 'long_call',
                'normal': 'bull_call_spread',
                'high': 'cash_secured_put'
            },
            'bearish': {
                'low': 'long_put',
                'normal': 'bear_put_spread',
                'high': 'covered_call'
            },
            'neutral': {
                'low': 'calendar_spread',
                'normal': 'iron_condor',
                'high': 'short_strangle'
            },
            'volatility': {
                'low': 'long_straddle',
                'normal': 'long_strangle',
                'high': 'short_iron_butterfly'
            }
        }
        
        strategy_name = strategies.get(goal, {}).get(iv_regime, 'long_call')
        
        return {
            'name': strategy_name,
            'goal': goal,
            'iv_regime': iv_regime,
            'rationale': f"Rule-based selection for {goal} in {iv_regime} IV",
            'ai_powered': False,
            'recommended_dte_min': 7,
            'recommended_dte_max': 45
        }
    
    def _ai_generate_recommendations(self, strategy: dict, market_data: dict,
                                    portfolio_risk: dict, constraints: dict) -> list:
        """Generate AI-powered recommendations"""
        
        recommendations = []
        
        # Always add strategy recommendation
        recommendations.append({
            'type': 'strategy',
            'priority': 'high',
            'message': f"Recommended: {strategy['name'].replace('_', ' ').title()}",
            'reason': strategy.get('rationale', f"Based on {strategy['goal']} outlook")
        })
        
        # Risk warnings
        if portfolio_risk['risk_level'] == 'high':
            recommendations.append({
                'type': 'risk_warning',
                'priority': 'high',
                'message': f"Portfolio risk is HIGH (Delta: {portfolio_risk['net_delta']:.2f})",
                'reason': "Consider reducing position sizes"
            })
        elif portfolio_risk['risk_level'] == 'unknown':
            recommendations.append({
                'type': 'risk_warning',
                'priority': 'high',
                'message': "Portfolio risk could not be determined",
                'reason': portfolio_risk.get('error', 'Risk summary unavailable')
            })
        
        # IV-based recommendations
        if market_data['iv_regime'] == 'high':
            recommendations.append({
                'type': 'market_condition',
                'priority': 'medium',
                'message': f"High IV detected ({market_data['avg_iv']:.1%})",
                'reason': "Consider selling options to collect premium"
            })
        
        return recommendations
    
    def _calculate_risk_score(self, portfolio_risk: dict, constraints: dict) -> float:
        """Calculate overall risk score (0-100)"""
        
        delta_score = min(abs(portfolio_risk['net_delta']) / constraints['max_delta_exposure'] * 30, 30)
        gamma_score = min(abs(portfolio_risk['net_gamma']) / constraints['max_gamma_risk'] * 30, 30)
        theta_score = min(abs(portfolio_risk['net_theta']) / constraints['max_theta_decay_daily'] * 40, 40)
        
        total_score = delta_score + gamma_score + theta_score
        
        self.set_confidence('risk_score', 100 - total_score, ['Calculated from portfolio Greeks'])
        
        return round(total_score, 2)


if __name__ == "__main__":
    print("\n" + "="*70)
    print("TESTING STRATEGY AGENT")
    print("="*70)
    
    agent = StrategyAgent()
    
    context = {
        'ticker': 'AAPL',
        'budget': 5000,
        'risk_profile': 'moderate',
        'goal': 'bullish'
    }
    
    result = agent.safe_execute(context)
    
    print(f"\nSuccess: {result['success']}")
    if result['success']:
        print(f"\nStrategy: {result['strategy']['name']}")
        print(f"Rationale: {result['strategy'].get('rationale', 'N/A')[:150]}")
        print(f"Risk Score: {result['risk_score']}/100")
        print(f"\nRecommendations:")
        for i, rec in enumerate(result['recommendations'], 1):
            print(f"  {i}. [{rec['priority'].upper()}] {rec['message']}")
    
    print("\n✅ Strategy Agent test complete!")