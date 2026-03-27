# --- 自動化建議邏輯 (Comment) ---
        if is_ready and buy_vol > 0:
            comment = "🎯 完美打底：建議進場/加碼"
        elif row['OSC'] < 0 and row['OSC'] > prev['OSC']:
            comment = "👀 跌勢收斂：列入觀察，等外資轉買"
        elif row['Close'] > row['MA20'] and row['OSC'] > 0:
            comment = "📈 強勢續漲：持股續抱，不宜追高"
        elif row['OSC'] < prev['OSC'] and row['Close'] < row['MA20']:
            comment = "⚠️ 趨勢轉弱：建議減碼或觀望"
        else:
            comment = "⏳ 盤整階段：耐心等待轉折訊號"

        # --- 組合訊息 ---
        icon = "🎯" if is_ready and buy_vol > 0 else "⏸️"
        report.append(f"{icon} <b>{sid.split('.')[0]} {sname}</b> ({buy_date[-5:]})")
        report.append(f" ├ 籌碼: {buy_vol}張 | 動能: {macd_status}")
        report.append(f" ├ 趨勢: {ma20_status} | KD: {kd_status} | {vol_status}")
        report.append(f" └ <b>💡 建議: {comment}</b>\n")
