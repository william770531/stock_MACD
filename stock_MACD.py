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
    """【強化版】確保抓到非零籌碼"""
    cid = sid.split('.')[0]
    start = (get_taiwan_time() - timedelta(days=10)).strftime("%Y-%m-%d")
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={cid}&start_date={start}&token={F_TOKEN}"
    try:
        res = requests.get(url, timeout=15).json()
        if res.get('data'):
            df = pd.DataFrame(res['data']).sort_values('date', ascending=False)
            last_date = df['date'].iloc[0]
            last_d = df[df['date'] == last_date]
            # 擴大比對範圍：包含所有法人單位
            buy = sum(r['buy']-r['sell'] for _, r in last_d.iterrows())
            return round(buy/1000), last_date
    except: pass
    return 0, "無資料"

stocks = {
    "6823.TWO": "濾能", "2330.TW": "台積電", "2337.TW": "旺宏", 
    "6770.TW": "力積電", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2409.TW": "友達", "3481.TW": "群創", "8299.TWO": "群聯", 
    "3019.TW": "亞光", "2812.TW": "台中銀"
}

tw_now = get_taiwan_time()
report = [f"📊<b>【台股強勢選股儀表板】</b>", f"🕒 時間: {tw_now.strftime('%m/%d %H:%M')}", "═" * 15]

for sid, sname in stocks.items():
    try:
        df = yf.download(sid, period="1y", progress=False)
        if df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # --- 指標計算 ---
        # MACD
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['OSC'] = df['DIF'] - df['DIF'].ewm(span=9, adjust=False).mean()
        # MA & 布林通道
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['STD'] = df['Close'].rolling(window=20).std()
        df['Lower'] = df['MA20'] - (df['STD'] * 2) # 布林下軌
        # 量能
        df['V_MA5'] = df['Volume'].rolling(window=5).mean()
        
        row, prev = df.iloc[-1], df.iloc[-2]
        buy_vol, buy_date = get_net_buy(sid)
        
        # --- 邏輯判定 ---
        is_macd_safe = row['OSC'] > prev['OSC'] # 負值縮短或正值增長
        is_oversold = row['Close'] < row['Lower'] # 股價低於布林下軌 (超跌)
        is_vol_up = row['Volume'] > df['V_MA5'].iloc[-1] * 1.5 # 成交量爆發
        
        # --- 💡 建議邏輯升級 ---
        if is_macd_safe and buy_vol > 0 and row['Close'] > row['MA20']:
            comment = "🎯 完美多頭：趨勢確立，分批進場"
        elif is_oversold and is_macd_safe:
            comment = "🔥 超跌反彈：觸及底線，短線機會"
        elif is_vol_up and buy_vol > 0:
            comment = "⚡ 異常大量：大戶進場點火，關注"
        elif row['OSC'] < prev['OSC'] and row['Close'] < row['MA20']:
            comment = "⚠️ 破線轉弱：避開落水狗，觀望"
        else:
            comment = "⏳ 盤整蓄勢：等待指標共振"

        # --- 狀態圖示 ---
        icon = "🎯" if (is_macd_safe and buy_vol > 0) else "⏸️"
        macd_txt = "📈收斂/擴大" if row['OSC'] > prev['OSC'] else "📉轉弱"
        
        report.append(f"{icon} <b>{sid.split('.')[0]} {sname}</b> ({buy_date[-5:]})")
        report.append(f" ├ 籌碼: {buy_vol}張 | 動能: {macd_txt}")
        report.append(f" └ <b>💡 建議: {comment}</b>\n")
        
    except:
        report.append(f"❌ {sname} 偵測失敗\n")

final_msg = "\n".join(report)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": final_msg, "parse_mode": "HTML"})
