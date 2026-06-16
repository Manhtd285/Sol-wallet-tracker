import pandas as pd
import numpy as np

# ==============================
# ⚙️ CẤU HÌNH
# ==============================
INPUT_CSV = "wallet_SP1-2-3.csv"
TARGET_WALLET = "Ar2Y6o1QmrRAskjii1cRfijeKugHH13ycxW5cd7rro1x"

# THAM SỐ PATTERN 2
MAX_BUY_VOL_SOL = 2.0        # Điều kiện C4
TARGET_SUM_MARGIN = -10.0    # Tổng margin C1+C2+C3 phải bé hơn -10%

# File Output
OUTPUT_DETAIL_FILE = "pattern2_sum_margin_detail.csv"
OUTPUT_DAILY_FILE = "pattern2_sum_margin_daily.csv"

def analyze_pattern_sum_margin():
    print(f"🚀 Bắt đầu chạy Pattern 2: Sum Margin 3 lệnh trước < {TARGET_SUM_MARGIN}%")

    # 1. Đọc dữ liệu & Pre-processing
    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f"❌ Không tìm thấy file: {INPUT_CSV}")
        return

    df = df[df['Wallet'] == TARGET_WALLET].copy()
    if df.empty: return

    df['Transaction Time'] = pd.to_datetime(df['Transaction Time'])

    # 2. Gom nhóm Cycle & Tính Margin luôn tại bước này
    cycle_stats = []
    grouped = df.groupby(['cycle_id'])
    
    for cycle_id, group in grouped:
        token_mint = group['Token'].iloc[0]
        net_profit = group['Sol change'].sum()
        
        buy_txs = group[group['Type'] == 'BUY']
        if buy_txs.empty: continue
            
        start_time = buy_txs['Transaction Time'].min()
        buy_vol = buy_txs['Sol change'].abs().sum()
        
        # Tính Margin % cho từng Cycle
        # Nếu Vol = 0 (trường hợp hiếm) thì margin = 0
        margin_pct = (net_profit / buy_vol * 100) if buy_vol > 0 else 0.0

        cycle_stats.append({
            'cycle_id': cycle_id,
            'Token': token_mint,
            'entry_time': start_time,
            'date_str': start_time.strftime('%Y-%m-%d'),
            'buy_vol': buy_vol,
            'profit': net_profit,
            'margin_percent': margin_pct # Lưu lại để dùng tính Sum
        })

    df_cycles = pd.DataFrame(cycle_stats)

    # 3. Logic: Cửa sổ trượt (Sliding Window) theo Token
    matched_cycles = []
    
    token_groups = df_cycles.groupby('Token')

    for token, group in token_groups:
        # Sort thời gian để có thứ tự C1 -> C2 -> C3 -> C4
        group = group.sort_values(by='entry_time').reset_index(drop=True)
        
        # Chúng ta cần ít nhất 4 cycle để xét điều kiện (3 quá khứ + 1 hiện tại)
        if len(group) < 4:
            continue

        # Duyệt từ phần tử thứ 4 (index = 3) trở đi
        for i in range(3, len(group)):
            # Lấy 3 cycle trước đó: index i-3, i-2, i-1
            prev_1 = group.iloc[i-1] # C3
            prev_2 = group.iloc[i-2] # C2
            prev_3 = group.iloc[i-3] # C1
            
            # Tính tổng margin 3 lệnh trước
            sum_prev_margin = prev_1['margin_percent'] + prev_2['margin_percent'] + prev_3['margin_percent']
            
            # Lấy cycle hiện tại (C4)
            current_c4 = group.iloc[i]

            # --- KIỂM TRA ĐIỀU KIỆN ---
            # 1. Tổng margin 3 lệnh trước < -10
            # 2. Vol lệnh hiện tại <= 2
            if sum_prev_margin < TARGET_SUM_MARGIN:
                if current_c4['buy_vol'] <= MAX_BUY_VOL_SOL:
                    
                    # Thỏa mãn -> Lưu lại
                    # Lưu thêm thông tin debug để bạn dễ check
                    row_data = current_c4.to_dict()
                    row_data['prev_sum_margin'] = round(sum_prev_margin, 2)
                    matched_cycles.append(row_data)

    if not matched_cycles:
        print("⚠️ Không có cycle nào thỏa mãn Pattern 2.")
        return

    # 4. Sắp xếp toàn bộ kết quả theo thời gian
    df_result = pd.DataFrame(matched_cycles)
    df_result = df_result.sort_values(by='entry_time').reset_index(drop=True)

    # 5. Xuất File 1: Chi tiết (Thêm cột Sum Margin Previous để check)
    df_detail_output = df_result[[
        'date_str', 'entry_time', 'Token', 'cycle_id', 
        'buy_vol', 'profit', 'margin_percent', 'prev_sum_margin'
    ]].copy()
    
    df_detail_output.rename(columns={
        'date_str': 'Date', 'entry_time': 'Time', 'buy_vol': 'Vol Buy', 
        'profit': 'Profit', 'margin_percent': 'Margin (C4) %',
        'prev_sum_margin': 'Sum Margin (C1+C2+C3) %'
    }, inplace=True)
    
    df_detail_output.to_csv(OUTPUT_DETAIL_FILE, index=False, encoding='utf-8-sig')
    print(f"✅ [File 1] Chi tiết Pattern 2: {OUTPUT_DETAIL_FILE}")

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
    print(f"✅ [File 2] Report Ngày Pattern 2: {OUTPUT_DAILY_FILE}")

if __name__ == "__main__":
    analyze_pattern_sum_margin()