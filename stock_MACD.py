import yfinance as yf
import pandas as pd
import requests
import os
import time
from datetime import datetime, timedelta, timezone

TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")
F_TOKEN = os.getenv("FINMIND_TOKEN")

def get_taiwan_time():
    return datetime.now(timezone(timedelta(hours=8)))

def get_net_buy(sid):
    """加強版籌碼抓取：增加重試邏輯"""
    cid = sid.split('.')[0]
    start = (get_taiwan_time() - timedelta(days=10)).strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id": cid,
        "start_date": start,
        "token": F_TOKEN
    }
    
    for _ in range(2): # 失敗會重試一次
        try:
            res = requests.get(url, params=params, timeout=15).json()
            if res.get('data'):
                df = pd.DataFrame(res['data']).sort_values('date', ascending=False)
                last_date = df['date'].iloc[0]
                last_d = df[df['date'] == last_date]
                # 同時檢查 外資、投信、自營商
                buy = sum(r['buy']-r['sell'] for _, r in last_d.iterrows() if any(n in r['name'] for n in ['外資', '投信', '自營']))
                return round(buy/1000), last_date
            time.sleep(1)
        except:
            time.sleep(1)
    return 0, "無資料"

stocks = {
    "6823.TWO": "濾能", "2330.TW": "台積電", "2337.TW": "旺宏", 
    "6770.TW": "力積電", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2409.TW": "友達", "3481.TW": "群創", "8299.TWO": "群聯", 
    "3019.TW": "亞光", "2812.TW": "台中銀"
}

tw_now = get_taiwan_time()
report = [f"📊<b>【台股監控儀表板】</b>", f"🕒 時間: {tw_now.strftime('%m/%d %H:%M')}", "═" * 15]

for sid, sname in stocks.items():
    try:
        # yfinance 抓取
        df = yf.download(sid, period="1y", progress=False)
        if df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['OSC'] = df['DIF'] - df['DIF'].ewm(span=9, adjust=False).mean()
        
        row, prev = df.iloc[-1], df.iloc[-2]
        buy_vol, buy_date = get_net_buy(sid)
        
        # 判定
        is_ready = (row['OSC'] < 0) and (row['OSC'] > prev['OSC']) and (row['DIF'] > prev['DIF'])
        status = "📉收斂" if row['OSC'] < 0 and row['OSC'] > prev['OSC'] else "📈漲勢" if row['OSC'] > 0 else "⚠️擴大"
        icon = "✅" if (is_ready and buy_vol > 0) else "⏸️"
        
        # 格式優化：顯示股票代號與日期
        report.append(f"{icon} {sid.split('.')[0]} {sname} | {buy_vol}張 | {status}")
    except:
        report.append(f"❌ {sname} 偵測失敗")

# 發送訊息
final_msg = "\n".join(report)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": final_msg, "parse_mode": "HTML"})
