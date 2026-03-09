import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
import scipy.cluster.hierarchy as sch
from matplotlib.colors import LinearSegmentedColormap
from datetime import date
import urllib.request
import matplotlib.font_manager as fm
import os

# ==========================================
# 🛠️ ตั้งค่าระบบและฟอนต์ภาษาไทย (แก้ปัญหาฟอนต์เต้าหู้บน Cloud)
# ==========================================
st.set_page_config(page_title="GPF Portfolio Simulator", page_icon="📊", layout="wide")

# 1. โหลดฟอนต์ภาษาไทย 'Sarabun' จาก Google Fonts (ถ้ายังไม่มีในระบบ)
font_url = "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Regular.ttf"
font_path = "Sarabun-Regular.ttf"

if not os.path.exists(font_path):
    urllib.request.urlretrieve(font_url, font_path)

# 2. นำฟอนต์ไปติดตั้งใน Matplotlib
fm.fontManager.addfont(font_path)
mpl.rc('font', family='Sarabun')
mpl.rcParams['axes.unicode_minus'] = False # ป้องกันเครื่องหมายลบเพี้ยน

st.title("📊 ระบบจำลองและวิเคราะห์แผนการลงทุน กบข.")
st.markdown("---")

# ==========================================
# 🧠 ส่วนที่ 1: ระบบโหลดข้อมูลอัจฉริยะ (Data Engine)
# ==========================================
@st.cache_data
def load_data():
    """ฟังก์ชันโหลดข้อมูลและทำความสะอาด (Cache ไว้เพื่อความรวดเร็ว)"""
    df = pd.read_excel('GPF.xlsx', sheet_name='NAV_GPF')
    
    df['วันที่'] = pd.to_datetime(df['วันที่'], format='%d/%m/%Y', errors='coerce')
    df.dropna(subset=['วันที่'], inplace=True)
    df.set_index('วันที่', inplace=True)
    df.sort_index(ascending=True, inplace=True)
    
    for col in df.columns:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
    
    df.fillna(method='ffill', inplace=True)
    returns = df.pct_change()
    
    # กำหนดกลุ่มกองทุนหลักที่ใช้ AI คำนวณ (ไม่รวมวายุภักษ์)
    core_funds = [
        'แผนตราสารหนี้', 'แผนเงินฝากและตราสารหนี้ระยะสั้น', 'แผนหุ้นไทย',
        'แผนกองทุนอสังหาริมทรัพย์ไทย', 'แผนหุ้นต่างประเทศ', 'แผนตราสารหนี้ต่างประเทศ', 'แผนทองคำ'
    ]
    
    returns_core = returns[[f for f in core_funds if f in returns.columns]].dropna()
    mean_returns_core = returns_core.mean() * 252
    cov_matrix_core = returns_core.cov() * 252
    
    return returns, returns_core, mean_returns_core, cov_matrix_core, core_funds

with st.spinner("⏳ กำลังเตรียมข้อมูลระบบ..."):
    returns, returns_core, mean_returns_core, cov_matrix_core, core_funds = load_data()

# ==========================================
# 🎛️ ส่วนที่ 2: แผงควบคุม (Sidebar)
# ==========================================
st.sidebar.header("⚙️ พารามิเตอร์การลงทุน")

# 2.1.1 ยอดเงิน กบข.
gpf_current_balance = st.sidebar.number_input("💰 ยอดเงิน กบข. ปัจจุบัน", min_value=0.0, value=284827.0, step=1000.0)
# เพิ่มบรรทัดนี้เพื่อโชว์ตัวเลขแบบมีลูกน้ำสวยๆ ด้านล่างกล่อง
st.sidebar.markdown(f"<div style='text-align: right; color: #00FF00; font-size: 18px; font-weight: bold;'>{gpf_current_balance:,.2f} บาท</div>", unsafe_allow_html=True)

# 2.1.2 เงินเดือน
current_salary = st.sidebar.number_input("💵 เงินเดือนปัจจุบัน", min_value=0.0, value=30870.0, step=1000.0)
st.sidebar.markdown(f"<div style='text-align: right; color: #00FF00; font-size: 18px; font-weight: bold;'>{current_salary:,.2f} บาท</div>", unsafe_allow_html=True)

# 2.1.3 อัตราออมเพิ่ม
extra_saving_pct = st.sidebar.slider("📈 อัตราออมเพิ่ม (%)", min_value=0, max_value=15, value=0, step=1)

