# =====================================================================
# KING TRADING OS: MASTER AUTOMATED PRODUCTION PIPELINE
# RUNS HEADLESS ON GITHUB ACTIONS CLOUD AT 15:30 ICT DAILY
# =====================================================================
import os
import sys
import time
import datetime
import warnings
import json
import base64
import requests
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

# -------------------------------------------------------------
# 🛡️ TRIPLE-GATE SENTINEL: MARKET HOLIDAY & GHOST BAR CIRCUIT BREAKER
# -------------------------------------------------------------
def verify_market_session_finalized() -> bool:
    now_vn = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    today_str = now_vn.strftime('%Y-%m-%d')
    today_display = now_vn.strftime('%d/%m/%Y')

    print("=" * 85)
    print("🛡️ [TRIPLE-GATE SENTINEL] Auditing Today's Market Session Finalization...")
    print(f"▶️ Execution Time (Vietnam UTC+7) : {now_vn.strftime('%d/%m/%Y %H:%M:%S')}")

    try:
        url = f"https://dchart-api.vndirect.com.vn/dchart/history?symbol=VNINDEX&resolution=D&from={int(now_vn.timestamp()) - 864000}&to={int(now_vn.timestamp())}"
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://dchart.vndirect.com.vn/'}
        res = requests.get(url, headers=headers, timeout=7).json()

        if 't' not in res or len(res['t']) == 0:
            print("⚠️ API data pending, falling back to pipeline...")
            return True

        last_timestamp = res['t'][-1]
        last_date = datetime.datetime.fromtimestamp(last_timestamp, datetime.timezone(datetime.timedelta(hours=7))).strftime('%Y-%m-%d')
        last_vol = float(res['v'][-1])
        last_close = float(res['c'][-1])
        last_high = float(res['h'][-1])
        last_low = float(res['l'][-1])

        print(f"▶️ Latest Benchmark Bar Date       : {last_date}")
        print(f"▶️ Latest Benchmark Session Volume : {last_vol:,.0f} shares")
        print(f"▶️ Latest Benchmark Settlement     : {last_close:,.2f} points")
        print("-" * 85)

        is_today = (last_date == today_str)
        is_valid_volume = (last_vol >= 50_000_000)
        is_valid_spread = (last_high > last_low) and (last_close > 0)

        if is_today and is_valid_volume and is_valid_spread:
            print(f"✅ [GATE 1, 2 & 3 PASSED] Official Session Confirmed for {today_display}!")
            print(f"   Real trading verified ({last_vol:,.0f} shares). Launching full Quant Engine...")
            print("=" * 85 + "\n")
            return True
        else:
            reasons = []
            if not is_today: reasons.append(f"No new bar for today (Latest: {last_date} vs Today: {today_str})")
            if not is_valid_volume: reasons.append(f"Volume too low ({last_vol:,.0f} < 50M) - Ghost/Holiday Bar")
            if not is_valid_spread: reasons.append("Zero intraday spread - Market halted")

            print(f"⏸️ [SENTINEL HALT] Today ({today_display}) is a Market Holiday / Non-Trading Session!")
            print(f"   ⚠️ Reason: {'; '.join(reasons)}.")
            print("💡 Execution halted safely. 0 compute minutes wasted!")
            print("=" * 85 + "\n")
            return False
    except Exception as ex:
        print(f"⚠️ Sentinel check bypassed due to network error: {ex}. Proceeding...")
        return True

# -------------------------------------------------------------
# MASTER EXECUTION ENTRY POINT
# -------------------------------------------------------------
if __name__ == "__main__":
    if not verify_market_session_finalized():
        sys.exit(0)

    print("🚀 [PIPELINE] Market finalized. Generating new KING_TRADING_SUITE.html and updating index.html...")
    # Khi chạy trên máy ảo GitHub Actions, hệ thống sẽ thực hiện cập nhật index.html
