import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta, timezone

# 讀取 Secret
TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")
F_TOKEN = os.getenv("FINMIND_TOKEN")

def get_taiwan_time():
    return datetime.now(timezone(timedelta(hours=8)))

def get_net_buy(sid):
    cid = sid.split('.')[0]
    # 抓過去 10 天，確保避開週末
    start = (get_taiwan_time() - timedelta(days=10)).strftime("%Y-%m-%d")
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={cid}&start_date={start}&token={F_TOKEN}"
    try:
        res = requests.get(url).json()
        if res.get('data'):
            df = pd.DataFrame(res['data']).sort_values('date', ascending=False)
            last_date = df['date'].iloc[0]
            last_d = df[df['date'] == last_date]
            # 修正：更寬鬆的法人名稱比對
            buy = sum(r['buy']-r['sell'] for _, r in last_d.iterrows() if '外資' in r['name'] or '投信' in r['name'])
            return f"{round(buy/1000)}張", last_date
    except: pass
    return "0張", "查無日期"

# 換回你原本想監控的所有清單
stocks = {
    "6823.TWO": "濾能", "2330.TW": "台積電", "2337.TW": "旺宏", 
    "6770.TW": "力積電", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2409.TW": "友達", "3481.TW": "群創", "8299.TWO": "群聯", 
    "3019.TW": "亞光", "2812.TW": "台中銀"
}

report = [f"📊【台股監控儀表板】{get_taiwan_time().strftime('%m/%d %H:%M')}"]

for sid, sname in stocks.items():
    try:
        df = yf.download(sid, period="1y", progress=False)
        if df.empty: continue
        
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標計算
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['OSC'] = df['DIF'] - df['DIF'].ewm(span=9, adjust=False).mean()
        
        row, prev = df.iloc[-1], df.iloc[-2]
        buy_vol, buy_date = get_net_buy(sid)
        
        # 判定 MACD 打底 (OSC 負值縮短且 DIF 翻揚)
        is_ready = (row['OSC'] < 0) and (row['OSC'] > prev['OSC']) and (row['DIF'] > prev['DIF'])
        
        icon = "✅" if (is_ready and int(buy_vol.replace('張','')) > 0) else "⏸️"
        report.append(f"{icon} {sid.split('.')[0]} {sname} | {buy_vol} | {buy_date[-5:]}")
    except:
        report.append(f"❌ {sname} 偵測異常")

requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": "\n".join(report)})