# 2.1.4 กองทุนรวมวายุภักษ์
st.sidebar.markdown("---")
vayupak_amount = st.sidebar.number_input("🏛️ จำนวนเงิน แผนกองทุนรวมวายุภักษ์\n(หากไม่มีให้ระบุ 0)", min_value=0.0, value=0.0, step=1000.0)
st.sidebar.markdown(f"<div style='text-align: right; color: #00FF00; font-size: 18px; font-weight: bold;'>{vayupak_amount:,.2f} บาท</div>", unsafe_allow_html=True)

# ลอจิกเพดานทองคำ: ถ้ามีวายุภักษ์ ทองคำจำกัด 25% | ถ้าไม่มี ทองคำได้ถึง 100%
gold_max_limit = 25 if vayupak_amount > 0 else 100

# 2.1.5 เพดานความเสี่ยง
target_vol_limit_pct = st.sidebar.slider("⚖️ เพดานความเสี่ยงที่ยอมรับได้ (%)", min_value=1, max_value=15, value=6, step=1)

# 2.1.6 สัดส่วนแผนการลงทุน DIY
st.sidebar.markdown("---")
st.sidebar.subheader("🎯 กำหนดสัดส่วนแผนการลงทุน (ต้องรวมได้ 100%)")

# ใช้ number_input แบบ step=5 เพื่อให้ปรับง่าย
alloc_th_eq = st.sidebar.number_input("แผนหุ้นไทย (%)", min_value=0, max_value=100, value=0, step=5)
alloc_inter_eq = st.sidebar.number_input("แผนหุ้นต่างประเทศ (%)", min_value=0, max_value=100, value=0, step=5)
alloc_prop = st.sidebar.number_input("แผนกองทุนอสังหาริมทรัพย์ไทย (%)", min_value=0, max_value=100, value=0, step=5)
alloc_gold = st.sidebar.number_input(f"แผนทองคำ (%) [สูงสุด {gold_max_limit}%]", min_value=0, max_value=gold_max_limit, value=min(0, gold_max_limit), step=5)
alloc_th_fi = st.sidebar.number_input("แผนตราสารหนี้ (%)", min_value=0, max_value=100, value=0, step=5)
alloc_inter_fi = st.sidebar.number_input("แผนตราสารหนี้ต่างประเทศ (%)", min_value=0, max_value=100, value=0, step=5)
alloc_short_fi = st.sidebar.number_input("แผนเงินฝากและตราสารหนี้ระยะสั้น (%)", min_value=0, max_value=100, value=0, step=5)

# 2.1.7 วันที่เริ่มพยากรณ์
st.sidebar.markdown("---")
forecast_start_date = st.sidebar.date_input("📅 วันที่เริ่มต้นการพยากรณ์", value=date.today())

# คำนวณยอดรวมสัดส่วน
total_alloc = sum([alloc_th_eq, alloc_inter_eq, alloc_prop, alloc_gold, alloc_th_fi, alloc_inter_fi, alloc_short_fi])

# สร้าง Dictionary เก็บสัดส่วน DIY
my_new_portfolio = {
    'แผนหุ้นไทย': alloc_th_eq,
    'แผนหุ้นต่างประเทศ': alloc_inter_eq,
    'แผนกองทุนอสังหาริมทรัพย์ไทย': alloc_prop,
    'แผนทองคำ': alloc_gold,
    'แผนตราสารหนี้': alloc_th_fi,
    'แผนตราสารหนี้ต่างประเทศ': alloc_inter_fi,
    'แผนเงินฝากและตราสารหนี้ระยะสั้น': alloc_short_fi
}

