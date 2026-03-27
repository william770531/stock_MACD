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
    """【終極相容版】確保上市與上櫃法人資料都能正確抓取"""
    cid = sid.split('.')[0]
    start = (get_taiwan_time() - timedelta(days=10)).strftime("%Y-%m-%d")
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={cid}&start_date={start}&token={F_TOKEN}"
    
    f_buy, i_buy, total = 0, 0, 0
    last_date = "N/A"
    
    try:
        res = requests.get(url, timeout=15).json()
        data = res.get('data', [])
        if data:
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            ld_obj = df['date'].max()
            last_date = ld_obj.strftime('%m-%d')
            curr = df[df['date'] == ld_obj]
            
            for _, row in curr.iterrows():
                name = str(row.get('name', ''))
                # 換算為張數 (買進 - 賣出) / 1000
                net = (row.get('buy', 0) - row.get('sell', 0)) / 1000
                
                if "外資" in name:
                    f_buy += net
                elif "投信" in name:
                    i_buy += net
            
            f_buy = round(f_buy)
            i_buy = round(i_buy)
            total = f_buy + i_buy
    except:
        pass
    return total, f_buy, i_buy, last_date

# 監控清單
stocks = {
    "2330.TW": ("台積電", "權值"), "2337.TW": ("旺宏", "權值"), 
    "6770.TW": ("力積電", "權值"), "2408.TW": ("南亞科", "權值"), 
    "2344.TW": ("華邦電", "權值"), "2409.TW": ("友達", "權值"), 
    "3481.TW": ("群創", "權值"), "2812.TW": ("台中銀", "權值"),
    "6823.TWO": ("濾能", "小型"), "8299.TWO": ("群聯", "小型"), 
    "3019.TW": ("亞光", "小型")
}

report = [f"🚀 <b>【台股投資導航儀】</b>", f"📅 執行時間: {get_taiwan_time().strftime('%m/%d %H:%M')}", "═" * 18]

for sid, (sname, stype) in stocks.items():
    try:
        df = yf.download(sid, period="1y", progress=False)
        if df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標計算
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['OSC'] = (df['EMA12'] - df['EMA26']) - (df['EMA12'] - df['EMA26']).ewm(span=9, adjust=False).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        row, prev = df.iloc[-1], df.iloc[-2]
        total, f_buy, i_buy, b_date = get_net_buy_detail(sid)
        
        m_up = row['OSC'] > prev['OSC']
        is_ma = row['Close'] > row['MA20']
        
        # 建議標籤邏輯
        if stype == "權值":
            if f_buy > 100 and m_up:
                cmd, icon = "🟢 <b>建議跟單：外資回補</b>", "✅"
            elif f_buy < -300:
                cmd, icon = "🔴 <b>建議保守：外資撤出</b>", "❌"
            else:
                cmd, icon = "🟡 <b>維持觀望：籌碼待定</b>", "⏸️"
        else:
            if i_buy > 0 and m_up:
                cmd, icon = "🟢 <b>建議跟單：投信認養</b>", "✨"
            elif i_buy < 0:
                cmd, icon = "🔴 <b>建議保守：投信棄權</b>", "❌"
            else:
                cmd, icon = "🟡 <b>維持觀望：靜待表態</b>", "⏸️"

        report.append(f"{icon} <b>{sname}</b> ({b_date})")
        report.append(f" ├ 籌碼: {total}張 (外:{f_buy} | 投:{i_buy})")
        report.append(f" └ 🚩 <b>{cmd}</b>\n")
        
    except Exception as e:
        report.append(f"❌ {sname} 診斷出錯\n")

# 發送訊息
final_msg = "\n".join(report)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": final_msg, "parse_mode": "HTML"})
