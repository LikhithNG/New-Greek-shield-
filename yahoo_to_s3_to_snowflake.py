#!/usr/bin/env python3
"""
Complete Pipeline: Yahoo Finance → S3 → Snowflake
Uses PAT authentication that your TA provided
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

load_dotenv()

logging.basicConfig(level=logging.INFO)

def safe_int(value, default=0):
    if pd.isna(value):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def safe_float(value, default=0.0):
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def main():
    logging.info("="*70)
    logging.info("COMPLETE PIPELINE: Yahoo → S3 → Snowflake")
    logging.info("="*70)
    
    ticker = 'AAPL'
    
    # ========================================
    # STEP 1: FETCH FROM YAHOO FINANCE
    # ========================================
    logging.info(f"\n📊 STEP 1: Fetching {ticker} from Yahoo Finance")
    
    stock = yf.Ticker(ticker)
    hist = stock.history(period='1d')
    if hist.empty:
        raise ValueError(f"No price history returned for {ticker}")
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
                        'collection_date': str(date.today()),
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
    
    # ========================================
    # STEP 2: SAVE TO S3
    # ========================================
    logging.info(f"\n📤 STEP 2: Uploading to S3")
    
    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION')
    )
    
    bucket = os.getenv('S3_BUCKET_NAME')
    today = date.today()
    folder = f"options-data/{ticker}/{today.year}/{today.month:02d}/{today.day:02d}"
    
    # Upload JSON
    json_key = f"{folder}/options_{ticker}_{today}.json"
    s3.put_object(
        Bucket=bucket,
        Key=json_key,
        Body=json.dumps(all_options, indent=2),
        ContentType='application/json'
    )
    logging.info(f"   ✅ JSON: s3://{bucket}/{json_key}")
    
    # Upload CSV
    csv_key = f"{folder}/options_{ticker}_{today}.csv"
    df = pd.DataFrame(all_options)
    s3.put_object(
        Bucket=bucket,
        Key=csv_key,
        Body=df.to_csv(index=False),
        ContentType='text/csv'
    )
    logging.info(f"   ✅ CSV: s3://{bucket}/{csv_key}")
    
    # ========================================
    # STEP 3: LOAD TO SNOWFLAKE
    # ========================================
    logging.info(f"\n💾 STEP 3: Loading to Snowflake")
    
    try:
        # Connect using PAT (as password parameter)
        conn = snowflake.connector.connect(
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),  # PAT token here
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
            database=os.getenv('SNOWFLAKE_DATABASE'),
            schema=os.getenv('SNOWFLAKE_SCHEMA'),
            role=os.getenv('SNOWFLAKE_ROLE')
        )
        
        logging.info("   ✅ Connected to Snowflake")
        
        cursor = conn.cursor()
        snapshot_id = all_options[0]['collection_timestamp']
        loaded = 0
        failed = 0
        
        for option in all_options:
            try:
                cursor.execute("""
                    INSERT INTO OPTIONS_SNAPSHOT 
                    (snapshot_id, collection_timestamp, ticker, underlying_price, 
                     contract_symbol, expiration_date, strike_price, option_type,
                     last_price, bid, ask, volume, open_interest, 
                     implied_volatility, days_to_expiry)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    snapshot_id,
                    option['collection_timestamp'],
                    option['ticker'],
                    option['underlying_price'],
                    option['contract_symbol'],
                    option['expiration_date'],
                    option['strike_price'],
                    option['option_type'],
                    option['last_price'],
                    option['bid'],
                    option['ask'],
                    option['volume'],
                    option['open_interest'],
                    option['implied_volatility'],
                    option['days_to_expiry']
                ))
                loaded += 1
            except Exception as e:
                failed += 1
                logging.warning(f"   ⚠️  Insert failed for {option['contract_symbol']}: {e}")
                continue
        
        conn.commit()
        logging.info(f"   ✅ Loaded {loaded} rows to Snowflake ({failed} failed)")
        
        # Verify
        cursor.execute("SELECT COUNT(*) FROM OPTIONS_SNAPSHOT")
        total = cursor.fetchone()[0]
        logging.info(f"   ✅ Total in Snowflake: {total} rows")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        logging.error(f"   ❌ Snowflake failed: {e}")
        logging.info(f"   ℹ️  Data is safely in S3!")
    
    logging.info("\n" + "="*70)
    logging.info("✅ PIPELINE FINISHED!")
    logging.info("="*70)

if __name__ == "__main__":
    main()