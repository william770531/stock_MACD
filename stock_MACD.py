import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta, timezone

TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")
F_TOKEN = os.getenv("FINMIND_TOKEN")

def get_taiwan_time():
    return datetime.now(timezone(timedelta(hours=8)))

def get_net_buy_detail(sid):
    """拆解外資與投信籌碼"""
    cid = sid.split('.')[0]
    start = (get_taiwan_time() - timedelta(days=10)).strftime("%Y-%m-%d")
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={cid}&start_date={start}&token={F_TOKEN}"
    try:
        res = requests.get(url, timeout=15).json()
        if res.get('data'):
            df = pd.DataFrame(res['data']).sort_values('date', ascending=False)
            last_date = df['date'].iloc[0]
            last_d = df[df['date'] == last_date]
            
            f_buy = sum(r['buy']-r['sell'] for _, r in last_d.iterrows() if '外資' in r['name'])
            i_buy = sum(r['buy']-r['sell'] for _, r in last_d.iterrows() if '投信' in r['name'])
            total = round((f_buy + i_buy)/1000)
            return total, round(f_buy/1000), round(i_buy/1000), last_date
    except: pass
    return 0, 0, 0, "無資料"

# 監控清單 (定義類型)
stocks = {
    "2330.TW": ("台積電", "權值"), "2337.TW": ("旺宏", "權值"), 
    "6770.TW": ("力積電", "權值"), "2408.TW": ("南亞科", "權值"), 
    "2344.TW": ("華邦電", "權值"), "2409.TW": ("友達", "權值"), 
    "3481.TW": ("群創", "權值"), "2812.TW": ("台中銀", "權值"),
    "6823.TWO": ("濾能", "小型"), "8299.TWO": ("群聯", "小型"), 
    "3019.TW": ("亞光", "小型")
}

tw_now = get_taiwan_time()
report = [f"📊<b>【台股全景監控儀表板】</b>", f"🕒 時間: {tw_now.strftime('%m/%d %H:%M')}", "═" * 15]

for sid, (sname, stype) in stocks.items():
    try:
        df = yf.download(sid, period="1y", progress=False)
        if df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標計算 (MACD, MA20)
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['OSC'] = df['DIF'] - df['DIF'].ewm(span=9, adjust=False).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        row, prev = df.iloc[-1], df.iloc[-2]
        total, f_buy, i_buy, b_date = get_net_buy_detail(sid)
        
        # 狀態判定
        macd_safe = row['OSC'] > prev['OSC']
        above_ma20 = row['Close'] > row['MA20']
        
        # --- 分類建議邏輯 ---
        if stype == "權值":
            focus = f"外資:{f_buy}張"
            if f_buy > 500 and macd_safe:
                comment = "🚀 外資回補 + 動能轉強，偏多看"
            elif f_buy < -500:
                comment = "📉 外資提款中，暫避風頭"
            else:
                comment = "⏳ 權值股看外資臉色，目前觀望"
        else: # 中小型股
            focus = f"投信:{i_buy}張"
            if i_buy > 0 and macd_safe:
                comment = "🔥 投信認養中，中小型動能優"
            elif i_buy < 0 and not macd_safe:
                comment = "💀 投信棄養，小心多殺多"
            else:
                comment = "👀 關注投信是否連續買超"

        # 組合訊息
        icon = "🎯" if (macd_safe and total > 0 and above_ma20) else "⏸️"
        report.append(f"{icon} <b>{sid.split('.')[0]} {sname}</b> ({b_date[-5:]})")
        report.append(f" ├ 籌碼: {total}張 (外:{f_buy} | 投:{i_buy})")
        report.append(f" ├ 關鍵: {focus} | {comment}")
        report.append(f" └ 趨勢: {'✅站上月線' if above_ma20 else '❌破月線'}\n")
        
    except:
        report.append(f"❌ {sname} 偵測失敗\n")

final_msg = "\n".join(report)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": final_msg, "parse_mode": "HTML"})
