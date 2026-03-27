import yfinance as yf
import pandas as pd
import requests
import time
import os
from datetime import datetime, timedelta, timezone

# ==========================================
# 🔑 憑證讀取 (從 GitHub Secrets)
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TG_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TG_CHAT_ID")
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")

def get_taiwan_time():
    """統一使用台北時區"""
    return datetime.now(timezone(timedelta(hours=8)))

def get_institutional_net_buy(stock_id):
    """【強化版】解決籌碼 0 張：自動搜尋最近一個有資料的交易日"""
    clean_id = stock_id.split('.')[0]
    # 抓取過去 14 天，確保避開週末與連假
    start_date = (get_taiwan_time() - timedelta(days=14)).strftime("%Y-%m-%d")
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
            # 依日期由新到舊排序
            df_inst = df_inst.sort_values(by='date', ascending=False)
            # 抓取最新一筆有資料的日期
            latest_date = df_inst['date'].iloc[0]
            latest_data = df_inst[df_inst['date'] == latest_date]
            
            buy_sum = 0
            for _, row in latest_data.iterrows():
                if any(n in row['name'] for n in ['外資', '投信']):
                    buy_sum += (row['buy'] - row['sell'])
            
            net_vol = round(buy_sum / 1000)
            print(f"DEBUG: {stock_id} 成功抓取日期 {latest_date} | 籌碼: {net_vol}張")
            return net_vol
    except Exception as e:
        print(f"DEBUG: {stock_id} 籌碼 API 錯誤: {e}")
    return 0

# 監控清單
stock_dict = {
    "6823.TWO": "濾能", "2337.TW": "旺宏", "2408.TW": "南亞科", 
    "2344.TW": "華邦電", "2409.TW": "友達", "3481.TW": "群創", 
    "2330.TW": "台積電", "8299.TWO": "群聯", "3019.TW": "亞光", 
    "2812.TW": "台中銀", "6770.TW": "力積電"
}

all_stocks_report = []
tw_now = get_taiwan_time()
print(f"🚀 啟動掃描 | Token狀態: {'已連接' if FINMIND_TOKEN else '未連接 (請檢查Secrets)'}")

for stock_id, stock_name in stock_dict.items():
    try:
        print(f"🔍 掃描中: {stock_name} ({stock_id})...")
        time.sleep(1.2)
        
        # 抓取資料
        df = yf.download(stock_id, period="1y", progress=False)
        
        # 如果 yfinance 失敗，不要 continue，而是記錄失敗原因
        if df.empty or len(df) < 20:
            print(f"⚠️ {stock_name} 下載失敗")
            all_stocks_report.append({
                "name": f"{stock_id.split('.')[0]} {stock_name}",
                "is_pass": False, "buy": "無資料", "macd": "抓取失敗", 
                "ma20": "-", "kd": "-", "vol": "-"
            })
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

        # 邏輯判定
        inst_buy = get_institutional_net_buy(stock_id)
        # MACD 打底條件
        is_ready = (row['OSC'] < 0) and (row['OSC'] > prev['OSC']) and (row['DIF'] > prev['DIF'])
        
        macd_status = "📉收斂" if row['OSC'] < 0 and row['OSC'] > prev['OSC'] else \
                      "⚠️擴大" if row['OSC'] < 0 else "📈漲勢"

        all_stocks_report.append({
            "name": f"{stock_id.split('.')[0]} {stock_name}",
            "is_pass": is_ready and inst_buy > 0,
            "buy": f"{inst_buy}張",
            "macd": macd_status,
            "ma20": "站上" if row['Close'] > row['MA20'] else "破線",
            "kd": "低" if row['K'] < 30 else "高" if row['K'] > 70 else "中",
            "vol": "出量" if row['Volume'] > row['V_MA5'] else "量縮"
        })
        print(f"✅ {stock_name} 完成")

    except Exception as e:
        print(f"❌ {stock_name} 異常: {e}")

# ==========================================
# 組合 Telegram 訊息
# ==========================================
msg = f"📊【診斷報告】{tw_now.strftime('%m/%d %H:%M')}\n"
msg += "═" * 15 + "\n"

# 分類顯示
passed = [s for s in all_stocks_report if s['is_pass']]
if passed:
    msg += "🎯【完美打底達標股】\n"
    for s in passed:
        msg += f"✅ {s['name']} | {s['buy']} | {s['macd']}\n"
    msg += "─" * 15 + "\n"

msg += "📋【觀察清單總覽】\n"
for s in all_stocks_report:
    icon = "✅" if s['is_pass'] else "⏸️"
    msg += f"{icon} {s['name']}\n"
    msg += f" ├ 籌碼: {s['buy']} | 動能: {s['macd']}\n"
    msg += f" └ 趨勢: {s['ma20']} | KD: {s['kd']} | {s['vol']}\n\n"

# 發送訊息
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
