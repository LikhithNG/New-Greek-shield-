#!/usr/bin/env python3
"""
UPDATED AUTOMATED PIPELINE - SNOWFLAKE AS SINGLE SOURCE OF TRUTH
Yahoo Finance → S3 → Snowflake → Risk Report (from Snowflake layers)
Runs daily at 6:30 PM - Fully Automated
UPDATED: Greeks now computed by Snowflake, not Python
"""

import os
from dotenv import load_dotenv
import boto3
import snowflake.connector
import yfinance as yf
import pandas as pd
from datetime import datetime, date
import json
import logging
import hashlib

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('daily_pipeline.log'),
        logging.StreamHandler()
    ]
)

def safe_int(value, default=0):
    """Safely convert to int, handling NaN"""
    if pd.isna(value):
        return default
    try:
        return int(value)
    except:
        return default

def safe_float(value, default=0.0):
    """Safely convert to float, handling NaN"""
    if pd.isna(value):
        return default
    try:
        return float(value)
    except:
        return default

def get_snowflake_connection():
    """Connect to Snowflake using PAT.

    TLS certificate validation stays on unless SNOWFLAKE_INSECURE_MODE=true.
    """
    return snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
        database=os.getenv('SNOWFLAKE_DATABASE'),
        schema=os.getenv('SNOWFLAKE_SCHEMA'),
        role=os.getenv('SNOWFLAKE_ROLE'),
        insecure_mode=os.getenv('SNOWFLAKE_INSECURE_MODE', 'false').lower() == 'true',
        client_session_keep_alive=True  # Keep connection alive
    )

def generate_risk_report(conn):
    """
    Read risk metrics from Snowflake-native layers:
      - PROCESSED.DAILY_RISK_SUMMARY  (portfolio Greeks / counts)
      - ALERTS.RISK_ALERTS            (per-option alerts from latest run)

    Returns: nicely formatted multi-line string.
    """
    report_lines = []

    try:
        cur = conn.cursor()

        # 1) Get latest daily risk summary (per ticker)
        cur.execute("""
            SELECT
                ASOF_DATE,
                TICKER,
                NET_DELTA,
                NET_GAMMA,
                NET_THETA,
                NET_VEGA,
                NET_RHO,
                N_CONTRACTS,
                N_ITM,
                N_OTM,
                N_ATM
            FROM RISK_MONITOR.PROCESSED.DAILY_RISK_SUMMARY
            QUALIFY ROW_NUMBER() OVER (PARTITION BY TICKER ORDER BY ASOF_DATE DESC) = 1
            ORDER BY TICKER
        """)
        summary_rows = cur.fetchall()
        summary_cols = [c[0] for c in cur.description]
        df_summary = pd.DataFrame(summary_rows, columns=summary_cols)

        # 2) Get latest alerts batch
        cur.execute("""
            SELECT
                GENERATED_TIMESTAMP,
                TICKER,
                EXPIRATION_DATE,
                STRIKE_PRICE,
                OPTION_TYPE,
                AGENT_NAME,
                SEVERITY,
                ALERT_TYPE,
                PLAIN_ENGLISH_SUMMARY,
                RECOMMENDATION,
                CURRENT_DELTA,
                CURRENT_GAMMA,
                CURRENT_THETA,
                CURRENT_VEGA,
                DAYS_TO_EXPIRATION
            FROM RISK_MONITOR.ALERTS.RISK_ALERTS
            WHERE GENERATED_TIMESTAMP = (
                SELECT MAX(GENERATED_TIMESTAMP)
                FROM RISK_MONITOR.ALERTS.RISK_ALERTS
            )
            ORDER BY
                SEVERITY DESC,
                TICKER,
                EXPIRATION_DATE,
                STRIKE_PRICE
        """)
        alert_rows = cur.fetchall()
        alert_cols = [c[0] for c in cur.description]
        df_alerts = pd.DataFrame(alert_rows, columns=alert_cols)

        # ───────────────── Header ─────────────────
        report_lines.append("\n")
        report_lines.append("╔" + "═" * 78 + "╗")
        report_lines.append("║" + " " * 23 + "OPTIONS RISK DASHBOARD" + " " * 26 + "║")
        report_lines.append(
            "║"
            + datetime.now().strftime("%Y-%m-%d %H:%M:%S").center(78)
            + "║"
        )
        report_lines.append("╚" + "═" * 78 + "╝")

        # ───────────────── Portfolio Summary ─────────────────
        if df_summary.empty:
            report_lines.append("\n⚠️  No entries in PROCESSED.DAILY_RISK_SUMMARY yet.")
        else:
            report_lines.append("\n📊 PORTFOLIO SUMMARY (Snowflake source of truth)\n")

            for _, row in df_summary.iterrows():
                report_lines.append(
                    f"Ticker: {row['TICKER']}, As of: {row['ASOF_DATE']}"
                )
                report_lines.append(
                    f"  • Contracts: {int(row['N_CONTRACTS'])}  "
                    f"(ITM={int(row['N_ITM'])}, ATM={int(row['N_ATM'])}, OTM={int(row['N_OTM'])})"
                )
                report_lines.append(
                    "  • Net Greeks: "
                    f"Δ={row['NET_DELTA']:.3f}, "
                    f"Γ={row['NET_GAMMA']:.3f}, "
                    f"Θ={row['NET_THETA']:.3f}, "
                    f"V={row['NET_VEGA']:.3f}, "
                    f"ρ={row['NET_RHO']:.3f}"
                )
                report_lines.append("")

        # ───────────────── Alerts ─────────────────
        report_lines.append("\n" + "=" * 80)
        report_lines.append("🚨 ACTIVE RISK ALERTS (from ALERTS.RISK_ALERTS)")
        report_lines.append("=" * 80)

        if df_alerts.empty:
            report_lines.append("\n✅ No alerts for the latest run.")
        else:
            for _, a in df_alerts.iterrows():
                header = (
                    f"[{a['SEVERITY']}] {a['ALERT_TYPE']} – "
                    f"{a['TICKER']} {a['OPTION_TYPE']} {a['STRIKE_PRICE']:.1f} "
                    f"(exp {a['EXPIRATION_DATE']}, DTE={a['DAYS_TO_EXPIRATION']})"
                )
                report_lines.append("\n" + header)
                report_lines.append(f"  • Summary: {a['PLAIN_ENGLISH_SUMMARY']}")
                report_lines.append(f"  • Recommendation: {a['RECOMMENDATION']}")
                report_lines.append(
                    "  • Greeks: "
                    f"Δ={a['CURRENT_DELTA']:.3f}, "
                    f"Γ={a['CURRENT_GAMMA']:.3f}, "
                    f"Θ={a['CURRENT_THETA']:.3f}, "
                    f"V={a['CURRENT_VEGA']:.3f}"
                )

        report_lines.append("\n" + "=" * 80)
        report_lines.append("Source: PROCESSED.DAILY_RISK_SUMMARY + ALERTS.RISK_ALERTS")
        report_lines.append("=" * 80)

        cur.close()

    except Exception as e:
        report_lines.append(f"\n⚠️ Error generating Snowflake risk report: {e}")

    return "\n".join(report_lines)

