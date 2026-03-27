import yfinance as yf
import pandas as pd
import requests
import os
import time
from datetime import datetime, timedelta, timezone

# 🔑 讀取 GitHub Secrets
TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")
F_TOKEN = os.getenv("FINMIND_TOKEN")

def get_taiwan_time():
    return datetime.now(timezone(timedelta(hours=8)))

def get_net_buy(sid):
    """抓取法人籌碼 (若當日沒資料會往前抓 10 天)"""
    cid = sid.split('.')[0]
    start = (get_taiwan_time() - timedelta(days=10)).strftime("%Y-%m-%d")
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={cid}&start_date={start}&token={F_TOKEN}"
    try:
        res = requests.get(url, timeout=15).json()
        if res.get('data'):
            df = pd.DataFrame(res['data']).sort_values('date', ascending=False)
            last_date = df['date'].iloc[0]
            last_d = df[df['date'] == last_date]
            buy = sum(r['buy']-r['sell'] for _, r in last_d.iterrows() if any(n in r['name'] for n in ['外資', '投信', '自營']))
            return round(buy/1000), last_date
    except: pass
    return 0, "無資料"

# 監控清單
stocks = {
    "6823.TWO": "濾能", "2330.TW": "台積電", "2337.TW": "旺宏", 
    "6770.TW": "力積電", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2409.TW": "友達", "3481.TW": "群創", "8299.TWO": "群聯", 
    "3019.TW": "亞光", "2812.TW": "台中銀"
}

tw_now = get_taiwan_time()
report = [f"📊<b>【台股全景監控儀表板】</b>", f"🕒 時間: {tw_now.strftime('%m/%d %H:%M')}", "═" * 15]

for sid, sname in stocks.items():
    try:
        df = yf.download(sid, period="1y", progress=False)
        if df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # --- 指標計算 ---
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['MACD_L'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['OSC'] = df['DIF'] - df['MACD_L']
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['V_MA5'] = df['Volume'].rolling(window=5).mean()
        
        # KD
        df['L9'] = df['Low'].rolling(window=9).min()
        df['H9'] = df['High'].rolling(window=9).max()
        df['RSV'] = 100 * (df['Close'] - df['L9']) / (df['H9'] - df['L9'])
        df['K'] = df['RSV'].ewm(alpha=1/3, adjust=False).mean()
        df['D'] = df['K'].ewm(alpha=1/3, adjust=False).mean()

        row, prev = df.iloc[-1], df.iloc[-2]
        buy_vol, buy_date = get_net_buy(sid)
        
        # --- 狀態判定 ---
        # MACD 狀態
        if row['OSC'] < 0:
            macd_status = "📉跌勢收斂" if row['OSC'] > prev['OSC'] else "⚠️跌勢擴大"
        else:
            macd_status = "📈漲勢擴大" if row['OSC'] > prev['OSC'] else "⚠️漲勢收斂"
            
        ma20_status = "✅站上" if row['Close'] > row['MA20'] else "❌破線"
        vol_status = "🔥出量" if row['Volume'] > row['V_MA5'] else "量縮"
        
        kd_status = "低" if row['K'] < 30 else "高" if row['K'] > 70 else "中"
        if row['K'] > row['D'] and prev['K'] <= prev['D']: kd_status += "(✨金叉)"

        # 判定是否為「完美打底股」
        is_ready = (row['OSC'] < 0) and (row['OSC'] > prev['OSC']) and (row['DIF'] > prev['DIF']) and (buy_vol > 0)
        icon = "🎯" if is_ready else "⏸️"

        # --- 組合訊息 ---
        report.append(f"{icon} <b>{sid.split('.')[0]} {sname}</b> ({buy_date[-5:]})")
        report.append(f" ├ 籌碼: {buy_vol}張 | 動能: {macd_status}")
        report.append(f" └ 趨勢: {ma20_status} | KD: {kd_status} | {vol_status}\n")
        
    except Exception as e:
        report.append(f"❌ {sname} 偵測失敗: {str(e)[:15]}\n")

# 發送訊息
final_msg = "\n".join(report)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": final_msg, "parse_mode": "HTML"})
