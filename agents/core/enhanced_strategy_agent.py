#!/usr/bin/env python3
"""
ENHANCED Strategy Agent with Advanced AI Features
- Plain-English explanations
- Confidence scoring
- Scenario analysis
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.core.strategy_agent import StrategyAgent
import json


class EnhancedStrategyAgent(StrategyAgent):
    """
    Enhanced Strategy Agent with AI-powered features:
    - Plain-English explanations for every recommendation
    - Confidence scoring with reasoning
    - Scenario analysis (bull/bear cases)
    """
    
    def __init__(self):
        super().__init__()
        self.agent_name = "EnhancedStrategyAgent"
    
    def execute(self, context: dict) -> dict:
        """Enhanced execution with additional AI features"""
        
        # Run base strategy logic
        result = super().execute(context)
        
        if not result:
            return result
        
        # Add AI enhancements
        result['plain_english_summary'] = self._generate_plain_english_summary(
            result['strategy'],
            result['market_analysis'],
            result['risk_score']
        )
        
        result['scenario_analysis'] = self._generate_scenario_analysis(
            context,
            result['strategy'],
            result['market_analysis']
        )
        
        result['confidence_analysis'] = self._generate_confidence_analysis(
            result['market_analysis'],
            result['portfolio_risk']
        )
        
        return result
    
    def _generate_plain_english_summary(self, strategy: dict, market_data: dict, 
                                       risk_score: float) -> str:
        """Use AI to generate plain-English explanation"""
        
        if not self.use_llm or not self.llm:
            return f"Recommended strategy: {strategy['name']} based on current market conditions."
        
        prompt = f"""You are explaining options trading to someone who is intelligent but not an expert.

STRATEGY RECOMMENDED: {strategy['name']}
MARKET CONDITIONS:
- Stock Price: ${market_data['underlying_price']:.2f}
- Implied Volatility: {market_data['avg_iv']:.1%} ({market_data['iv_regime']} regime)
- Liquidity: {market_data['liquidity']}

RISK SCORE: {risk_score}/100

Explain in 2-3 simple sentences:
1. What this strategy means in plain English
2. Why it's a good fit right now
3. What the main risk is

Be conversational and clear. No jargon."""

        try:
            explanation = self.ask_llm(
                prompt=prompt,
                system="You are a helpful financial educator who explains complex concepts simply.",
                temperature=0.7,
                max_tokens=200
            )
            
            self.log_action("Generated plain-English explanation", {
                'length': len(explanation)
            })
            
            return explanation
        
        except Exception as e:
            self.logger.warning(f"Failed to generate explanation: {e}")
            return f"Recommended strategy: {strategy['name']}"
    
    def _generate_scenario_analysis(self, context: dict, strategy: dict, 
                                    market_data: dict) -> dict:
        """Generate what-if scenarios using AI"""
        
        if not self.use_llm or not self.llm:
            return {
                'bull_case': 'Stock moves up - strategy profits',
                'bear_case': 'Stock moves down - strategy may lose',
                'base_case': 'Stock stays flat - time decay affects position'
            }
        
        prompt = f"""Analyze these scenarios for a {strategy['name']} on {context['ticker']}:

Current Price: ${market_data['underlying_price']:.2f}
Strategy: {strategy['name']}
Budget: ${context['budget']:,.2f}

Provide a brief 1-sentence analysis for each:

{{
  "bull_case_5pct": "if stock rises 5%...",
  "bear_case_5pct": "if stock falls 5%...",
  "sideways": "if stock stays flat for 2 weeks..."
}}

