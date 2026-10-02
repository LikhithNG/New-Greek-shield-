#!/usr/bin/env python3
"""
Slack Alert Manager - Send formatted alerts to Slack
"""

import os
import requests
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, List, Optional

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SLACK_TIMEOUT_SECONDS = 10


class SlackAlertManager:
    """Manages Slack notifications for agent recommendations"""
    
    def __init__(self):
        """Initialize Slack manager"""
        self.webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        self.enabled = os.getenv('SLACK_ALERTS_ENABLED', 'false').lower() == 'true'
        self.channel = os.getenv('SLACK_CHANNEL', '#options-alerts')
        
        if not self.webhook_url or 'YOUR-WEBHOOK-HERE' in self.webhook_url:
            logger.warning("⚠️  Slack webhook not configured")
            self.enabled = False
        
        if self.enabled:
            logger.info(f"✅ Slack alerts enabled for {self.channel}")
        else:
            logger.info("ℹ️  Slack alerts disabled")
    
    def send_analysis_alert(self, analysis_result: dict) -> bool:
        """
        Send complete analysis results to Slack
        
        Args:
            analysis_result: Complete output from enhanced system
        
        Returns:
            True if successful
        """
        if not self.enabled:
            logger.info("Slack disabled, skipping alert")
            return False
        
        try:
            summary = analysis_result.get('summary', {})
            strategy = analysis_result.get('strategy', {})
            
            # Build Slack message
            message = self._build_analysis_message(analysis_result)
            
            # Send to Slack
            response = requests.post(
                self.webhook_url,
                json=message,
                headers={'Content-Type': 'application/json'},
                timeout=SLACK_TIMEOUT_SECONDS
            )
            
            if response.status_code == 200:
                logger.info("✅ Slack alert sent successfully")
                return True
            else:
                logger.error(f"❌ Slack alert failed: {response.status_code} {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Slack alert error: {e}")
            return False
    
    def _build_analysis_message(self, result: dict) -> dict:
        """Build formatted Slack message"""
        
        summary = result.get('summary', {})
        strategy_data = result.get('strategy', {})
        confidence = strategy_data.get('confidence_analysis', {})
        input_data = result.get('input', {})
        
        # Determine emoji based on confidence
        if confidence.get('confidence_score', 0) >= 80:
            confidence_emoji = "🟢"
        elif confidence.get('confidence_score', 0) >= 60:
            confidence_emoji = "🟡"
        else:
            confidence_emoji = "🔴"
        
        # Determine risk emoji
        risk_score = summary.get('risk_score', 0)
        if risk_score < 30:
            risk_emoji = "🟢"
        elif risk_score < 60:
            risk_emoji = "🟡"
        else:
            risk_emoji = "🔴"
        
        # Build message blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🎯 Options Analysis Complete: {input_data.get('ticker', 'N/A')}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Strategy:*\n{summary.get('strategy_name', 'N/A').replace('_', ' ').title()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Goal:*\n{input_data.get('goal', 'N/A').title()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Confidence:*\n{confidence_emoji} {confidence.get('confidence_score', 0):.0f}% {confidence.get('confidence_level', 'N/A')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Risk Score:*\n{risk_emoji} {risk_score:.1f}/100"
                    }
                ]
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*💰 Financial Summary*\n• Positions: {summary.get('positions_count', 0)}\n• Investment: ${summary.get('total_investment', 0):,.2f}\n• Budget: ${input_data.get('budget', 0):,.2f}\n• Utilization: {(summary.get('total_investment', 0) / input_data.get('budget', 1) * 100):.1f}%"
                }
            }
        ]
        
        # Add plain-English explanation if available
        if 'plain_english_summary' in strategy_data:
            explanation = strategy_data['plain_english_summary'][:300]  # Truncate
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*💬 What This Means:*\n{explanation}..."
                }
            })
        
        # Add concerns if any
        if confidence.get('concerns'):
            concerns_text = "\n".join([f"• {c}" for c in confidence['concerns'][:3]])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*⚠️ Watch Out For:*\n{concerns_text}"
                }
            })
        
        # Add scenario analysis
        scenarios = strategy_data.get('scenario_analysis', {})
        if scenarios:
            scenario_text = ""
            if 'bull_case_5pct' in scenarios:
                scenario_text += f"📈 *+5%:* {scenarios['bull_case_5pct'][:100]}...\n"
            if 'bear_case_5pct' in scenarios:
                scenario_text += f"📉 *-5%:* {scenarios['bear_case_5pct'][:100]}...\n"
            
            if scenario_text:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*🎲 Scenarios:*\n{scenario_text}"
                    }
                })
        
        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Generated: {datetime.now().strftime('%Y-%m-%d %I:%M %p')} | Multi-Agent AI System"
                }
            ]
        })
        
        return {"blocks": blocks}
    
    def send_simple_alert(self, message: str, emoji: str = "🔔") -> bool:
        """
        Send simple text alert
        
        Args:
            message: Alert message
            emoji: Emoji prefix
        
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        try:
            payload = {
                "text": f"{emoji} {message}"
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=SLACK_TIMEOUT_SECONDS
            )
            
            return response.status_code == 200
        
        except Exception as e:
            logger.error(f"Simple alert failed: {e}")
            return False
    
    def send_error_alert(self, error: str, context: dict) -> bool:
        """Send error notification"""
        if not self.enabled:
            return False
        
        message = {
            "text": f"❌ Options Agent Error",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "❌ Agent Execution Error"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Error:* {error}\n\n*Context:* {context.get('ticker', 'N/A')} | Budget: ${context.get('budget', 0):,.2f}"
                    }
                }
            ]
        }
        
        try:
            response = requests.post(self.webhook_url, json=message,
                                     timeout=SLACK_TIMEOUT_SECONDS)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error alert failed: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Test Slack connection"""
        if not self.enabled:
            logger.warning("Slack not enabled")
            return False
        
        try:
            test_message = {
                "text": "✅ Options Risk Multi-Agent System - Slack Integration Test",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "✅ *Slack Integration Working!*\n\nYour multi-agent system is now connected to Slack.\n\nYou'll receive alerts here when new recommendations are generated."
                        }
                    }
                ]
            }
            
            response = requests.post(
                self.webhook_url,
                json=test_message,
                headers={'Content-Type': 'application/json'},
                timeout=SLACK_TIMEOUT_SECONDS
            )
            
            if response.status_code == 200:
                logger.info("✅ Slack test message sent!")
                return True
            else:
                logger.error(f"❌ Test failed: {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Slack test failed: {e}")
            return False


# Singleton
_slack_manager = None


def get_slack_manager() -> SlackAlertManager:
    """Get or create Slack manager singleton"""
    global _slack_manager
    if _slack_manager is None:
        _slack_manager = SlackAlertManager()
    return _slack_manager


if __name__ == "__main__":
    print("\n" + "="*70)
    print("TESTING SLACK INTEGRATION")
    print("="*70)
    
    slack = get_slack_manager()
    
    if not slack.enabled:
        print("\n❌ Slack not enabled")
        print("\nTo enable:")
        print("1. Create webhook at https://api.slack.com/apps")
        print("2. Add SLACK_WEBHOOK_URL to .env")
        print("3. Set SLACK_ALERTS_ENABLED=true")
    else:
        print("\n✅ Slack configured, testing connection...")
        success = slack.test_connection()
        
        if success:
            print("\n✅ TEST PASSED!")
            print("Check your Slack channel for the test message!")
        else:
            print("\n❌ Test failed - check webhook URL")
            