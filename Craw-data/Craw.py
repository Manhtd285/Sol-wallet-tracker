import sqlite3
import requests
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from requests.exceptions import ConnectionError, Timeout, ChunkedEncodingError, ReadTimeout

# ==============================
# ⚙️ CẤU HÌNH
# ==============================
HELIUS_API_KEY = "8de5342b-96b1-42d8-961f-2d8c39611d37" 
TARGET_WALLETS = [
     "Ar2Y6o1QmrRAskjii1cRfijeKugHH13ycxW5cd7rro1x",# SP1
    "7BNaxx6KdUYrjACNQZ9He26NBFoFxujQMAfNLnArLGH5", # SP2
     "5aLY85pyxiuX3fd4RgM3Yc1e3MAL6b7UgaZz6MS3JUfG" # SP3
]
DB_FILE = "solana_trading5.db"
SOL_MINT = "So11111111111111111111111111111111111111112"
DAYS_AGO_DEFAULT = 30

HELIUS_BASE_URL = "https://api.helius.xyz/v0/addresses"

VN_TIMEZONE = timezone(timedelta(hours=7))

# ==============================
# 1. QUẢN LÝ DATABASE (CẬP NHẬT)
# ==============================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Bảng trades (Giữ nguyên)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        signature TEXT PRIMARY KEY,
        block_time INTEGER,
        human_time TEXT,
        signer TEXT,
        swap_type TEXT,
        token_mint TEXT,
        token_amount REAL,
        sol_amount REAL
    )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signer ON trades(signer)")
    
    # [CẬP NHẬT] Bảng tokens thêm cột 'graduated'
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tokens (
        mint TEXT PRIMARY KEY,
        symbol TEXT,
        name TEXT,
        created_at_ts INTEGER, 
        created_at_fmt TEXT,
        graduated INTEGER DEFAULT 0,  -- 0: Chưa, 1: Đã tốt nghiệp (Raydium)
        graduated_at_ts INTEGER DEFAULT NULL, -- Cột mới để lưu thời gian tốt nghiệp
        graduated_at_fmt TEXT DEFAULT NULL    -- Cột mới để lưu thời gian dạng đọc được
    )
    ''')
    
    conn.commit()
    conn.close()

# ==============================
# 2. HÀM GỌI DEXSCREENER (CẬP NHẬT LOGIC GRADUATED)
# ==============================

def fetch_token_metadata_dexscreener(mint_list):
    if not mint_list: return
    
    chunk_size = 30
    chunks = [mint_list[i:i + chunk_size] for i in range(0, len(mint_list), chunk_size)]
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    print(f"   🕵️‍♀️ Đang check Graduated Time cho {len(mint_list)} token...")
    
    GRADUATED_DEXS = ["raydium", "meteora", "orca"]

    for chunk in chunks:
        mints_str = ",".join(chunk)
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mints_str}"
        
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])
                token_info_map = {}
                
                for pair in pairs:
                    base_mint = pair.get("baseToken", {}).get("address")
                    if base_mint not in chunk: continue
                    
                    # Thời gian tạo của Pair hiện tại
                    pair_created_ts = int(pair.get("pairCreatedAt", 0) / 1000)
                    dex_id = pair.get("dexId", "").lower()
                    
                    # Khởi tạo data nếu chưa có
                    if base_mint not in token_info_map:
                        token_info_map[base_mint] = {
                            "mint": base_mint,
                            "symbol": pair.get("baseToken", {}).get("symbol", "N/A"),
                            "name": pair.get("baseToken", {}).get("name", "N/A"),
                            "created_at": pair_created_ts, # Tạm gán, sẽ update tìm min sau
                            "graduated": 0,
                            "graduated_at": None
                        }
                    
                    info = token_info_map[base_mint]

                    # 1. Tìm ngày sinh (Created At): Là thời gian của pair CŨ NHẤT (bất kể dex nào)
                    if pair_created_ts < info["created_at"]:
                        info["created_at"] = pair_created_ts

                    # 2. Tìm ngày tốt nghiệp (Graduated At): 
                    # Là thời gian tạo của pair thuộc Raydium/Meteora...
                    if dex_id in GRADUATED_DEXS:
                        info["graduated"] = 1
                        # Nếu chưa có graduated_at hoặc tìm thấy pair Raydium cũ hơn (hiếm gặp nhưng cứ check)
                        if info["graduated_at"] is None or pair_created_ts < info["graduated_at"]:
                            info["graduated_at"] = pair_created_ts

                # Lưu vào DB
                for mint, info in token_info_map.items():
                    # Format thời gian
                    fmt_created = datetime.fromtimestamp(info["created_at"], tz=VN_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
                    
                    grad_ts = info["graduated_at"]
                    fmt_grad = None
                    if grad_ts:
                        fmt_grad = datetime.fromtimestamp(grad_ts, tz=VN_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

                    cursor.execute('''
                    INSERT OR REPLACE INTO tokens 
                    (mint, symbol, name, created_at_ts, created_at_fmt, graduated, graduated_at_ts, graduated_at_fmt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (mint, info["symbol"], info["name"], info["created_at"], fmt_created, info["graduated"], grad_ts, fmt_grad))
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"   ⚠️ Lỗi DexScreener: {e}")
            
    conn.commit()
    conn.close()
