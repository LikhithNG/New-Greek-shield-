#!/usr/bin/env python3
"""
Visual Risk Monitor Agent
Provides clear, understandable risk insights for everyone
"""

import os
from dotenv import load_dotenv
import snowflake.connector
import pandas as pd
from datetime import datetime

load_dotenv()

def get_snowflake_connection():
    return snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
        database=os.getenv('SNOWFLAKE_DATABASE'),
        schema=os.getenv('SNOWFLAKE_SCHEMA'),
        role=os.getenv('SNOWFLAKE_ROLE')
    )

def print_header(title):
    """Print a nice header"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def print_risk_bar(value, max_value, label, threshold_low, threshold_high):
    """Print a visual risk bar"""
    percentage = min(abs(value) / max_value * 100, 100)
    bar_length = 40
    filled = int(bar_length * percentage / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    # Determine color/severity
    if abs(value) < threshold_low:
        status = "🟢 LOW RISK"
        color = "green"
    elif abs(value) < threshold_high:
        status = "🟡 MODERATE"
        color = "yellow"
    else:
        status = "🔴 HIGH RISK"
        color = "red"
    
    print(f"{label:20s} |{bar}| {percentage:5.1f}% - {status}")

def explain_greek(greek_name, value, option_type):
    """Translate Greek values to plain English"""
    
    if greek_name == 'DELTA':
        if option_type == 'CALL':
            shares = abs(value) * 100
            if abs(value) > 0.7:
                return f"💪 Acts like owning {shares:.0f} shares - strong directional bet"
            elif abs(value) > 0.3:
                return f"📊 Acts like owning {shares:.0f} shares - moderate exposure"
            else:
                return f"📉 Acts like owning {shares:.0f} shares - low probability"
        else:  # PUT
            shares = abs(value) * 100
            if abs(value) > 0.7:
                return f"💪 Acts like shorting {shares:.0f} shares - strong hedge"
            elif abs(value) > 0.3:
                return f"📊 Acts like shorting {shares:.0f} shares - moderate hedge"
            else:
                return f"📉 Acts like shorting {shares:.0f} shares - low probability"
    
    elif greek_name == 'GAMMA':
        if value > 0.05:
            return f"⚡ DANGER! Delta will swing wildly - position very unstable"
        elif value > 0.02:
            return f"⚠️  Delta changing moderately fast - watch closely"
        else:
            return f"✅ Delta stable - position predictable"
    
    elif greek_name == 'THETA':
        daily_loss = abs(value) * 100  # Per contract
        if abs(value) > 0.10:
            return f"💸 Losing ${daily_loss:.2f} EVERY DAY - time is your enemy!"
        elif abs(value) > 0.05:
            return f"⏰ Losing ${daily_loss:.2f} daily - moderate time decay"
        else:
            return f"✅ Losing ${daily_loss:.2f} daily - low time decay"
    
    elif greek_name == 'VEGA':
        if value > 0.30:
            return f"🎢 Very sensitive to volatility swings - high uncertainty"
        elif value > 0.15:
            return f"📊 Moderate volatility sensitivity"
        else:
            return f"✅ Low volatility sensitivity - more stable"

def visual_risk_dashboard():
    """Create visual risk dashboard"""
    
    print("\n" + "🎯" * 40)
    print_header("OPTIONS RISK DASHBOARD - PLAIN ENGLISH ANALYSIS")
    print("🎯" * 40)
    
    conn = get_snowflake_connection()
    
    # Get latest data
    df = pd.read_sql("""
        SELECT * FROM OPTIONS_SNAPSHOT
        WHERE DELTA IS NOT NULL
        AND SNAPSHOT_TS >= CURRENT_TIMESTAMP() - INTERVAL '1 DAY'
    """, conn)
    
    if df.empty:
        print("\n⚠️  No options with Greeks found in OPTIONS_SNAPSHOT for the last day.")
        print("   Run final_complete_pipeline.py and calculate_greeks.py first.")
        conn.close()
        return
    
    total_contracts = len(df)
    print(f"\n📊 Analyzing {total_contracts} AAPL options contracts from latest collection")
    print(f"📅 Current AAPL Price: ${df['UNDERLYING_PRICE'].iloc[0]:.2f}")
    
    # ==========================================
    # OVERALL RISK SCORE
    # ==========================================
    print_header("📈 OVERALL PORTFOLIO RISK SCORE")
    
    # Calculate risk scores
    avg_gamma = df['GAMMA'].mean()
    avg_theta = abs(df['THETA'].mean())
    avg_vega = df['VEGA'].mean()
    
    print(f"\n{'Metric':<20s} {'Visual Risk Level':<50s} {'Status'}")
    print("-" * 80)
    print_risk_bar(avg_gamma, 0.10, "Gamma (Speed)", 0.02, 0.05)
    print_risk_bar(avg_theta, 0.20, "Theta (Decay)", 0.05, 0.10)
    print_risk_bar(avg_vega, 0.50, "Vega (Volatility)", 0.15, 0.30)
    
    # ==========================================
    # POSITION BREAKDOWN
    # ==========================================
    print_header("💼 POSITION BREAKDOWN - What You Own")
    
    calls = df[df['OPTION_TYPE'] == 'CALL']
    puts = df[df['OPTION_TYPE'] == 'PUT']
    
    print(f"\n📞 CALL Options: {len(calls)} contracts")
    print(f"   Average Delta: {calls['DELTA'].mean():.3f} (acts like owning {calls['DELTA'].mean()*100:.0f} shares per contract)")
    print(f"   Total Volume: {calls['VOLUME'].sum():,.0f} contracts traded")
    
    print(f"\n📉 PUT Options: {len(puts)} contracts")
    print(f"   Average Delta: {puts['DELTA'].mean():.3f} (acts like shorting {abs(puts['DELTA'].mean())*100:.0f} shares per contract)")
    print(f"   Total Volume: {puts['VOLUME'].sum():,.0f} contracts traded")
    
    # ==========================================
    # RISK ALERTS
    # ==========================================
    print_header("🚨 ACTIVE RISK ALERTS")
    
    alert_count = 0
    
    # Alert 1: High Gamma
    high_gamma = df[df['GAMMA'] > 0.05]
    if len(high_gamma) > 0:
        alert_count += len(high_gamma)
        print(f"\n🔴 CRITICAL: {len(high_gamma)} positions with HIGH GAMMA")
        print(f"   What this means: These options will gain or lose value VERY QUICKLY")
        print(f"   Why it matters: Small stock moves = BIG profit or loss")
        print(f"   Action needed: Monitor closely - be ready to exit quickly")
        print(f"\n   Top 3 most sensitive:")
        for _, row in high_gamma.nlargest(3, 'GAMMA').iterrows():
            print(f"   → ${row['STRIKE']} {row['OPTION_TYPE']}: Gamma {row['GAMMA']:.4f}")
            print(f"      {explain_greek('GAMMA', row['GAMMA'], row['OPTION_TYPE'])}")
    
    # Alert 2: High Theta
    high_theta = df[df['THETA'] < -0.10]
    if len(high_theta) > 0:
        alert_count += len(high_theta)
        total_daily_loss = abs(high_theta['THETA'].sum()) * 100
        print(f"\n🟡 WARNING: {len(high_theta)} positions with RAPID TIME DECAY")
        print(f"   What this means: You're losing ${total_daily_loss:.2f} EVERY DAY from time passing")
        print(f"   Why it matters: Even if stock doesn't move, you lose money")
        print(f"   Action needed: Either close positions or be confident stock will move soon")
        print(f"\n   Biggest daily losers:")
        for _, row in high_theta.nsmallest(3, 'THETA').iterrows():
            daily_loss = abs(row['THETA']) * 100
            print(f"   → ${row['STRIKE']} {row['OPTION_TYPE']}: Losing ${daily_loss:.2f}/day")
            print(f"      {explain_greek('THETA', row['THETA'], row['OPTION_TYPE'])}")
    
    # Alert 3: Expiring Soon
    expiring = df[df['DTE'] <= 7]
    if len(expiring) > 0:
        alert_count += len(expiring)
        print(f"\n🟡 WARNING: {len(expiring)} positions EXPIRING WITHIN 7 DAYS")
        print(f"   What this means: You have less than a week to be right")
        print(f"   Why it matters: Time is running out - these need immediate attention")
        print(f"   Action needed: Decide NOW - hold or close?")
        print(f"\n   Urgent positions:")
        for _, row in expiring.nsmallest(5, 'DTE').iterrows():
            print(f"   → ${row['STRIKE']} {row['OPTION_TYPE']}: {row['DTE']} days left (expires {row['EXPIRY']})")
    
    # Alert 4: Low Probability Positions
    low_prob = df[abs(df['DELTA']) < 0.15]
    if len(low_prob) > 0:
        print(f"\n⚠️  CAUTION: {len(low_prob)} FAR OUT-OF-THE-MONEY positions")
        print(f"   What this means: Stock needs to move A LOT for these to profit")
        print(f"   Why it matters: Low probability of success - lottery tickets")
        print(f"   Action needed: Understand these are speculative bets")
    
    # Alert 5: Safe Positions
    safe = df[abs(df['DELTA']) > 0.80]
    if len(safe) > 0:
        print(f"\n🟢 GOOD NEWS: {len(safe)} DEEP IN-THE-MONEY positions")
        print(f"   What this means: These are almost certain to be profitable")
        print(f"   Why it matters: High probability of success - safe bets")
        print(f"   Action needed: Hold - these behave like owning stock")
    
    if alert_count == 0:
        print(f"\n✅ NO MAJOR ALERTS - Portfolio looks healthy!")
    
    # ==========================================
    # EASY-TO-UNDERSTAND SUMMARY
    # ==========================================
    print_header("📋 EXECUTIVE SUMMARY - What You Need to Know")
    
    print(f"\n1️⃣  TOTAL POSITIONS: {total_contracts} option contracts")
    
    print(f"\n2️⃣  RISK LEVEL:")
    if alert_count > 50:
        print(f"    🔴 HIGH RISK - {alert_count} alerts require immediate attention")
    elif alert_count > 20:
        print(f"    🟡 MODERATE RISK - {alert_count} positions need monitoring")
    else:
        print(f"    🟢 LOW RISK - {alert_count} minor alerts, portfolio stable")
    
    print(f"\n3️⃣  TIME SENSITIVITY:")
    urgent = len(df[df['DTE'] <= 3])
    if urgent > 0:
        print(f"    🚨 URGENT: {urgent} positions expire in 3 days or less - ACT NOW!")
    else:
        print(f"    ✅ No immediate expiration concerns")
    
    print(f"\n4️⃣  DAILY COST OF WAITING:")
    total_theta_loss = abs(df['THETA'].sum()) * 100
    print(f"    💸 Losing ${total_theta_loss:.2f} per day just from time passing")
    print(f"    📅 Weekly cost: ${total_theta_loss * 5:.2f}")
    print(f"    📆 Monthly cost: ${total_theta_loss * 20:.2f}")
    
    print(f"\n5️⃣  PROFIT PROBABILITY:")
    high_prob = len(df[abs(df['DELTA']) > 0.60])
    medium_prob = len(df[(abs(df['DELTA']) >= 0.30) & (abs(df['DELTA']) <= 0.60)])
    low_prob = len(df[abs(df['DELTA']) < 0.30])
    
    print(f"    🟢 High probability: {high_prob} contracts ({high_prob/total_contracts*100:.1f}%)")
    print(f"    🟡 Medium probability: {medium_prob} contracts ({medium_prob/total_contracts*100:.1f}%)")
    print(f"    🔴 Low probability: {low_prob} contracts ({low_prob/total_contracts*100:.1f}%)")
    
    print(f"\n6️⃣  VOLATILITY EXPOSURE:")
    high_vega = len(df[df['VEGA'] > 0.25])
    if high_vega > 20:
        print(f"    🎢 HIGH - {high_vega} positions very sensitive to volatility spikes")
        print(f"       If market gets crazy, expect big price swings!")
    else:
        print(f"    ✅ STABLE - Portfolio not overly sensitive to volatility")
    
    # ==========================================
    # TOP 5 POSITIONS NEEDING ATTENTION
    # ==========================================
    print_header("⚠️  TOP 5 POSITIONS REQUIRING YOUR ATTENTION")
    
    # Calculate composite risk score
    df['risk_score'] = (
        abs(df['GAMMA']) * 100 +      # Gamma heavily weighted
        abs(df['THETA']) * 50 +        # Theta medium weight
        (10 / (df['DTE'] + 1)) * 10 +  # Close expiry = higher risk
        (1 - abs(df['DELTA'])) * 20    # Low delta = higher risk
    )
    
    top_risks = df.nlargest(5, 'risk_score')
    
    for i, (_, row) in enumerate(top_risks.iterrows(), 1):
        print(f"\n📌 POSITION #{i}: ${row['STRIKE']:.2f} {row['OPTION_TYPE']} (expires {row['EXPIRY']})")
        print(f"   ⏰ Days Left: {row['DTE']} days")
        print(f"   💰 Current Price: ${row['LAST_PRICE']:.2f}")
        print(f"   📊 Risk Score: {row['risk_score']:.1f}/100")
        
        print(f"\n   📈 What the Greeks Tell You:")
        print(f"   • Delta {row['DELTA']:+.3f}: {explain_greek('DELTA', row['DELTA'], row['OPTION_TYPE'])}")
        print(f"   • Gamma {row['GAMMA']:.4f}: {explain_greek('GAMMA', row['GAMMA'], row['OPTION_TYPE'])}")
        print(f"   • Theta {row['THETA']:.4f}: {explain_greek('THETA', row['THETA'], row['OPTION_TYPE'])}")
        print(f"   • Vega {row['VEGA']:.4f}: {explain_greek('VEGA', row['VEGA'], row['OPTION_TYPE'])}")
        
        print(f"\n   💡 RECOMMENDATION:")
        if row['risk_score'] > 50:
            print(f"      🔴 HIGH RISK - Consider closing this position soon")
        elif row['risk_score'] > 30:
            print(f"      🟡 MODERATE - Monitor daily and have exit plan ready")
        else:
            print(f"      🟢 ACCEPTABLE - Continue monitoring")
    
    # ==========================================
    # PLAIN ENGLISH INSIGHTS
    # ==========================================
    print_header("💡 KEY INSIGHTS - What This All Means")
    
    # Insight 1: Gamma
    avg_gamma = df['GAMMA'].mean()
    if avg_gamma > 0.05:
        print("\n⚡ Your positions are VERY SENSITIVE to price changes")
        print("   → Small moves in AAPL = BIG gains or losses")
        print("   → This is HIGH RISK but also HIGH REWARD")
        print("   → Watch the stock price closely!")
    else:
        print("\n✅ Your positions have STABLE price sensitivity")
        print("   → Price changes affect you gradually")
        print("   → Lower risk, more predictable")
    
    # Insight 2: Theta
    avg_theta = df['THETA'].mean()
    total_daily_cost = abs(df['THETA'].sum()) * 100
    if total_daily_cost > 100:
        print(f"\n💸 TIME IS EXPENSIVE - You're losing ${total_daily_cost:.2f} EVERY DAY")
        print(f"   → That's ${total_daily_cost * 7:.2f} per week!")
        print(f"   → Stock needs to move to overcome this cost")
        print(f"   → Consider: Is the time decay worth it?")
    else:
        print(f"\n✅ Time decay is manageable - ${total_daily_cost:.2f} per day")
    
    # Insight 3: Strike Distribution
    underlying = df['UNDERLYING_PRICE'].iloc[0]
    near_money = df[(df['STRIKE'] >= underlying * 0.95) & (df['STRIKE'] <= underlying * 1.05)]
    
    print(f"\n🎯 {len(near_money)} contracts are NEAR THE MONEY (strike within 5% of stock price)")
    print(f"   → These are most active and likely to move")
    print(f"   → Focus your attention here!")
    
    # Insight 4: Expiration Timeline
    print(f"\n📅 EXPIRATION TIMELINE:")
    for dte_range, label in [(3, "⚠️  URGENT"), (7, "🟡 SOON"), (14, "📅 THIS MONTH")]:
        count = len(df[df['DTE'] <= dte_range])
        if count > 0:
            print(f"   {label}: {count} positions expire within {dte_range} days")
    
    # ==========================================
    # ACTIONABLE RECOMMENDATIONS
    # ==========================================
    print_header("✅ RECOMMENDED ACTIONS - What to Do Next")
    
    recommendations = []
    
    # Recommendation 1: High risk positions
    critical = df[df['risk_score'] > 50]
    if len(critical) > 0:
        recommendations.append(
            f"1. REVIEW {len(critical)} HIGH-RISK POSITIONS immediately\n"
            f"   → These have high gamma + short expiry + rapid decay\n"
            f"   → Consider closing or rolling to later dates"
        )
    
    # Recommendation 2: Theta decay
    if total_daily_cost > 50:
        recommendations.append(
            f"2. ADDRESS TIME DECAY - You're losing ${total_daily_cost:.2f} daily\n"
            f"   → Close positions with theta < -0.15\n"
            f"   → Or be confident stock will move significantly"
        )
    
    # Recommendation 3: Expiring soon
    urgent = df[df['DTE'] <= 3]
    if len(urgent) > 0:
        recommendations.append(
            f"3. URGENT: {len(urgent)} positions expire in 3 days\n"
            f"   → Make decision TODAY - close or let expire\n"
            f"   → After 3 PM Friday, can't exit easily"
        )
    
    # Recommendation 4: Far OTM
    lottery = df[abs(df['DELTA']) < 0.10]
    if len(lottery) > 0:
        total_lottery_cost = (lottery['LAST_PRICE'] * 100).sum()
        recommendations.append(
            f"4. EVALUATE {len(lottery)} FAR OUT-OF-MONEY positions\n"
            f"   → Total invested: ${total_lottery_cost:,.2f}\n"
            f"   → These are low-probability bets\n"
            f"   → Only keep if you're comfortable losing it all"
        )
    
    if len(recommendations) == 0:
        print("\n🎉 GREAT NEWS! No critical actions needed right now")
        print("   Your portfolio looks well-balanced")
        print("   Continue monitoring daily")
    else:
        for rec in recommendations:
            print(f"\n{rec}")
    
    # ==========================================
    # RISK METER VISUALIZATION
    # ==========================================
    print_header("🌡️  OVERALL RISK METER")
    
    # Calculate overall risk (0-100 scale)
    overall_risk = (
        (avg_gamma / 0.10) * 30 +
        (avg_theta / 0.20) * 30 +
        (alert_count / total_contracts) * 40
    ) * 100
    
    overall_risk = min(overall_risk, 100)
    
    # Visual meter
    meter_length = 50
    filled = int(meter_length * overall_risk / 100)
    meter = "█" * filled + "░" * (meter_length - filled)
    
    if overall_risk < 30:
        status = "🟢 LOW RISK"
        advice = "Portfolio is stable. Continue current strategy."
    elif overall_risk < 60:
        status = "🟡 MODERATE RISK"
        advice = "Some positions need attention. Review alerts above."
    else:
        status = "🔴 HIGH RISK"
        advice = "Take action! Multiple high-risk positions detected."
    
    print(f"\n   0%  |{meter}| 100%")
    print(f"   LOW {'':45s} HIGH")
    print(f"\n   Your Risk Level: {overall_risk:.1f}% - {status}")
    print(f"   Advice: {advice}")
    
    # ==========================================
    # FINAL SUMMARY
    # ==========================================
    print("\n" + "="*80)
    print("📊 BOTTOM LINE")
    print("="*80)
    print(f"✅ Total Contracts: {total_contracts}")
    print(f"⚠️  Active Alerts: {alert_count}")
    print(f"💸 Daily Cost: ${total_daily_cost:.2f}")
    print(f"📈 Overall Risk: {overall_risk:.1f}%")
    print(f"🎯 Recommendation: {advice}")
    print("="*80)
    print(f"\n📅 Report Generated: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
    print("🔄 Next Update: Tomorrow at 6:30 PM (automatic)")
    print("\n")
    
    conn.close()

if __name__ == "__main__":
    visual_risk_dashboard()