import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# ==========================================
# 🔑 您的專屬 Telegram 憑證已綁定！
TELEGRAM_BOT_TOKEN = "8793345742:AAFUbjHQ7xBvNBE11SbhbWpwsXrE5ZhTLGY"
TELEGRAM_CHAT_ID = "948927297"
# ==========================================

stock_dict = {
    "2337.TW": "旺宏", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2409.TW": "友達", "3481.TW": "群創", "2330.TW": "台積電",
    "8299.TWO": "群聯", "3019.TW": "亞光", "2812.TW": "台中銀",
    "6823.TWO": "濾能"
}

# 改用一個清單來收集「所有」股票的狀態
all_stocks_report = []
print("🚀 開始執行【全景監控版 籌碼掃描器】...\n")

def get_institutional_net_buy(stock_id):
    clean_id = stock_id.split('.')[0]
    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "data_id": clean_id, "start_date": start_date}
    try:
        res = requests.get(url, params=params).json()
        if res["msg"] == "success" and len(res["data"]) > 0:
            df = pd.DataFrame(res["data"])
            latest_data = df[df['date'] == df['date'].max()]
            net_buy = sum(row['buy'] - row['sell'] for _, row in latest_data.iterrows() if row['name'] in ['外資及陸資(不含外資自營商)', '投信'])
            return round(net_buy / 1000)
    except Exception:
        pass
    return 0

def send_telegram_message(msg, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": msg})
        print("✅ Telegram 訊息發送成功！")
    except Exception as e:
        print(f"❌ 發送異常: {e}")

for stock_id, stock_name in stock_dict.items():
    clean_id = stock_id.split('.')[0]
    try:
        time.sleep(1)
        df = yf.download(stock_id, period="1y", progress=False)
        if df.empty: continue

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        # 1. MACD 計算
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['MACD_line'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['OSC'] = df['DIF'] - df['MACD_line']

        # 2. MA20 月線計算
        df['MA20'] = df['Close'].rolling(window=20).mean()

        # 3. KD 計算
        df['9_min'] = df['Low'].rolling(window=9).min()
        df['9_max'] = df['High'].rolling(window=9).max()
        df['RSV'] = 100 * (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min'])
        df['K'] = df['RSV'].ewm(alpha=1/3, adjust=False).mean()
        df['D'] = df['K'].ewm(alpha=1/3, adjust=False).mean()

        # 4. 5日均量
        df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()

        # --- 取得最新數據 ---
        close_price = float(df['Close'].iloc[-1].item())
        ma20 = float(df['MA20'].iloc[-1].item())
        today_osc = float(df['OSC'].iloc[-1].item())
        yest_osc = float(df['OSC'].iloc[-2].item())
        today_dif = float(df['DIF'].iloc[-1].item())
        yest_dif = float(df['DIF'].iloc[-2].item())
        k_today = float(df['K'].iloc[-1].item())
        d_today = float(df['D'].iloc[-1].item())
        k_yest = float(df['K'].iloc[-2].item())
        d_yest = float(df['D'].iloc[-2].item())
        vol_today = float(df['Volume'].iloc[-1].item())
        vol_ma5 = float(df['Vol_MA5'].iloc[-1].item())

        # --- 判斷邏輯 ---
        inst_net_buy = get_institutional_net_buy(stock_id)
        
        # 判斷 MACD 嚴格打底條件是否成立
        is_macd_ready = (today_osc < 0) and (today_osc > yest_osc) and (today_dif > yest_dif)
        is_pass = is_macd_ready and (inst_net_buy > 0) # 雙重過關

        # 判斷 MACD 目前的動能狀態 (轉換成白話文)
        if today_osc < 0:
            macd_status = "📉跌勢收斂" if today_osc > yest_osc else "⚠️跌勢擴大"
        else:
            macd_status = "📈漲勢擴大" if today_osc > yest_osc else "⚠️漲勢收斂"

        # 判斷其他狀態
        ma20_status = "站上" if close_price > ma20 else "破線"
        vol_status = "量縮" if vol_today < vol_ma5 else "出量"
        
        kd_str = "中"
        if k_today < 30: kd_str = "低"
        elif k_today > 70: kd_str = "高"
        if k_today > d_today and k_yest <= d_yest: kd_str += "(✨金叉)"

        print(f"掃描完成: {stock_name} | 是否達標: {is_pass}")
        
        # 將「每一檔」股票的資訊都存入總表
        all_stocks_report.append({
            "name": f"{clean_id} {stock_name}",
            "is_pass": is_pass,
            "buy": f"{inst_net_buy}張",
            "macd_status": macd_status,
            "ma20": ma20_status,
            "kd": kd_str,
            "vol": vol_status
        })

    except Exception as e:
         print(f"發生異常 ({stock_name}): {e}")

# ==========================================
# 組合超專業 Telegram 全景訊息
# ==========================================
print("\n" + "="*50)
print("🛡️ 正在整理報告並發送至 Telegram...")

# 將名單分成「達標」與「未達標」兩組，讓畫面更有層次
passed_stocks = [s for s in all_stocks_report if s['is_pass']]
other_stocks = [s for s in all_stocks_report if not s['is_pass']]

notify_msg = f"📊【盤前全庫存監控儀表板】\n"
notify_msg += "═" * 15 + "\n"

# 第一段：重點打底達標股
if passed_stocks:
    notify_msg += "🎯【完美打底達標股】(MACD收斂+法人買)\n"
    for item in passed_stocks:
         notify_msg += f"✅ {item['name']}\n"
         notify_msg += f" ├ 籌碼: 大戶 {item['buy']} | 月線: {item['ma20']}\n"
         notify_msg += f" └ 動能: {item['macd_status']} | ＫＤ: {item['kd']}\n\n"
else:
    notify_msg += "🎯【完美打底達標股】\n今日無符合標的，請耐心等待。\n\n"

notify_msg += "─" * 15 + "\n"

# 第二段：其他觀察清單總覽 (使用精簡排版避免洗版)
notify_msg += "📋【觀察清單狀態總覽】\n"
for item in other_stocks:
     notify_msg += f"⏸️ {item['name']}\n"
     notify_msg += f" ├ 籌碼: {item['buy']} | 動能: {item['macd_status']}\n"
     notify_msg += f" └ 趨勢: {item['ma20']} | ＫＤ: {item['kd']} | {item['vol']}\n\n"

# 最終推播
send_telegram_message(notify_msg, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
print("="*50)
