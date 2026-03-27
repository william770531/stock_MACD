import yfinance as yf
import pandas as pd
import requests
import time
import os
from datetime import datetime, timedelta, timezone

# 🔑 憑證
TELEGRAM_BOT_TOKEN = os.getenv("TG_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TG_CHAT_ID")
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")

def get_taiwan_time():
    return datetime.now(timezone(timedelta(hours=8)))

def get_institutional_net_buy(stock_id):
    clean_id = stock_id.split('.')[0]
    start_date = (get_taiwan_time() - timedelta(days=14)).strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "data_id": clean_id, "start_date": start_date, "token": FINMIND_TOKEN}
    try:
        res = requests.get(url, params=params, timeout=10).json()
        if res.get("msg") == "success" and len(res["data"]) > 0:
            df_inst = pd.DataFrame(res["data"]).sort_values(by='date', ascending=False)
            latest_data = df_inst[df_inst['date'] == df_inst['date'].iloc[0]]
            buy_sum = sum(row['buy'] - row['sell'] for _, row in latest_data.iterrows() if any(n in row['name'] for n in ['外資', '投信']))
            return round(buy_sum / 1000)
    except: pass
    return 0

stock_dict = {
    "6823.TWO": "濾能", "2337.TW": "旺宏", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2409.TW": "友達", "3481.TW": "群創", "2330.TW": "台積電", "8299.TWO": "群聯",
    "3019.TW": "亞光", "2812.TW": "台中銀", "6770.TW": "力積電"
}

all_report = []
tw_now = get_taiwan_time()

for sid, sname in stock_dict.items():
    try:
        time.sleep(1.2)
        df = yf.download(sid, period="1y", progress=False)
        if df.empty:
            all_report.append(f"❌ {sname}({sid}) | 無資料")
            continue

        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['OSC'] = df['DIF'] - df['DIF'].ewm(span=9, adjust=False).mean()
        
        row, prev = df.iloc[-1], df.iloc[-2]
        buy = get_institutional_net_buy(sid)
        
        # 判定
        is_p = (row['OSC'] < 0) and (row['OSC'] > prev['OSC']) and (row['DIF'] > prev['DIF']) and (buy > 0)
        status = "📉收斂" if row['OSC'] < 0 and row['OSC'] > prev['OSC'] else "📈漲勢" if row['OSC'] > 0 else "⚠️擴大"
        
        res_icon = "🎯" if is_p else "⏸️"
        all_report.append(f"{res_icon} {sid.split('.')[0]} {sname} | {buy}張 | {status}")
    except Exception as e:
        all_report.append(f"❌ {sname} 異常: {str(e)[:20]}")

# 組合大訊息
msg = f"🛡️【強攻版診斷報告】\n時間: {tw_now.strftime('%H:%M')}\n" + "\n".join(all_report)
requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
