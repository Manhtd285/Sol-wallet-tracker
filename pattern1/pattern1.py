import pandas as pd
import numpy as np

#  CẤU HÌNH
INPUT_CSV = "wallet_SP1-2-3.csv"
TARGET_WALLET = "Ar2Y6o1QmrRAskjii1cRfijeKugHH13ycxW5cd7rro1x"

# Tham số chiến lược
MAX_BUY_VOL_SOL = 2.0       # Vol mua <= 2 SOL
REQUIRED_LOSS_STREAK = 3    # Đúng 3 cycle trước đó (CÙNG TOKEN) thất bại

# Tên file xuất ra
OUTPUT_DETAIL_FILE = "strategy_cycles_final_detail.csv"
OUTPUT_DAILY_FILE = "strategy_daily_final_report.csv"

def analyze_final_flow():
    print(f" Bắt đầu xử lý theo luồng: Filter Token -> Sort Time -> Daily Report")

  # BƯỚC 0: CHUẨN BỊ DỮ LIỆU THÔ

    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f" Không tìm thấy file: {INPUT_CSV}")
        return

    df = df[df['Wallet'] == TARGET_WALLET].copy()
    if df.empty: return

    df['Transaction Time'] = pd.to_datetime(df['Transaction Time'])

    # Gom nhóm thành từng Cycle trước
    cycle_stats = []
    grouped = df.groupby(['cycle_id'])
    
    for cycle_id, group in grouped:
        token_mint = group['Token'].iloc[0]
        net_profit = group['Sol change'].sum()
        
        buy_txs = group[group['Type'] == 'BUY']
        if buy_txs.empty: continue
            
        start_time = buy_txs['Transaction Time'].min() # Time entry
        buy_vol = buy_txs['Sol change'].abs().sum()
        
        cycle_stats.append({
            'cycle_id': cycle_id,
            'Token': token_mint,
            'entry_time': start_time,
            'date_str': start_time.strftime('%Y-%m-%d'),
            'buy_vol': buy_vol,
            'profit': net_profit,
            'is_loss': net_profit < 0
        })

    df_cycles = pd.DataFrame(cycle_stats)


    # BƯỚC 1: LỌC THEO TOKEN & TÌM CYCLE THỎA MÃN

    matched_cycles = []
    
    # Group by Token để xét streak riêng biệt cho từng con hàng
    token_groups = df_cycles.groupby('Token')

    for token, group in token_groups:
        # Sort thời gian trong nội bộ Token để đếm streak
        group = group.sort_values(by='entry_time').reset_index(drop=True)
        
        current_streak = 0
        
        for index, row in group.iterrows():
            # Logic: Streak cũ = 3 VÀ Vol hiện tại <= 2
            if current_streak == REQUIRED_LOSS_STREAK:
                if row['buy_vol'] <= MAX_BUY_VOL_SOL:
                    # Đây là cycle thỏa mãn
                    matched_cycles.append(row.to_dict())
            
            # Cập nhật Streak cho vòng sau
            if row['is_loss']:
                current_streak += 1
            else:
                current_streak = 0 # Thắng hoặc Hòa là reset

    if not matched_cycles:
        print(" Không có cycle nào thỏa mãn.")
        return

    # ---------------------------------------------------------
    # BƯỚC 2: SORT TOÀN BỘ THEO THỜI GIAN
    # ---------------------------------------------------------
    df_result = pd.DataFrame(matched_cycles)
    
    # Sắp xếp lại toàn bộ các kèo đã lọc được theo thứ tự thời gian thực tế xảy ra
    df_result = df_result.sort_values(by='entry_time').reset_index(drop=True)
    
    # Tính thêm Margin từng lệnh để xuất file chi tiết
    df_result['margin_percent'] = df_result.apply(
        lambda x: (x['profit'] / x['buy_vol'] * 100) if x['buy_vol'] > 0 else 0, axis=1
    )

    # Xuất File 1: Chi tiết
    df_detail_output = df_result[[
        'date_str', 'entry_time', 'Token', 'cycle_id', 'buy_vol', 'profit', 'margin_percent'
    ]].rename(columns={
        'date_str': 'Date', 'entry_time': 'Time', 'buy_vol': 'Vol Buy', 
        'profit': 'Profit', 'margin_percent': 'Margin %'
    })
    df_detail_output.to_csv(OUTPUT_DETAIL_FILE, index=False, encoding='utf-8-sig')
    print(f" [File 1] Chi tiết từng lệnh: {OUTPUT_DETAIL_FILE}")


    # BƯỚC 3: TÍNH TOÁN DAILY REPORT (MARGIN DAILY)

    # Group theo ngày từ danh sách đã lọc
    daily_group = df_result.groupby('date_str')
    
    daily_report = daily_group.agg({
        'cycle_id': 'count',
        'buy_vol': 'sum',
        'profit': 'sum'
    }).rename(columns={'cycle_id': 'Matched Cycles', 'buy_vol': 'Total Vol', 'profit': 'Total Profit'})

    # Tính Margin của cả ngày = (Tổng Profit ngày / Tổng Vol ngày) * 100
    daily_report['Margin (%)'] = daily_report.apply(
        lambda x: (x['Total Profit'] / x['Total Vol'] * 100) if x['Total Vol'] > 0 else 0, axis=1
    )

    # Format làm tròn
    daily_report['Total Vol'] = daily_report['Total Vol'].round(2)
    daily_report['Total Profit'] = daily_report['Total Profit'].round(4)
    daily_report['Margin (%)'] = daily_report['Margin (%)'].round(2)

    # Sắp xếp cột
    daily_report = daily_report[['Margin (%)', 'Matched Cycles', 'Total Vol', 'Total Profit']]
    
    # Xuất File 2: Report Ngày
    daily_report.to_csv(OUTPUT_DAILY_FILE, encoding='utf-8-sig')
    print(f" [File 2] Báo cáo theo ngày: {OUTPUT_DAILY_FILE}")

    # In thử vài dòng kết quả
    print("\n--- PREVIEW DAILY REPORT ---")
    print(daily_report.head())

if __name__ == "__main__":
    analyze_final_flow()
