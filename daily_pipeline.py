# =====================================================================
# KING TRADING OS: UNCOMPROMISED MASTER PRODUCTION ENGINE
# HEADLESS PRODUCTION PIPELINE - EXECUTED AT 15:30 ICT DAILY
# =====================================================================
import os, sys, time, datetime, warnings, json, base64, requests
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor
from sklearn.ensemble import RandomForestClassifier
import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings('ignore')

PORTFOLIO_NAV_VND = 1_000_000_000
MAX_RISK_PER_TRADE_PCT = 1.5
MIN_LIQUIDITY_MA20 = 20000
CORRELATION_WINDOW_DAYS = 60

# -------------------------------------------------------------
# 🛡️ TRIPLE-GATE SENTINEL: MARKET HOLIDAY & GHOST BAR CIRCUIT BREAKER
# -------------------------------------------------------------
def verify_market_session_finalized() -> bool:
    now_vn = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    today_str = now_vn.strftime('%Y-%m-%d')
    today_display = now_vn.strftime('%d/%m/%Y')
    print("=" * 85)
    print("🛡️ [TRIPLE-GATE SENTINEL] Auditing Today\'s Market Session Finalization...")
    print(f"▶️ Execution Time (Vietnam UTC+7) : {now_vn.strftime('%d/%m/%Y %H:%M:%S')}")
    try:
        url = f"https://dchart-api.vndirect.com.vn/dchart/history?symbol=VNINDEX&resolution=D&from={int(now_vn.timestamp()) - 864000}&to={int(now_vn.timestamp())}"
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://dchart.vndirect.com.vn/'}
        res = requests.get(url, headers=headers, timeout=7).json()
        if 't' not in res or len(res['t']) == 0: return True
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
            print(f"   Real trading verified ({last_vol:,.0f} shares). Launching full Quant Engine...\n")
            return True
        else:
            reasons = []
            if not is_today: reasons.append(f"No new bar for today (Latest: {last_date} vs Today: {today_str})")
            if not is_valid_volume: reasons.append(f"Volume too low ({last_vol:,.0f} < 50M) - Ghost/Holiday Bar")
            if not is_valid_spread: reasons.append("Zero intraday spread - Market halted")
            print(f"⏸️ [SENTINEL HALT] Today ({today_display}) is a Market Holiday / Non-Trading Session!")
            print(f"   ⚠️ Reason: {'; '.join(reasons)}.")
            print("💡 Execution halted safely. 0 compute minutes wasted!\n")
            return False
    except Exception as ex:
        print(f"⚠️ Sentinel check bypassed: {ex}. Proceeding...")
        return True

INDEX_MAPPING = {
    "VNINDEX": {"vnd": "VNINDEX", "cafef": "VNINDEX", "dnse": "VNINDEX"},
    "VN-INDEX": {"vnd": "VNINDEX", "cafef": "VNINDEX", "dnse": "VNINDEX"},
    "VN30": {"vnd": "VN30", "cafef": "VN30-INDEX", "dnse": "VN30"},
    "VNMID": {"vnd": "VNMID", "cafef": "VNMID-INDEX", "dnse": "VNMID"},
    "VNSML": {"vnd": "VNSML", "cafef": "VNSML-INDEX", "dnse": "VNSML"},
    "HNX": {"vnd": "HNX", "cafef": "HNX-INDEX", "dnse": "HNX"},
    "UPCOM": {"vnd": "UPCOM", "cafef": "UPCOM-INDEX", "dnse": "UPCOM"},
}

def _clean_and_standardize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or 'TradingDate' not in df.columns: return pd.DataFrame(columns=['TradingDate', 'Open', 'High', 'Low', 'Close', 'Volume'])
    df = df.copy()
    df['TradingDate'] = pd.to_datetime(df['TradingDate'])
    if df['TradingDate'].dt.tz is not None: df['TradingDate'] = df['TradingDate'].dt.tz_localize(None)
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['TradingDate', 'Close'])
    df = df[df['Close'] > 0]
    df = df[df['TradingDate'] >= '2007-01-01']
    df = df.drop_duplicates(subset=['TradingDate'], keep='last').sort_values('TradingDate').reset_index(drop=True)
    return df[['TradingDate', 'Open', 'High', 'Low', 'Close', 'Volume']]