# ==========================================
# 🚀 ส่วนที่ 3: ฟังก์ชันเครื่องยนต์หลัก (Refactored)
# ==========================================
def calculate_ai_portfolios(target_vol_limit, risk_free_rate, core_funds, mean_returns, cov_matrix, has_vayupak):
    """สุ่ม 100,000 รูปแบบ เพื่อหา Max Sharpe และ Target Risk"""
    num_portfolios = 100000
    all_weights = np.zeros((num_portfolios, len(core_funds)))
    ret_arr = np.zeros(num_portfolios)
    vol_arr = np.zeros(num_portfolios)
    sharpe_arr = np.zeros(num_portfolios)
    
    gold_idx = core_funds.index('แผนทองคำ') if 'แผนทองคำ' in core_funds else -1

    np.random.seed(42)
    for i in range(num_portfolios):
        w = np.random.random(len(core_funds))
        w /= np.sum(w)
        
        # กฎเหล็ก: ล็อกทองคำ 25% "เฉพาะเมื่อมีวายุภักษ์"
        if has_vayupak and gold_idx != -1 and w[gold_idx] > 0.25:
            excess = w[gold_idx] - 0.25
            w[gold_idx] = 0.25
            other_indices = [idx for idx in range(len(core_funds)) if idx != gold_idx]
            if np.sum(w[other_indices]) > 0:
                w[other_indices] += excess * (w[other_indices] / np.sum(w[other_indices]))
                
        all_weights[i, :] = w
        ret = np.sum(mean_returns * w)
        vol = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
        ret_arr[i], vol_arr[i] = ret, vol
        sharpe_arr[i] = (ret - risk_free_rate) / vol

    max_sharpe_idx = sharpe_arr.argmax()
    acc_ports = np.where(vol_arr <= target_vol_limit)[0]
    target_risk_idx = acc_ports[ret_arr[acc_ports].argmax()] if len(acc_ports) > 0 else max_sharpe_idx
    
    return all_weights, ret_arr, vol_arr, sharpe_arr, max_sharpe_idx, target_risk_idx

