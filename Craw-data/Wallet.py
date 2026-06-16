import sqlite3
import csv
import uuid
from datetime import datetime, timedelta, timezone

# ==============================
# ⚙️ CẤU HÌNH
# ==============================
DB_FILE = "solana_trading5.db"
OUTPUT_CSV = "wallet_SP1-2-3.csv"
VN_TIMEZONE = timezone(timedelta(hours=7))

RESET_MIN_SELL_COUNT = 5
RESET_MAX_DURATION = 120 # giây
TOKEN_BALANCE_TOLERANCE = 10 

# ==============================
# 1. TÌM ĐIỂM RESET CHO 1 VÍ CỤ THỂ
# ==============================
def find_reset_t0_for_wallet(cursor, wallet_address):
    """
    Tìm điểm reset (xả hàng) sớm nhất của MỘT ví cụ thể.
    """
    cursor.execute('''
        SELECT swap_type, block_time 
        FROM trades WHERE signer = ? ORDER BY block_time ASC
    ''', (wallet_address,))
    txs = cursor.fetchall()
    
    current_seq = []
    earliest_reset_end_ts = None

    # Logic tìm Reset
    for tx in txs:
        if tx[0] == 'SELL':
            current_seq.append(tx)
        else:
            if current_seq:
                count = len(current_seq)
                duration = current_seq[-1][1] - current_seq[0][1]
                if count >= RESET_MIN_SELL_COUNT and duration <= RESET_MAX_DURATION:
                    reset_end_ts = current_seq[-1][1]
                    if earliest_reset_end_ts is None or reset_end_ts < earliest_reset_end_ts:
                        earliest_reset_end_ts = reset_end_ts
                current_seq = []
    
    # Check lần cuối
    if current_seq:
        count = len(current_seq)
        duration = current_seq[-1][1] - current_seq[0][1]
        if count >= RESET_MIN_SELL_COUNT and duration <= RESET_MAX_DURATION:
            reset_end_ts = current_seq[-1][1]
            if earliest_reset_end_ts is None or reset_end_ts < earliest_reset_end_ts:
                earliest_reset_end_ts = reset_end_ts

    return earliest_reset_end_ts