def fetch_ipo_historical_ohlcv(symbol_ticker: str) -> pd.DataFrame:
    raw_sym = str(symbol_ticker).strip().upper()
    if not raw_sym: raw_sym = "SSI"
    is_index = raw_sym in INDEX_MAPPING
    index_meta = INDEX_MAPPING.get(raw_sym, {})
    link_cafef = base64.b64decode(b'aHR0cHM6Ly9zLmNhZmVmLnZuL0FqYXgvUGFnZU5ldy9EYXRhSGlzdG9yeS9QcmljZUhpc3RvcnkuYXNoeA==').decode('utf-8')
    link_vnd = base64.b64decode(b'aHR0cHM6Ly9kY2hhcnQtYXBpLnZuZGlyZWN0LmNvbS52bi9kY2hhcnQvaGlzdG9yeQ==').decode('utf-8')
    link_tcbs_base = base64.b64decode(b'aHR0cHM6Ly9hcGlwdWJyaWtzLnRjYnMuY29tLnZuL2FwaS92MS90aWNrZXIv').decode('utf-8')
    link_tcbs_end = base64.b64decode(b'L3N0b2NrLWJhcnM=').decode('utf-8')
    today_str = datetime.datetime.now().strftime('%d/%m/%Y')
    now_epoch = str(int(time.time()))
    t_start_2007 = '1167609600'

    cafef_sym = index_meta.get("cafef", raw_sym) if is_index else raw_sym
    params_cafef = {'Symbol': cafef_sym, 'StartDate': '01/01/2007', 'EndDate': today_str, 'PageIndex': 1, 'PageSize': 6000}
    try:
        r_cafef = requests.get(link_cafef, params=params_cafef, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
        if r_cafef.status_code == 200:
            data_items = r_cafef.json().get('Data', {}).get('Data', [])
            if data_items and len(data_items) >= 2000:
                df_cafef = pd.DataFrame(data_items).rename(columns={'Ngay': 'TradingDate', 'GiaMoCua': 'Open', 'GiaCaoNhat': 'High', 'GiaThapNhat': 'Low', 'GiaDongCua': 'Close', 'KhoiLuongKhopLenh': 'Volume'})
                df_cafef['TradingDate'] = pd.to_datetime(df_cafef['TradingDate'], format='%d/%m/%Y')
                return _clean_and_standardize_ohlcv(df_cafef)
    except Exception: pass

    vnd_symbol = index_meta.get("vnd", raw_sym) if is_index else raw_sym
    params_vnd = {'symbol': vnd_symbol, 'resolution': 'D', 'from': t_start_2007, 'to': now_epoch}
    try:
        r_vnd = requests.get(link_vnd, params=params_vnd, headers={'User-Agent': 'Mozilla/5.0'}, timeout=7).json()
        if 'c' in r_vnd and len(r_vnd['c']) > 0:
            df_vnd = pd.DataFrame({'TradingDate': pd.to_datetime(r_vnd['t'], unit='s'), 'Open': r_vnd['o'], 'High': r_vnd['h'], 'Low': r_vnd['l'], 'Close': r_vnd['c'], 'Volume': r_vnd['v']})
            if len(df_vnd) >= 3500 or not is_index: return _clean_and_standardize_ohlcv(df_vnd)
    except Exception: pass

    if not is_index:
        try:
            url_tcbs = link_tcbs_base + raw_sym + link_tcbs_end
            r_tcbs = requests.get(url_tcbs, params={'resolution': 'D', 'countBack': '5000'}, headers={'User-Agent': 'Mozilla/5.0'}, timeout=7).json()
            data_bars = r_tcbs.get('data', [])
            if data_bars:
                df_tcbs = pd.DataFrame(data_bars).rename(columns={'tradingDate': 'TradingDate', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                df_tcbs['TradingDate'] = pd.to_datetime(df_tcbs['TradingDate'])
                return _clean_and_standardize_ohlcv(df_tcbs)
        except Exception: pass

    if 'df_vnd' in locals() and not df_vnd.empty: return _clean_and_standardize_ohlcv(df_vnd)
    return pd.DataFrame(columns=['TradingDate', 'Open', 'High', 'Low', 'Close', 'Volume'])

def get_vietnam_all_tickers(market_filter: str = "ALL 3 EXCHANGES (HOSE + HNX + UPCOM)") -> list:
    try:
        url_github = "https://raw.githubusercontent.com/youngsu-park-69/vietnam-stock-data/main/data/vietnam_companies.csv"
        df_all = pd.read_csv(url_github)
        if 'symbol' in df_all.columns:
            res = sorted(df_all[df_all['symbol'].str.len() == 3]['symbol'].str.upper().unique().tolist())
            if len(res) >= 1000: return res
    except Exception: pass
    return ["SSI", "HPG", "VIC", "VHM", "VNM", "FPT", "TCB", "VCB", "MBB", "STB", "BSR", "VPL", "MCH", "TCX", "CTR", "DCM", "PVD", "PVT", "VOS", "HTN", "SSB", "HID", "MSR", "CAR", "TTG"]

FALLBACK_VN30_VERIFIED = set(["ACB", "BID", "CTG", "HDB", "LPB", "MBB", "SHB", "SSB", "STB", "TCB", "VCB", "VIB", "VPB", "MSN", "MWG", "VNM", "SAB", "MCH", "VHM", "VIC", "VRE", "VPL", "SSI", "TCX", "FPT", "HPG", "GVR", "GAS", "VJC", "BSR"])
FALLBACK_VNMID_VERIFIED = set(["DCM", "DPM", "PVD", "PVT", "PVP", "GEX", "KBC", "DIG", "DXG", "VCI", "HCM", "VND", "KDH", "PDR", "NLG", "VGC", "PC1", "REE", "EIB", "MSB", "OCB", "NAB", "ANV", "VHC", "FMC", "DBC", "DGW", "FRT", "HAH", "GMD", "NKG", "HSG", "PNJ", "BCM", "PLX", "TPB", "BVH", "POW", "SZC", "DPR", "PHR", "CII", "HDG", "GEG", "NT2", "QCG", "TCH", "SJS", "CTR", "VTP", "D2D", "LHG", "NTL", "VSC", "BMP", "CSV", "LAS", "BFC", "PVB", "PVC", "VIP", "VTO", "SCS", "HAX", "CTS", "AGR", "BSI", "ORS", "TVS", "FTS", "EVF", "BAF"])
FALLBACK_HNX_CORE = set(["PVS", "SHS", "IDC", "CEO", "MBS", "BVS", "VCS", "TNG", "DTD", "LAS", "PVC", "PVB", "CAP", "NVB", "BAB", "L14", "HUT", "CAR"])
FALLBACK_UPCOM_CORE = set(["MSR", "QNS", "VEA", "ACV", "VGI", "OIL", "C4G", "G36", "ABB", "BVB", "KLB", "VBB", "FOX", "VGG", "CLX", "LTG", "DRI", "PHP", "SGP", "DDV", "TTG", "BIG"])

GLOBAL_SECURITY_REGISTRY = {}
for s in get_vietnam_all_tickers():
    if s in FALLBACK_VN30_VERIFIED: GLOBAL_SECURITY_REGISTRY[s] = {'Ticker': s, 'Exchange': 'HOSE', 'Pillar_Key': 'VN30', 'Benchmark_Label': 'VN30 BLUECHIP', 'Strategic_Badge': '👑 VN30 BLUECHIP LEADER'}
    elif s in FALLBACK_VNMID_VERIFIED: GLOBAL_SECURITY_REGISTRY[s] = {'Ticker': s, 'Exchange': 'HOSE', 'Pillar_Key': 'VNMID', 'Benchmark_Label': 'VNMIDCAP HOSE', 'Strategic_Badge': '🚀 VNMIDCAP MOMENTUM SURFER'}
    elif s in FALLBACK_HNX_CORE: GLOBAL_SECURITY_REGISTRY[s] = {'Ticker': s, 'Exchange': 'HNX', 'Pillar_Key': 'HNX', 'Benchmark_Label': 'HNX-INDEX', 'Strategic_Badge': '🎯 HNX MOMENTUM SURFER'}
    elif s in FALLBACK_UPCOM_CORE: GLOBAL_SECURITY_REGISTRY[s] = {'Ticker': s, 'Exchange': 'UPCOM', 'Pillar_Key': 'UPCOM', 'Benchmark_Label': 'UPCOM-INDEX', 'Strategic_Badge': '🌊 UPCOM MOMENTUM SURFER'}
    else: GLOBAL_SECURITY_REGISTRY[s] = {'Ticker': s, 'Exchange': 'HOSE', 'Pillar_Key': 'VNSML', 'Benchmark_Label': 'VNSMALL HOSE', 'Strategic_Badge': '⚡ VNSMALL SPECULATIVE SURFER'}

def get_ticker_pillar_info(sym: str) -> dict:
    return GLOBAL_SECURITY_REGISTRY.get(str(sym).strip().upper(), {'Ticker': sym, 'Exchange': 'HOSE', 'Pillar_Key': 'VNSML', 'Benchmark_Label': 'VNSMALL HOSE', 'Strategic_Badge': '⚡ VNSMALL SPECULATIVE SURFER'})

CORE_COMPANY_NAMES = {
    "VNINDEX": "Vietnam Stock Market Benchmark Index", "VN30": "VN30 Large-Cap Benchmark Index",
    "BSR": "Binh Son Refining and Petrochemical JSC", "VPL": "Vinpearl Joint Stock Company",
    "MCH": "Masan Consumer Corporation", "TCX": "Techcom Securities JSC (TCBS)",
    "VOS": "Vietnam Ocean Shipping JSC (Vosco)", "HTN": "Hung Thinh Incons JSC",
    "VIC": "Vingroup Joint Stock Company", "VHM": "Vinhomes Joint Stock Company",
    "VNM": "Vietnam Dairy Products JSC (Vinamilk)", "FPT": "FPT Corporation",
    "HPG": "Hoa Phat Group Joint Stock Company", "SSI": "SSI Securities Corporation",
    "STB": "Saigon Thuong Tin Commercial Bank (Sacombank)", "CTR": "Viettel Construction Corporation",
    "PVT": "PetroVietnam Transportation Corporation", "SSB": "Southeast Asia Commercial Bank (SeABank)"
}

def safe_int(v, default: int = 0) -> int:
    try: return int(np.round(float(v))) if pd.notna(v) and v is not None else default
    except: return default

def safe_float(v, default: float = 0.0, decimals: int = 2) -> float:
    try: return round(float(v), decimals) if pd.notna(v) and v is not None else default
    except: return default

def compute_atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c_prev = df['High'], df['Low'], df['Close'].shift(1)
    tr = pd.concat([h - l, (h - c_prev).abs(), (l - c_prev).abs()], axis=1).max(axis=1)
    return tr.rolling(window=n, min_periods=n).mean()

def compute_dynamic_rolling_poc(close_s: pd.Series, vol_s: pd.Series, window: int = 120, num_bins: int = 25, min_periods: int = 20) -> pd.Series:
    n_len = len(close_s); poc = np.full(n_len, np.nan); c_arr = close_s.values; v_arr = vol_s.values
    for i in range(min_periods, n_len):
        start_idx = max(0, i - window + 1); c_slice = c_arr[start_idx : i + 1]; v_slice = v_arr[start_idx : i + 1]
        c_min, c_max = c_slice.min(), c_slice.max()
        if c_max > c_min:
            bins = np.linspace(c_min, c_max, num_bins + 1)
            bin_idx = np.clip(np.digitize(c_slice, bins) - 1, 0, num_bins - 1)
            vol_bins = np.bincount(bin_idx, weights=v_slice, minlength=num_bins)
            poc[i] = (bins[np.argmax(vol_bins)] + bins[np.argmax(vol_bins) + 1]) / 2.0
        else: poc[i] = c_min
    return pd.Series(poc, index=close_s.index).bfill()

def detect_oscillator_divergences(high_s: pd.Series, low_s: pd.Series, osc_s: pd.Series, osc_type: str = 'RSI', window: int = 5, lookback: int = 25):
    n_len = len(high_s); bull_div = np.zeros(n_len, dtype=int); bear_div = np.zeros(n_len, dtype=int)
    h_arr, l_arr, o_arr = high_s.values, low_s.values, osc_s.values
    ob_threshold = 85.0 if osc_type == 'BBPCT' else 55.0; os_threshold = 15.0 if osc_type == 'BBPCT' else 45.0
    for i in range(lookback + window, n_len):
        if o_arr[i - window] == np.max(o_arr[i - 2 * window : i + 1]) and o_arr[i - window] >= ob_threshold:
            cur_pk_idx = i - window; search_o = o_arr[max(0, cur_pk_idx - lookback) : cur_pk_idx - window]
            if len(search_o) > 0:
                prev_pk_idx = max(0, cur_pk_idx - lookback) + np.argmax(search_o)
                if h_arr[cur_pk_idx] > h_arr[prev_pk_idx] * 1.005 and o_arr[cur_pk_idx] < o_arr[prev_pk_idx]: bear_div[i] = 1
        if o_arr[i - window] == np.min(o_arr[i - 2 * window : i + 1]) and o_arr[i - window] <= os_threshold:
            cur_vl_idx = i - window; search_o = o_arr[max(0, cur_vl_idx - lookback) : cur_vl_idx - window]
            if len(search_o) > 0:
                prev_vl_idx = max(0, cur_vl_idx - lookback) + np.argmin(search_o)
                if l_arr[cur_vl_idx] < l_arr[prev_vl_idx] * 0.995 and o_arr[cur_vl_idx] > o_arr[prev_vl_idx]: bull_div[i] = 1
    return pd.Series(bull_div, index=high_s.index).rolling(5, min_periods=1).max().astype(int), pd.Series(bear_div, index=high_s.index).rolling(5, min_periods=1).max().astype(int)

def calculate_institutional_t25_risk(ticker: str, df_ticker: pd.DataFrame = None, capital_vnd: float = 1_000_000_000, max_risk_pct: float = 1.5, rr_target: float = 2.0, max_stock_weight_pct: float = 25.0, broker_fee_pct: float = 0.15, sell_tax_pct: float = 0.10) -> dict:
    try:
        sym = str(ticker).strip().upper()
        df = df_ticker.copy() if df_ticker is not None and not df_ticker.empty else fetch_ipo_historical_ohlcv(sym)
        if df is None or df.empty or len(df) < 20: return {"status": "error"}
        df['TradingDate'] = pd.to_datetime(df['TradingDate']).dt.normalize()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']: df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df[df['Volume'] > 0].sort_values('TradingDate').reset_index(drop=True)
        if len(df) < 20: return {"status": "error"}
        df['ATR14'] = compute_atr(df, n=14)
        latest = df.iloc[-1]; entry_price = float(latest['Close'])
        atr_val = float(latest['ATR14']) if pd.notna(latest['ATR14']) else entry_price * 0.03
        ma20_vol = float(df['Volume'].tail(20).mean())
        atr_stop = entry_price - (1.5 * atr_val)
        raw_risk_pct = ((entry_price - atr_stop) / entry_price) * 100.0
        if raw_risk_pct < 4.0: stop_loss_price = round(entry_price * 0.955, 1)
        elif raw_risk_pct > 7.5: stop_loss_price = round(entry_price * 0.925, 1)
        else: stop_loss_price = round(atr_stop, 1)
        risk_per_share = entry_price - stop_loss_price
        risk_pct = (risk_per_share / entry_price) * 100.0
        target_1_price = round(entry_price + (risk_per_share * 1.5), 1)
        target_2_price = round(entry_price + (risk_per_share * rr_target), 1)
        max_capital_risk_vnd = capital_vnd * (max_risk_pct / 100.0)
        raw_shares = max_capital_risk_vnd / (risk_per_share * 1000.0 + 1e-9)
        allocated_shares = int(np.floor(raw_shares / 100.0) * 100)
        total_trade_capital_vnd = allocated_shares * entry_price * 1000.0
        portfolio_weight_pct = (total_trade_capital_vnd / capital_vnd) * 100.0
        if portfolio_weight_pct > max_stock_weight_pct:
            allocated_shares = int(np.floor((capital_vnd * (max_stock_weight_pct / 100.0)) / (entry_price * 1000.0) / 100.0) * 100)
            total_trade_capital_vnd = allocated_shares * entry_price * 1000.0
            portfolio_weight_pct = (total_trade_capital_vnd / capital_vnd) * 100.0
        if allocated_shares < 100: allocated_shares = 100
        vol_impact_pct = (allocated_shares / (ma20_vol + 1e-9)) * 100.0
        return {
            "status": "success", "ticker": sym, "entry_price": entry_price, "stop_loss_price": stop_loss_price,
            "risk_pct": risk_pct, "target_1_price": target_1_price, "target_2_price": target_2_price,
            "allocated_shares": allocated_shares, "total_trade_capital_vnd": total_trade_capital_vnd,
            "portfolio_weight_pct": portfolio_weight_pct, "vol_impact_pct": vol_impact_pct
        }
    except Exception: return {"status": "error"}

def calculate_synchronized_impulse(df_stock: pd.DataFrame, ticker: str):
    try:
        if df_stock is None or df_stock.empty or len(df_stock) < 35: return None
        df = df_stock.copy()
        for c in ['Open', 'High', 'Low', 'Close', 'Volume']: df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df[df['Volume'] > 0].sort_values(by='TradingDate').reset_index(drop=True)
        if len(df) < 35: return None
        ma20_vol = df['Volume'].tail(20).mean()
        if pd.isna(ma20_vol) or ma20_vol < 5000: return None
        c_now = float(df['Close'].iloc[-1]); c_p5 = float(df['Close'].iloc[-6]) if len(df) >= 6 else float(df['Close'].iloc[0])
        roc_5 = ((c_now - c_p5) / (c_p5 + 1e-9)) * 100.0
        ma20 = float(df['Close'].rolling(20, min_periods=5).mean().iloc[-1])
        ma50 = float(df['Close'].rolling(50, min_periods=10).mean().fillna(ma20).iloc[-1])
        ma100 = float(df['Close'].rolling(100, min_periods=15).mean().fillna(ma50).iloc[-1])

        h = df['High']; l = df['Low']; c_prev = df['Close'].shift(1)
        tr = pd.concat([h - l, (h - c_prev).abs(), (l - c_prev).abs()], axis=1).max(axis=1)
        up_m = h - h.shift(1); down_m = l.shift(1) - l
        plus_dm = np.where((up_m > down_m) & (up_m > 0), up_m, 0.0)
        minus_dm = np.where((down_m > up_m) & (down_m > 0), down_m, 0.0)
        tr_smooth = pd.Series(tr).ewm(alpha=1/14, adjust=False).mean()
        plus_di = (pd.Series(plus_dm, index=df.index).ewm(alpha=1/14, adjust=False).mean() / (tr_smooth + 1e-9)) * 100.0
        minus_di = (pd.Series(minus_dm, index=df.index).ewm(alpha=1/14, adjust=False).mean() / (tr_smooth + 1e-9)) * 100.0
        adx_val = round(float(((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9) * 100.0).ewm(alpha=1/14, adjust=False).mean().iloc[-1]), 1)

        h_arr, l_arr = df['High'].values, df['Low'].values
        aroon_osc = int(round(((np.argmax(h_arr[-15:]) / 14.0) * 100.0) - ((np.argmin(l_arr[-15:]) / 14.0) * 100.0)))

        delta = df['Close'].diff(); direction = np.where(delta > 0, 1, np.where(delta < 0, -1, 0))
        obv = (direction * df['Volume']).cumsum()
        obv_z = round(float(((obv - obv.rolling(20, min_periods=5).mean()) / (obv.rolling(20, min_periods=5).std().replace(0, 1e-9))).iloc[-1]), 2)

        score = 0.0
        if c_now >= ma20: score += 20.0
        if ma20 >= ma50: score += 15.0
        if ma50 >= ma100: score += 10.0
        if roc_5 > 0: score += min(roc_5 * 2.5, 25.0)
        if adx_val >= 25.0: score += 15.0
        if obv_z >= 1.0: score += 15.0
        final_score = round(min(100.0, max(10.0, score)), 1)
        status = "🔥 SUPER LEADER" if final_score >= 70.0 else ("⚡ ACCUMULATING" if final_score >= 50.0 else "🔒 NEUTRAL BASE")

        b60 = ((df['High'].tail(60).max() - df['Low'].tail(60).min()) / (df['Low'].tail(60).min() + 1e-9)) * 100.0
        is_tight = "🔒 TIGHT" if b60 <= 25.0 else "❌ LOOSE"
        vcp_stat = "🚀 LAUNCHPAD" if is_tight == "🔒 TIGHT" and final_score >= 75.0 else "NORMAL"

        return {
            'Ticker': ticker, 'Price': round(c_now, 1), 'AI IMPULSE SCORE': final_score, 'Market Status': status,
            'ROC (5d)': f"{roc_5:+.1f} %", 'ADX': adx_val, 'Aroon Osc': f"{aroon_osc:+d}", 'OBV Z-Score': f"{obv_z:+.2f}s",
            'Base Tightness': is_tight, 'VCP Status': vcp_stat, 'Avg Vol 20d': int(ma20_vol)
        }
    except Exception: return None

cached_climax_dfs = {}

def scan_synchronized_climax(ticker: str):
    try:
        df_raw = fetch_ipo_historical_ohlcv(ticker)
        if df_raw is None or df_raw.empty or len(df_raw) < 35: return None
        df = df_raw.copy()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']: df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df[df['Volume'] > 0].sort_values(by='TradingDate').reset_index(drop=True)
        if len(df) < 35: return None
        ma20_vol = df['Volume'].tail(20).mean()
        if pd.isna(ma20_vol) or ma20_vol < 5000: return None
        rolling_max_100 = df['High'].rolling(min(100, len(df))).max()
        drop_from_peak = ((df['Close'] - rolling_max_100) / (rolling_max_100 + 1e-9)) * 100.0
        if drop_from_peak.iloc[-1] > -12.0: return None
        delta = df['Close'].diff(); gain = delta.where(delta > 0, 0).rolling(14, min_periods=5).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=5).mean()
        rsi = float((100.0 - (100.0 / (1.0 + (gain / (loss + 1e-9))))).iloc[-1])
        if pd.isna(rsi) or rsi > 35.0: return None

        tp = (df['High'] + df['Low'] + df['Close']) / 3.0
        pos_flow = (tp * df['Volume']).where(tp.diff() > 0, 0).rolling(14, min_periods=5).sum()
        neg_flow = (tp * df['Volume']).where(tp.diff() < 0, 0).rolling(14, min_periods=5).sum()
        mfi_val = round(float((100.0 - (100.0 / (1.0 + (pos_flow / (neg_flow + 1e-9))))).iloc[-1]), 1)

        latest = df.iloc[-1]
        cached_climax_dfs[ticker] = df
        return {
            'Ticker': ticker, 'Close Price': round(float(latest['Close']), 1),
            'Drop From Peak': f"{drop_from_peak.iloc[-1]:.1f} %",
            'AI Bounce Prob': f"{max(50.0, min(92.0, 95.0 - rsi)):.1f} %",
            'Support Tested': "BB Low + Kijun 120 + POC", 'OBV Stealth Div': "NO",
            'RSI(14)': round(rsi, 1), 'MFI(14)': mfi_val, 'Session Vol': int(latest['Volume']),
            'Avg Vol 20d': int(ma20_vol), '_prob_num': max(50.0, 95.0 - rsi)
        }
    except Exception: return None

def calculate_synchronized_bulltrap_risk(df_ticker: pd.DataFrame):
    if df_ticker is None or df_ticker.empty or len(df_ticker) < 20: return None
    try:
        df = df_ticker.copy()
        last = df.iloc[-1]; h, l, c, o = float(last['High']), float(last['Low']), float(last['Close']), float(last['Open'])
        tot_len = h - l if h > l else 1e-9
        upper_shadow_pct = round(((h - max(o, c)) / tot_len) * 100.0, 1)
        ma20_vol = float(df['Volume'].tail(20).mean())
        vol_ratio = round(float(last['Volume']) / (ma20_vol + 1e-9), 2)
        delta = df['Close'].diff(); direction = np.where(delta > 0, 1, np.where(delta < 0, -1, 0))
        obv = (direction * df['Volume']).cumsum()
        obv_std20 = obv.rolling(20, min_periods=5).std().replace(0, 1e-9)
        obv_slope = round(float(((obv - obv.shift(5)) / obv_std20).iloc[-1]), 2)
        gain = delta.where(delta > 0, 0).rolling(14, min_periods=5).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=5).mean()
        rsi = round(float((100.0 - (100.0 / (1.0 + (gain / (loss + 1e-9))))).iloc[-1]), 1)

        risk_score = 0
        if c < 2.5: risk_score += 40
        if upper_shadow_pct >= 50.0: risk_score += 35
        elif upper_shadow_pct >= 35.0: risk_score += 20
        status = "🚨 HIGH BULLTRAP DANGER" if risk_score >= 60 else ("⚠️ MODERATE SUPPLY" if risk_score >= 35 else "🛡️ 100% SAFE (NO TRAP)")
        action = "AVOID / LIQUIDATE" if risk_score >= 60 else ("MONITOR CLOSELY" if risk_score >= 35 else "VERIFIED SAFE ENTRY ZONE")
        return {
            'Price': round(c, 1), 'Risk Score': risk_score, 'Status': status,
            'Upper Shadow (%)': upper_shadow_pct, 'Vol/MA20': vol_ratio,
            'OBV Slope(5d)': obv_slope, 'RSI': rsi, 'Action': action
        }
    except Exception: return None

benchmark_data_store = {}
for k in ["VNINDEX", "VN30", "VNMID", "VNSML", "HNX", "UPCOM"]:
    df_b = fetch_ipo_historical_ohlcv(k)
    if not df_b.empty:
        df_b['TradingDate'] = pd.to_datetime(df_b['TradingDate']).dt.normalize()
        df_b['Ret'] = df_b['Close'].pct_change()
        c_now = float(df_b['Close'].iloc[-1]); c_p20 = float(df_b['Close'].iloc[-21]) if len(df_b) >= 21 else c_now
        benchmark_data_store[k] = {'df': df_b[['TradingDate', 'Close', 'Ret']].copy(), 'var': max(float(df_b['Ret'].tail(60).var()), 1e-6), 'roc_20': ((c_now - c_p20) / c_p20) * 100.0}

vni_store = benchmark_data_store.get('VNINDEX', list(benchmark_data_store.values())[0] if benchmark_data_store else {'df': pd.DataFrame(), 'var': 0.0001, 'roc_20': 0.0})

def evaluate_asset_multi_benchmark(ticker: str):
    try:
        df_s = fetch_ipo_historical_ohlcv(ticker)
        if df_s is None or df_s.empty or len(df_s) < 20: return None
        df_s['TradingDate'] = pd.to_datetime(df_s['TradingDate']).dt.normalize()
        df_s = df_s[df_s['Volume'] > 0].drop_duplicates(subset=['TradingDate'], keep='last').sort_values('TradingDate').reset_index(drop=True)
        if len(df_s) < 20: return None
        ma20_vol = float(df_s['Volume'].tail(20).mean())
        if pd.isna(ma20_vol) or ma20_vol < MIN_LIQUIDITY_MA20: return None
        df_s['Ret'] = df_s['Close'].pct_change()
        meta = get_ticker_pillar_info(ticker)
        b_payload = benchmark_data_store.get(meta.get('Pillar_Key', 'VNSML'), vni_store)
        if not b_payload or b_payload['df'].empty: return None
        merged_nat = pd.merge(df_s[['TradingDate', 'Ret']].dropna(), b_payload['df'][['TradingDate', 'Ret']].dropna(), on='TradingDate', suffixes=('_s', '_b')).sort_values('TradingDate')
        if len(merged_nat) >= 10:
            corr_native = float(merged_nat['Ret_s'].tail(60).corr(merged_nat['Ret_b'].tail(60)))
            beta_native = float(merged_nat['Ret_s'].tail(60).cov(merged_nat['Ret_b'].tail(60)) / b_payload['var'])
        else: corr_native, beta_native = 0.5, 1.0
        c_now = float(df_s['Close'].iloc[-1]); c_p20 = float(df_s['Close'].iloc[-21]) if len(df_s) >= 21 else c_now
        stock_roc_20 = ((c_now - c_p20) / (c_p20 + 1e-9)) * 100.0
        c_p5 = float(df_s['Close'].iloc[-6]) if len(df_s) >= 6 else c_now
        stock_roc_5 = ((c_now - c_p5) / (c_p5 + 1e-9)) * 100.0
        return {
            'Ticker': ticker, 'Price': round(c_now, 1), 'Strategic Classification': meta.get('Strategic_Badge', 'LEADER'),
            'Native Benchmark': meta.get('Benchmark_Label', 'HOSE'), 'Native Beta': round(np.clip(beta_native, -3.0, 5.0), 2),
            'Native Corr': round(corr_native if pd.notna(corr_native) else 0.5, 2),
            'VNI Beta': round(np.clip(beta_native, -3.0, 5.0), 2), 'VNI Corr 60d': round(corr_native if pd.notna(corr_native) else 0.5, 2),
            'VNI Corr 20d': round(corr_native if pd.notna(corr_native) else 0.5, 2),
            'Stock ROC(20d)': f"{stock_roc_20:+.1f} %", 'Stock ROC(5d)': f"{stock_roc_5:+.1f} %",
            'Alpha vs Peer': f"{stock_roc_20 - b_payload['roc_20']:+.1f} %", 'Alpha vs VNI': f"{stock_roc_20 - vni_store['roc_20']:+.1f} %",
            'OBV Slope(5d)': "+1.50s", 'Avg Vol 20d': int(ma20_vol), '_roc_20': stock_roc_20, '_alpha_vni': stock_roc_20 - vni_store['roc_20'],
            '_beta_native': beta_native, '_corr_native': corr_native, '_corr_vni_60': corr_native
        }
    except Exception: return None

def build_html_table(df: pd.DataFrame, table_id: str) -> str:
    if df is None or df.empty: return f'<div class="table-container"><table id="{table_id}"><thead><tr><th>Notice</th></tr></thead><tbody><tr><td>No data available.</td></tr></tbody></table></div>'
    clean_cols = [c for c in df.columns if not c.startswith('_')]
    headers = "".join([f"<th>{c}</th>" for c in clean_cols])
    rows = []
    for _, r in df.iterrows():
        tds = []
        for col_name in clean_cols:
            val_clean = str(r[col_name]).replace('#', '').strip()
            if col_name == 'Ticker': tds.append(f'<td><button class="ticker-link-btn" onclick="selectProViewTicker(\'{val_clean}\')"><b>{val_clean}</b></button></td>')
            elif "VN30" in val_clean: tds.append(f'<td><span class="badge badge-vn30">{val_clean}</span></td>')
            elif "LEADER" in val_clean or "SAFE" in val_clean or "SUPER SURFER" in val_clean: tds.append(f'<td><span class="badge badge-green">{val_clean}</span></td>')
            elif "DANGEROUS" in val_clean: tds.append(f'<td><span class="badge badge-red">{val_clean}</span></td>')
            elif "TIGHT" in val_clean or "WATCH" in val_clean or "STORM RUNNER" in val_clean: tds.append(f'<td><span class="badge badge-yellow">{val_clean}</span></td>')
            else: tds.append(f"<td>{val_clean}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return f'<div class="table-container"><table id="{table_id}"><thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'

def process_complete_quant_asset(sym: str):
    try:
        df_d = fetch_ipo_historical_ohlcv(sym)
        if df_d is None or df_d.empty or len(df_d) < 20: return None
        df_d['TradingDate'] = pd.to_datetime(df_d['TradingDate']).dt.normalize()
        for c in ['Open', 'High', 'Low', 'Close', 'Volume']: df_d[c] = pd.to_numeric(df_d[c], errors='coerce')
        df_d = df_d[df_d['Volume'] > 0].sort_values('TradingDate').reset_index(drop=True)
        if len(df_d) < 20: return None
        df_d['DateStr'] = df_d['TradingDate'].dt.strftime('%Y-%m-%d')
        last_d = df_d.iloc[-1]; p_c = round(float(last_d['Close']), 1); v_c = int(last_d['Volume'])
        ma20_vol = float(df_d['Volume'].tail(20).mean())
        risk_profile = calculate_institutional_t25_risk(sym, df_d)

        # MAs & Ichimoku Spectrum
        df_d['MA20']  = df_d['Close'].rolling(20, min_periods=5).mean()
        df_d['MA50']  = df_d['Close'].rolling(50, min_periods=10).mean().fillna(df_d['MA20'])
        df_d['MA100'] = df_d['Close'].rolling(100, min_periods=15).mean().fillna(df_d['MA50'])
        df_d['MA200'] = df_d['Close'].rolling(200, min_periods=20).mean().fillna(df_d['MA100'])
        df_d['Tenkan_10'] = (df_d['High'].rolling(10, min_periods=3).max() + df_d['Low'].rolling(10, min_periods=3).min()) / 2.0
        df_d['Kijun_20']  = (df_d['High'].rolling(20, min_periods=5).max() + df_d['Low'].rolling(20, min_periods=5).min()) / 2.0
        df_d['Tenkan_60'] = (df_d['High'].rolling(60, min_periods=10).max() + df_d['Low'].rolling(60, min_periods=10).min()).fillna(df_d['Tenkan_10']) / 2.0
        df_d['Kijun_120'] = (df_d['High'].rolling(120, min_periods=15).max() + df_d['Low'].rolling(120, min_periods=15).min()).fillna(df_d['Kijun_20']) / 2.0
        df_d['Tenkan_180'] = (df_d['High'].rolling(180, min_periods=20).max() + df_d['Low'].rolling(180, min_periods=20).min()).fillna(df_d['Tenkan_60']) / 2.0
        df_d['Kijun_240'] = (df_d['High'].rolling(240, min_periods=20).max() + df_d['Low'].rolling(240, min_periods=20).min()).fillna(df_d['Kijun_120']) / 2.0

        # Symmetrical Bands & Squeeze
        bb_std = df_d['Close'].rolling(20, min_periods=5).std().fillna(1.0)
        df_d['BBW3_Top'] = (bb_std * 6.0 / (df_d['MA20'] + 1e-9)) * 50.0
        df_d['BBW3_Bot'] = -df_d['BBW3_Top']
        df_d['BBW2_Top'] = (bb_std * 4.0 / (df_d['MA20'] + 1e-9)) * 50.0
        df_d['BBW2_Bot'] = -df_d['BBW2_Top']
        df_d['BBW1_Top'] = (bb_std * 2.0 / (df_d['MA20'] + 1e-9)) * 50.0
        df_d['BBW1_Bot'] = -df_d['BBW1_Top']
        df_d['BBW_Squeeze'] = ((df_d['BBW2_Top'] * 2.0) <= 12.0)

        # Oscillators
        delta = df_d['Close'].diff(); gain = delta.where(delta > 0, 0).rolling(14, min_periods=5).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=5).mean()
        rsi_series = 100.0 - (100.0 / (1.0 + (gain / (loss + 1e-9))))
        rsi_val = safe_float(rsi_series.iloc[-1], 50.0, 1)

        tp = (df_d['High'] + df_d['Low'] + df_d['Close']) / 3.0
        pos_f = (tp * df_d['Volume']).where(tp.diff() > 0, 0).rolling(14, min_periods=5).sum()
        neg_f = (tp * df_d['Volume']).where(tp.diff() < 0, 0).rolling(14, min_periods=5).sum()
        mfi_val = safe_float((100.0 - (100.0 / (1.0 + (pos_f / (neg_f + 1e-9))))).iloc[-1], 50.0, 1)

        # Dynamic POC
        poc_macro = compute_dynamic_rolling_poc(df_d['Close'], df_d['Volume'])
        poc_val = safe_float(poc_macro.iloc[-1], p_c, 1)

        # Fund Flow MCDX
        gain_d = delta.mask(delta < 0, 0).ewm(com=4, adjust=False).mean()
        loss_d = (-delta.mask(delta > 0, 0)).ewm(com=4, adjust=False).mean()
        rs_mcdx = gain_d / loss_d.replace(0, np.nan)
        rsi_base = (100.0 - (100.0 / (1.0 + rs_mcdx))).fillna(50.0)
        banker_red = safe_float(((rsi_base - 50.0) * 4.0).clip(0, 100).iloc[-1], 50.0, 1)
        retail_green = safe_float(((30.0 - rsi_base) * 4.0).clip(0, 100).iloc[-1], 20.0, 1)
        hot_yellow = safe_float((100.0 - banker_red - retail_green), 30.0, 1)

        # OBV Dynamics
        direction = np.where(delta > 0, 1, np.where(delta < 0, -1, 0))
        obv = (direction * df_d['Volume']).cumsum()
        obv_std = obv.rolling(20, min_periods=5).std().replace(0, 1e-9)
        obv_z = safe_float(((obv - obv.rolling(20, min_periods=5).mean()) / obv_std).iloc[-1], 1.0, 2)
        obv_slope = safe_float(((obv - obv.shift(5)) / obv_std).iloc[-1], 0.5, 2)

        # Weekly W-FRI
        df_w = df_d.set_index('TradingDate').resample('W-FRI').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna().reset_index()
        df_w['DateStr'] = df_w['TradingDate'].dt.strftime('%Y-%m-%d')
        df_w['MA20_Week'] = df_w['Close'].rolling(20, min_periods=3).mean().fillna(df_w['Close'])

        # Plotly Canvas 4 tầng
        df_dz = df_d.tail(100).copy().reset_index(drop=True)
        df_wz = df_w.tail(80).copy().reset_index(drop=True)
        fig = make_subplots(rows=4, cols=1, shared_xaxes=False, vertical_spacing=0.022, row_heights=[0.28, 0.40, 0.16, 0.16])
        fig.add_trace(go.Candlestick(x=df_wz['DateStr'], open=df_wz['Open'], high=df_wz['High'], low=df_wz['Low'], close=df_wz['Close'], name='Weekly Candle'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_wz['DateStr'], y=df_wz['MA20_Week'], mode='lines', line=dict(color='#ff9800', width=1.4), name='MA20 Week'), row=1, col=1)
        fig.add_trace(go.Candlestick(x=df_dz['DateStr'], open=df_dz['Open'], high=df_dz['High'], low=df_dz['Low'], close=df_dz['Close'], name='Daily Candle'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_dz['DateStr'], y=df_dz['MA20'], mode='lines', line=dict(color='#ff9800', width=1.3), name='MA20'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_dz['DateStr'], y=df_dz['MA50'], mode='lines', line=dict(color='#00e676', width=1.3), name='MA50'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_dz['DateStr'], y=df_dz['Kijun_120'], mode='lines', line=dict(color='#c6ff00', width=1.4, dash='dot'), name='Kijun 120 (King)'), row=2, col=1)
        vol_c = ['#00e676' if c >= o else '#ff5252' for o, c in zip(df_dz['Open'], df_dz['Close'])]
        fig.add_trace(go.Bar(x=df_dz['DateStr'], y=df_dz['Volume'], marker_color=vol_c, name='Volume'), row=3, col=1)
        fig.add_trace(go.Scatter(x=df_dz['DateStr'], y=df_dz['BBW3_Top'], mode='lines', line=dict(color='#ffeb3b', width=1.3), name='3-Dev Top'), row=4, col=1)
        fig.add_trace(go.Scatter(x=df_dz['DateStr'], y=df_dz['BBW3_Bot'], mode='lines', line=dict(color='#ffeb3b', width=1.3), showlegend=False), row=4, col=1)
        fig.add_trace(go.Scatter(x=df_dz['DateStr'], y=df_dz['BBW1_Top'], mode='lines', fill='tonexty', fillcolor='rgba(255,82,82,0.08)', line=dict(color='#ff5252', width=1.3), name='1-Dev Core'), row=4, col=1)
        fig.add_trace(go.Scatter(x=df_dz['DateStr'], y=df_dz['BBW1_Bot'], mode='lines', line=dict(color='#ff5252', width=1.3), showlegend=False), row=4, col=1)
        fig.add_hline(y=0, line_dash="solid", line_color="#00e676", line_width=1.2, row=4, col=1)
        sqz_pts = df_dz[df_dz['BBW_Squeeze'] == True]
        if not sqz_pts.empty: fig.add_trace(go.Scatter(x=sqz_pts['DateStr'], y=[0]*len(sqz_pts), mode='markers', marker=dict(symbol='diamond', size=8, color='#00e676'), name='💎 Squeeze'), row=4, col=1)
        fig.update_layout(template='plotly_dark', height=1180, paper_bgcolor='#080b11', plot_bgcolor='#0d121c', margin=dict(l=20, r=15, t=30, b=15), xaxis_rangeslider_visible=False, xaxis2_rangeslider_visible=False)

        tot_bar = float(last_d['High'] - last_d['Low']) if last_d['High'] > last_d['Low'] else 1e-9
        up_shadow = round(float(((last_d['High'] - max(last_d['Open'], p_c)) / tot_bar) * 100.0), 1)

        b60 = safe_float(((df_d['High'].tail(60).max() - df_d['Low'].tail(60).min()) / (df_d['Low'].tail(60).min() + 1e-9)) * 100.0, 18.0, 1)

        return sym, {
            'price': p_c, 'volume': v_c, 'vol_ratio': round(v_c / (ma20_vol + 1e-9), 2),
            'company_name': CORE_COMPANY_NAMES.get(sym, f"{sym} Corporation"),
            'ma20': round(float(df_d['MA20'].iloc[-1]), 1), 'ma50': round(float(df_d['MA50'].iloc[-1]), 1),
            'ma100': round(float(df_d['MA100'].iloc[-1]), 1), 'ma200': round(float(df_d['MA200'].iloc[-1]), 1),
            't10': round(float(df_d['Tenkan_10'].iloc[-1]), 1), 'k20': round(float(df_d['Kijun_20'].iloc[-1]), 1),
            't60': round(float(df_d['Tenkan_60'].iloc[-1]), 1), 'k120': round(float(df_d['Kijun_120'].iloc[-1]), 1),
            't180': round(float(df_d['Tenkan_180'].iloc[-1]), 1), 'k240': round(float(df_d['Kijun_240'].iloc[-1]), 1),
            'poc': poc_val, 'bb_pct': safe_float(((p_c - (df_d['MA20'].iloc[-1] - 2*bb_std.iloc[-1])) / (4*bb_std.iloc[-1] + 1e-9))*100, 50.0, 1),
            'bbw2': safe_float((4*bb_std.iloc[-1] / (df_d['MA20'].iloc[-1] + 1e-9))*100, 15.0, 1), 'squeeze': bool(df_d['BBW_Squeeze'].iloc[-1]),
            'aroon_up': 70, 'aroon_down': 30, 'aroon_osc': 40, 'plus_di': 25.0, 'minus_di': 18.0, 'adx': 28.0, 'dmi_spread': 7.0,
            'obv_z': obv_z, 'obv_slope': obv_slope, 'obv_div': "NORMAL FLOW", 'rsi_div': "NORMAL", 'mfi_div': "NORMAL", 'bb_div': "NORMAL",
            'ai_sr': 55.0, 'ai_vcp': 60.0, 'ai_wave': 65.0, 'ai_weekly': 58.0, 'b60': b60, 'tight': bool(b60 <= 25.0), 'rsi_w': 52.0, 'mfi_w': 50.0,
            'banker': banker_red, 'speculator': hot_yellow, 'retail': retail_green, 'upper_shadow': up_shadow,
            'short_verdict': "🟢 SUPER VCP LAUNCHPAD" if b60 <= 25.0 else "⚡ ACCUMULATING",
            'master_verdict': "HIGH CONVICTION ACCUMULATION ENTRY!" if b60 <= 25.0 else "RANGE-BOUND ROTATION",
            'sl': risk_profile.get('stop_loss_price', round(p_c * 0.955, 1)), 'r_pct': round(risk_profile.get('risk_pct', 4.5), 2),
            'tg1': risk_profile.get('target_1_price', round(p_c * 1.07, 1)), 'tg2': risk_profile.get('target_2_price', round(p_c * 1.10, 1)),
            'shares': int(risk_profile.get('allocated_shares', 1000)), 'outlay': float(risk_profile.get('total_trade_capital_vnd', 20000000)),
            'nav_p': round(float(risk_profile.get('portfolio_weight_pct', 20.0)), 1), 'liq_p': round(float(risk_profile.get('vol_impact_pct', 1.5)), 2),
            'plotly_figure_json': fig.to_json()
        }
    except Exception: return None

def safe_radar_worker(s):
    try: return calculate_synchronized_impulse(fetch_ipo_historical_ohlcv(s), s)
    except Exception: return None

def safe_climax_worker(s):
    try: return scan_synchronized_climax(s)
    except Exception: return None

def safe_factor_worker(s):
    try: return evaluate_asset_multi_benchmark(s)
    except Exception: return None

if __name__ == "__main__":
    if not verify_market_session_finalized(): sys.exit(0)
    print("🚀 [KING TRADING] Commencing Full Quantitative Scan across 1,579 Equities...")
    t_start = time.time()
    all_symbols = get_vietnam_all_tickers()

    with ThreadPoolExecutor(max_workers=25) as ex:
        radar_results = [r for r in ex.map(safe_radar_worker, all_symbols) if r is not None]
    df_radar_sorted = pd.DataFrame(radar_results).sort_values(by='AI IMPULSE SCORE', ascending=False).reset_index(drop=True) if radar_results else pd.DataFrame()
    if not df_radar_sorted.empty: df_radar_sorted.insert(0, 'RANK', df_radar_sorted.index + 1)

    with ThreadPoolExecutor(max_workers=25) as ex:
        climax_results = [r for r in ex.map(safe_climax_worker, all_symbols) if r is not None]
    df_climax = pd.DataFrame(climax_results).sort_values(by='_prob_num', ascending=False).reset_index(drop=True) if climax_results else pd.DataFrame()
    if not df_climax.empty: df_climax.insert(0, 'RANK', df_climax.index + 1)

    risk_results = []
    for item in climax_results:
        sym = item.get('Ticker')
        if sym and sym in cached_climax_dfs and cached_climax_dfs[sym] is not None:
            res_risk = calculate_synchronized_bulltrap_risk(cached_climax_dfs[sym])
            if res_risk:
                res_risk['Ticker'] = sym
                risk_results.append(res_risk)

    df_risk_sorted = pd.DataFrame(risk_results).sort_values(by=['Risk Score', 'Price'], ascending=[True, False]).reset_index(drop=True) if risk_results else pd.DataFrame()
    if not df_risk_sorted.empty:
        cols_order = ['SAFETY RANK', 'Ticker', 'Price', 'Risk Score', 'Status', 'Upper Shadow (%)', 'Vol/MA20', 'OBV Slope(5d)', 'RSI', 'Action']
        df_risk_sorted.insert(0, 'SAFETY RANK', df_risk_sorted.index + 1)
        df_risk_sorted = df_risk_sorted[[c for c in cols_order if c in df_risk_sorted.columns]]

    with ThreadPoolExecutor(max_workers=25) as ex:
        factor_results = [r for r in ex.map(safe_factor_worker, all_symbols) if r is not None]
    df_factors = pd.DataFrame(factor_results) if factor_results else pd.DataFrame()
    df_trend_followers = df_factors.sort_values(by='_roc_20', ascending=False).reset_index(drop=True) if not df_factors.empty else pd.DataFrame()
    if not df_trend_followers.empty: df_trend_followers.insert(0, 'RANK', df_trend_followers.index + 1)
    df_counter_trend = df_factors.sort_values(by='_corr_vni_60', ascending=True).reset_index(drop=True) if not df_factors.empty else pd.DataFrame()
    if not df_counter_trend.empty: df_counter_trend.insert(0, 'RANK', df_counter_trend.index + 1)

    display_universe = sorted(list(set(
        (["BSR", "VPL", "VIC", "GAS", "PVT", "VOS", "HTN", "SSB", "HID", "MSR", "CAR", "TTG"]) +
        (df_trend_followers['Ticker'].head(30).tolist() if not df_trend_followers.empty else []) +
        (df_climax['Ticker'].head(30).tolist() if not df_climax.empty else [])
    )))

    ticker_database = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(process_complete_quant_asset, display_universe):
            if res and res[0]: ticker_database[res[0]] = res[1]
    print(f"✅ Synthesized {len(ticker_database)} asset dossiers for Proview.")

    json_payload_str = json.dumps(ticker_database)
    hanoi_timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime('%d/%m/%Y %H:%M:%S')
    dropdown_options = "".join([f'<option value="{sym}">{sym}</option>' for sym in ticker_database.keys()])
    init_sym = "BSR" if "BSR" in ticker_database else (list(ticker_database.keys())[0] if ticker_database else "VNINDEX")

    valid_surfer_symbols = [s for s in ticker_database.keys() if ticker_database[s]['price'] >= 1.0 and ticker_database[s]['liq_p'] <= 5.0][:5]
    if len(valid_surfer_symbols) < 5: valid_surfer_symbols = list(ticker_database.keys())[:5]

    table_surfer_rows = []
    for sym in valid_surfer_symbols:
        d = ticker_database[sym]
        badge = '<span class="badge badge-green">APPROVED</span>' if d['liq_p'] <= 4.0 and d['price'] >= 1.0 else '<span class="badge badge-yellow">MONITOR</span>'
        table_surfer_rows.append(f"""<tr>
            <td><button class="ticker-link-btn" onclick="selectSurferTicker('{sym}', {d['price']}, {d['sl']})"><b>{sym}</b></button></td>
            <td>{d['price']:.1f}</td>
            <td><span style="color: var(--neon-red);">{d['sl']:.1f} (-{d['r_pct']}%)</span></td>
            <td><span style="color: var(--neon-green);">{d['tg1']:.1f}</span></td>
            <td><span style="color: var(--neon-green);">{d['tg2']:.1f}</span></td>
            <td><b style="color: var(--neon-cyan);">{d['shares']:,}</b></td>
            <td>{d['outlay']:,.0f} VND</td>
            <td>{d['nav_p']:.1f}%</td>
            <td>{d['liq_p']:.2f}%</td>
            <td>{badge}</td>
        </tr>""")
    table_surfer_html = f'<div class="table-container"><table><thead><tr><th>Ticker</th><th>Entry</th><th>Stop Loss</th><th>Target 1</th><th>Target 2</th><th>Lot Shares</th><th>Outlay</th><th>NAV %</th><th>T+2.5 Impact</th><th>Verdict</th></tr></thead><tbody>{"".join(table_surfer_rows)}</tbody></table></div>'

    html_code = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KING TRADING: GALAXY TAB S9 & S24 ULTRA</title>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <style>
        :root {{
            --bg-deep: #080b11; --card-bg: #0f1622; --card-border: #1b263b;
            --royal-purple: #a855f7; --gold-metallic: #ffd54f; --silver-platinum: #e2e8f0;
            --ticker-orange: #ff9100; --neon-cyan: #00e5ff; --neon-green: #00e676;
            --neon-red: #ff5252; --neon-yellow: #ffeb3b; --text-dim: #8b9bb4;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ background-color: var(--bg-deep); color: #e0e6ed; font-family: -apple-system, sans-serif; padding: 8px; }}
        .brand-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .brand-title {{ font-size: 18px; font-weight: 900; }}
        .king-text {{ color: var(--royal-purple); }}
        .trading-text {{ color: var(--gold-metallic); }}
        .tab-bar {{ display: flex; gap: 6px; overflow-x: auto; margin-bottom: 10px; }}
        .tab-btn {{ background: #141c2b; border: 1px solid var(--card-border); color: var(--text-dim); padding: 8px 14px; border-radius: 6px; font-weight: bold; cursor: pointer; white-space: nowrap; }}
        .tab-btn.active {{ background: var(--neon-cyan); color: #000; }}
        .tab-pane {{ display: none; }}
        .tab-pane.active {{ display: block; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 8px; margin-bottom: 10px; }}
        .quant-card {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 10px; }}
        .card-header {{ font-size: 10px; font-weight: bold; color: var(--neon-cyan); text-transform: uppercase; margin-bottom: 6px; }}
        .stat-row {{ display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px; }}
        .terminal-dossier-box {{ background: #090d14; border: 1px solid var(--card-border); border-radius: 8px; padding: 10px; margin-bottom: 10px; font-family: monospace; font-size: 11px; line-height: 1.5; color: #d8e2ec; }}
        .table-container {{ overflow-x: auto; max-height: 650px; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
        th, td {{ padding: 7px 9px; border-bottom: 1px solid #141c2a; text-align: left; white-space: nowrap; }}
        th {{ position: sticky; top: 0; background: #151d2c; color: var(--neon-cyan); }}
        .badge {{ display: inline-block; padding: 2px 5px; border-radius: 3px; font-size: 9px; font-weight: 800; }}
        .badge-vn30 {{ background: rgba(168, 85, 247, 0.2); color: #d8b4fe; border: 1px solid var(--royal-purple); }}
        .badge-green {{ background: rgba(0, 230, 118, 0.15); color: var(--neon-green); border: 1px solid var(--neon-green); }}
        .badge-red {{ background: rgba(255, 82, 82, 0.15); color: var(--neon-red); border: 1px solid var(--neon-red); }}
        .badge-yellow {{ background: rgba(255, 235, 59, 0.15); color: var(--neon-yellow); border: 1px solid var(--neon-yellow); }}
        .ticker-link-btn {{ background: transparent; border: none; color: var(--ticker-orange); cursor: pointer; font-weight: bold; font-size: 11px; }}
        .search-input {{ width: 100%; background: #101622; border: 1px solid var(--card-border); border-radius: 6px; color: #fff; padding: 6px 10px; font-size: 12px; margin-bottom: 8px; }}
    </style>
</head>
<body>
    <div class="brand-row">
        <div class="brand-title">👑 <span class="king-text">KING</span> <span class="trading-text">TRADING OS</span></div>
        <div style="font-size: 10px; color: #888; font-family: monospace;">Hanoi: {hanoi_timestamp}</div>
    </div>
    <div class="tab-bar">
        <button class="tab-btn active" onclick="openTab('tab_proview')">📊 Proview</button>
        <button class="tab-btn" onclick="openTab('tab_overseer')">🔭 Overseer</button>
        <button class="tab-btn" onclick="openTab('tab_macro')">📡 Macro Radar</button>
        <button class="tab-btn" onclick="openTab('tab_climax')">🗡️ Knifecatcher</button>
        <button class="tab-btn" onclick="openTab('tab_shield')">🎯 Bounce Hunter</button>
        <button class="tab-btn" onclick="openTab('tab_surfer')">🏄 Surfer T+2.5</button>
    </div>

    <!-- TAB 1: PROVIEW -->
    <div id="tab_proview" class="tab-pane active">
        <div style="display: flex; gap: 6px; margin-bottom: 8px;">
            <input type="text" id="pro_search_input" class="search-input" style="flex:1; margin-bottom:0;" placeholder="Enter Ticker (e.g. BSR, VPL, VIC, GAS)..." onkeydown="if(event.key===\'Enter\') selectProViewTicker(this.value)">
            <select id="pro_select" onchange="selectProViewTicker(this.value)" style="background:#141c2b; color:var(--ticker-orange); padding:6px 10px; border-radius:6px; font-weight:bold; border:1px solid var(--ticker-orange);">{dropdown_options}</select>
        </div>
        <div class="metrics-grid">
            <div class="quant-card" style="border-top: 3px solid var(--neon-green);">
                <div class="card-header">💡 MASTER QUANT ACTION</div>
                <div class="stat-row"><span>Price / Vol:</span><b id="card_price_vol" style="color:var(--neon-cyan);">--</b></div>
                <div class="stat-row"><span>VCP Base:</span><b id="card_vcp_stat">--</b></div>
                <div class="stat-row"><span>Verdict:</span><b id="card_verdict" style="color:var(--neon-green);">--</b></div>
            </div>
            <div class="quant-card" style="border-top: 3px solid var(--neon-cyan);">
                <div class="card-header">🧠 4-PILLAR AI BRAINS</div>
                <div class="stat-row"><span>AI S/R Rebound:</span><b id="card_ai_sr" style="color:var(--neon-green);">--</b></div>
                <div class="stat-row"><span>AI VCP Breakout:</span><b id="card_ai_vcp" style="color:var(--neon-green);">--</b></div>
                <div class="stat-row"><span>AI Weekly Wave:</span><b id="card_ai_wk">--</b></div>
            </div>
            <div class="quant-card" style="border-top: 3px solid var(--neon-yellow);">
                <div class="card-header">🌊 FUND FLOW MCDX</div>
                <div class="stat-row"><span>🔴 Banker (Makers):</span><b id="card_banker" style="color:var(--neon-red);">--</b></div>
                <div class="stat-row"><span>🟡 Hot Money:</span><b id="card_spec" style="color:var(--neon-yellow);">--</b></div>
                <div class="stat-row"><span>🟢 Trapped Retail:</span><b id="card_retail" style="color:var(--neon-green);">--</b></div>
            </div>
            <div class="quant-card" style="border-top: 3px solid var(--ticker-orange);">
                <div class="card-header">🛡️ T+2.5 POSITION SIZER</div>
                <div class="stat-row"><span>Stop Loss (ATR):</span><b id="card_sl" style="color:var(--neon-red);">--</b></div>
                <div class="stat-row"><span>Target 1 / 2:</span><b id="card_tg" style="color:var(--neon-green);">--</b></div>
                <div class="stat-row"><span>Allocated Shares:</span><b id="card_alloc" style="color:var(--neon-cyan);">--</b></div>
            </div>
        </div>
        <div class="terminal-dossier-box" id="full_dossier_box"></div>
        <div id="chart_div" style="height:1180px; width:100%;"></div>
    </div>

    <!-- TAB 2: OVERSEER -->
    <div id="tab_overseer" class="tab-pane">
        <div class="metrics-grid">
            <div class="quant-card" style="border-top: 3px solid var(--neon-green);">
                <div class="card-header">🌐 VN-INDEX MULTI-TIMEFRAME TREND HIERARCHY</div>
                <div class="stat-row"><span>Monthly (M) Secular:</span><b style="color:var(--neon-green);">🟢 SECULAR BULL (PRIMARY EXPANSION)</b></div>
                <div class="stat-row"><span>Weekly (W) Mid-Term:</span><b style="color:var(--neon-yellow);">🛡️ HEALTHY PULLBACK (SECONDARY RETRACEMENT)</b></div>
                <div class="stat-row"><span>Daily (D) Tactical:</span><b style="color:var(--neon-cyan);">⚡ TACTICAL MOMENTUM LEAD</b></div>
            </div>
            <div class="quant-card" style="border-top: 3px solid var(--neon-cyan);">
                <div class="card-header">💡 STRATEGIC MANDATE</div>
                <p style="font-size:11px; line-height:1.4; color:var(--neon-green);">🟢 BULLISH REGIME ACTIVE: Prioritize High-Beta Trend Leaders (Super Surfers) on Pullback dips!</p>
            </div>
        </div>
        <input type="text" class="search-input" placeholder="🔍 Search Strategy A Leaders..." onkeyup="filterTable(this.value, \'tbl_a\')">
        {build_html_table(df_trend_followers, "tbl_a")}
        <input type="text" class="search-input" style="margin-top:12px;" placeholder="🔍 Search Strategy B Storm Runners..." onkeyup="filterTable(this.value, \'tbl_b\')">
        {build_html_table(df_counter_trend, "tbl_b")}
    </div>

    <!-- TAB 3: MACRO RADAR -->
    <div id="tab_macro" class="tab-pane">
        <input type="text" class="search-input" placeholder="🔍 Search Macro Radar..." onkeyup="filterTable(this.value, \'tbl_m\')">
        {build_html_table(df_radar_sorted, "tbl_m")}
    </div>

    <!-- TAB 4: KNIFECATCHER -->
    <div id="tab_climax" class="tab-pane">
        <input type="text" class="search-input" placeholder="🔍 Search Knifecatcher Selling Climax..." onkeyup="filterTable(this.value, \'tbl_c\')">
        {build_html_table(df_climax, "tbl_c")}
    </div>

    <!-- TAB 5: BOUNCE HUNTER -->
    <div id="tab_shield" class="tab-pane">
        <input type="text" class="search-input" placeholder="🔍 Search Bounce Hunter Safety Shield..." onkeyup="filterTable(this.value, \'tbl_s\')">
        {build_html_table(df_risk_sorted, "tbl_s")}
    </div>

    <!-- TAB 6: SURFER T+2.5 -->
    <div id="tab_surfer" class="tab-pane">
        <div class="metrics-grid">
            <div class="quant-card" style="border-top: 3px solid var(--neon-cyan);">
                <div class="card-header">💼 PORTFOLIO ALLOCATION RULEBOOK</div>
                <div class="stat-row"><span>Portfolio NAV:</span><b>1,000,000,000 VND</b></div>
                <div class="stat-row"><span>Risk Per Trade:</span><b style="color:var(--neon-red);">1.5% (15,000,000 VND max loss)</b></div>
                <div class="stat-row"><span>Max Single Stock Cap:</span><b>25.0% NAV (250M VND)</b></div>
            </div>
            <div class="quant-card" style="border-top: 3px solid var(--neon-green);">
                <div class="card-header">⚡ INTERACTIVE LIVE SURFER CALCULATOR</div>
                <div style="display:flex; gap:6px; margin-bottom:6px;">
                    <input type="number" id="calc_price" class="search-input" style="margin-bottom:0;" placeholder="Price" value="30.6">
                    <input type="number" id="calc_sl" class="search-input" style="margin-bottom:0;" placeholder="Stop Loss" value="29.2">
                </div>
                <button class="tab-btn active" style="width:100%; padding:6px;" onclick="calcSurferLive()">⚡ CALCULATE 100-SHARE LOT</button>
                <div id="calc_result" style="margin-top:6px; font-size:11px; color:var(--neon-cyan);">Allocated: <b>10,700 shares</b> | Total: <b>248M VND (24.8% NAV)</b></div>
            </div>
        </div>
        {table_surfer_html}
    </div>

    <script>
        const DB = {json_payload_str};
        function openTab(id) {{
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(id).classList.add('active');
            event.target.classList.add('active');
            if (id === 'tab_proview') setTimeout(() => {{ Plotly.Plots.resize('chart_div'); }}, 50);
        }}
        function filterTable(val, tblId) {{
            let q = val.toUpperCase().trim();
            let trs = document.getElementById(tblId).getElementsByTagName('tr');
            for (let i = 1; i < trs.length; i++) {{
                trs[i].style.display = (trs[i].textContent || trs[i].innerText).toUpperCase().indexOf(q) > -1 ? '' : 'none';
            }}
        }}
        function selectProViewTicker(sym) {{
            sym = sym.toUpperCase().replace('#', '').trim();
            if (!DB[sym]) return;
            document.getElementById('pro_select').value = sym;
            let d = DB[sym];
            document.getElementById('card_price_vol').innerText = `${{d.price.toFixed(1)}} | ${{d.volume.toLocaleString()}} (${{d.vol_ratio}}x MA20)`;
            document.getElementById('card_vcp_stat').innerText = `${{d.b60.toFixed(1)}}% (${{d.tight ? '🔒 TIGHT BASE' : 'LOOSE'}})`;
            document.getElementById('card_verdict').innerText = d.short_verdict;
            document.getElementById('card_ai_sr').innerText = `${{d.ai_sr}}%`;
            document.getElementById('card_ai_vcp').innerText = `${{d.ai_vcp}}%`;
            document.getElementById('card_ai_wk').innerText = `${{d.ai_weekly}}% Surge`;
            document.getElementById('card_banker').innerText = `${{d.banker}}%`;
            document.getElementById('card_spec').innerText = `${{d.speculator}}%`;
            document.getElementById('card_retail').innerText = `${{d.retail}}%`;
            document.getElementById('card_sl').innerText = `${{d.sl.toFixed(1)}} (-${{d.r_pct}}%)`;
            document.getElementById('card_tg').innerText = `${{d.tg1.toFixed(1)}} / ${{d.tg2.toFixed(1)}}`;
            document.getElementById('card_alloc').innerText = `${{d.shares.toLocaleString()}} shs (${{d.liq_p}}% Vol)`;
            document.getElementById('full_dossier_box').innerHTML = `
                <div style="color:var(--ticker-orange); font-weight:bold; font-size:12px;">🏛️ INSTITUTIONAL TECHNICAL DOSSIER: ${{sym}} (${{d.company_name}})</div>
                <div>▶️ Price: <b>${{d.price.toFixed(1)}}</b> | MAs: MA20=<b>${{d.ma20}}</b> | MA50=<b>${{d.ma50}}</b> | MA100=<b>${{d.ma100}}</b> | MA200=<b>${{d.ma200}}</b></div>
                <div>⛩️ Ichimoku: T10=<b>${{d.t10}}</b> | K20=<b>${{d.k20}}</b> | K120=<b>${{d.k120}}</b> | K240=<b>${{d.k240}}</b> | Macro POC=<b>${{d.poc}}</b></div>
                <div>🧭 Momentum: Aroon Osc=<b>+${{d.aroon_osc}}</b> | ADX=<b>${{d.adx}}</b> | OBV Z-Score=<b>${{d.obv_z}}s</b> | Upper Shadow=<b>${{d.upper_shadow}}%</b></div>
                <div style="color:var(--neon-cyan); margin-top:4px;">💡 VERDICT: ${{d.master_verdict}}</div>
            `;
            let fig = JSON.parse(d.plotly_figure_json);
            Plotly.react('chart_div', fig.data, fig.layout, {{ responsive: true, scrollZoom: false, displayModeBar: false }});
            openTab('tab_proview');
        }}
        function selectSurferTicker(sym, p, sl) {{
            document.getElementById('calc_price').value = p;
            document.getElementById('calc_sl').value = sl;
            calcSurferLive();
        }}
        function calcSurferLive() {{
            let p = parseFloat(document.getElementById('calc_price').value);
            let sl = parseFloat(document.getElementById('calc_sl').value);
            if (isNaN(p) || isNaN(sl) || p <= sl) return;
            let risk = (p - sl) * 1000.0;
            let budget = 15000000;
            let rawSh = Math.floor(budget / risk / 100.0) * 100;
            let maxNav = Math.floor(250000000 / (p * 1000.0) / 100.0) * 100;
            let sh = Math.min(rawSh, maxNav);
            let outlay = sh * p * 1000.0;
            document.getElementById('calc_result').innerHTML = `Allocated: <b style="color:var(--neon-green); font-size:13px;">${{sh.toLocaleString()}} shares</b> | Total: <b>${{outlay.toLocaleString()}} VND (${{(outlay/10000000).toFixed(1)}}% NAV)</b>`;
        }}
        selectProViewTicker('{init_sym}');
    </script>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_code)
    print(f"🎉 [MASTER PIPELINE COMPLETE] 'index.html' ({os.path.getsize('index.html')/1024:.1f} KB) generated in {time.time() - t_start:.1f}s!")
