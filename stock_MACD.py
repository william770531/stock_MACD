import yfinance as yf
import pandas as pd
import requests
import time
import os
from datetime import datetime, timedelta, timezone

# ==========================================
# 🔑 憑證讀取
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TG_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TG_CHAT_ID")
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "") 

# ⚠️ 這裡請務必確認後綴：上市 .TW / 上櫃 .TWO
stock_dict = {
    "2337.TW": "旺宏", 
    "2408.TW": "南亞科", 
    "2344.TW": "華邦電",
    "2409.TW": "友達", 
    "3481.TW": "群創", 
    "2330.TW": "台積電",
    "8299.TWO": "群聯", 
    "3019.TW": "亞光", 
    "2812.TW": "台中銀",
    "6823.TWO": "濾能",  # 確認是 .TWO
    "6770.TW": "力積電"
}

def get_taiwan_time():
    return datetime.now(timezone(timedelta(hours=8)))

def get_institutional_net_buy(stock_id):
    """加強版：如果今天沒資料，會嘗試抓昨天的"""
    clean_id = stock_id.split('.')[0]
    # 抓過去 10 天，確保能涵蓋連假或週末
    start_date = (get_taiwan_time() - timedelta(days=10)).strftime("%Y-%m-%d")
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
            # 抓取「有資料」的最後一天
            latest_date = df_inst['date'].max()
            today_data = df_inst[df_inst['date'] == latest_date]
            
            buy_sum = 0
            for _, row in today_data.iterrows():
                if any(n in row['name'] for n in ['外資', '投信']):
                    buy_sum += (row['buy'] - row['sell'])
            return round(buy_sum / 1000)
    except Exception as e:
        print(f"DEBUG: {stock_id} 籌碼 API 錯誤: {e}")
    return 0

all_stocks_report = []
tw_now = get_taiwan_time()
print(f"🚀 開始掃描... 台北時間: {tw_now.strftime('%Y-%m-%d %H:%M')}")

for stock_id, stock_name in stock_dict.items():
    try:
        time.sleep(1.5)
        # 修正：yfinance 有時需要 1mo 的資料才能穩定計算 MA20
        df = yf.download(stock_id, period="1y", progress=False)
        
        if df.empty:
            print(f"❌ 嚴重錯誤：{stock_name}({stock_id}) yfinance 完全抓不到資料！")
            continue

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 指標計算
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['MACD_line'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['OSC'] = df['DIF'] - df['MACD_line']
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['V_MA5'] = df['Volume'].rolling(window=5).mean()
        
        # KD
        df['L9'] = df['Low'].rolling(window=9).min()
        df['H9'] = df['High'].rolling(window=9).max()
        df['RSV'] = 100 * (df['Close'] - df['L9']) / (df['H9'] - df['L9'])
        df['K'] = df['RSV'].ewm(alpha=1/3, adjust=False).mean()
        df['D'] = df['K'].ewm(alpha=1/3, adjust=False).mean()

        df.dropna(inplace=True)
        row = df.iloc[-1]
        prev = df.iloc[-2]

        # 判斷
        inst_buy = get_institutional_net_buy(stock_id)
        is_macd_ready = (row['OSC'] < 0) and (row['OSC'] > prev['OSC']) and (row['DIF'] > prev['DIF'])
        
        status = "📉跌勢收斂" if row['OSC'] < 0 and row['OSC'] > prev['OSC'] else \
                 "⚠️跌勢擴大" if row['OSC'] < 0 else \
                 "📈漲勢擴大" if row['OSC'] > prev['OSC'] else "⚠️漲勢收斂"

        all_stocks_report.append({
            "name": f"{stock_id.split('.')[0]} {stock_name}",
            "is_pass": is_macd_ready and inst_buy > 0,
            "buy": f"{inst_buy}張",
            "macd": status,
            "ma20": "站上" if row['Close'] > row['MA20'] else "破線",
            "kd": "低" if row['K'] < 30 else "高" if row['K'] > 70 else "中",
            "vol": "出量" if row['Volume'] > row['V_MA5'] else "量縮"
        })
        print(f"✅ 完成: {stock_name}")

    except Exception as e:
        print(f"❌ 發生異常 ({stock_name}): {e}")

# ==========================================
# 組合訊息
# ==========================================
msg = f"📊【全景監控報告】({tw_now.strftime('%m/%d %H:%M')})\n"
msg += "═" * 15 + "\n"

passed = [s for s in all_stocks_report if s['is_pass']]
if passed:
    msg += "🎯【完美打底達標股】\n"
    for s in passed:
        msg += f"✅ {s['name']} | {s['buy']} | {s['macd']}\n"
    msg += "─" * 15 + "\n"

msg += "📋【清單總覽】(名單共計: " + str(len(all_stocks_report)) + " 檔)\n"
for s in all_stocks_report:
    msg += f"⏸️ {s['name']}\n ├ 籌碼: {s['buy']} | 動能: {s['macd']}\n └ 趨勢: {s['ma20']} | KD: {s['kd']} | {s['vol']}\n\n"

# 發送至 Telegram
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