def update_missing_tokens():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT DISTINCT token_mint FROM trades 
        WHERE token_mint NOT IN (SELECT mint FROM tokens)
        AND token_mint != ?
    ''', (SOL_MINT,))
    
    missing_mints = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if missing_mints:
        fetch_token_metadata_dexscreener(missing_mints)
    else:
        print("   ✅ Tất cả token đều đã có thông tin.")

# ==============================
# 3. CÁC HÀM XỬ LÝ GIAO DỊCH (GIỮ NGUYÊN)
# ==============================
def get_latest_sig_for_wallet(wallet_address):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT signature FROM trades WHERE signer = ? ORDER BY block_time DESC LIMIT 1", (wallet_address,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def parse_token_amount(ta):
    if ta is None: return 0.0
    if isinstance(ta, (int, float)): return float(ta)
    try: return float(ta) 
    except: pass
    if isinstance(ta, dict):
        amount = ta.get("amount", 0)
        decimals = ta.get("decimals", 0)
        try: return int(amount) / (10 ** int(decimals))
        except: return 0.0
    return 0.0

def owner_is_target(transfer, direction, target_address):
    if direction == "from":
        return (transfer.get("fromUserAccountOwner") == target_address or transfer.get("fromUserAccount") == target_address)
    else:
        return (transfer.get("toUserAccountOwner") == target_address or transfer.get("toUserAccount") == target_address)

def process_transaction(tx, wallet_address):
    if tx.get("type") != "SWAP": return None
    timestamp = tx.get("timestamp")
    human_time = datetime.fromtimestamp(timestamp, tz=VN_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    
    sent_map = defaultdict(float)
    recv_map = defaultdict(float)
    
    for transfer in tx.get("tokenTransfers", []):
        mint = transfer.get("mint")
        amt = parse_token_amount(transfer.get("tokenAmount"))
        if owner_is_target(transfer, "from", wallet_address): sent_map[mint] += amt
        if owner_is_target(transfer, "to", wallet_address): recv_map[mint] += amt
            
    if not sent_map or not recv_map: return None
    
    token_sent = max(sent_map, key=sent_map.get)
    amount_sent = sent_map[token_sent]
    token_recv = max(recv_map, key=recv_map.get)
    amount_recv = recv_map[token_recv]
    
    if token_sent == token_recv: return None 

    swap_type = "UNKNOWN"
    token_mint = ""
    token_amount = 0.0
    sol_amount = 0.0
    
    if token_sent == SOL_MINT:
        swap_type = "BUY"
        token_mint = token_recv
        token_amount = amount_recv
        sol_amount = amount_sent
    elif token_recv == SOL_MINT:
        swap_type = "SELL"
        token_mint = token_sent
        token_amount = amount_sent
        sol_amount = amount_recv
    else: return None

    return {
        "signature": tx.get("signature"),
        "block_time": timestamp,
        "human_time": human_time,
        "signer": wallet_address,
        "swap_type": swap_type,
        "token_mint": token_mint,
        "token_amount": token_amount,
        "sol_amount": sol_amount
    }

def save_batch_to_db(trades_list):
    if not trades_list: return 0
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    count = 0
    for t in trades_list:
        try:
            cursor.execute('''
            INSERT OR IGNORE INTO trades 
            (signature, block_time, human_time, signer, swap_type, token_mint, token_amount, sol_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (t['signature'], t['block_time'], t['human_time'], t['signer'], t['swap_type'], t['token_mint'], t['token_amount'], t['sol_amount']))
            if cursor.rowcount > 0: count += 1
        except Exception: pass
    conn.commit()
    conn.close()
    return count

