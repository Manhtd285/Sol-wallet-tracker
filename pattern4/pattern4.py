import pandas as pd
import numpy as np

# ==============================
# ⚙️ CẤU HÌNH
# ==============================
INPUT_CSV = "wallet_SP1-2-3.csv"
TARGET_WALLET = "Ar2Y6o1QmrRAskjii1cRfijeKugHH13ycxW5cd7rro1x"

# THAM SỐ PATTERN 4
MAX_BUY_VOL_SOL = 2.0         # Điều kiện Vol C3
RANGE_MIN = -40.0             # Ngưỡng dưới (-40%)
RANGE_MAX = -20.0             # Ngưỡng trên (-20%)

# File Output
OUTPUT_DETAIL_FILE = "pattern4_range_margin_detail.csv"
OUTPUT_DAILY_FILE = "pattern4_range_margin_daily.csv"

def analyze_pattern4_range_margin():
    print(f"🚀 Bắt đầu chạy Pattern 4: Sum Margin (C1+C2) trong khoảng [{RANGE_MIN}%, {RANGE_MAX}%]")

    # 1. Đọc dữ liệu & Xử lý sơ bộ
    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f"❌ Không tìm thấy file: {INPUT_CSV}")
        return

    df = df[df['Wallet'] == TARGET_WALLET].copy()
    if df.empty: return

    df['Transaction Time'] = pd.to_datetime(df['Transaction Time'])

    # 2. Gom nhóm Cycle & Tính Margin
    cycle_stats = []
    grouped = df.groupby(['cycle_id'])
    
    for cycle_id, group in grouped:
        token_mint = group['Token'].iloc[0]
        net_profit = group['Sol change'].sum()
        
        buy_txs = group[group['Type'] == 'BUY']
        if buy_txs.empty: continue
            
        start_time = buy_txs['Transaction Time'].min()
        buy_vol = buy_txs['Sol change'].abs().sum()
        
        # Tính Margin %
        margin_pct = (net_profit / buy_vol * 100) if buy_vol > 0 else 0.0

        cycle_stats.append({
            'cycle_id': cycle_id,
            'Token': token_mint,
            'entry_time': start_time,
            'date_str': start_time.strftime('%Y-%m-%d'),
            'buy_vol': buy_vol,
            'profit': net_profit,
            'margin_percent': margin_pct 
        })

    df_cycles = pd.DataFrame(cycle_stats)

    # 3. Logic Sliding Window (3 phần tử: C1, C2 -> C3)
    matched_cycles = []
    token_groups = df_cycles.groupby('Token')

    for token, group in token_groups:
        # Sort thời gian
        group = group.sort_values(by='entry_time').reset_index(drop=True)
        
        # Cần ít nhất 3 lệnh (C1, C2 quá khứ + C3 hiện tại)
        if len(group) < 3:
            continue

        # Duyệt từ phần tử thứ 3 (index = 2)
        for i in range(2, len(group)):
            # Lấy 2 cycle quá khứ
            prev_1 = group.iloc[i-1] # C2 (gần nhất)
            prev_2 = group.iloc[i-2] # C1 (xa hơn)
            
            # Tính tổng margin 2 lệnh trước
            sum_prev_margin = prev_1['margin_percent'] + prev_2['margin_percent']
            
            # Cycle hiện tại (C3)
            current_c3 = group.iloc[i]

            # --- KIỂM TRA ĐIỀU KIỆN ---
            # 1. Tổng margin (C1+C2) nằm trong đoạn [-40, -20]
            # 2. Vol lệnh hiện tại (C3) <= 2
            if RANGE_MIN <= sum_prev_margin <= RANGE_MAX:
                if current_c3['buy_vol'] <= MAX_BUY_VOL_SOL:
                    
                    # Lưu kết quả
                    row_data = current_c3.to_dict()
                    row_data['prev_sum_margin'] = round(sum_prev_margin, 2)
                    matched_cycles.append(row_data)

    if not matched_cycles:
        print("⚠️ Không có cycle nào thỏa mãn Pattern 4.")
        return

    # 4. Sắp xếp kết quả toàn cục
    df_result = pd.DataFrame(matched_cycles)
    df_result = df_result.sort_values(by='entry_time').reset_index(drop=True)

    # 5. Xuất File 1: Chi tiết
    df_detail_output = df_result[[
        'date_str', 'entry_time', 'Token', 'cycle_id', 
        'buy_vol', 'profit', 'margin_percent', 'prev_sum_margin'
    ]].copy()
    
    df_detail_output.rename(columns={
        'date_str': 'Date', 'entry_time': 'Time', 'buy_vol': 'Vol Buy', 
        'profit': 'Profit', 'margin_percent': 'Margin (C3) %',
        'prev_sum_margin': 'Sum Margin (C1+C2) %'
    }, inplace=True)
    
    df_detail_output.to_csv(OUTPUT_DETAIL_FILE, index=False, encoding='utf-8-sig')
    print(f"✅ [File 1] Chi tiết Pattern 4: {OUTPUT_DETAIL_FILE}")

    # 6. Xuất File 2: Report Ngày
    daily_report = df_result.groupby('date_str').agg({
        'cycle_id': 'count',
        'buy_vol': 'sum',
        'profit': 'sum'
    }).rename(columns={'cycle_id': 'Matched Cycles', 'buy_vol': 'Total Vol', 'profit': 'Total Profit'})

    daily_report['Margin (%)'] = daily_report.apply(
        lambda x: (x['Total Profit'] / x['Total Vol'] * 100) if x['Total Vol'] > 0 else 0, axis=1
    )

    # Format
    daily_report['Total Vol'] = daily_report['Total Vol'].round(2)
    daily_report['Total Profit'] = daily_report['Total Profit'].round(4)
    daily_report['Margin (%)'] = daily_report['Margin (%)'].round(2)
    
    daily_report = daily_report[['Margin (%)', 'Matched Cycles', 'Total Vol', 'Total Profit']]
    daily_report.to_csv(OUTPUT_DAILY_FILE, encoding='utf-8-sig')
    print(f"✅ [File 2] Report Ngày Pattern 4: {OUTPUT_DAILY_FILE}")

if __name__ == "__main__":
    analyze_pattern4_range_margin()