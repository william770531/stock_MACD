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

def get_net_buy_detail(sid):
    """【修正版】模糊比對法人名稱，確保抓到數字"""
    cid = sid.split('.')[0]
    start = (get_taiwan_time() - timedelta(days=10)).strftime("%Y-%m-%d")
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={cid}&start_date={start}&token={F_TOKEN}"
    try:
        res = requests.get(url, timeout=15).json()
        if res.get('data'):
            df = pd.DataFrame(res['data']).sort_values('date', ascending=False)
            last_date = df['date'].iloc[0]
            last_d = df[df['date'] == last_date]
            
            f_buy = 0
            i_buy = 0
            for _, row in last_d.iterrows():
                name = row['name']
                net_val = row['buy'] - row['sell']
                if '外資' in name:
                    f_buy += net_val
                elif '投信' in name:
                    i_buy += net_val
            
            total = round((f_buy + i_buy) / 1000)
            return total, round(f_buy / 1000), round(i_buy / 1000), last_date
    except Exception as e:
        print(f"DEBUG: {sid} 籌碼抓取失敗: {e}")
    return 0, 0, 0, "無資料"

# 監控清單 (權值 vs 小型)
stocks = {
    "2330.TW": ("台積電", "權值"), "2337.TW": ("旺宏", "權值"), 
    "6770.TW": ("力積電", "權值"), "2408.TW": ("南亞科", "權值"), 
    "2344.TW": ("華邦電", "權值"), "2409.TW": ("友達", "權值"), 
    "3481.TW": ("群創", "權值"), "2812.TW": ("台中銀", "權值"),
    "6823.TWO": ("濾能", "小型"), "8299.TWO": ("群聯", "小型"), 
    "3019.TW": ("亞光", "小型")
}

tw_now = get_taiwan_time()
report = [f"📊<b>【台股精準監控儀表板】</b>", f"🕒 時間: {tw_now.strftime('%m/%d %H:%M')}", "═" * 15]

for sid, (sname, stype) in stocks.items():
    try:
        df = yf.download(sid, period="1y", progress=False)
        if df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['OSC'] = df['DIF'] - df['DIF'].ewm(span=9, adjust=False).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        row, prev = df.iloc[-1], df.iloc[-2]
        total, f_buy, i_buy, b_date = get_net_buy_detail(sid)
        
        macd_safe = row['OSC'] > prev['OSC']
        above_ma20 = row['Close'] > row['MA20']
        
        # --- 分類與建議邏輯 ---
        if stype == "權值":
            focus_val = f_buy
            focus_name = "外資"
            if f_buy > 200 and macd_safe:
                comment = "🚀 外資買盤進場，趨勢偏多"
            elif f_buy < -500:
                comment = "📉 外資持續提款，建議觀望"
            else:
                comment = "⏳ 權值看外資，目前動能不足"
        else: # 小型
            focus_val = i_buy
            focus_name = "投信"
            if i_buy > 0 and macd_safe:
                comment = "🔥 投信認養中，具備噴發潛力"
            elif i_buy < 0:
                comment = "💀 投信拋售，避開高位股"
            else:
                comment = "👀 靜待投信表態認養"

        # 組合
        icon = "🎯" if (macd_safe and total > 0 and above_ma20) else "⏸️"
        report.append(f"{icon} <b>{sid.split('.')[0]} {sname}</b> ({b_date[-5:]})")
        report.append(f" ├ 籌碼: {total}張 (外:{f_buy} | 投:{i_buy})")
        report.append(f" ├ 重點: {focus_name} {focus_val}張 | {comment}")
        report.append(f" └ 趨勢: {'✅站上月線' if above_ma20 else '❌破月線'}\n")
        
    except:
        report.append(f"❌ {sname} 偵測失敗\n")

final_msg = "\n".join(report)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": final_msg, "parse_mode": "HTML"})
