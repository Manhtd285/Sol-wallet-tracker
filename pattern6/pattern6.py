import pandas as pd
import numpy as np


#  CẤU HÌNH

INPUT_CSV = "wallet_SP1-2-3.csv"
TARGET_WALLET = "Ar2Y6o1QmrRAskjii1cRfijeKugHH13ycxW5cd7rro1x"

# THAM SỐ PATTERN (C1 -> C2 -> C3 -> C4)
COND_C1_MARGIN = -7.0    # C1 < -7
COND_C2_MARGIN = 3.0     # C2 < 3
COND_C3_MARGIN = -13.0   # C3 < -13
COND_C4_MAX_VOL = 2.0    # C4 Vol <= 2 SOL

# File Output
OUTPUT_DETAIL_FILE = "pattern_specific_c1_c2_c3_detail.csv"
OUTPUT_DAILY_FILE = "pattern_specific_c1_c2_c3_daily.csv"

def analyze_specific_pattern():
    print(f" Bắt đầu chạy Pattern: C1<-7, C2<3, C3<-13 -> C4 Vol<=2")


    # BƯỚC 1: ĐỌC DỮ LIỆU & TÍNH MARGIN CƠ BẢN
    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f" Không tìm thấy file: {INPUT_CSV}")
        return

    df = df[df['Wallet'] == TARGET_WALLET].copy()
    if df.empty: return

    df['Transaction Time'] = pd.to_datetime(df['Transaction Time'])

    # Gom nhóm Cycle
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


    # BƯỚC 2: LOGIC SLIDING WINDOW (C1, C2, C3, C4)
    matched_cycles = []
    token_groups = df_cycles.groupby('Token')

    for token, group in token_groups:
        # Sort thời gian: Cũ -> Mới
        group = group.sort_values(by='entry_time').reset_index(drop=True)
        
        # Cần ít nhất 4 lệnh để tạo thành pattern
        if len(group) < 4:
            continue

        # Sliding Window
        for i in range(3, len(group)):
            # Ánh xạ theo thời gian
            c4 = group.iloc[i]   # Hiện tại
            c3 = group.iloc[i-1] # Gần nhất
            c2 = group.iloc[i-2] # Giữa
            c1 = group.iloc[i-3] # Xa nhất

            m1 = c1['margin_percent']
            m2 = c2['margin_percent']
            m3 = c3['margin_percent']
            
            # --- KIỂM TRA ĐIỀU KIỆN ---
            # Logic: C1 < -7 AND C2 < 3 AND C3 < -13
            if (m1 < COND_C1_MARGIN) and (m2 < COND_C2_MARGIN) and (m3 < COND_C3_MARGIN):
                
                # Logic: C4 Vol <= 2
                if c4['buy_vol'] <= COND_C4_MAX_VOL:
                    
                    # Thỏa mãn -> Lưu lại
                    row_data = c4.to_dict()
                    # Lưu thêm thông tin C1, C2, C3 để dễ kiểm tra
                    row_data['margin_c1'] = round(m1, 2)
                    row_data['margin_c2'] = round(m2, 2)
                    row_data['margin_c3'] = round(m3, 2)
                    
                    matched_cycles.append(row_data)

    if not matched_cycles:
        print(" Không có cycle nào thỏa mãn Pattern.")
        return

    # BƯỚC 3: XUẤT BÁO CÁO
    df_result = pd.DataFrame(matched_cycles)
    df_result = df_result.sort_values(by='entry_time').reset_index(drop=True)

    # 1. File Chi tiết
    cols_order = [
        'date_str', 'entry_time', 'Token', 'cycle_id', 
        'buy_vol', 'profit', 'margin_percent', 
        'margin_c1', 'margin_c2', 'margin_c3' # Cột mới để debug
    ]
    df_detail = df_result[cols_order].rename(columns={
        'date_str': 'Date', 
        'buy_vol': 'Vol Buy (C4)', 
        'profit': 'Profit (C4)', 
        'margin_percent': 'Margin (C4) %',
        'margin_c1': 'Margin C1 %',
        'margin_c2': 'Margin C2 %',
        'margin_c3': 'Margin C3 %'
    })
    
    df_detail.to_csv(OUTPUT_DETAIL_FILE, index=False, encoding='utf-8-sig')
    print(f" [File 1] Chi tiết từng lệnh: {OUTPUT_DETAIL_FILE}")

    # 2. File Daily Report
    daily_report = df_result.groupby('date_str').agg({
        'cycle_id': 'count',
        'buy_vol': 'sum',
        'profit': 'sum'
    }).rename(columns={'cycle_id': 'Matched Cycles', 'buy_vol': 'Total Vol', 'profit': 'Total Profit'})

    daily_report['Margin (%)'] = daily_report.apply(
        lambda x: (x['Total Profit'] / x['Total Vol'] * 100) if x['Total Vol'] > 0 else 0, axis=1
    )
    
    daily_report['Total Vol'] = daily_report['Total Vol'].round(2)
    daily_report['Total Profit'] = daily_report['Total Profit'].round(4)
    daily_report['Margin (%)'] = daily_report['Margin (%)'].round(2)
    
    daily_report = daily_report[['Margin (%)', 'Matched Cycles', 'Total Vol', 'Total Profit']]
    daily_report.to_csv(OUTPUT_DAILY_FILE, encoding='utf-8-sig')
    print(f" [File 2] Báo cáo ngày: {OUTPUT_DAILY_FILE}")

if __name__ == "__main__":
    analyze_specific_pattern()
