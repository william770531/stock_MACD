import yfinance as yf
import pandas as pd
import requests
import time
import os  # <--- 1. 務必導入這個環境變數模組
from datetime import datetime, timedelta, timezone

# ==========================================
# 🔑 從 GitHub Secrets 安全讀取憑證
# os.getenv("名字") 會去抓你在 GitHub 設定的那個 Secret
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TG_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TG_CHAT_ID")
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "") # 如果你有設 FinMind Token 也可以這樣抓
# ==========================================

# 檢查一下有沒有抓到 (除錯用，GitHub Actions 日誌看得到)
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ 錯誤：找不到 Telegram 憑證，請檢查 GitHub Secrets 設定！")

stock_dict = {
    "2337.TW": "旺宏", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2409.TW": "發達", "3481.TW": "群創", "2330.TW": "台積電",
    "8299.TWO": "群聯", "3019.TW": "亞光", "2812.TW": "台中銀",
    "6823.TWO": "濾能", "6770.TW": "力積電"
}
# ==========================================

def get_taiwan_time():
    """獲取台灣目前的日期字串"""
    tz_tw = timezone(timedelta(hours=8))
    return datetime.now(tz_tw)

def get_institutional_net_buy(stock_id):
    """獲取法人買賣超 (外資+投信)"""
    clean_id = stock_id.split('.')[0]
    # 抓取過去 7 天確保能涵蓋到最近的交易日
    start_date = (get_taiwan_time() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id": clean_id,
        "start_date": start_date,
        "token": FINMIND_TOKEN
    }
    
    try:
        res = requests.get(url, params=params, timeout=10).json()
        if res.get("msg") == "success" and len(res["data"]) > 0:
            df_inst = pd.DataFrame(res["data"])
            # 抓取最後一個有資料的日期 (通常是昨天或前一個交易日)
            last_date = df_inst['date'].max()
            latest_data = df_inst[df_inst['date'] == last_date]
            
            # 篩選外資與投信
            net_buy = 0
            for _, row in latest_data.iterrows():
                if any(name in row['name'] for name in ['外資', '投信']):
                    net_buy += (row['buy'] - row['sell'])
            return round(net_buy / 1000)
    except Exception as e:
        print(f"⚠️ 籌碼抓取失敗 ({stock_id}): {e}")
    return 0

all_stocks_report = []
print(f"🚀 啟動掃描器 | 台北時間: {get_taiwan_time().strftime('%Y-%m-%d %H:%M')}\n")

for stock_id, stock_name in stock_dict.items():
    try:
        time.sleep(1.5) # 稍微增加延遲避免被 API 封鎖
        df = yf.download(stock_id, period="1y", progress=False)
        if df.empty or len(df) < 30: continue

        # 處理 yfinance 新版的 MultiIndex 欄位
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # --- 技術指標計算 ---
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['MACD_line'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['OSC'] = df['DIF'] - df['MACD_line']
        
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        df['9_min'] = df['Low'].rolling(window=9).min()
        df['9_max'] = df['High'].rolling(window=9).max()
        df['RSV'] = 100 * (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min'])
        df['K'] = df['RSV'].ewm(alpha=1/3, adjust=False).mean()
        df['D'] = df['K'].ewm(alpha=1/3, adjust=False).mean()
        df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()

        df.dropna(inplace=True) # 移除空值確保 iloc 準確

        # --- 數據擷取 ---
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        close_p = float(last_row['Close'])
        ma20_v = float(last_row['MA20'])
        today_osc = float(last_row['OSC'])
        yest_osc = float(prev_row['OSC'])
        today_dif = float(last_row['DIF'])
        yest_dif = float(prev_row['DIF'])
        k_t, d_t = float(last_row['K']), float(last_row['D'])
        k_y, d_y = float(prev_row['K']), float(prev_row['D'])
        vol_t, vol_ma5 = float(last_row['Volume']), float(last_row['Vol_MA5'])

        # --- 邏輯判定 ---
        inst_net_buy = get_institutional_net_buy(stock_id)
        
        # MACD 打底：柱狀體負值縮短且 DIF 翻揚
        is_macd_ready = (today_osc < 0) and (today_osc > yest_osc) and (today_dif > yest_dif)
        is_pass = is_macd_ready and (inst_net_buy > 0)

        # 狀態文字處理
        if today_osc < 0:
            macd_status = "📉跌勢收斂" if today_osc > yest_osc else "⚠️跌勢擴大"
        else:
            macd_status = "📈漲勢擴大" if today_osc > yest_osc else "⚠️漲勢收斂"

        ma20_status = "✅站上" if close_p > ma20_v else "❌破線"
        vol_status = "量縮" if vol_t < vol_ma5 else "🔥出量"
        
        kd_str = "中"
        if k_t < 25: kd_str = "低(超賣)"
        elif k_t > 75: kd_str = "高(超買)"
        if k_t > d_t and k_y <= d_y: kd_str += "✨金叉"

        all_stocks_report.append({
            "name": f"{stock_id.split('.')[0]} {stock_name}",
            "is_pass": is_pass,
            "buy": f"{inst_net_buy}張",
            "macd_status": macd_status,
            "ma20": ma20_status,
            "kd": kd_str,
            "vol": vol_status
        })
        print(f"✅ 已掃描: {stock_name}")

    except Exception as e:
        print(f"❌ 發生異常 ({stock_name}): {e}")

# ==========================================
# Telegram 訊息組合與發送 (略，保持您原本的格式)
# ==========================================
# ... (這裡接您原本的 notify_msg 組合邏輯與 send_telegram_message)
