import yfinance as yf
import pandas as pd
import requests
import time
import os
from datetime import datetime, timedelta, timezone

# ==========================================
# 🔑 從 GitHub Secrets 安全讀取憑證
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TG_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TG_CHAT_ID")
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "") 

# 監控清單 (請確認上市用 .TW, 上櫃用 .TWO)
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
    "6823.TWO": "濾能", 
    "6770.TW": "力積電"
}

def get_taiwan_time():
    """獲取台灣目前的日期對象"""
    tz_tw = timezone(timedelta(hours=8))
    return datetime.now(tz_tw)

def send_telegram_message(msg):
    """發送 Telegram 訊息"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ 錯誤：找不到 Telegram 憑證，無法發送訊息！")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
        if res.status_code == 200:
            print("✅ Telegram 訊息發送成功！")
        else:
            print(f"❌ 發送失敗，狀態碼: {res.status_code}, 回應: {res.text}")
    except Exception as e:
        print(f"❌ 發送異常: {e}")

def get_institutional_net_buy(stock_id):
    """獲取法人買賣超 (最近一個交易日)"""
    clean_id = stock_id.split('.')[0]
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
            last_date = df_inst['date'].max()
            latest_data = df_inst[df_inst['date'] == last_date]
            net_buy = 0
            for _, row in latest_data.iterrows():
                if any(name in row['name'] for name in ['外資', '投信']):
                    net_buy += (row['buy'] - row['sell'])
            return round(net_buy / 1000)
    except:
        pass
    return 0

all_stocks_report = []
tw_now = get_taiwan_time()
print(f"🚀 啟動掃描器 | 台北時間: {tw_now.strftime('%Y-%m-%d %H:%M')}")
print(f"DEBUG: 監控清單: {list(stock_dict.values())}\n")

for stock_id, stock_name in stock_dict.items():
    try:
        time.sleep(1.2) # 避免 API 頻繁請求被封鎖
        df = yf.download(stock_id, period="1y", progress=False)
        
        if df.empty:
            print(f"⚠️ {stock_name}({stock_id}) yfinance 抓不到數據，跳過。")
            continue
        
        # 處理 MultiIndex 欄位 (yfinance 新版特性)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if len(df) < 35:
            print(f"⚠️ {stock_name} 歷史資料不足，跳過。")
            continue

        # --- 指標計算 ---
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['MACD_line'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['OSC'] = df['DIF'] - df['MACD_line']
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
        
        # KD 計算
        df['9_min'] = df['Low'].rolling(window=9).min()
        df['9_max'] = df['High'].rolling(window=9).max()
        df['RSV'] = 100 * (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min'])
        df['K'] = df['RSV'].ewm(alpha=1/3, adjust=False).mean()
        df['D'] = df['K'].ewm(alpha=1/3, adjust=False).mean()

        df.dropna(inplace=True)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # --- 判斷邏輯 ---
        inst_buy = get_institutional_net_buy(stock_id)
        is_macd_ready = (last['OSC'] < 0) and (last['OSC'] > prev['OSC']) and (last['DIF'] > prev['DIF'])
        is_pass = is_macd_ready and (inst_buy > 0)

        # 狀態文字轉換
        macd_txt = "📉跌勢收斂" if last['OSC'] < 0 and last['OSC'] > prev['OSC'] else \
                   "⚠️跌勢擴大" if last['OSC'] < 0 else \
                   "📈漲勢擴大" if last['OSC'] > prev['OSC'] else "⚠️漲勢收斂"
        
        ma20_txt = "✅站上" if last['Close'] > last['MA20'] else "❌破線"
        vol_txt = "🔥出量" if last['Volume'] > last['Vol_MA5'] else "量縮"
        
        kd_txt = "中"
        if last['K'] < 25: kd_txt = "低(超賣)"
        elif last['K'] > 75: kd_txt = "高(超買)"
        if last['K'] > last['D'] and prev['K'] <= prev['D']: kd_txt += "✨金叉"

        all_stocks_report.append({
            "name": f"{stock_id.split('.')[0]} {stock_name}",
            "is_pass": is_pass,
            "buy": f"{inst_buy}張",
            "macd": macd_txt,
            "ma20": ma20_txt,
            "kd": kd_txt,
            "vol": vol_txt
        })
        print(f"✅ 完成掃描: {stock_name}")

    except Exception as e:
        print(f"❌ 異常 ({stock_name}): {e}")

# ==========================================
# 組合訊息並推播
# ==========================================
passed = [s for s in all_stocks_report if s['is_pass']]
others = [s for s in all_stocks_report if not s['is_pass']]

msg = f"<b>📊【盤前全庫存監控儀表板】</b>\n"
msg += f"🕒 執行時間: {tw_now.strftime('%m/%d %H:%M')}\n"
msg += "═" * 15 + "\n"

msg += "🎯<b>【完美打底達標股】</b>\n"
if passed:
    for s in passed:
        msg += f"✅ {s['name']}\n"
        msg += f" ├ 籌碼: {s['buy']} | 月線: {s['ma20']}\n"
        msg += f" └ 動能: {s['macd']} | KD: {s['kd']}\n\n"
else:
    msg += "今日無符合標的。\n\n"

msg += "─" * 15 + "\n"
msg += "📋<b>【觀察清單總覽】</b>\n"
for s in others:
    msg += f"⏸️ {s['name']} | {s['macd']} | {s['ma20']}\n"

send_telegram_message(msg)