# ==============================
# 4. MAIN FETCHER
# ==============================
def run_fetcher():
    init_db()
    
    for wallet in TARGET_WALLETS:
        print(f"\nExample: 🔍 Đang xử lý ví: {wallet}")
        
        latest_sig = get_latest_sig_for_wallet(wallet)
        stop_at_signature = latest_sig
        
        stop_time_limit = 0
        if not latest_sig:
            print(f"   🆕 Ví mới/chưa có data. Quét {DAYS_AGO_DEFAULT} ngày gần nhất.")
            stop_time_limit = int((datetime.now(VN_TIMEZONE) - timedelta(days=DAYS_AGO_DEFAULT)).timestamp())
        else:
            print(f"   🔄 Update từ giao dịch: {latest_sig[:8]}...")

        base_url = f"{HELIUS_BASE_URL}/{wallet}/transactions?api-key={HELIUS_API_KEY}"
        last_fetched_sig = None
        wallet_saved_count = 0
        retry_count = 0
        
        while True:
            url = f"{base_url}&limit=100"
            if last_fetched_sig: url += f"&before={last_fetched_sig}"
            
            try:
                resp = requests.get(url, timeout=45)
                
                if resp.status_code == 429:
                    print("   ⏳ Helius Rate Limit. Ngủ 5s...")
                    time.sleep(5)
                    continue
                
                if 500 <= resp.status_code < 600:
                    print(f"   ⚠️ Helius Server Error ({resp.status_code}). Ngủ 10s...")
                    time.sleep(10)
                    continue
                
                resp.raise_for_status()
                retry_count = 0 
                
                data = resp.json()
                if not data: 
                    print("   ✅ Hết dữ liệu từ API.")
                    break
                
                batch_processed = []
                should_stop = False
                
                for tx in data:
                    if stop_at_signature and tx.get("signature") == stop_at_signature:
                        should_stop = True
                        break
                    
                    if not stop_at_signature and tx.get("timestamp", 0) < stop_time_limit:
                        should_stop = True
                        break
                        
                    parsed = process_transaction(tx, wallet)
                    if parsed: batch_processed.append(parsed)
                
                saved = save_batch_to_db(batch_processed)
                wallet_saved_count += saved
                print(f"   📥 Fetch {len(data)} txs -> Lưu {saved} trades.")
                
                if should_stop:
                    print("   ✅ Đã khớp dữ liệu cũ hoặc chạm giới hạn thời gian.")
                    break
                    
                last_fetched_sig = data[-1].get("signature")
                time.sleep(0.5) 
                
            except (ConnectionError, Timeout, ChunkedEncodingError, ReadTimeout) as e:
                retry_count += 1
                print(f"   🔌 Lỗi mạng ({e}). Thử lại lần {retry_count}/5...")
                time.sleep(5)
                if retry_count > 5:
                    print("   ❌ Mạng quá yếu. Bỏ qua ví này.")
                    break
                continue
                
            except Exception as e:
                print(f"   ❌ Lỗi không xác định: {e}")
                break
        
        print(f"   🎉 Xong ví {wallet[:6]}... Tổng cộng: {wallet_saved_count} giao dịch mới.")
        
        print("   ⏳ Đang cập nhật Token & trạng thái Graduated...")
        update_missing_tokens()
        print("   ✅ Hoàn tất Metadata.")

if __name__ == "__main__":
    run_fetcher()