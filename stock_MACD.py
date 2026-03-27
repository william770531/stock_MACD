import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta, timezone

# 讀取 Secret
TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")
F_TOKEN = os.getenv("FINMIND_TOKEN")

def get_net_buy(sid):
    """抓取最近有資料的法人買賣"""
    cid = sid.split('.')[0]
    start = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=14)).strftime("%Y-%m-%d")
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={cid}&start_date={start}&token={F_TOKEN}"
    try:
        data = requests.get(url).json()['data']
        if data:
            df = pd.DataFrame(data).sort_values('date', ascending=False)
            last_d = df[df['date'] == df['date'].iloc[0]]
            buy = sum(r['buy']-r['sell'] for _, r in last_d.iterrows() if any(n in r['name'] for n in ['外資','投信']))
            return f"{round(buy/1000)}張({df['date'].iloc[0]})"
    except: pass
    return "0張(無資料)"

stocks = {"6823.TWO":"濾能", "2330.TW":"台積電", "2337.TW":"旺宏", "6770.TW":"力積電"}
report = [f"🔍 深度檢測報告 | Token:{'有' if F_TOKEN else '無'}"]

for sid, sname in stocks.items():
    try:
        df = yf.download(sid, period="1mo", progress=False)
        if df.empty:
            report.append(f"❌ {sname} | yf抓不到資料")
            continue
        buy_info = get_net_buy(sid)
        report.append(f"✅ {sname}({sid}) | 籌碼:{buy_info}")
    except Exception as e:
        report.append(f"❌ {sname} 錯誤:{str(e)[:15]}")

requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": "\n".join(report)})
