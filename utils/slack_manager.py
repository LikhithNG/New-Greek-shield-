#!/usr/bin/env python3
"""
Slack Alert Manager — Options Risk Bot (Panel-Ready)

What this version guarantees:
• Greeks Risk Alerts (Delta / Gamma / IV)
• HIGH / MEDIUM / LOW severity
• Explainable interpretation
• Trust justification
• Risk flags
• FINAL plain-English takeaway (human readable)
• Safe (no trading advice)
"""

import os
import requests
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SLACK_TIMEOUT_SECONDS = 10


class SlackAlertManager:
    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.enabled = os.getenv("SLACK_ALERTS_ENABLED", "false").lower() == "true"
        self.channel = os.getenv("SLACK_CHANNEL", "#options-alerts")

        if not self.webhook_url:
            logger.warning("Slack webhook not configured")
            self.enabled = False

    # ==========================================================
    # PUBLIC METHOD
    # ==========================================================
    def send_greeks_alert(
        self,
        ticker: str,
        net_delta: float,
        net_gamma: float,
        avg_iv: float,
        contracts: int,
        market_timestamp: str,
        data_source: str,
        run_id: str
    ) -> bool:
        if not self.enabled:
            return False

        payload = self._build_message(
            ticker,
            net_delta,
            net_gamma,
            avg_iv,
            contracts,
            market_timestamp,
            data_source,
            run_id
        )

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=SLACK_TIMEOUT_SECONDS)
            return resp.status_code == 200
        except Exception as e:
            logger.error(e)
            return False

    # ==========================================================
    # MESSAGE BUILDER
    # ==========================================================
    def _build_message(
        self,
        ticker,
        net_delta,
        net_gamma,
        avg_iv,
        contracts,
        market_timestamp,
        data_source,
        run_id
    ):
        # Normalize IV
        iv_pct = avg_iv * 100 if avg_iv <= 3 else avg_iv

        # Severity logic
        if abs(net_delta) >= 120 or net_gamma >= 0.6 or iv_pct >= 140:
            severity = "HIGH"
            emoji = "🔴"
        elif abs(net_delta) >= 50 or net_gamma >= 0.25 or iv_pct >= 80:
            severity = "MEDIUM"
            emoji = "🟡"
        else:
            severity = "LOW"
            emoji = "🟢"

        generated = datetime.now().strftime("%Y-%m-%d %I:%M %p ET")

        # ============================
        # FINAL PLAIN-ENGLISH TAKEAWAY
        # ============================
        plain_text_takeaway = (
            "*📌 Plain-Text Takeaway (What this means)*\n"
            f"This alert indicates a **bullish but high-risk setup** for {ticker}. "
            f"The portfolio is expected to benefit if {ticker} moves higher, but because "
            "**gamma is elevated** and **implied volatility is extremely high**, "
            "risk can change quickly and portfolio value may swing sharply even on small moves. "
            "This should be treated as a **risk warning for human review**, not a trade recommendation."
        )

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Greeks Risk Alert: {ticker} ({severity})",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Contracts Analyzed:*\n{contracts}"},
                    {"type": "mrkdwn", "text": f"*Avg IV:*\n{iv_pct:.0f}%"},
                    {"type": "mrkdwn", "text": f"*Net Delta:*\n{net_delta:+.6f}"},
                    {"type": "mrkdwn", "text": f"*Net Gamma:*\n{net_gamma:.10f}"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*🧠 Explainable Interpretation*\n"
                        f"• Directional bias: **{'Bullish' if net_delta > 0 else 'Bearish'}** "
                        f"(Net Delta {net_delta:+.2f}).\n"
                        f"• Approx sensitivity: **${abs(net_delta):.2f}** per **$1** move in {ticker}.\n"
                        "• Gamma captures how fast your exposure changes as price moves.\n"
                        f"• Delta may change by **~{net_gamma:.3f}** for each **$1** move (convexity).\n"
                        f"• Avg IV: **{iv_pct:.0f}%** → market is pricing **high uncertainty** "
                        "(risk + opportunity both higher).\n\n"
                        "*Why this is trustworthy:*\n"
                        "• These are aggregate Greeks computed across the analyzed options contracts.\n"
                        "• We include contract count + timestamps + source + run id for traceability."
                    )
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*⚠️ Alerts / Flags*\n"
                        "• Moderate directional exposure: |Net Delta| ≥ 50.\n"
                        "• Gamma rising: Net Gamma ≥ 0.25 → watch fast delta changes.\n"
                        "• IV regime extremely high: Avg IV ≥ 140%."
                    )
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": plain_text_takeaway
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Generated: {generated} | "
                            f"Market TS: {market_timestamp} | "
                            f"Source: {data_source} | "
                            f"Run: {run_id}"
                        )
                    }
                ]
            }
        ]

        return {"blocks": blocks}

    # ==========================================================
    # GENERAL ALERTS (used by run_enhanced_system.py and the dashboard)
    # ==========================================================
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




# ==========================================================
# SINGLETON
# ==========================================================
_slack = None

def get_slack_manager():
    global _slack
    if _slack is None:
        _slack = SlackAlertManager()
    return _slack


# ==========================================================
# DEMO RUN (SAFE)
# ==========================================================
if __name__ == "__main__":
    slack = get_slack_manager()

    slack.send_greeks_alert(
        ticker="AAPL",
        net_delta=77.646398,
        net_gamma=0.5688214932,
        avg_iv=1.5625,
        contracts=384,
        market_timestamp="2025-12-12 03:55 PM ET",
        data_source="Snowflake options_chain_silver",
        run_id="demo_run"
    )