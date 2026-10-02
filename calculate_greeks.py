#!/usr/bin/env python3
"""
Calculate Black-Scholes Greeks for Options
Updates DELTA, GAMMA, THETA, VEGA, RHO columns in Snowflake
"""

import os
from dotenv import load_dotenv
import snowflake.connector
import pandas as pd
import numpy as np
from scipy.stats import norm
import logging
from datetime import datetime

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('greeks_calculation.log'),
        logging.StreamHandler()
    ]
)

def black_scholes_greeks(S, K, T, r, sigma, option_type='CALL'):
    """
    Calculate option Greeks using Black-Scholes model
    
    Parameters:
    S: Current stock price (underlying_price)
    K: Strike price
    T: Time to expiration in years (days_to_expiry / 365)
    r: Risk-free rate (default 0.045 = 4.5%)
    sigma: Implied volatility (annual)
    option_type: 'CALL' or 'PUT'
    
    Returns:
    dict with delta, gamma, theta, vega, rho
    """
    
    # Handle edge cases
    if T <= 0:
        # Option expired or expires today
        if option_type == 'CALL':
            delta = 1.0 if S > K else 0.0
        else:
            delta = -1.0 if S < K else 0.0
        
        return {
            'delta': delta,
            'gamma': 0.0,
            'theta': 0.0,
            'vega': 0.0,
            'rho': 0.0
        }
    
    if np.isnan(sigma) or sigma <= 0:
        raise ValueError(f"Implied volatility must be positive, got {sigma}")
    
    # Calculate d1 and d2
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    # Calculate Greeks
    if option_type == 'CALL':
        delta = norm.cdf(d1)
        theta = ((-S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) 
                 - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
        rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100
    else:  # PUT
        delta = norm.cdf(d1) - 1
        theta = ((-S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) 
                 + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365
        rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100
    
    # Same for calls and puts
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100
    
    return {
        'delta': float(delta),
        'gamma': float(gamma),
        'theta': float(theta),
        'vega': float(vega),
        'rho': float(rho)
    }

def get_snowflake_connection():
    """Connect to Snowflake"""
    return snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
        database=os.getenv('SNOWFLAKE_DATABASE'),
        schema=os.getenv('SNOWFLAKE_SCHEMA'),
        role=os.getenv('SNOWFLAKE_ROLE')
    )

def calculate_and_update_greeks():
    """Calculate Greeks for all options and update Snowflake"""
    
    logging.info("="*70)
    logging.info(f"GREEKS CALCULATION STARTED: {datetime.now()}")
    logging.info("="*70)
    
    # Connect to Snowflake
    logging.info("\n📊 Connecting to Snowflake...")
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    logging.info("✅ Connected")
    
    # Get all options where Greeks are NULL (not yet calculated)
    logging.info("\n📥 Loading options data...")
    query = """
    SELECT 
        ID_MD5,
        UNDERLYING_PRICE,
        STRIKE,
        DTE,
        IMPLIED_VOL,
        OPTION_TYPE
    FROM OPTIONS_SNAPSHOT
    WHERE DELTA IS NULL
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    logging.info(f"✅ Found {len(rows)} contracts needing Greeks calculation")
    
    if len(rows) == 0:
        logging.info("ℹ️  All Greeks already calculated!")
        cursor.close()
        conn.close()
        return
    
    # Constants
    RISK_FREE_RATE = 0.045  # 4.5% annual risk-free rate
    
    # Calculate Greeks for each option
    logging.info("\n🧮 Calculating Greeks...")
    updated = 0
    skipped = 0
    failed = 0
    
    for row in rows:
        id_md5 = row[0]
        
        try:
            S = float(row[1])  # Underlying price
            K = float(row[2])  # Strike
            T = float(row[3]) / 365.0  # Days to expiry → years
            option_type = row[5]
            
            # Skip unexpired contracts without a usable implied volatility
            # rather than inventing one: a fake IV produces misleading Greeks.
            # (Expired contracts use intrinsic values and do not need IV.)
            sigma = float(row[4]) if row[4] is not None else float('nan')
            if T > 0 and (np.isnan(sigma) or sigma <= 0):
                skipped += 1
                logging.warning(f"Skipping {id_md5}: missing or non-positive IV ({row[4]})")
                continue
            
            # Calculate Greeks
            greeks = black_scholes_greeks(S, K, T, RISK_FREE_RATE, sigma, option_type)
            
            # Update Snowflake
            cursor.execute("""
                UPDATE OPTIONS_SNAPSHOT
                SET 
                    DELTA = %s,
                    GAMMA = %s,
                    THETA = %s,
                    VEGA = %s,
                    RHO = %s
                WHERE ID_MD5 = %s
            """, (
                greeks['delta'],
                greeks['gamma'],
                greeks['theta'],
                greeks['vega'],
                greeks['rho'],
                id_md5
            ))
            
            updated += 1
            
            if updated % 50 == 0:
                logging.info(f"   {updated} contracts updated...")
                conn.commit()  # Commit in batches
                
        except Exception as e:
            failed += 1
            logging.error(f"Error calculating Greeks for {id_md5}: {e}")
            continue
    
    # Final commit
    conn.commit()
    logging.info(f"\n✅ Successfully calculated Greeks for {updated} contracts")
    logging.info(f"   Skipped (missing/non-positive IV): {skipped}")
    logging.info(f"   Failed: {failed}")
    if failed:
        logging.error(f"❌ {failed} of {len(rows)} contracts failed Greeks calculation")
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM OPTIONS_SNAPSHOT WHERE DELTA IS NOT NULL")
    total_with_greeks = cursor.fetchone()[0]
    logging.info(f"✅ Total contracts with Greeks: {total_with_greeks}")
    
    # Show sample with Greeks
    logging.info("\n📊 Sample Greeks values:")
    cursor.execute("""
        SELECT SYMBOL, STRIKE, OPTION_TYPE, DELTA, GAMMA, THETA, VEGA
        FROM OPTIONS_SNAPSHOT
        WHERE DELTA IS NOT NULL
        ORDER BY ABS(DELTA) DESC
        LIMIT 5
    """)
    
    for row in cursor.fetchall():
        logging.info(f"   {row[0]} ${row[1]} {row[2]}: Δ={row[3]:.4f} Γ={row[4]:.4f} Θ={row[5]:.4f} ν={row[6]:.4f}")
    
    cursor.close()
    conn.close()
    
    logging.info("\n" + "="*70)
    logging.info("✅ GREEKS CALCULATION COMPLETED!")
    logging.info("="*70)

if __name__ == "__main__":
    calculate_and_update_greeks()