def main():
    logging.info("="*70)
    logging.info(f"COMPLETE AUTOMATED PIPELINE")
    logging.info(f"Started: {datetime.now()}")
    logging.info("="*70)
    
    ticker = 'AAPL'
    report_file = None  # Initialize variable to avoid UnboundLocalError
    
    try:
        # ===============================================
        # STEP 1: FETCH FROM YAHOO FINANCE
        # ===============================================
        logging.info(f"\n📊 STEP 1: Fetching {ticker} from Yahoo Finance")
        
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1d')
        underlying_price = hist['Close'].iloc[-1]
        logging.info(f"   Current price: ${underlying_price:.2f}")
        
        expiries = stock.options[:3]
        all_options = []
        
        for expiry in expiries:
            logging.info(f"   Processing {expiry}...")
            opt_chain = stock.option_chain(expiry)
            
            for opt_type, data in [('CALL', opt_chain.calls), ('PUT', opt_chain.puts)]:
                if not data.empty:
                    for _, row in data.iterrows():
                        exp_date = pd.to_datetime(expiry).date()
                        
                        all_options.append({
                            'ticker': ticker,
                            'collection_timestamp': datetime.now().isoformat(),
                            'underlying_price': safe_float(underlying_price),
                            'contract_symbol': str(row.get('contractSymbol', '')),
                            'expiration_date': str(expiry),
                            'strike_price': safe_float(row.get('strike', 0)),
                            'option_type': opt_type,
                            'last_price': safe_float(row.get('lastPrice', 0)),
                            'bid': safe_float(row.get('bid', 0)),
                            'ask': safe_float(row.get('ask', 0)),
                            'volume': safe_int(row.get('volume', 0)),
                            'open_interest': safe_int(row.get('openInterest', 0)),
                            'implied_volatility': safe_float(row.get('impliedVolatility', 0)),
                            'days_to_expiry': int((exp_date - date.today()).days)
                        })
        
        logging.info(f"✅ Collected {len(all_options)} contracts")
        
        # ===============================================
        # STEP 2: SAVE TO S3
        # ===============================================
        logging.info(f"\n📤 STEP 2: Saving to S3")
        
        s3 = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
        
        bucket = os.getenv('S3_BUCKET_NAME')
        today = date.today()
        folder = f"options-data/{ticker}/{today.year}/{today.month:02d}/{today.day:02d}"
        
        # Save JSON
        json_key = f"{folder}/options_{ticker}_{today}.json"
        s3.put_object(
            Bucket=bucket,
            Key=json_key,
            Body=json.dumps(all_options, indent=2),
            ContentType='application/json'
        )
        logging.info(f"   ✅ JSON: s3://{bucket}/{json_key}")
        
        # Save CSV
        csv_key = f"{folder}/options_{ticker}_{today}.csv"
        df_save = pd.DataFrame(all_options)
        s3.put_object(
            Bucket=bucket,
            Key=csv_key,
            Body=df_save.to_csv(index=False),
            ContentType='text/csv'
        )
        logging.info(f"   ✅ CSV: s3://{bucket}/{csv_key}")
        
        # ===============================================
        # STEP 3: LOAD TO SNOWFLAKE
        # ===============================================
        logging.info(f"\n💾 STEP 3: Loading to Snowflake")
        
        conn = get_snowflake_connection()
        logging.info("   ✅ Connected to Snowflake")
        
        cursor = conn.cursor()
        loaded = 0
        
        for option in all_options:
            try:
                id_string = f"{option['contract_symbol']}_{option['collection_timestamp']}"
                id_md5 = hashlib.md5(id_string.encode()).hexdigest()
                
                cursor.execute("""
                    INSERT INTO OPTIONS_SNAPSHOT 
                    (SNAPSHOT_TS, SYMBOL, CONTRACT_SYMBOL, OPTION_TYPE,
                     STRIKE, EXPIRY, BID, ASK, LAST_PRICE, 
                     VOLUME, OPEN_INTEREST, IMPLIED_VOL, UNDERLYING_PRICE,
                     DTE, ID_MD5)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    option['collection_timestamp'],
                    option['ticker'],
                    option['contract_symbol'],
                    option['option_type'],
                    option['strike_price'],
                    option['expiration_date'],
                    option['bid'],
                    option['ask'],
                    option['last_price'],
                    option['volume'],
                    option['open_interest'],
                    option['implied_volatility'],
                    option['underlying_price'],
                    option['days_to_expiry'],
                    id_md5
                ))
                loaded += 1
            except Exception as e:
                # Log but continue with other inserts
                logging.debug(f"   Skipped duplicate: {option['contract_symbol']}")
                continue
        
        conn.commit()
        logging.info(f"   ✅ Loaded {loaded} rows to Snowflake")
        
        cursor.execute("SELECT COUNT(*) FROM OPTIONS_SNAPSHOT")
        total = cursor.fetchone()[0]
        logging.info(f"   ✅ Total rows in Snowflake: {total}")
        
        # ===============================================
        # STEP 4: GENERATE RISK REPORT (FROM SNOWFLAKE)
        # ===============================================
        logging.info(f"\n📊 STEP 4: Generating Risk Analysis Report from Snowflake layers")
        
        try:
            risk_report = generate_risk_report(conn)
            
            # Save report to file
            os.makedirs('risk_reports', exist_ok=True)
            report_file = f"risk_reports/risk_report_{today}.txt"
            
            with open(report_file, 'w') as f:
                f.write(risk_report)
            
            logging.info(f"   ✅ Risk report saved: {report_file}")
            
            # Print report to console
            print("\n" + risk_report)
            
        except Exception as e:
            logging.error(f"   ❌ Risk report error: {e}")
        
        # Close connections
        cursor.close()
        conn.close()
        
        # ===============================================
        # FINAL SUMMARY
        # ===============================================
        logging.info("\n" + "="*70)
        logging.info("✅ COMPLETE PIPELINE FINISHED SUCCESSFULLY!")
        logging.info(f"   Collected: {len(all_options)} contracts")
        logging.info(f"   Loaded into OPTIONS_SNAPSHOT: {loaded} contracts")
        logging.info("   Greeks: computed by Snowflake tasks into FEATURES.OPTIONS_GREEKS")
        logging.info(f"   Total in OPTIONS_SNAPSHOT: {total} contracts")
        
        if report_file:
            logging.info(f"   Risk Report: {report_file}")
        else:
            logging.info(f"   Risk Report: Not generated")
            
        logging.info("="*70)
        
    except Exception as e:
        logging.error(f"❌ Pipeline error: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
        # Ensure connection is closed even on error
        try:
            if 'conn' in locals() and conn:
                conn.close()
        except:
            pass

if __name__ == "__main__":
    main()