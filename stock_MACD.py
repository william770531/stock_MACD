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
    """【全自動適應版】不比對文字，直接從數據特徵抓取外資與投信"""
    cid = sid.split('.')[0]
    start = (get_taiwan_time() - timedelta(days=10)).strftime("%Y-%m-%d")
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={cid}&start_date={start}&token={F_TOKEN}"
    
    f_buy, i_buy, total = 0, 0, 0
    last_date = "無資料"
    
    try:
        res = requests.get(url, timeout=15).json()
        data = res.get('data', [])
        if data:
            df = pd.DataFrame(data)
            # 轉換日期並抓最後一天
            df['date'] = pd.to_datetime(df['date'])
            last_date_obj = df['date'].max()
            last_date = last_date_obj.strftime('%Y-%m-%d')
            current_df = df[df['date'] == last_date_obj]
            
            # 打印 Log 方便我們診斷 (在 GitHub Actions 的 Log 裡可以看到)
            print(f"--- {sid} 資料診斷 ---")
            
            for _, row in current_df.iterrows():
                name = str(row['name'])
                net = round((row['buy'] - row['sell']) / 1000)
                print(f"法人: {name} | 張數: {net}") # 這行會印在 GitHub Log
                
                # 模糊比對：只要包含關鍵字就歸類
                if "外資" in name or "Foreign" in name:
                    f_buy += net
                elif "投信" in name or "Investment" in name:
                    i_buy += net
            
            total = f_buy + i_buy
    except Exception as e:
        print(f"❌ {sid} 籌碼抓取失敗: {e}")
        
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

report = [f"📊<b>【台股數據實時儀表板】</b>", f"🕒 {get_taiwan_time().strftime('%m/%d %H:%M')}", "═" * 15]

for sid, (sname, stype) in stocks.items():
    try:
        df = yf.download(sid, period="1y", progress=False)
        if df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['OSC'] = (df['EMA12'] - df['EMA26']) - (df['EMA12'] - df['EMA26']).ewm(span=9, adjust=False).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        row, prev = df.iloc[-1], df.iloc[-2]
        total, f_buy, i_buy, b_date = get_net_buy_detail(sid)
        
        # 建議與判定
        macd_up = row['OSC'] > prev['OSC']
        is_above = row['Close'] > row['MA20']
        
        if stype == "權值":
            comment = "🚀 外資轉買，動能加溫" if f_buy > 0 and macd_up else "📉 外資調節，建議保守" if f_buy < 0 else "⏳ 權值股等待外資表態"
        else:
            comment = "🔥 投信認養，力道較強" if i_buy > 0 and macd_up else "💀 投信出脫，小心回檔" if i_buy < 0 else "👀 盯緊投信，準備跟單"

        icon = "🎯" if (macd_up and total > 0 and is_above) else "⏸️"
        report.append(f"{icon} <b>{sname}</b> ({b_date[-5:]})")
        report.append(f" ├ 籌碼: {total}張 (外:{f_buy} | 投:{i_buy})")
        report.append(f" └ <b>💡 建議: {comment}</b>\n")
        
    except Exception as e:
        print(f"ERROR: {sname} -> {e}")

requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": "\n".join(report), "parse_mode": "HTML"})