def calculate_tactical_hrp(core_funds, returns_core, mean_returns, cov_matrix, has_vayupak):
    """คำนวณพอร์ต HRP พร้อมระบุสภาวะตลาด"""
    # ... (ฟังก์ชัน HRP อัลกอริทึมย่อย) ...
    def get_hrp_weights(returns_df):
        if returns_df.shape[1] == 1: return np.array([1.0])
        if returns_df.shape[1] == 0: return np.array([])
        cov, corr = returns_df.cov() * 252, returns_df.corr()
        dist = np.sqrt(np.clip((1.0 - corr) / 2.0, 0.0, 1.0)).values
        link = sch.linkage(dist[np.triu_indices(dist.shape[0], k=1)], method='single')
        def get_quasi_diag(link):
            link = link.astype(int)
            sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
            num_items = link[-1, 3]
            while sort_ix.max() >= num_items:
                sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
                df0 = sort_ix[sort_ix >= num_items]
                i, j = df0.index, df0.values - num_items
                sort_ix[i] = link[j, 0]
                sort_ix = pd.concat([sort_ix, pd.Series(link[j, 1], index=i + 1)]).sort_index()
                sort_ix.index = range(len(sort_ix))
            return sort_ix.tolist()
        sort_ix = get_quasi_diag(link)
        def get_cluster_var(cov, c_items):
            cov_ = cov.iloc[c_items, c_items]
            ivp = 1. / np.diag(cov_)
            w_ = (ivp / ivp.sum()).reshape(-1, 1)
            return np.dot(np.dot(w_.T, cov_), w_)[0, 0]
        w = pd.Series(1.0, index=sort_ix)
        c_items = [sort_ix]
        while len(c_items) > 0:
            c_items = [i[j:k] for i in c_items for j, k in ((0, len(i)//2), (len(i)//2, len(i))) if len(i) > 1]
            for i in range(0, len(c_items), 2):
                c_items0, c_items1 = c_items[i], c_items[i+1]
                c_var0, c_var1 = get_cluster_var(cov, c_items0), get_cluster_var(cov, c_items1)
                alpha = 1 - c_var0 / (c_var0 + c_var1)
                w[c_items0] *= alpha
                w[c_items1] *= 1 - alpha
        w.index = returns_df.columns[sort_ix]
        return w[returns_df.columns].values

    high_risk_cols = ['แผนหุ้นไทย', 'แผนหุ้นต่างประเทศ', 'แผนกองทุนอสังหาริมทรัพย์ไทย', 'แผนทองคำ']
    low_risk_cols = ['แผนตราสารหนี้', 'แผนตราสารหนี้ต่างประเทศ', 'แผนเงินฝากและตราสารหนี้ระยะสั้น']
    
    high_risk_funds = [f for f in high_risk_cols if f in core_funds]
    low_risk_funds = [f for f in low_risk_cols if f in core_funds]

    norm_prices = (1 + returns_core[high_risk_funds]).cumprod()
    high_risk_index = norm_prices.mean(axis=1)
    ma200 = high_risk_index.rolling(window=200).mean()

    is_bull = high_risk_index.iloc[-1] > ma200.iloc[-1]
    w_high_target = 0.80 if is_bull else 0.40
    w_low_target = 1.0 - w_high_target

    hrp_weights_arr = np.zeros(len(core_funds))
    fund_idx_map = {f: i for i, f in enumerate(core_funds)}

    if len(high_risk_funds) > 0:
        w_high_rel = get_hrp_weights(returns_core[high_risk_funds])
        for f, w in zip(high_risk_funds, w_high_rel):
            hrp_weights_arr[fund_idx_map[f]] = w * w_high_target

    if len(low_risk_funds) > 0:
        w_low_rel = get_hrp_weights(returns_core[low_risk_funds])
        for f, w in zip(low_risk_funds, w_low_rel):
            hrp_weights_arr[fund_idx_map[f]] = w * w_low_target

    # กฎเหล็ก: ล็อกทองคำ 25% "เฉพาะเมื่อมีวายุภักษ์"
    gold_idx = core_funds.index('แผนทองคำ') if 'แผนทองคำ' in core_funds else -1
    if has_vayupak and gold_idx != -1 and hrp_weights_arr[gold_idx] > 0.25:
        excess = hrp_weights_arr[gold_idx] - 0.25
        hrp_weights_arr[gold_idx] = 0.25
        other_high_risk = [fund_idx_map[f] for f in high_risk_funds if f != 'แผนทองคำ']
        sum_other_high = np.sum(hrp_weights_arr[other_high_risk])
        if sum_other_high > 0:
            hrp_weights_arr[other_high_risk] += excess * (hrp_weights_arr[other_high_risk] / sum_other_high)
        elif len(other_high_risk) > 0:
            hrp_weights_arr[other_high_risk] += excess / len(other_high_risk)

    hrp_ret = np.sum(mean_returns * hrp_weights_arr)
    hrp_vol = np.sqrt(np.dot(hrp_weights_arr.T, np.dot(cov_matrix, hrp_weights_arr)))
    
    return hrp_weights_arr, hrp_ret, hrp_vol, is_bull

# ==========================================
# 📊 ส่วนที่ 4: การตรวจสอบ UI และปุ่มกด
# ==========================================
# 4.1 ตรวจสอบความถูกต้องของสัดส่วน DIY
if total_alloc != 100:
    st.sidebar.error(f"⚠️ สัดส่วนรวมปัจจุบัน: {total_alloc}% (ต้องปรับให้เท่ากับ 100%)")
elif gpf_current_balance < vayupak_amount:
    st.sidebar.error(f"⚠️ ยอดเงินวายุภักษ์ ({vayupak_amount:,.2f}) ไม่สามารถมากกว่ายอด กบข. รวม ({gpf_current_balance:,.2f}) ได้")
else:
    # 4.2 ถ้าสัดส่วนครบ 100% ถึงจะโชว์ปุ่มให้กด
    if st.sidebar.button("🚀 ประมวลผลและวิเคราะห์แผนการลงทุน"):
        progress_bar = st.progress(0)
        st.markdown("### ⚙️ ระบบกำลังประมวลผลอัลกอริทึมและสร้างแบบจำลอง...")
        
        # --- ลอจิกการแบ่งเงิน ---
        # 1. เงินที่ใช้จัดพอร์ตหลัก 7 กองทุน
        available_core_capital = gpf_current_balance - vayupak_amount 
        monthly_inflow = current_salary * ((8 + extra_saving_pct) / 100)
        target_vol = target_vol_limit_pct / 100.0
        has_vayupak = vayupak_amount > 0
        
        # --- 1. เตรียมพอร์ต DIY ---
        diy_weights = np.array([my_new_portfolio.get(f, 0) for f in core_funds]) / 100.0
        diy_ret = np.sum(mean_returns_core * diy_weights)
        diy_vol = np.sqrt(np.dot(diy_weights.T, np.dot(cov_matrix_core, diy_weights)))
        
        # --- 2. คำนวณ AI Portfolios ---
        all_weights, ret_arr, vol_arr, sharpe_arr, max_sharpe_idx, target_risk_idx = calculate_ai_portfolios(
            target_vol, 0.025, core_funds, mean_returns_core, cov_matrix_core, has_vayupak
        )
        progress_bar.progress(40)
        
        # --- 3. คำนวณ HRP ---
        hrp_weights, hrp_ret, hrp_vol, is_bull = calculate_tactical_hrp(
            core_funds, returns_core, mean_returns_core, cov_matrix_core, has_vayupak
        )
        progress_bar.progress(60)
        
        # โชว์สถานะตลาด
        market_status = "ภาวะตลาดกระทิง (เน้นเติบโต 80%)" if is_bull else "ภาวะตลาดหมี (เน้นตั้งรับ 60%)"
        st.success(f"📡 ข้อมูลเชิงลึกจากระบบ: ตรวจพบ {market_status}")
        if has_vayupak:
            st.info("⚖️ ตรวจพบยอดเงินวายุภักษ์: ระบบเปิดใช้งานการจำกัดเพดานแผนทองคำที่ 25% โดยอัตโนมัติ")

        # --- 4. วาดกราฟ Efficient Frontier ---
        bg_color, text_color, grid_color = '#1E1E1E', 'white', '#404040'
        cmap_or_rd = LinearSegmentedColormap.from_list("OrangeRed", ["#FFA500", "#FF0000"])

        fig, ax = plt.subplots(figsize=(12, 5))
        fig.patch.set_facecolor(bg_color)
        ax.set_facecolor(bg_color)

        ax.scatter(vol_arr * 100, ret_arr * 100, c=sharpe_arr, cmap=cmap_or_rd, marker='o', alpha=0.05)
        ax.scatter(vol_arr[max_sharpe_idx] * 100, ret_arr[max_sharpe_idx] * 100, color='white', marker='*', s=250, edgecolors='black', label='พอร์ตประสิทธิภาพสูงสุด (Max Sharpe)')
        ax.scatter(hrp_vol * 100, hrp_ret * 100, color='lime', marker='s', s=250, edgecolors='black', label='พอร์ตกระจายความเสี่ยง (HRP)')
        ax.scatter(vol_arr[target_risk_idx] * 100, ret_arr[target_risk_idx] * 100, color='cyan', marker='P', s=250, edgecolors='black', label=f'พอร์ตความเสี่ยงเป้าหมาย (≤{target_vol_limit_pct}%)')
        ax.scatter(diy_vol * 100, diy_ret * 100, color='#FF3399', marker='X', s=400, edgecolors='white', label='พอร์ตกำหนดเอง (Custom)')

        ax.set_title('เส้นขอบเขตประสิทธิภาพการลงทุน (Efficient Frontier)', fontsize=16, fontweight='bold', color=text_color)
        ax.set_xlabel('ความเสี่ยง (Volatility) % ต่อปี', color=text_color)
        ax.set_ylabel('ผลตอบแทนคาดหวัง (Return) % ต่อปี', color=text_color)
        ax.tick_params(colors=text_color)
        ax.grid(True, linestyle='--', alpha=0.5, color=grid_color)
        ax.legend(loc='upper left', fontsize=10, facecolor='#2C2C2C', edgecolor=text_color, labelcolor=text_color)
        
        st.pyplot(fig)
        progress_bar.progress(80)

        # --- 5. การจำลอง Monte Carlo (30 วัน) ---
        forecast_days, n_sims = 30, 500
        f_dates = pd.bdate_range(start=forecast_start_date, periods=forecast_days)
        
        # จัดการเงินสมทบ
        f_inflows = np.zeros(forecast_days)
        f_ends = f_dates[:-1][f_dates.month[:-1] != f_dates.month[1:]].tolist()
        if f_dates[-1].day >= 25: f_ends.append(f_dates[-1])
        for i, dt in enumerate(f_dates):
            if dt in f_ends: f_inflows[i] = monthly_inflow

        # จำลองกองทุนวายุภักษ์ (ใช้ Mean 0.03/252 ป้องกัน Error กรณีไม่มีข้อมูลใน Excel)
        vayupak_paths = np.zeros((forecast_days, n_sims))
        vayupak_paths[0] = vayupak_amount
        if has_vayupak:
            np.random.seed(99)
            # จำลองผลตอบแทนวายุภักษ์แบบอนุรักษ์นิยม (ไม่ผันผวนมาก)
            v_shocks = np.random.normal(loc=0.03/252, scale=0.01/np.sqrt(252), size=(forecast_days, n_sims))
            for t in range(1, forecast_days):
                vayupak_paths[t] = vayupak_paths[t-1] * (1 + v_shocks[t])

        def simulate_total_portfolio(weights):
            mu, std = returns_core.dot(weights).mean(), returns_core.dot(weights).std()
            np.random.seed(42)
            shocks = np.random.normal(loc=mu, scale=std, size=(forecast_days, n_sims))
            
            # จำลองพอร์ตหลัก (เริ่มต้นที่ available_core_capital)
            core_paths = np.zeros((forecast_days, n_sims))
            core_paths[0] = available_core_capital
            
            for t in range(1, forecast_days): 
                core_paths[t] = core_paths[t-1] * (1 + shocks[t]) + f_inflows[t]
                
            # รวมพอร์ตหลัก + วายุภักษ์
            total_paths = core_paths + vayupak_paths
            return total_paths.mean(axis=1), np.percentile(total_paths, 5, axis=1)

        m_diy, l_diy = simulate_total_portfolio(diy_weights)
        m_hrp, l_hrp = simulate_total_portfolio(hrp_weights)
        m_tgt, l_tgt = simulate_total_portfolio(all_weights[target_risk_idx])
        m_max, l_max = simulate_total_portfolio(all_weights[max_sharpe_idx])

        fig2, ax2 = plt.subplots(figsize=(12, 5))
        fig2.patch.set_facecolor(bg_color)
        ax2.set_facecolor(bg_color)

        ax2.plot(f_dates, m_diy, color='#FF3399', linewidth=3, label='มูลค่าคาดหวัง - พอร์ตกำหนดเอง (Custom)')
        ax2.plot(f_dates, m_hrp, color='lime', linewidth=2, linestyle='--', label='มูลค่าคาดหวัง - พอร์ตกระจายความเสี่ยง (HRP)')
        ax2.plot(f_dates, m_tgt, color='cyan', linewidth=2, linestyle='--', label='มูลค่าคาดหวัง - พอร์ตความเสี่ยงเป้าหมาย')

        ax2.set_title(f'แบบจำลองพยากรณ์มูลค่าพอร์ตลงทุน (30 วันทำการถัดไป)', fontsize=16, fontweight='bold', color=text_color)
        ax2.set_xlabel('วันที่พยากรณ์', color=text_color)
        ax2.set_ylabel('มูลค่าพอร์ตสุทธิ (บาท)', color=text_color)
        ax2.tick_params(colors=text_color, rotation=45)
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
        ax2.grid(True, linestyle='--', alpha=0.5, color=grid_color)
        ax2.legend(loc='upper left', fontsize=10, facecolor='#2C2C2C', edgecolor=text_color, labelcolor=text_color)
        
        st.pyplot(fig2)

        # --- 6. รายงานสรุปผลเชิงสถิติ ---
        f_invested = gpf_current_balance + f_inflows.sum()
        st.markdown("---")
        st.subheader("📑 รายงานสรุปผลการวิเคราะห์และพยากรณ์")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**เงินทุนตั้งต้นรวม:** {gpf_current_balance:,.2f} บาท")
            if has_vayupak:
                st.markdown(f"*(แบ่งเป็นกองทุนวายุภักษ์: {vayupak_amount:,.2f} บาท)*")
        with col2:
            st.markdown(f"**เงินสมทบคาดการณ์ ({forecast_days} วัน):** {f_inflows.sum():,.2f} บาท")
            st.markdown(f"**ต้นทุนรวมสุทธิ:** {f_invested:,.2f} บาท")
        
        def display_forecast(name, m_val, l_val):
            profit = m_val - f_invested
            worst_profit = l_val - f_invested
            return (f"**{name}** -> กำไรคาดหวัง: **{profit:+,.2f}** บาท | กรณีเลวร้าย (VaR 5%): **{worst_profit:+,.2f}** บาท  \n"
                    f"*(ช่วงมูลค่าพอร์ตสุทธิ: **{l_val:,.2f}** ถึง **{m_val:,.2f}** บาท)*")

        st.info(display_forecast("พอร์ตกำหนดเอง (Custom)", m_diy[-1], l_diy[-1]))
        st.info(display_forecast("พอร์ตกระจายความเสี่ยง (HRP)", m_hrp[-1], l_hrp[-1]))
        st.info(display_forecast("พอร์ตความเสี่ยงเป้าหมาย", m_tgt[-1], l_tgt[-1]))
        st.info(display_forecast("พอร์ตประสิทธิภาพสูงสุด (Max Sharpe)", m_max[-1], l_max[-1]))

        st.markdown("#### 📊 ตารางสรุปสัดส่วนแผนการลงทุนที่แนะนำ (%)")
        df_alloc = pd.DataFrame({
            'พอร์ตกำหนดเอง (Custom)': diy_weights * 100,
            'พอร์ต HRP': hrp_weights * 100,
            f'พอร์ตความเสี่ยงเป้าหมาย (≤{target_vol_limit_pct}%)': all_weights[target_risk_idx] * 100,
            'พอร์ต Max Sharpe': all_weights[max_sharpe_idx] * 100
        }, index=core_funds)
        
        st.dataframe(df_alloc.style.format("{:.2f}%"))
        
        progress_bar.progress(100)

        st.balloons()



