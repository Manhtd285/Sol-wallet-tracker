import sqlite3
import json
from datetime import datetime, timedelta, timezone

# ==============================
# ⚙️ CẤU HÌNH
# ==============================
DB_FILE = "solana_trading5.db"
OUTPUT_FILE = "sp1_transactions_export.jsonl"
TARGET_WALLET = "Ar2Y6o1QmrRAskjii1cRfijeKugHH13ycxW5cd7rro1x"

# Mốc thời gian bắt đầu: 01/11/2025 (Giờ Việt Nam)
VN_TIMEZONE = timezone(timedelta(hours=7))
START_DATE_STR = "2025-11-01 00:00:00"

# [QUAN TRỌNG] Mặc định số thập phân của Token là 6 (Chuẩn SPL Token thông thường)
DEFAULT_DECIMALS = 6 

def export_transactions_jsonl():
    print(f"🚀 Bắt đầu export giao dịch ví {TARGET_WALLET[:6]}... từ {START_DATE_STR}")

    # 1. Tính toán Timestamp bắt đầu
    start_dt = datetime.strptime(START_DATE_STR, "%Y-%m-%d %H:%M:%S")
    start_ts = start_dt.replace(tzinfo=VN_TIMEZONE).timestamp()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 2. Query dữ liệu (ĐÃ SỬA: Chỉ lấy từ bảng trades, bỏ JOIN tokens)
    query = '''
        SELECT 
            signer, 
            signature, 
            swap_type, 
            token_mint, 
            sol_amount, 
            token_amount, 
            block_time
        FROM trades 
        WHERE signer = ? AND block_time >= ?
        ORDER BY block_time ASC
    '''

    try:
        cursor.execute(query, (TARGET_WALLET, start_ts))
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"❌ Lỗi SQL: {e}")
        conn.close()
        return
    
    print(f"🔍 Tìm thấy {len(rows)} giao dịch.")

    if not rows:
        print("⚠️ Không có dữ liệu để export.")
        conn.close()
        return

    # 3. Ghi file JSON Lines
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for row in rows:
            signer, signature, swap_type, token_mint, sol_amt, token_amt, block_time = row

            # --- Xử lý dữ liệu ---
            
            # 1. Timestamp: Convert giây -> mili-giây
            ts_ms = int(block_time * 1000)

            # 2. Lamport: Sol * 10^9 (làm tròn thành int)
            lamport_val = int(sol_amt * 1_000_000_000)

            # 3. Token Raw Amount: Token * 10^6 (Mặc định)
            # Vì DB thiếu cột decimals nên ta dùng mặc định là 6
            raw_amount_val = int(token_amt * (10 ** DEFAULT_DECIMALS))

            # Tạo dictionary
            record = {
                "signer": signer,
                "signature": signature,
                "type": swap_type,
                "token": token_mint,
                "lamport": lamport_val,
                "amount": raw_amount_val,
                "timestamp": ts_ms
            }

            # Ghi dòng JSON vào file
            f.write(json.dumps(record) + "\n")

    conn.close()
    print(f"✅ Đã xuất xong file: {OUTPUT_FILE}")
    
    # In check
    print("\n--- SAMPLE OUTPUT (First 3 lines) ---")
    try:
        with open(OUTPUT_FILE, 'r') as f:
            for _ in range(3):
                line = f.readline()
                if line:
                    print(line.strip())
    except FileNotFoundError:
        pass

if __name__ == "__main__":
    export_transactions_jsonl()