Be specific about profit/loss potential."""

        try:
            scenarios = self.ask_llm_json(
                prompt=prompt,
                system="You are an expert options analyst.",
                max_tokens=300
            )
            
            self.log_action("Generated scenario analysis", {
                'scenarios': len(scenarios)
            })
            
            return scenarios
        
        except Exception as e:
            self.logger.warning(f"Failed to generate scenarios: {e}")
            return {
                'bull_case_5pct': 'Potential profit if stock rises',
                'bear_case_5pct': 'Limited risk if stock falls',
                'sideways': 'Time decay is a factor'
            }
    
    def _generate_confidence_analysis(self, market_data: dict, 
                                     portfolio_risk: dict) -> dict:
        """Generate detailed confidence analysis"""
        
        confidence_score = 100.0
        confidence_factors = []
        concerns = []
        
        # Factor 1: Data quality
        if market_data['total_contracts'] < 100:
            confidence_score -= 20
            concerns.append("Limited contract data available")
        else:
            confidence_factors.append("Sufficient market data")
        
        # Factor 2: Liquidity
        if market_data['liquidity'] == 'high':
            confidence_factors.append("High liquidity environment")
        elif market_data['liquidity'] == 'low':
            confidence_score -= 15
            concerns.append("Lower liquidity may impact execution")
        
        # Factor 3: IV regime
        if market_data['iv_regime'] == 'high':
            confidence_score -= 10
            concerns.append("Elevated volatility increases uncertainty")
        else:
            confidence_factors.append(f"{market_data['iv_regime'].title()} IV regime")
        
        # Factor 4: Current portfolio risk
        if portfolio_risk['risk_level'] == 'high':
            confidence_score -= 25
            concerns.append("Existing portfolio at elevated risk")
        elif portfolio_risk['risk_level'] == 'low':
            confidence_factors.append("Current portfolio well-balanced")
        elif portfolio_risk['risk_level'] == 'unknown':
            concerns.append("Current portfolio risk could not be determined")
        
        confidence_score = max(0, min(100, confidence_score))
        
        # Determine confidence level
        if confidence_score >= 80:
            level = "HIGH"
            recommendation = "Strong conviction - execute as planned"
        elif confidence_score >= 60:
            level = "MODERATE"
            recommendation = "Good setup - monitor execution closely"
        elif confidence_score >= 40:
            level = "LOW"
            recommendation = "Proceed with caution - consider smaller position sizes"
        else:
            level = "VERY LOW"
            recommendation = "High uncertainty - wait for better conditions"
        
        return {
            'confidence_score': round(confidence_score, 1),
            'confidence_level': level,
            'supporting_factors': confidence_factors,
            'concerns': concerns,
            'recommendation': recommendation
        }


if __name__ == "__main__":
    print("\n" + "="*70)
    print("TESTING ENHANCED STRATEGY AGENT")
    print("="*70)
    
    agent = EnhancedStrategyAgent()
    
    context = {
        'ticker': 'AAPL',
        'budget': 5000,
        'risk_profile': 'moderate',
        'goal': 'bullish'
    }
    
    result = agent.safe_execute(context)
    
    print(f"\nSuccess: {result['success']}")
    
    if result['success']:
        print(f"\n📊 STRATEGY: {result['strategy']['name']}")
        print(f"Risk Score: {result['risk_score']}/100")
        
        print(f"\n💬 PLAIN-ENGLISH EXPLANATION:")
        print(f"{result['plain_english_summary']}")
        
        print(f"\n🎲 SCENARIO ANALYSIS:")
        scenarios = result['scenario_analysis']
        for scenario, outcome in scenarios.items():
            print(f"  {scenario}: {outcome}")
        
        print(f"\n📈 CONFIDENCE ANALYSIS:")
        conf = result['confidence_analysis']
        print(f"  Score: {conf['confidence_score']}/100 ({conf['confidence_level']})")
        print(f"  Recommendation: {conf['recommendation']}")
        
        if conf['supporting_factors']:
            print(f"\n  ✅ Supporting Factors:")
            for factor in conf['supporting_factors']:
                print(f"    • {factor}")
        
        if conf['concerns']:
            print(f"\n  ⚠️  Concerns:")
            for concern in conf['concerns']:
                print(f"    • {concern}")
    
    print("\n✅ Enhanced Strategy Agent test complete!")