import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams

# 1. SETUP FONT & BAHASA
rcParams['font.family'] = 'serif'
rcParams['font.serif'] = ['Palatino', 'Palatino Linotype', 'DejaVu Serif']

# 2. LOAD DATA
file_path = r"D:\Documents\ITB\MyRiset\RDI - BIRU PROJECT\Database\Clean Data BUS - with DIY NTT Jawa Barat Jawa Timur 20260521-135533.xlsx"
xls = pd.ExcelFile(file_path)
provinces = ['Jawa Tengah', 'Sulawesi Selatan', 'Bali','DIY', 'Jawa Barat', 'Jawa Timur', 'NTT', 'NTB']
df_list = []
for p in provinces:
    temp_df = pd.read_excel(xls, sheet_name=p)
    temp_df['Province_Label'] = p
    df_list.append(temp_df)
df = pd.concat(df_list, ignore_index=True)

# Helper untuk mencari kolom
def find_col(prefix, dataframe):
    matches = [c for c in dataframe.columns if f"/{prefix}" in str(c) or str(c).startswith(prefix)]
    return matches[0] if matches else None

# Kolom Penting
target_col = find_col('G2.', df)      # Overall Satisfaction
issue_col = find_col('G8.', df)       # Reasons for dissatisfaction
suggestion_col = find_col('G12.', df) # Improvements suggestions

# 3. MAPPING DIMENSI
dim_map = {
    'Technical Performance': ['A9.', 'G3.', 'G4.'],
    'Economic Impact': ['G5.', 'D25.', 'D1-a.'],
    'Health & Sanitation': ['C2.', 'C3.', 'C22.', 'C26.'],
    'Operations & Maintenance': ['A18.', 'A21.', 'A23.', 'A29.', 'A36.'],
    'Agricultural Impact': ['E13.', 'E16.', 'E31.'],
    'Service Quality (CPO)': ['G7.'],
    'Social & Gender Impact': ['F1.', 'F2.', 'F4.', 'D8.']
}

mapping = {
    'Sangat puas': 100, 'Puas': 75, 'Cukup puas': 50, 'Tidak puas': 25, 'Sangat tidak puas': 0,
    'Jauh lebih baik': 100, 'Lebih baik': 75, 'Cukup membaik': 75, 'Tidak ada perubahan': 50, 'Sama saja': 50, 'Kurang membaik': 25, 'Memburuk': 25, 'Jauh lebih buruk': 0,
    'Jauh lebih bersih': 100, 'Lebih bersih': 75, 'Sama saja': 50, 'Kurang bersih': 25, 'Lebih kotor': 0,
    'Sangat meningkat': 100, 'Cukup meningkat': 75, 'Sedikit meningkat': 75, 'Sedikit menurun': 25, 'Sangat menurun': 0,
    'Selalu (setiap hari)': 100, 'Setiap hari': 100, 'Sering': 75, 'Cukup sering': 50, 'Jarang': 25, 'Tidak pernah': 0,
    'Ya': 100, 'Tidak': 0, 'Berfungsi dengan baik': 100, 'Tidak berfungsi sama sekali': 0,
    'Sangat memahami': 100, 'Memahami': 75, 'Cukup memahami': 50, 'Kurang memahami': 25, 'Tidak memahami': 0,
    'Sangat setuju': 100, 'Setuju': 75, 'Netral/tidak tahu': 50, 'Tidak setuju': 25, 'Sangat tidak setuju': 0,
    'Tidak pernah': 100, 'Lebih jarang': 75, 'Lebih sering': 25, 'Sangat sering': 0
}

# 4. FILTERING & SCORING
extreme_df = df[df[target_col].isin(['Sangat puas', 'Tidak puas'])].copy()
extreme_df['Status'] = extreme_df[target_col].apply(lambda x: 'Highly Satisfied' if x == 'Sangat puas' else 'Highly Dissatisfied')

for dim, ids in dim_map.items():
    cols = [find_col(idx, extreme_df) for idx in ids if find_col(idx, extreme_df)]
    if cols:
        extreme_df[dim] = extreme_df[cols].apply(lambda x: x.map(mapping)).mean(axis=1)

# 5. SUMMARY TABLE
summary_table = extreme_df.groupby(['Province_Label', 'Status']).agg({
    target_col: 'count',
    'Technical Performance': 'mean',
    'Service Quality (CPO)': 'mean'
}).rename(columns={target_col: 'Sample (N)'})

print("--- SUMMARY TABLE ---")
print(summary_table)

# 6. RADAR FUNCTION FIXED
def plot_final_radar(data_subset, title):
    categories = list(dim_map.keys())
    num_vars = len(categories)
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]
    
    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    
    # PERBAIKAN: Menambah palet warna untuk semua provinsi
    # Menggunakan colormap agar otomatis menyesuaikan jumlah provinsi
    cmap = plt.get_cmap('tab10')
    province_colors = {prov: cmap(i) for i, prov in enumerate(provinces)}
    
    for prov in provinces:
        prov_data = data_subset[data_subset['Province_Label'] == prov]
        if not prov_data.empty:
            n_sample = len(prov_data)
            # Pastikan kategori yang ada di dim_map dihitung rata-ratanya
            values = prov_data[categories].mean().values.tolist()
            values += values[:1]
            
            # Gunakan .get() untuk menghindari KeyError jika ada provinsi baru
            color = province_colors.get(prov, 'gray')
            
            ax.plot(angles, values, linewidth=2, label=f"{prov} (N={n_sample})", color=color)
            ax.fill(angles, values, alpha=0.1, color=color)
        
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10, fontweight='bold')
    ax.set_ylim(0, 100)
    
    plt.title(title, size=16, y=1.1, fontweight='bold')
    # Letakkan legend di bawah untuk menghindari tumpang tindih karena banyak provinsi
    plt.legend(loc='upper right', bbox_to_anchor=(1.3, 0.1))
    plt.tight_layout()
    plt.show()

# 7. EXECUTE
# Pastikan data tidak kosong sebelum plotting untuk menghindari error
satisfied_subset = extreme_df[extreme_df['Status'] == 'Highly Satisfied']
dissatisfied_subset = extreme_df[extreme_df['Status'] == 'Highly Dissatisfied']

if not satisfied_subset.empty:
    plot_final_radar(satisfied_subset, "Highly Satisfied Profile Across Provinces")

if not dissatisfied_subset.empty:
    plot_final_radar(dissatisfied_subset, "Highly Dissatisfied Profile Across Provinces")