# ==============================
# 2. XỬ LÝ CYCLE CHO 1 VÍ
# ==============================
def analyze_cycles_for_wallet(cursor, wallet_address, t0_timestamp):
    """
    Phân tích cycle cho 1 ví cụ thể tính từ sau T0.
    Cập nhật: Cycle ID sinh theo format {WalletPrefix}_{TokenPrefix}_{FirstTxTime}
    """
    print(f"   -> Đang phân tích ví {wallet_address[:6]}... từ mốc {datetime.fromtimestamp(t0_timestamp, VN_TIMEZONE)}")
    
    cursor.execute('''
        SELECT DISTINCT token_mint FROM trades 
        WHERE signer = ? AND block_time > ?
    ''', (wallet_address, t0_timestamp))
    tokens = [row[0] for row in cursor.fetchall()]

    wallet_report_rows = []

    for token_mint in tokens:
        # Lấy metadata token (như cũ)
        cursor.execute('SELECT * FROM tokens WHERE mint = ?', (token_mint,))
        token_meta = cursor.fetchone()
        if token_meta:
            created_at_fmt = token_meta[4] if len(token_meta) > 4 else "N/A"
            graduated_at_fmt = token_meta[7] if len(token_meta) > 7 else "N/A"
        else:
            created_at_fmt = "N/A"
            graduated_at_fmt = "N/A"

        cursor.execute('''
            SELECT * FROM trades 
            WHERE signer = ? AND token_mint = ? AND block_time > ? 
            ORDER BY block_time ASC
        ''', (wallet_address, token_mint, t0_timestamp))
        
        columns = [column[0] for column in cursor.description]
        trades = [dict(zip(columns, row)) for row in cursor.fetchall()]

        current_cycle_rows = []
        token_balance = 0.0
        
        # [THAY ĐỔI 1] Khởi tạo là None, chưa sinh ID vội
        current_cycle_id = None 

        for trade in trades:
            # [THAY ĐỔI 2] Nếu chưa có ID (tức là đây là giao dịch đầu tiên của cycle), thì sinh ID mới
            if current_cycle_id is None:
                # Format: Wallet6_Token6_TimestampMillis
                # trade['block_time'] thường là giây, nhân 1000 để ra mili-giây như ví dụ của bạn
                w_prefix = wallet_address[:6]
                t_prefix = token_mint[:6]
                ts_ms = int(trade['block_time'] * 1000) 
                current_cycle_id = f"{w_prefix}_{t_prefix}_{ts_ms}"

            is_buy = trade['swap_type'] == 'BUY'
            token_amt = float(trade['token_amount'])
            sol_amt = float(trade['sol_amount'])

            if is_buy:
                token_change = token_amt
                sol_change = -sol_amt
            else:
                token_change = -token_amt
                sol_change = sol_amt

            token_balance += token_change
            
            row_data = {
                "Wallet": wallet_address,
                "cycle_id": current_cycle_id, # Sử dụng ID vừa sinh
                "Token": token_mint,
                "Token created time": created_at_fmt,
                "Token graduated time": graduated_at_fmt,
                "Signature": trade['signature'],
                "Transaction Time": datetime.fromtimestamp(trade['block_time'], VN_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S'),
                "Type": trade['swap_type'],
                "Sol change": sol_change,
                "Token change": token_change
            }
            current_cycle_rows.append(row_data)

            # --- Logic FIFO Check ---
            # 1. Âm balance -> Token tồn từ trước -> Bỏ cycle
            if token_balance < -TOKEN_BALANCE_TOLERANCE:
                current_cycle_rows = []
                token_balance = 0.0
                current_cycle_id = None # [THAY ĐỔI 3] Reset về None để cycle sau tự sinh ID mới
                continue

            # 2. Balance về 0 -> Đóng cycle
            if abs(token_balance) < TOKEN_BALANCE_TOLERANCE and len(current_cycle_rows) > 0:
                wallet_report_rows.extend(current_cycle_rows)
                
                # Reset
                current_cycle_rows = []
                token_balance = 0.0
                current_cycle_id = None # [THAY ĐỔI 4] Reset về None

    return wallet_report_rows

# ==============================
# 3. MAIN LOOP & EXPORT
# ==============================
def process_all_wallets():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    print("🚀 Bắt đầu quét Multi-Wallet...")
    
    cursor.execute("SELECT DISTINCT signer FROM trades")
    wallets = [row[0] for row in cursor.fetchall()]
    print(f"🔍 Tìm thấy {len(wallets)} ví trong Database.\n")

    all_data = []

    for wallet in wallets:
        # Tìm điểm Reset T0
        t0 = find_reset_t0_for_wallet(cursor, wallet)
        
        # [THAY ĐỔI] Logic chọn điểm bắt đầu
        start_time = 0 
        status_msg = ""
        
        if t0:
            start_time = t0
            fmt_time = datetime.fromtimestamp(t0, VN_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
            status_msg = f"Từ mốc Reset ({fmt_time})"
        else:
            start_time = 0 # Unix timestamp 0 (năm 1970) -> Lấy hết từ đầu
            status_msg = "Không có Reset -> Lấy TỪ ĐẦU"

        print(f"   👉 Ví {wallet[:6]}...: {status_msg}")

        # Gọi hàm phân tích với start_time đã chọn
        cycles = analyze_cycles_for_wallet(cursor, wallet, start_time)
        
        if cycles:
            all_data.extend(cycles)
            print(f"      ✅ Ghi nhận {len(cycles)} dòng giao dịch hợp lệ.")
        else:
            print(f"      ⚠️ Không tìm thấy chu trình (Cycle) nào hợp lệ.")

    conn.close()
    
    # Xuất CSV
    if all_data:
        headers = [
            "Wallet", "cycle_id", "Token", "Token created time", "Token graduated time", 
            "Signature", "Transaction Time", "Type", "Sol change", "Token change"
        ]
        with open(OUTPUT_CSV, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_data)
        print(f"\n🏁 HOÀN TẤT! File báo cáo: {OUTPUT_CSV}")
    else:
        print("\n❌ Không có dữ liệu nào để xuất báo cáo.")

if __name__ == "__main__":
    process_all_wallets()