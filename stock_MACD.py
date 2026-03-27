import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta, timezone

# 讀取 GitHub Secrets
TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")
F_TOKEN = os.getenv("FINMIND_TOKEN")

def get_taiwan_time():
    return datetime.now(timezone(timedelta(hours=8)))

def get_net_buy_detail(sid):
    """抓取法人詳細籌碼"""
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
                net = (row.get('buy', 0) - row.get('sell', 0)) / 1000
                if any(k in name for k in ["外資", "Foreign"]): f_buy += net
                elif any(k in name for k in ["投信", "Investment"]): i_buy += net
            f_buy, i_buy = round(f_buy), round(i_buy)
            total = f_buy + i_buy
    except: pass
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

report = [f"🔥 <b>【台股盤前 AI 強勢導航】</b>", f"🕒 {get_taiwan_time().strftime('%m/%d %H:%M')}", "═" * 18]

for sid, (sname, stype) in stocks.items():
    try:
        df = yf.download(sid, period="1y", progress=False)
        if df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # --- 技術指標計算 ---
        # 1. MACD
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['OSC'] = df['DIF'] - df['DEA']
        
        # 2. KD (9, 3, 3)
        df['L9'] = df['Low'].rolling(window=9).min()
        df['H9'] = df['High'].rolling(window=9).max()
        df['RSV'] = 100 * (df['Close'] - df['L9']) / (df['H9'] - df['L9'])
        df['K'] = df['RSV'].ewm(alpha=1/3, adjust=False).mean()
        df['D'] = df['K'].ewm(alpha=1/3, adjust=False).mean()
        
        # 3. 成交量均量
        df['V_MA5'] = df['Volume'].rolling(window=5).mean()
        
        row, prev = df.iloc[-1], df.iloc[-2]
        total, f_buy, i_buy, b_date = get_net_buy_detail(sid)
        
        # --- 狀態判定 ---
        # MACD & KD 訊號
        kd_cross = "✨KD金叉" if row['K'] > row['D'] and prev['K'] <= prev['D'] else ""
        vol_up = "🔥爆量" if row['Volume'] > row['V_MA5'] * 1.5 else ""
        m_txt = f"{'🔴紅' if row['OSC'] > 0 else '🟢綠'} {'增長' if row['OSC'] > prev['OSC'] else '縮短'}"
        
        # 綜合建議邏輯
        m_up = row['OSC'] > prev['OSC']
        
        if stype == "權值":
            if f_buy > 200 and m_up: 
                cmd, icon = "🟢 <b>建議跟單：外資點火</b>", "✅"
            elif f_buy < -500: 
                cmd, icon = "🔴 <b>建議保守：法人撤離</b>", "❌"
            else: 
                cmd, icon = "🟡 <b>維持觀望：動能蓄勢</b>", "⏸️"
        else: # 小型
            if i_buy > 0 and m_up: 
                cmd, icon = "🟢 <b>建議跟單：投信佈局</b>", "✨"
            elif i_buy < 0: 
                cmd, icon = "🔴 <b>建議保守：籌碼鬆動</b>", "❌"
            else: 
                cmd, icon = "🟡 <b>維持觀望：靜待認養</b>", "⏸️"

        # 輸出格式
        report.append(f"{icon} <b>{sname}</b> ({b_date})")
        report.append(f" ├ 籌碼: <code>{total:+}張</code> (外:{f_buy:+} | 投:{i_buy:+})")
        report.append(f" ├ 指標: {m_txt} {kd_cross} {vol_up}")
        report.append(f" └ 🚩 {cmd}\n")
    except:
        report.append(f"❌ {sname} 偵測失敗\n")

requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": "\n".join(report), "parse_mode": "HTML"})
