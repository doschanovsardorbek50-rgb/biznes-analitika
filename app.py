import io
import re
import sqlite3
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

# =========================================================
# 1. SAHIFA SOZLAMALARI VA ZAMONAVIY SODDA DIZAYN (CSS)
# =========================================================
st.set_page_config(
    page_title="Biznes Yordamchi — Moliyaviy Tahlil",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    /* Umumiy fon va shrift */
    .stApp {
        background-color: #F6F8FB;
        color: #1E293B;
    }
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2.5rem;
        max-width: 1280px;
    }
    /* Yon menyu (Sidebar) */
    section[data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E2E8F0;
    }
    section[data-testid="stSidebar"] .stRadio > div {
        gap: 6px;
    }
    section[data-testid="stSidebar"] .stRadio label {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 10px 14px !important;
        transition: all 0.15s ease;
        cursor: pointer;
        font-weight: 500;
    }
    section[data-testid="stSidebar"] .stRadio label:hover {
        background-color: #EFF6FF;
        border-color: #93C5FD;
    }
    /* Yuqori sarlavha kartasi */
    .hero-card {
        background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 100%);
        color: #FFFFFF;
        padding: 22px 26px;
        border-radius: 16px;
        margin-bottom: 18px;
        box-shadow: 0 4px 14px rgba(30, 58, 138, 0.14);
    }
    .hero-title {
        font-size: 1.55rem;
        font-weight: 700;
        margin: 0 0 6px 0;
        color: #FFFFFF;
    }
    .hero-sub {
        font-size: 0.96rem;
        opacity: 0.92;
        margin: 0;
        color: #E0E7FF;
    }
    /* Metrika kartalari */
    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 18px 20px;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.04);
        height: 100%;
    }
    .kpi-label {
        font-size: 0.85rem;
        color: #64748B;
        font-weight: 600;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 1.45rem;
        font-weight: 700;
        color: #0F172A;
        margin-bottom: 4px;
    }
    .kpi-note {
        font-size: 0.82rem;
        font-weight: 500;
    }
    .kpi-good { color: #15803D; }
    .kpi-warn { color: #B45309; }
    .kpi-bad  { color: #B91C1C; }
    .kpi-muted { color: #64748B; }

    /* Muammo va tavsiya kartalari */
    .issue-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-left: 5px solid #2563EB;
        border-radius: 12px;
        padding: 16px 18px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }
    .issue-high { border-left-color: #DC2626; }
    .issue-mid  { border-left-color: #D97706; }
    .issue-low  { border-left-color: #16A34A; }

    /* Oddiy yordamchi banner */
    .hint-box {
        background: #EFF6FF;
        border: 1px solid #BFDBFE;
        border-radius: 12px;
        padding: 14px 18px;
        color: #1E3A8A;
        margin-bottom: 14px;
        font-size: 0.93rem;
    }
    /* Streamlit standart elementlarini chiroyliroq qilish */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 14px 16px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 8px 16px;
        font-weight: 600;
        color: #334155;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1E3A8A !important;
        color: #FFFFFF !important;
        border-color: #1E3A8A !important;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# =========================================================
# 2. MA'LUMOTLAR BAZASI (SQLITE) VA SOHA ME'YORLARI
# =========================================================
DB_PATH = "biznes_yordamchi.db"

SOHALAR = {
    "Savdo (Do'kon / Ulgurji)": {"min_marja": 12.0, "max_ombor_kun": 45, "max_qarz_kun": 25},
    "Ishlab chiqarish": {"min_marja": 15.0, "max_ombor_kun": 60, "max_qarz_kun": 35},
    "Xizmat ko'rsatish": {"min_marja": 22.0, "max_ombor_kun": 15, "max_qarz_kun": 20},
    "Umumiy ovqatlanish (Kafe / Restoran)": {"min_marja": 18.0, "max_ombor_kun": 10, "max_qarz_kun": 10},
    "Qurilish va ta'mirlash": {"min_marja": 14.0, "max_ombor_kun": 50, "max_qarz_kun": 40},
}

DEFAULT_PROFILE = {
    "davr_kun": 30,
    "jami_mijozlar": 120,
    "yangi_mijozlar": 25,
    "qayta_mijozlar": 55,
    "reklama_xarajati": 6_000_000.0,
    "mijoz_davomiyligi_oy": 8.0,
    "top3_mijoz_ulushi": 35.0,
    "xodimlar_soni": 10,
    "oylik_fondi": 40_000_000.0,
    "ketgan_xodimlar": 1,
    "reja_bajarilishi": 80.0,
    "brak_qaytarilish": 3.0,
    "bajarilish_vaqti_kun": 2.0,
    "quvvat_bandligi": 75.0,
    "asosiy_yetkazuvchi_ulushi": 40.0,
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            sector TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'so''m',
            cash_balance REAL NOT NULL DEFAULT 0,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            tx_date TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Umumiy',
            item_name TEXT NOT NULL,
            qty REAL NOT NULL DEFAULT 1,
            revenue REAL NOT NULL DEFAULT 0,
            cogs REAL NOT NULL DEFAULT 0,
            opex REAL NOT NULL DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            counterparty TEXT NOT NULL,
            debt_type TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Faol'
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Umumiy',
            qty REAL NOT NULL DEFAULT 0,
            unit_cost REAL NOT NULL DEFAULT 0,
            last_sale_date TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS company_profile (
            company_id INTEGER PRIMARY KEY,
            davr_kun INTEGER DEFAULT 30,
            jami_mijozlar INTEGER DEFAULT 120,
            yangi_mijozlar INTEGER DEFAULT 25,
            qayta_mijozlar INTEGER DEFAULT 55,
            reklama_xarajati REAL DEFAULT 6000000,
            mijoz_davomiyligi_oy REAL DEFAULT 8,
            top3_mijoz_ulushi REAL DEFAULT 35,
            xodimlar_soni INTEGER DEFAULT 10,
            oylik_fondi REAL DEFAULT 40000000,
            ketgan_xodimlar INTEGER DEFAULT 1,
            reja_bajarilishi REAL DEFAULT 80,
            brak_qaytarilish REAL DEFAULT 3,
            bajarilish_vaqti_kun REAL DEFAULT 2,
            quvvat_bandligi REAL DEFAULT 75,
            asosiy_yetkazuvchi_ulushi REAL DEFAULT 40
        )
        """
    )
    conn.commit()
    conn.close()


def ensure_default_company():
    conn = get_conn()
    cnt = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    if cnt == 0:
        conn.execute(
            "INSERT INTO companies (name, sector, currency, cash_balance, created_at) VALUES (?, ?, ?, ?, ?)",
            ("Mening Korxonam", "Savdo (Do'kon / Ulgurji)", "so'm", 45_000_000.0, datetime.now().isoformat()),
        )
        conn.commit()
    conn.close()


def list_companies() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM companies ORDER BY id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_company(name: str, sector: str, currency: str, cash_balance: float) -> tuple:
    clean = str(name).strip()
    if not clean:
        return False, "Korxona nomini kiriting."
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO companies (name, sector, currency, cash_balance, created_at) VALUES (?, ?, ?, ?, ?)",
            (clean, sector, currency, float(cash_balance), datetime.now().isoformat()),
        )
        conn.commit()
        return True, f"'{clean}' korxonasi qo'shildi."
    except sqlite3.IntegrityError:
        return False, "Bu nomdagi korxona allaqachon mavjud."
    finally:
        conn.close()


def update_company_cash(company_id: int, cash_balance: float):
    conn = get_conn()
    conn.execute("UPDATE companies SET cash_balance = ? WHERE id = ?", (float(cash_balance), int(company_id)))
    conn.commit()
    conn.close()


def delete_company(company_id: int):
    conn = get_conn()
    for tbl in ("transactions", "debts", "inventory", "company_profile"):
        conn.execute(f"DELETE FROM {tbl} WHERE company_id = ?", (int(company_id),))
    conn.execute("DELETE FROM companies WHERE id = ?", (int(company_id),))
    conn.commit()
    conn.close()


def load_table(table: str, company_id: int) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(f"SELECT * FROM {table} WHERE company_id = ?", conn, params=(int(company_id),))
    conn.close()
    return df


def replace_transactions(company_id: int, df: pd.DataFrame):
    conn = get_conn()
    conn.execute("DELETE FROM transactions WHERE company_id = ?", (int(company_id),))
    if df is not None and not df.empty:
        rows = []
        for _, r in df.iterrows():
            rows.append((
                int(company_id),
                _clean_date_str(r.get("tx_date")),
                _clean_text(r.get("category"), "Umumiy"),
                _clean_text(r.get("item_name"), "Nomsiz mahsulot"),
                _clean_num(r.get("qty"), 1.0),
                _clean_num(r.get("revenue"), 0.0),
                _clean_num(r.get("cogs"), 0.0),
                _clean_num(r.get("opex"), 0.0),
            ))
        conn.executemany(
            """
            INSERT INTO transactions (company_id, tx_date, category, item_name, qty, revenue, cogs, opex)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    conn.commit()
    conn.close()


def append_transactions(company_id: int, df: pd.DataFrame):
    if df is None or df.empty:
        return
    conn = get_conn()
    rows = []
    for _, r in df.iterrows():
        rows.append((
            int(company_id),
            _clean_date_str(r.get("tx_date")),
            _clean_text(r.get("category"), "Umumiy"),
            _clean_text(r.get("item_name"), "Nomsiz mahsulot"),
            _clean_num(r.get("qty"), 1.0),
            _clean_num(r.get("revenue"), 0.0),
            _clean_num(r.get("cogs"), 0.0),
            _clean_num(r.get("opex"), 0.0),
        ))
    conn.executemany(
        """
        INSERT INTO transactions (company_id, tx_date, category, item_name, qty, revenue, cogs, opex)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def replace_debts(company_id: int, df: pd.DataFrame):
    conn = get_conn()
    conn.execute("DELETE FROM debts WHERE company_id = ?", (int(company_id),))
    if df is not None and not df.empty:
        rows = []
        for _, r in df.iterrows():
            rows.append((
                int(company_id),
                _clean_text(r.get("counterparty"), "Noma'lum hamkor"),
                _normalize_debt_type(r.get("debt_type")),
                _clean_num(r.get("amount"), 0.0),
                _clean_date_str(r.get("due_date")),
                _normalize_debt_status(r.get("status"), _clean_date_str(r.get("due_date"))),
            ))
        conn.executemany(
            "INSERT INTO debts (company_id, counterparty, debt_type, amount, due_date, status) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    conn.commit()
    conn.close()


def replace_inventory(company_id: int, df: pd.DataFrame):
    conn = get_conn()
    conn.execute("DELETE FROM inventory WHERE company_id = ?", (int(company_id),))
    if df is not None and not df.empty:
        rows = []
        for _, r in df.iterrows():
            rows.append((
                int(company_id),
                _clean_text(r.get("item_name"), "Nomsiz tovar"),
                _clean_text(r.get("category"), "Umumiy"),
                _clean_num(r.get("qty"), 0.0),
                _clean_num(r.get("unit_cost"), 0.0),
                _clean_date_str(r.get("last_sale_date")),
            ))
        conn.executemany(
            "INSERT INTO inventory (company_id, item_name, category, qty, unit_cost, last_sale_date) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    conn.commit()
    conn.close()


def load_profile(company_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM company_profile WHERE company_id = ?", (int(company_id),)).fetchone()
    conn.close()
    res = dict(DEFAULT_PROFILE)
    if row is not None:
        for k in DEFAULT_PROFILE:
            if k in row.keys() and row[k] is not None:
                res[k] = row[k]
    return res


def save_profile(company_id: int, data: dict):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO company_profile (
            company_id, davr_kun, jami_mijozlar, yangi_mijozlar, qayta_mijozlar,
            reklama_xarajati, mijoz_davomiyligi_oy, top3_mijoz_ulushi,
            xodimlar_soni, oylik_fondi, ketgan_xodimlar, reja_bajarilishi,
            brak_qaytarilish, bajarilish_vaqti_kun, quvvat_bandligi, asosiy_yetkazuvchi_ulushi
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            davr_kun=excluded.davr_kun,
            jami_mijozlar=excluded.jami_mijozlar,
            yangi_mijozlar=excluded.yangi_mijozlar,
            qayta_mijozlar=excluded.qayta_mijozlar,
            reklama_xarajati=excluded.reklama_xarajati,
            mijoz_davomiyligi_oy=excluded.mijoz_davomiyligi_oy,
            top3_mijoz_ulushi=excluded.top3_mijoz_ulushi,
            xodimlar_soni=excluded.xodimlar_soni,
            oylik_fondi=excluded.oylik_fondi,
            ketgan_xodimlar=excluded.ketgan_xodimlar,
            reja_bajarilishi=excluded.reja_bajarilishi,
            brak_qaytarilish=excluded.brak_qaytarilish,
            bajarilish_vaqti_kun=excluded.bajarilish_vaqti_kun,
            quvvat_bandligi=excluded.quvvat_bandligi,
            asosiy_yetkazuvchi_ulushi=excluded.asosiy_yetkazuvchi_ulushi
        """,
        (
            int(company_id),
            int(data["davr_kun"]),
            int(data["jami_mijozlar"]),
            int(data["yangi_mijozlar"]),
            int(data["qayta_mijozlar"]),
            float(data["reklama_xarajati"]),
            float(data["mijoz_davomiyligi_oy"]),
            float(data["top3_mijoz_ulushi"]),
            int(data["xodimlar_soni"]),
            float(data["oylik_fondi"]),
            int(data["ketgan_xodimlar"]),
            float(data["reja_bajarilishi"]),
            float(data["brak_qaytarilish"]),
            float(data["bajarilish_vaqti_kun"]),
            float(data["quvvat_bandligi"]),
            float(data["asosiy_yetkazuvchi_ulushi"]),
        ),
    )
    conn.commit()
    conn.close()


# =========================================================
# 3. XATOSIZ TOZALASH VA YORDAMCHI FUNKSIYALAR
# =========================================================
def _clean_text(val, default: str = "Umumiy") -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return default
    return s


def _clean_num(val, default: float = 0.0) -> float:
    if val is None:
        return float(default)
    if isinstance(val, (int, float, np.number)):
        if np.isnan(val) or np.isinf(val):
            return float(default)
        return float(val)
    s = str(val).strip().replace(" ", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s) if s else float(default)
    except Exception:
        return float(default)


def _clean_date_str(val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return date.today().strftime("%Y-%m-%d")
    if isinstance(val, (datetime, date, pd.Timestamp)):
        try:
            if pd.isna(val):
                return date.today().strftime("%Y-%m-%d")
            return val.strftime("%Y-%m-%d")
        except Exception:
            return date.today().strftime("%Y-%m-%d")
    parsed = pd.to_datetime(str(val).strip(), errors="coerce")
    if pd.isna(parsed):
        return date.today().strftime("%Y-%m-%d")
    return parsed.strftime("%Y-%m-%d")


def _normalize_debt_type(val) -> str:
    s = _clean_text(val, "Bizga qarzdor").lower()
    if any(k in s for k in ("kred", "cred", "bizning", "berish", "yetkaz")):
        return "Bizning qarzimiz"
    return "Bizga qarzdor"


def _normalize_debt_status(val, due_date_str: str) -> str:
    s = _clean_text(val, "").lower()
    if "to'lan" in s or "yopil" in s or "paid" in s:
        return "To'langan"
    if "kechik" in s or "over" in s:
        return "Kechikkan"
    try:
        d = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        if d < date.today():
            return "Kechikkan"
    except Exception:
        pass
    return "Muddatida"


def fmt_pul(val: float, curr: str = "so'm") -> str:
    try:
        return f"{float(val):,.0f} {curr}".replace(",", " ")
    except Exception:
        return f"0 {curr}"


def clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, val)))


def load_demo_data(company_id: int):
    """Birinchi kirgan odam 1 tugma bilan tizimni sinab ko'rishi uchun tayyor namuna ma'lumotlar."""
    today = date.today()
    tx_rows = [
        ((today - timedelta(days=28)).strftime("%Y-%m-%d"), "Noutbuklar", "Lenovo IdeaPad 3", 3, 21_600_000, 17_400_000, 950_000),
        ((today - timedelta(days=26)).strftime("%Y-%m-%d"), "Smartfonlar", "Samsung Galaxy A55", 5, 22_500_000, 18_500_000, 800_000),
        ((today - timedelta(days=24)).strftime("%Y-%m-%d"), "Aksessuarlar", "Sichqoncha va Klaviatura", 18, 4_500_000, 2_700_000, 300_000),
        ((today - timedelta(days=21)).strftime("%Y-%m-%d"), "Monitorlar", "Dell 24 Monitor", 4, 9_600_000, 7_600_000, 450_000),
        ((today - timedelta(days=18)).strftime("%Y-%m-%d"), "Noutbuklar", "HP Pavilion 15", 2, 16_400_000, 13_600_000, 700_000),
        ((today - timedelta(days=15)).strftime("%Y-%m-%d"), "Smartfonlar", "Redmi Note 13 Pro", 6, 19_800_000, 16_200_000, 650_000),
        ((today - timedelta(days=13)).strftime("%Y-%m-%d"), "Printerlar", "HP LaserJet M111w", 2, 4_800_000, 4_600_000, 500_000),
        ((today - timedelta(days=10)).strftime("%Y-%m-%d"), "Noutbuklar", "Lenovo IdeaPad 3", 4, 28_800_000, 23_200_000, 1_100_000),
        ((today - timedelta(days=8)).strftime("%Y-%m-%d"), "Smartfonlar", "Samsung Galaxy A55", 4, 18_000_000, 14_800_000, 650_000),
        ((today - timedelta(days=5)).strftime("%Y-%m-%d"), "Printerlar", "Epson Rangli Printer", 1, 2_950_000, 2_850_000, 350_000),
        ((today - timedelta(days=3)).strftime("%Y-%m-%d"), "Monitorlar", "Dell 24 Monitor", 3, 7_200_000, 5_700_000, 320_000),
        ((today - timedelta(days=1)).strftime("%Y-%m-%d"), "Aksessuarlar", "USB Fleshka 64GB", 30, 3_000_000, 1_800_000, 180_000),
    ]
    tx_df = pd.DataFrame(tx_rows, columns=["tx_date", "category", "item_name", "qty", "revenue", "cogs", "opex"])

    debt_rows = [
        ("MegaSavdo MChJ", "Bizga qarzdor", 18_500_000, (today - timedelta(days=14)).strftime("%Y-%m-%d"), "Kechikkan"),
        ("Samarqand Ofis Servis", "Bizga qarzdor", 9_200_000, (today + timedelta(days=12)).strftime("%Y-%m-%d"), "Muddatida"),
        ("Aloqa Savdo Markazi", "Bizga qarzdor", 7_400_000, (today - timedelta(days=25)).strftime("%Y-%m-%d"), "Kechikkan"),
        ("TexnoImport Ulgurji", "Bizning qarzimiz", 21_000_000, (today + timedelta(days=8)).strftime("%Y-%m-%d"), "Muddatida"),
        ("Tezkor Logistika", "Bizning qarzimiz", 4_800_000, (today - timedelta(days=5)).strftime("%Y-%m-%d"), "Kechikkan"),
    ]
    debts_df = pd.DataFrame(debt_rows, columns=["counterparty", "debt_type", "amount", "due_date", "status"])

    inv_rows = [
        ("Lenovo IdeaPad 3", "Noutbuklar", 7, 5_800_000, (today - timedelta(days=10)).strftime("%Y-%m-%d")),
        ("Samsung Galaxy A55", "Smartfonlar", 11, 3_700_000, (today - timedelta(days=8)).strftime("%Y-%m-%d")),
        ("Dell 24 Monitor", "Monitorlar", 6, 1_900_000, (today - timedelta(days=3)).strftime("%Y-%m-%d")),
        ("Eski VGA Kabel 3m", "Aksessuarlar", 45, 35_000, (today - timedelta(days=140)).strftime("%Y-%m-%d")),
        ("Eski Planshet G'ilofi", "Aksessuarlar", 32, 65_000, (today - timedelta(days=165)).strftime("%Y-%m-%d")),
    ]
    inv_df = pd.DataFrame(inv_rows, columns=["item_name", "category", "qty", "unit_cost", "last_sale_date"])

    replace_transactions(company_id, tx_df)
    replace_debts(company_id, debts_df)
    replace_inventory(company_id, inv_df)
    update_company_cash(company_id, 45_000_000.0)
    save_profile(company_id, {
        **DEFAULT_PROFILE,
        "top3_mijoz_ulushi": 52.0,
        "brak_qaytarilish": 4.5,
        "oylik_fondi": 44_000_000.0,
    })


# =========================================================
# 4. EXCEL SHABLON YARATISH VA XATOSIZ YUKLASH
# =========================================================
def build_excel_template() -> bytes:
    today = date.today()
    ops_df = pd.DataFrame([
        {
            "Sana": today.strftime("%Y-%m-%d"),
            "Bo'lim": "Noutbuklar",
            "Mahsulot nomi": "Lenovo IdeaPad 3",
            "Miqdor": 2,
            "Tushum": 14400000,
            "Tannarx": 11600000,
            "Boshqa xarajat": 600000,
        },
        {
            "Sana": (today - timedelta(days=2)).strftime("%Y-%m-%d"),
            "Bo'lim": "Aksessuarlar",
            "Mahsulot nomi": "Sichqoncha",
            "Miqdor": 10,
            "Tushum": 1800000,
            "Tannarx": 1100000,
            "Boshqa xarajat": 120000,
        },
    ])
    debts_df = pd.DataFrame([
        {
            "Hamkor nomi": "Baraka Savdo MChJ",
            "Qarz turi": "Bizga qarzdor",
            "Summa": 12000000,
            "To'lov muddati": (today + timedelta(days=15)).strftime("%Y-%m-%d"),
            "Holati": "Muddatida",
        }
    ])
    inv_df = pd.DataFrame([
        {
            "Mahsulot nomi": "Lenovo IdeaPad 3",
            "Bo'lim": "Noutbuklar",
            "Qoldiq soni": 5,
            "Birlik tannarxi": 5800000,
            "Oxirgi sotilgan sana": today.strftime("%Y-%m-%d"),
        }
    ])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        ops_df.to_excel(writer, sheet_name="Savdo", index=False)
        debts_df.to_excel(writer, sheet_name="Qarzlar", index=False)
        inv_df.to_excel(writer, sheet_name="Ombor", index=False)
    return buf.getvalue()


def _find_col(df: pd.DataFrame, aliases: list):
    cols = {str(c).lower().strip(): c for c in df.columns}
    for a in aliases:
        if a.lower() in cols:
            return cols[a.lower()]
    for a in aliases:
        al = a.lower()
        for k, orig in cols.items():
            if al in k:
                return orig
    return None


def parse_uploaded_excel(file_bytes: bytes) -> dict:
    """Har qanday Excel faylini bo'sh qatorlar va NaN lardan tozalab xatosiz o'qiydi."""
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheet_names = xls.sheet_names
    result = {"tx": pd.DataFrame(), "debts": pd.DataFrame(), "inv": pd.DataFrame(), "messages": []}

    tx_sheet = None
    debt_sheet = None
    inv_sheet = None

    for s in sheet_names:
        sl = s.lower()
        if any(k in sl for k in ("savdo", "operat", "trans", "sotuv", "data")):
            tx_sheet = tx_sheet or s
        elif any(k in sl for k in ("qarz", "debt")):
            debt_sheet = debt_sheet or s
        elif any(k in sl for k in ("ombor", "inv", "zaxira", "sklad")):
            inv_sheet = inv_sheet or s

    if tx_sheet is None and len(sheet_names) >= 1:
        tx_sheet = sheet_names[0]

    # 1. Savdo varag'ini o'qish
    if tx_sheet:
        raw = pd.read_excel(xls, sheet_name=tx_sheet).dropna(how="all")
        if not raw.empty:
            c_date = _find_col(raw, ["sana", "date", "tx_date"])
            c_cat = _find_col(raw, ["bo'lim", "guruh", "category", "filial", "tur"])
            c_item = _find_col(raw, ["mahsulot nomi", "mahsulot", "item_name", "sku", "nomi", "product"])
            c_qty = _find_col(raw, ["miqdor", "soni", "qty", "sotilgan"])
            c_rev = _find_col(raw, ["tushum", "savdo", "revenue", "summa"])
            c_cogs = _find_col(raw, ["tannarx", "cogs", "xarid"])
            c_opex = _find_col(raw, ["boshqa xarajat", "operatsion xarajat", "opex", "xarajat"])

            rows = []
            for _, r in raw.iterrows():
                rev_v = _clean_num(r[c_rev], 0.0) if c_rev else 0.0
                cogs_v = _clean_num(r[c_cogs], 0.0) if c_cogs else 0.0
                opex_v = _clean_num(r[c_opex], 0.0) if c_opex else 0.0
                item_v = _clean_text(r[c_item], "") if c_item else ""
                if not item_v and rev_v == 0 and cogs_v == 0 and opex_v == 0:
                    continue
                if item_v.lower() in ("jami", "itogo", "total", "всего"):
                    continue
                rows.append({
                    "tx_date": _clean_date_str(r[c_date]) if c_date else date.today().strftime("%Y-%m-%d"),
                    "category": _clean_text(r[c_cat], "Umumiy") if c_cat else "Umumiy",
                    "item_name": item_v or "Nomsiz mahsulot",
                    "qty": max(_clean_num(r[c_qty], 1.0), 0.0) if c_qty else 1.0,
                    "revenue": rev_v,
                    "cogs": cogs_v,
                    "opex": opex_v,
                })
            if rows:
                result["tx"] = pd.DataFrame(rows)
                result["messages"].append(f"'{tx_sheet}' varag'idan {len(rows)} ta savdo qatori o'qildi.")

    # 2. Qarzlar varag'i
    if debt_sheet:
        raw_d = pd.read_excel(xls, sheet_name=debt_sheet).dropna(how="all")
        if not raw_d.empty:
            c_cp = _find_col(raw_d, ["hamkor", "kontragent", "mijoz", "counterparty", "nomi"])
            c_type = _find_col(raw_d, ["qarz turi", "turi", "type", "debt_type"])
            c_amt = _find_col(raw_d, ["summa", "amount", "qoldiq"])
            c_due = _find_col(raw_d, ["muddat", "due", "sana"])
            c_st = _find_col(raw_d, ["holat", "status"])
            d_rows = []
            for _, r in raw_d.iterrows():
                amt_v = _clean_num(r[c_amt], 0.0) if c_amt else 0.0
                cp_v = _clean_text(r[c_cp], "") if c_cp else ""
                if not cp_v and amt_v == 0:
                    continue
                due_s = _clean_date_str(r[c_due]) if c_due else date.today().strftime("%Y-%m-%d")
                d_rows.append({
                    "counterparty": cp_v or "Noma'lum hamkor",
                    "debt_type": _normalize_debt_type(r[c_type]) if c_type else "Bizga qarzdor",
                    "amount": amt_v,
                    "due_date": due_s,
                    "status": _normalize_debt_status(r[c_st] if c_st else "", due_s),
                })
            if d_rows:
                result["debts"] = pd.DataFrame(d_rows)
                result["messages"].append(f"'{debt_sheet}' varag'idan {len(d_rows)} ta qarz qatori o'qildi.")

    # 3. Ombor varag'i
    if inv_sheet:
        raw_i = pd.read_excel(xls, sheet_name=inv_sheet).dropna(how="all")
        if not raw_i.empty:
            c_item = _find_col(raw_i, ["mahsulot", "item", "tovar", "nomi"])
            c_cat = _find_col(raw_i, ["bo'lim", "guruh", "category"])
            c_qty = _find_col(raw_i, ["qoldiq", "miqdor", "soni", "qty"])
            c_cost = _find_col(raw_i, ["tannarx", "narx", "cost"])
            c_last = _find_col(raw_i, ["oxirgi", "sana", "last_sale"])
            i_rows = []
            for _, r in raw_i.iterrows():
                item_v = _clean_text(r[c_item], "") if c_item else ""
                qty_v = _clean_num(r[c_qty], 0.0) if c_qty else 0.0
                if not item_v and qty_v == 0:
                    continue
                i_rows.append({
                    "item_name": item_v or "Nomsiz tovar",
                    "category": _clean_text(r[c_cat], "Umumiy") if c_cat else "Umumiy",
                    "qty": qty_v,
                    "unit_cost": _clean_num(r[c_cost], 0.0) if c_cost else 0.0,
                    "last_sale_date": _clean_date_str(r[c_last]) if c_last else date.today().strftime("%Y-%m-%d"),
                })
            if i_rows:
                result["inv"] = pd.DataFrame(i_rows)
                result["messages"].append(f"'{inv_sheet}' varag'idan {len(i_rows)} ta ombor qatori o'qildi.")

    return result


# =========================================================
# 5. YAGONA TAHLIL DVIGATELI (100% O'ZBEKCHA VA TUSHUNARLI)
# =========================================================
def compute_full_analysis(company: dict, tx_df: pd.DataFrame, debts_df: pd.DataFrame, inv_df: pd.DataFrame, prof: dict) -> dict:
    sector_norm = SOHALAR.get(company["sector"], SOHALAR["Savdo (Do'kon / Ulgurji)"])
    days = max(int(prof["davr_kun"]), 1)

    # --- 1. Foyda va Zarar ---
    if tx_df is not None and not tx_df.empty:
        tdf = tx_df.copy()
        for c in ("qty", "revenue", "cogs", "opex"):
            tdf[c] = pd.to_numeric(tdf[c], errors="coerce").fillna(0.0)
        tdf["foyda"] = tdf["revenue"] - tdf["cogs"] - tdf["opex"]
        rev = float(tdf["revenue"].sum())
        cogs = float(tdf["cogs"].sum())
        opex = float(tdf["opex"].sum())
    else:
        tdf = pd.DataFrame(columns=["tx_date", "category", "item_name", "qty", "revenue", "cogs", "opex", "foyda"])
        rev = cogs = opex = 0.0

    gross_profit = rev - cogs
    net_profit = rev - cogs - opex
    gross_margin = (gross_profit / rev * 100.0) if rev > 0 else 0.0
    net_margin = (net_profit / rev * 100.0) if rev > 0 else 0.0

    # --- 2. Qarzlar ---
    receivables = payables = overdue_rec = overdue_pay = 0.0
    if debts_df is not None and not debts_df.empty:
        ddf = debts_df.copy()
        ddf["amount"] = pd.to_numeric(ddf["amount"], errors="coerce").fillna(0.0)
        is_open = ~ddf["status"].astype(str).str.lower().str.contains("to'lan")
        is_rec = ddf["debt_type"].astype(str).str.lower().str.contains("bizga")
        is_pay = ~is_rec
        is_late = ddf["status"].astype(str).str.lower().str.contains("kechik")

        receivables = float(ddf.loc[is_open & is_rec, "amount"].sum())
        payables = float(ddf.loc[is_open & is_pay, "amount"].sum())
        overdue_rec = float(ddf.loc[is_open & is_rec & is_late, "amount"].sum())
        overdue_pay = float(ddf.loc[is_open & is_pay & is_late, "amount"].sum())
    else:
        ddf = pd.DataFrame(columns=["counterparty", "debt_type", "amount", "due_date", "status"])

    # --- 3. Ombor va Sotilmay qolgan tovarlar ---
    inv_val = dead_stock_val = 0.0
    dead_items = pd.DataFrame()
    if inv_df is not None and not inv_df.empty:
        idf = inv_df.copy()
        idf["qty"] = pd.to_numeric(idf["qty"], errors="coerce").fillna(0.0)
        idf["unit_cost"] = pd.to_numeric(idf["unit_cost"], errors="coerce").fillna(0.0)
        idf["jami_qiymat"] = idf["qty"] * idf["unit_cost"]
        last_dt = pd.to_datetime(idf["last_sale_date"], errors="coerce").fillna(pd.Timestamp.today())
        idf["yotgan_kun"] = (pd.Timestamp.today().normalize() - last_dt.dt.normalize()).dt.days.clip(lower=0)
        inv_val = float(idf["jami_qiymat"].sum())
        dead_mask = idf["yotgan_kun"] >= max(60, sector_norm["max_ombor_kun"])
        dead_items = idf.loc[dead_mask].sort_values("jami_qiymat", ascending=False)
        dead_stock_val = float(dead_items["jami_qiymat"].sum())
    else:
        idf = pd.DataFrame(columns=["item_name", "category", "qty", "unit_cost", "last_sale_date", "jami_qiymat", "yotgan_kun"])

    # --- 4. Pul aylanish tezligi (kunlarda) ---
    daily_rev = rev / days if rev > 0 else 0.0
    daily_cogs = cogs / days if cogs > 0 else (daily_rev * 0.7 if daily_rev > 0 else 0.0)
    ombor_kun = (inv_val / daily_cogs) if daily_cogs > 0 else 0.0
    qarz_olish_kun = (receivables / daily_rev) if daily_rev > 0 else 0.0
    qarz_berish_kun = (payables / daily_cogs) if daily_cogs > 0 else 0.0
    pul_aylanish_kun = ombor_kun + qarz_olish_kun - qarz_berish_kun

    # --- 5. Mahsulotlar reytingi (ABC-XYZ oddiy o'zbekchada) ---
    if not tdf.empty:
        prod_df = (
            tdf.groupby("item_name", as_index=False)
            .agg(
                miqdor=("qty", "sum"),
                tushum=("revenue", "sum"),
                tannarx=("cogs", "sum"),
                xarajat=("opex", "sum"),
                sof_foyda=("foyda", "sum"),
                sotuv_soni=("revenue", "count"),
                ortacha=("revenue", "mean"),
                tebranish=("revenue", "std"),
            )
            .sort_values("tushum", ascending=False)
            .reset_index(drop=True)
        )
        pos_rev = prod_df.loc[prod_df["tushum"] > 0, "tushum"].sum()
        prod_df["ulush_foiz"] = np.where(prod_df["tushum"] > 0, prod_df["tushum"] / pos_rev * 100.0, 0.0) if pos_rev > 0 else 0.0
        prod_df["jamlangan_foiz"] = prod_df["ulush_foiz"].cumsum()
        prev_cum = prod_df["jamlangan_foiz"].shift(1, fill_value=0.0)

        def _daraja(row, prev_c):
            if row["sof_foyda"] < 0:
                return "Zararli"
            if prev_c < 80.0:
                return "Asosiy (Top)"
            if prev_c < 95.0:
                return "O'rtacha"
            return "Zaif"

        prod_df["Daraja"] = [_daraja(r, prev_cum.iloc[i]) for i, r in prod_df.iterrows()]

        def _barqarorlik(row):
            if row["sotuv_soni"] < 2 or pd.isna(row["tebranish"]) or row["ortacha"] <= 0:
                return "Kam sotiladi"
            cv = (row["tebranish"] / row["ortacha"]) * 100.0
            if cv <= 15:
                return "Doimiy talab"
            if cv <= 35:
                return "O'zgaruvchan"
            return "Tartibsiz"

        prod_df["Talab holati"] = prod_df.apply(_barqarorlik, axis=1)

        def _tavsiya(row):
            if row["Daraja"] == "Zararli":
                return "Narxini oshiring yoki sotuvdan olib tashlang"
            if row["Daraja"] == "Asosiy (Top)":
                return "Omborda doim bo'lishi shart — asosiy daromad manbai"
            if row["Daraja"] == "O'rtacha":
                return "Muntazam nazorat qiling va aksiyalar bilan oshiring"
            return "Ortiqcha zaxira ushlamang, buyurtma asosida olib keling"

        prod_df["Maslahat"] = prod_df.apply(_tavsiya, axis=1)
    else:
        prod_df = pd.DataFrame(columns=["item_name", "miqdor", "tushum", "tannarx", "xarajat", "sof_foyda", "ulush_foiz", "jamlangan_foiz", "Daraja", "Talab holati", "Maslahat"])

    # --- 6. Zararsiz ishlash chegarasi ---
    var_ratio = (cogs / rev) if rev > 0 else 0.70
    cmr = 1.0 - var_ratio
    bep_rev = (opex / cmr) if cmr > 0 else float("inf")
    safety_amt = (rev - bep_rev) if np.isfinite(bep_rev) else -opex
    safety_pct = (safety_amt / rev * 100.0) if (rev > 0 and np.isfinite(bep_rev)) else 0.0

    # --- 7. Mijozlar, Jamoa va 5 yo'nalish bahosi (0-100) ---
    tot_c = max(int(prof["jami_mijozlar"]), 1)
    new_c = max(int(prof["yangi_mijozlar"]), 0)
    rep_c = min(max(int(prof["qayta_mijozlar"]), 0), tot_c)
    mkt = max(float(prof["reklama_xarajati"]), 0.0)
    lt_m = max(float(prof["mijoz_davomiyligi_oy"]), 1.0)

    qayta_foiz = rep_c / tot_c * 100.0
    mijoz_jalb_narxi = (mkt / new_c) if new_c > 0 else 0.0
    oylik_chek = (rev / tot_c) * (30.0 / days) if rev > 0 else 0.0
    mijoz_foydasi = oylik_chek * lt_m * max(gross_margin / 100.0, 0.1)
    foyda_reklama_nisbat = (mijoz_foydasi / mijoz_jalb_narxi) if mijoz_jalb_narxi > 0 else (3.5 if rev > 0 else 0.0)

    emp = max(int(prof["xodimlar_soni"]), 1)
    oylik_fondi = max(float(prof["oylik_fondi"]), 0.0)
    xodim_tushumi = rev / emp if rev > 0 else 0.0
    oylik_ulushi = (oylik_fondi / rev * 100.0) if rev > 0 else 0.0
    kadr_ketish = (max(int(prof["ketgan_xodimlar"]), 0) / emp) * 100.0

    # 5 ta yo'nalish ballari
    ball_moliya = clamp((50.0 + net_margin * 2.5 if rev > 0 else 30.0) - max(0.0, pul_aylanish_kun - 25.0) * 0.6)
    ball_mijoz = clamp((clamp(foyda_reklama_nisbat / 3.5 * 100.0) * 0.55) + (clamp(qayta_foiz / 55.0 * 100.0) * 0.45))
    ball_sifat = clamp((100.0 - float(prof["brak_qaytarilish"]) * 8.0) * 0.5 + clamp(float(prof["quvvat_bandligi"]) / 80.0 * 100.0) * 0.5)
    ball_jamoa = clamp((100.0 - max(0.0, oylik_ulushi - 22.0) * 2.0) * 0.45 + float(prof["reja_bajarilishi"]) * 0.35 + (100.0 - kadr_ketish * 4.5) * 0.20)
    ball_xavfsizlik = clamp((100.0 - max(0.0, float(prof["top3_mijoz_ulushi"]) - 25.0) * 1.4) * 0.5 + (100.0 - max(0.0, float(prof["asosiy_yetkazuvchi_ulushi"]) - 35.0) * 1.3) * 0.5)

    ballar = {
        "Moliya va foyda": round(ball_moliya, 1),
        "Mijozlar va sotuv": round(ball_mijoz, 1),
        "Sifat va ish jarayoni": round(ball_sifat, 1),
        "Jamoa samaradorligi": round(ball_jamoa, 1),
        "Xavfsizlik va barqarorlik": round(ball_xavfsizlik, 1),
    }
    umumiy_ball = round(
        ball_moliya * 0.28 + ball_mijoz * 0.22 + ball_sifat * 0.18 + ball_jamoa * 0.17 + ball_xavfsizlik * 0.15,
        1,
    )

    if umumiy_ball >= 80:
        holat_matni, holat_turi = "Barqaror va sog'lom biznes", "good"
    elif umumiy_ball >= 62:
        holat_matni, holat_turi = "Yaxshi, lekin yaxshilash kerak bo'lgan joylar bor", "warn"
    else:
        holat_matni, holat_turi = "Diqqat! Muhim muammolarni tezroq hal qilish kerak", "bad"

    # --- 8. Muammolar va Aniq Yechimlar ---
    curr = company["currency"]
    muammolar = []

    if rev > 0 and net_margin < sector_norm["min_marja"]:
        if gross_margin < 22.0:
            sabab = f"Sotuv narxi bilan tannarx orasidagi farq kichik ({gross_margin:.1f}%)."
            yechim = "Eng kam foyda berayotgan mahsulotlar narxini 5–8% ga oshiring yoki arzonroq yetkazib beruvchi toping."
            samara = rev * 0.04
        else:
            sabab = f"Asosiy daromad yaxshi ({gross_margin:.1f}%), lekin boshqa xarajatlar foydani yeb qo'ymoqda."
            yechim = "Ijara, ma'muriy va keraksiz oylik xarajatlarni kamida 12% ga qisqartiring."
            samara = opex * 0.12
        muammolar.append({
            "daraja": "Yuqori" if net_profit < 0 else "O'rta",
            "bolim": "Foyda va xarajat",
            "muammo": f"Sof foyda ulushi past ({net_margin:.1f}%, me'yor kamida {sector_norm['min_marja']:.0f}%)",
            "sabab": sabab,
            "yechim": yechim,
            "samara_summa": samara,
            "samara_matn": f"+{fmt_pul(samara, curr)} qo'shimcha sof foyda",
            "bosqich": "1-oy (Shoshilinch)",
        })

    zararli_soni = int((prod_df["sof_foyda"] < 0).sum()) if not prod_df.empty else 0
    if zararli_soni > 0:
        zarar_jami = abs(float(prod_df.loc[prod_df["sof_foyda"] < 0, "sof_foyda"].sum()))
        nomlar = ", ".join(prod_df.loc[prod_df["sof_foyda"] < 0, "item_name"].head(3).tolist())
        muammolar.append({
            "daraja": "Yuqori",
            "bolim": "Mahsulotlar",
            "muammo": f"{zararli_soni} ta mahsulot zarar keltirmoqda ({nomlar})",
            "sabab": "Bu tovarlarni sotishdan tushgan pul ularning tannarxi va xarajatini qoplamayapti.",
            "yechim": "Ushbu mahsulotlar narxini qayta hisoblang yoki sotuvdan chiqarib tashlang.",
            "samara_summa": zarar_jami,
            "samara_matn": f"+{fmt_pul(zarar_jami, curr)} zararning oldi olinadi",
            "bosqich": "1-oy (Shoshilinch)",
        })

    if overdue_rec > 0:
        muammolar.append({
            "daraja": "Yuqori",
            "bolim": "Qarzlar va pul",
            "muammo": f"Mijozlardan {fmt_pul(overdue_rec, curr)} miqdorida muddati o'tgan qarz bor",
            "sabab": "To'lov muddatlari qat'iy nazorat qilinmagan va oldindan to'lov olinmagan.",
            "yechim": "Qarzdorlar bilan shu hafta bog'lanib to'lov grafigi tuzing; yangi savdolarda kamida 30% oldindan to'lov joriy qiling.",
            "samara_summa": overdue_rec * 0.7,
            "samara_matn": f"+{fmt_pul(overdue_rec * 0.7, curr)} naqd pul kassaga qaytadi",
            "bosqich": "1-oy (Shoshilinch)",
        })

    if dead_stock_val > 0:
        muammolar.append({
            "daraja": "O'rta",
            "bolim": "Ombor",
            "muammo": f"Omborda {len(dead_items)} turdagi tovar uzoq vaqtdan beri sotilmay yotibdi",
            "sabab": f"{fmt_pul(dead_stock_val, curr)} pulingiz omborda harakatsiz qolib ketgan.",
            "yechim": "Bu tovarlarga 15–25% chegirma yoki boshqa tovar bilan birga aksiya qilib naqd pulga aylantiring.",
            "samara_summa": dead_stock_val * 0.8,
            "samara_matn": f"+{fmt_pul(dead_stock_val * 0.8, curr)} naqd pul aylanmaga qaytadi",
            "bosqich": "1-oy (Shoshilinch)",
        })

    if rev > 0 and oylik_ulushi > 28.0:
        ortiqcha = max(oylik_fondi - rev * 0.24, 0.0)
        muammolar.append({
            "daraja": "O'rta",
            "bolim": "Jamoa va oylik",
            "muammo": f"Ish haqi xarajati jami savdoning {oylik_ulushi:.1f}% ini tashkil etmoqda",
            "sabab": f"Har bir xodimga to'g'ri keladigan savdo ({fmt_pul(xodim_tushumi, curr)}) oylik yukini qoplash uchun yetarli emas.",
            "yechim": "Oylikning 30% qismini aniq savdo va bajarilgan ish natijasiga (bonusga) bog'lab qo'ying.",
            "samara_summa": ortiqcha * 0.5,
            "samara_matn": f"+{fmt_pul(ortiqcha * 0.5, curr)} samaradorlik oshishi",
            "bosqich": "2-oy (Tartibga solish)",
        })

    if float(prof["brak_qaytarilish"]) > 3.0 and rev > 0:
        brak_zarar = rev * (float(prof["brak_qaytarilish"]) / 100.0)
        muammolar.append({
            "daraja": "O'rta",
            "bolim": "Sifat nazorati",
            "muammo": f"Qaytarilgan yoki nuqsonli mahsulotlar ulushi yuqori ({prof['brak_qaytarilish']:.1f}%)",
            "sabab": f"Sifat tekshiruvi sustligi tufayli taxminan {fmt_pul(brak_zarar, curr)} yo'qotilmoqda.",
            "yechim": "Mijozga topshirishdan oldin oddiy 5 bandli sifat tekshiruv varag'ini majburiy qiling.",
            "samara_summa": brak_zarar * 0.6,
            "samara_matn": f"+{fmt_pul(brak_zarar * 0.6, curr)} tejaladi",
            "bosqich": "2-oy (Tartibga solish)",
        })

    if mijoz_jalb_narxi > 0 and foyda_reklama_nisbat < 3.0:
        muammolar.append({
            "daraja": "O'rta",
            "bolim": "Mijozlar va reklama",
            "muammo": f"Reklama o'zini sekin oqlayapti (1 so'mga {foyda_reklama_nisbat:.1f} so'm qaytmoqda)",
            "sabab": f"1 ta yangi mijoz jalb qilish {fmt_pul(mijoz_jalb_narxi, curr)} ga tushmoqda, qayta xarid esa {qayta_foiz:.0f}%.",
            "yechim": "Natija bermayotgan reklamani to'xtating va eski mijozlarga Telegram/SMS orqali qayta taklif yuboring.",
            "samara_summa": mkt * 0.25,
            "samara_matn": f"+{fmt_pul(mkt * 0.25, curr)} reklama tejami",
            "bosqich": "2-oy (Tartibga solish)",
        })

    if float(prof["top3_mijoz_ulushi"]) > 45.0 and rev > 0:
        xavf_pul = rev * (float(prof["top3_mijoz_ulushi"]) / 100.0) / 3.0
        muammolar.append({
            "daraja": "O'rta",
            "bolim": "Biznes xavfsizligi",
            "muammo": f"Savdoning {prof['top3_mijoz_ulushi']:.0f}% i bor-yo'g'i 3 ta mijozga bog'lanib qolgan",
            "sabab": f"Agar ulardan bittasi ketsa, tushumingiz birdan ~{fmt_pul(xavf_pul, curr)} ga tushib ketadi.",
            "yechim": "Yangi o'rta mijozlarni ko'paytiring — bitta mijoz ulushi 15% dan oshmasligiga harakat qiling.",
            "samara_summa": xavf_pul,
            "samara_matn": f"{fmt_pul(xavf_pul, curr)} lik tushumni xavfdan himoyalash",
            "bosqich": "3-oy (Rivojlanish)",
        })

    if not muammolar:
        muammolar.append({
            "daraja": "Past",
            "bolim": "O'sish imkoniyati",
            "muammo": "Jiddiy muammo topilmadi — korxona barqaror ishlamoqda",
            "sabab": "Asosiy moliyaviy va ichki ko'rsatkichlar me'yorida.",
            "yechim": "Eng foydali mahsulotlar zaxirasini ko'paytiring va yangi savdo kanallarini oching.",
            "samara_summa": rev * 0.15,
            "samara_matn": f"+{fmt_pul(rev * 0.15, curr)} qo'shimcha o'sish imkoniyati",
            "bosqich": "3-oy (Rivojlanish)",
        })

    order_map = {"Yuqori": 0, "O'rta": 1, "Past": 2}
    muammolar.sort(key=lambda x: (order_map.get(x["daraja"], 3), -x["samara_summa"]))

    # --- 9. 12 oylik 3-ssenariyli prognoz ---
    oylik_koeff = 30.0 / days
    m_rev = rev * oylik_koeff
    m_opex = opex * oylik_koeff
    m_var_ratio = var_ratio

    fc_rows = []
    for oy in range(1, 13):
        ramp = min(1.0, oy / 4.0)
        yomon = (m_rev * (0.975 ** (oy - 1))) * (1.0 - min(m_var_ratio + 0.03, 0.96)) - m_opex * (1.015 ** (oy - 1))
        ortacha = (m_rev * (1.02 ** (oy - 1))) * (1.0 - m_var_ratio) - m_opex * (1.008 ** (oy - 1))
        yaxshi = (m_rev * (1.045 ** (oy - 1))) * (1.0 - max(0.10, m_var_ratio - 0.035 * ramp)) - m_opex * (1.0 - 0.08 * ramp) * (1.005 ** (oy - 1))
        fc_rows.append({
            "Oy": f"{oy}-oy",
            "Yomon holat": yomon,
            "Hozirgi holat": ortacha,
            "Reja bajarilganda": yaxshi,
        })
    forecast_df = pd.DataFrame(fc_rows)

    # Kassa 30 kunlik prognozi
    cash_now = float(company["cash_balance"])
    expected_cash_30 = cash_now + (net_profit * oylik_koeff) + (receivables * 0.6) - payables

    return {
        "tdf": tdf,
        "ddf": ddf,
        "idf": idf,
        "prod_df": prod_df,
        "dead_items": dead_items,
        "forecast_df": forecast_df,
        "rev": rev,
        "cogs": cogs,
        "opex": opex,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "gross_margin": gross_margin,
        "net_margin": net_margin,
        "receivables": receivables,
        "payables": payables,
        "overdue_rec": overdue_rec,
        "overdue_pay": overdue_pay,
        "inv_val": inv_val,
        "dead_stock_val": dead_stock_val,
        "ombor_kun": ombor_kun,
        "qarz_olish_kun": qarz_olish_kun,
        "qarz_berish_kun": qarz_berish_kun,
        "pul_aylanish_kun": pul_aylanish_kun,
        "bep_rev": bep_rev,
        "safety_amt": safety_amt,
        "safety_pct": safety_pct,
        "var_ratio": var_ratio,
        "qayta_foiz": qayta_foiz,
        "mijoz_jalb_narxi": mijoz_jalb_narxi,
        "foyda_reklama_nisbat": foyda_reklama_nisbat,
        "xodim_tushumi": xodim_tushumi,
        "oylik_ulushi": oylik_ulushi,
        "ballar": ballar,
        "umumiy_ball": umumiy_ball,
        "holat_matni": holat_matni,
        "holat_turi": holat_turi,
        "muammolar": muammolar,
        "cash_now": cash_now,
        "expected_cash_30": expected_cash_30,
        "sector_norm": sector_norm,
    }


# =========================================================
# 6. TAYYOR PDF VA EXCEL HISOBOTLAR
# =========================================================
def _pdf_safe(text) -> str:
    if text is None:
        return ""
    s = str(text)
    for k, v in {"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "—": "-", "–": "-", "…": "...", "«": '"', "»": '"'}.items():
        s = s.replace(k, v)
    s = s.encode("latin-1", "ignore").decode("latin-1")
    return re.sub(r"\s+", " ", s).strip()


def build_pdf_report(company: dict, res: dict) -> bytes:
    if not FPDF_AVAILABLE:
        raise RuntimeError("PDF yaratish uchun requirements.txt faylida fpdf2 bo'lishi kerak.")
    curr = company["currency"]
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    usable_w = pdf.w - pdf.l_margin - pdf.r_margin

    # Sarlavha
    pdf.set_fill_color(30, 58, 138)
    pdf.rect(0, 0, 210, 30, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_xy(12, 7)
    pdf.cell(0, 8, _pdf_safe("BIZNES TAHLIL VA RIVOJLANISH HISOBOTI"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(12, 17)
    pdf.cell(0, 6, _pdf_safe(f"Korxona: {company['name']}  |  Soha: {company['sector']}  |  Sana: {date.today()}"), ln=True)

    pdf.ln(14)
    pdf.set_text_color(15, 23, 42)

    # 1. Asosiy raqamlar
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, _pdf_safe("1. Asosiy Moliyaviy Natijalar"), ln=True)
    pdf.set_text_color(15, 23, 42)

    rows = [
        ("Jami savdo (Tushum)", fmt_pul(res["rev"], curr)),
        ("Mahsulot tannarxi", fmt_pul(res["cogs"], curr)),
        ("Boshqa xarajatlar", fmt_pul(res["opex"], curr)),
        ("Sof foyda", fmt_pul(res["net_profit"], curr)),
        ("Sof foyda ulushi", f"{res['net_margin']:.1f}%"),
        ("Kassadagi pul", fmt_pul(res["cash_now"], curr)),
        ("Biznes sog'lomlik bahosi", f"{res['umumiy_ball']:.1f} / 100"),
    ]
    for idx, (lbl, val) in enumerate(rows):
        pdf.set_fill_color(241, 245, 249 if idx % 2 == 0 else 255)
        is_bold = lbl in ("Sof foyda", "Biznes sog'lomlik bahosi")
        pdf.set_font("Helvetica", "B" if is_bold else "", 10)
        pdf.cell(110, 7, _pdf_safe(lbl), border=1, fill=True)
        pdf.cell(75, 7, _pdf_safe(val), border=1, align="R", fill=True, ln=True)

    pdf.ln(6)

    # 2. 5 yo'nalish bahosi
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, _pdf_safe("2. Korxonaning 5 Yo'nalish Bo'yicha Bahosi"), ln=True)
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Helvetica", "", 10)
    for k, v in res["ballar"].items():
        pdf.cell(110, 6.5, _pdf_safe(k), border=1)
        pdf.cell(75, 6.5, _pdf_safe(f"{v:.1f} / 100"), border=1, align="R", ln=True)

    pdf.ln(6)

    # 3. Asosiy muammolar va yechimlar
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, _pdf_safe("3. Aniqlangan Muammolar va Yechimlar"), ln=True)
    pdf.set_text_color(15, 23, 42)

    for i, m in enumerate(res["muammolar"][:6], start=1):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(usable_w, 6, _pdf_safe(f"{i}. [{m['bosqich']}] {m['muammo']}"))
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 9.5)
        pdf.multi_cell(usable_w, 5.5, _pdf_safe(f"   Sababi: {m['sabab']}"))
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(usable_w, 5.5, _pdf_safe(f"   Yechim: {m['yechim']} ({m['samara_matn']})"))
        pdf.ln(2)

    out = pdf.output(dest="S")
    return bytes(out) if isinstance(out, (bytes, bytearray)) else out.encode("latin-1")


def build_excel_report(company: dict, res: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary = pd.DataFrame([
            {"Ko'rsatkich": "Korxona nomi", "Qiymat": company["name"]},
            {"Ko'rsatkich": "Faoliyat sohasi", "Qiymat": company["sector"]},
            {"Ko'rsatkich": "Jami savdo", "Qiymat": res["rev"]},
            {"Ko'rsatkich": "Mahsulot tannarxi", "Qiymat": res["cogs"]},
            {"Ko'rsatkich": "Boshqa xarajatlar", "Qiymat": res["opex"]},
            {"Ko'rsatkich": "Sof foyda", "Qiymat": res["net_profit"]},
            {"Ko'rsatkich": "Sof foyda ulushi (%)", "Qiymat": round(res["net_margin"], 1)},
            {"Ko'rsatkich": "Biznes bahosi (0-100)", "Qiymat": res["umumiy_ball"]},
        ])
        summary.to_excel(writer, sheet_name="Umumiy_Xulosa", index=False)
        if not res["prod_df"].empty:
            res["prod_df"][["item_name", "miqdor", "tushum", "sof_foyda", "Daraja", "Talab holati", "Maslahat"]].rename(
                columns={"item_name": "Mahsulot", "miqdor": "Miqdor", "tushum": "Savdo", "sof_foyda": "Sof foyda"}
            ).to_excel(writer, sheet_name="Mahsulotlar_Tahlili", index=False)
        pd.DataFrame(res["muammolar"])[["bosqich", "daraja", "bolim", "muammo", "sabab", "yechim", "samara_matn"]].rename(
            columns={
                "bosqich": "Bosqich", "daraja": "Muhimlik", "bolim": "Bo'lim",
                "muammo": "Muammo", "sabab": "Sababi", "yechim": "Yechim", "samara_matn": "Kutilayotgan samara"
            }
        ).to_excel(writer, sheet_name="Muammolar_va_Reja", index=False)
        res["forecast_df"].to_excel(writer, sheet_name="12_Oylik_Prognoz", index=False)
    return buf.getvalue()


# =========================================================
# 7. INTERFEYS YORDAMCHI KOMPONENTLARI
# =========================================================
def render_kpi_card(label: str, value: str, note: str, tone: str = "muted"):
    tone_cls = {"good": "kpi-good", "warn": "kpi-warn", "bad": "kpi-bad"}.get(tone, "kpi-muted")
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-note {tone_cls}">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_issue_card(idx: int, item: dict):
    cls = "issue-high" if item["daraja"] == "Yuqori" else ("issue-mid" if item["daraja"] == "O'rta" else "issue-low")
    badge = "🔴 Muhim" if item["daraja"] == "Yuqori" else ("🟠 O'rtacha" if item["daraja"] == "O'rta" else "🟢 Tavsiya")
    st.markdown(
        f"""
        <div class="issue-card {cls}">
            <div style="font-size:0.82rem; color:#64748B; font-weight:600; margin-bottom:4px;">
                {badge} &nbsp;•&nbsp; {item['bolim']} &nbsp;•&nbsp; {item['bosqich']}
            </div>
            <div style="font-size:1.05rem; font-weight:700; color:#0F172A; margin-bottom:6px;">
                {idx}. {item['muammo']}
            </div>
            <div style="font-size:0.92rem; color:#334155; margin-bottom:4px;">
                <b>Nega bunday bo'ldi?</b> {item['sabab']}
            </div>
            <div style="font-size:0.92rem; color:#1E3A8A; margin-bottom:6px;">
                <b>Nima qilish kerak?</b> {item['yechim']}
            </div>
            <div style="font-size:0.86rem; font-weight:700; color:#15803D;">
                Kutilayotgan foyda: {item['samara_matn']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# 8. ASOSIY ILOVA OQIMI
# =========================================================
def main():
    init_db()
    ensure_default_company()
    companies = list_companies()

    # --- CHAP TOMONDAGI SODDA MENYU (SIDEBAR) ---
    with st.sidebar:
        st.markdown("## 📊 Biznes Yordamchi")
        st.caption("Oddiy va tushunarli biznes tahlili")

        menu = st.radio(
            "Bo'limni tanlang:",
            options=[
                "🏠 Bosh sahifa",
                "📥 Ma'lumot kiritish",
                "📊 Savdo va Mahsulotlar",
                "💰 Pul, Qarz va Ombor",
                "🩺 Muammolar, Reja va Hisobot",
            ],
            label_visibility="collapsed",
        )

        st.divider()
        st.markdown("**🏢 Korxonangiz**")
        comp_labels = {f"{c['name']}": c for c in companies}
        selected_name = st.selectbox("Korxona tanlash", list(comp_labels.keys()), label_visibility="collapsed")
        company = comp_labels[selected_name]
        st.caption(f"Soha: {company['sector']}")

        new_cash = st.number_input(
            f"Hozir kassadagi pul ({company['currency']})",
            min_value=0.0,
            value=float(company["cash_balance"]),
            step=1_000_000.0,
            format="%.0f",
        )
        if abs(new_cash - float(company["cash_balance"])) > 0.01:
            update_company_cash(company["id"], new_cash)
            company["cash_balance"] = new_cash

        with st.expander("➕ Yangi korxona qo'shish"):
            with st.form("add_comp_form", clear_on_submit=True):
                c_name = st.text_input("Korxona nomi", placeholder="Masalan: Baraka Savdo")
                c_sector = st.selectbox("Faoliyat sohasi", list(SOHALAR.keys()))
                c_curr = st.selectbox("Valyuta", ["so'm", "USD", "RUB"])
                c_cash = st.number_input("Boshlang'ich kassa", min_value=0.0, value=0.0, step=1_000_000.0)
                if st.form_submit_button("Qo'shish", use_container_width=True, type="primary"):
                    ok, msg = create_company(c_name, c_sector, c_curr, c_cash)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        if len(companies) > 1:
            with st.expander("🗑️ Korxonani o'chirish"):
                st.warning(f"'{company['name']}' va uning barcha ma'lumotlari o'chadi.")
                if st.button("Ha, o'chirish", use_container_width=True):
                    delete_company(company["id"])
                    st.rerun()

    # Ma'lumotlarni yuklash va hisoblash
    tx_df = load_table("transactions", company["id"])
    debts_df = load_table("debts", company["id"])
    inv_df = load_table("inventory", company["id"])
    prof = load_profile(company["id"])
    res = compute_full_analysis(company, tx_df, debts_df, inv_df, prof)
    curr = company["currency"]

    # Yuqori tushunarli sarlavha
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-title">{company['name']} — {menu.split(' ', 1)[1]}</div>
            <div class="hero-sub">Soha: {company['sector']} &nbsp;|&nbsp; Umumiy holat: {res['holat_matni']} ({res['umumiy_ball']:.0f}/100 ball)</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # =====================================================
    # 1-BO'LIM: BOSH SAHIFA (ENG MUHIM NARSALAR 1 EKRANDA)
    # =====================================================
    if menu == "🏠 Bosh sahifa":
        if tx_df.empty:
            st.markdown(
                """
                <div class="hint-box">
                    <b>👋 Xush kelibsiz! Boshlash juda oson — atigi 2 ta qadam:</b><br>
                    1. Tizim qanday ishlashini darhol ko'rish uchun pastdagi <b>"Namuna ma'lumot bilan sinab ko'rish"</b> tugmasini bosing.<br>
                    2. O'zingizning raqamlaringizni kiritish uchun chap menyudan <b>"📥 Ma'lumot kiritish"</b> bo'limiga o'ting.
                </div>
                """,
                unsafe_allow_html=True,
            )
            b1, b2 = st.columns([1, 2])
            if b1.button("✨ Namuna ma'lumot bilan sinab ko'rish", type="primary", use_container_width=True):
                load_demo_data(company["id"])
                st.success("Namuna ma'lumotlar yuklandi!")
                st.rerun()
            st.stop()

        # 4 ta asosiy karta
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_kpi_card("Jami savdo (Tushum)", fmt_pul(res["rev"], curr), f"{len(tx_df)} ta savdo qatori", "muted")
        with c2:
            foyda_tone = "good" if res["net_profit"] > 0 else "bad"
            render_kpi_card("Sof foyda", fmt_pul(res["net_profit"], curr), f"Savdoning {res['net_margin']:.1f}% i foyda", foyda_tone)
        with c3:
            kassa_tone = "good" if res["expected_cash_30"] >= 0 else "bad"
            kassa_izoh = "30 kundan keyin ham pul yetarli" if res["expected_cash_30"] >= 0 else "30 kunda pul yetishmasligi xavfi bor!"
            render_kpi_card("Kassadagi pul", fmt_pul(res["cash_now"], curr), kassa_izoh, kassa_tone)
        with c4:
            render_kpi_card("Biznes bahosi", f"{res['umumiy_ball']:.0f} / 100 ball", res["holat_matni"], res["holat_turi"])

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        # Oddiy grafik + Top 3 muammo yonma-yon
        left, right = st.columns([1.2, 1])
        with left:
            st.subheader("📈 Pul qayerga ketyapti?")
            fig = go.Figure(
                go.Bar(
                    x=["Jami savdo", "Tannarx", "Boshqa xarajat", "Sof foyda"],
                    y=[res["rev"], res["cogs"], res["opex"], res["net_profit"]],
                    marker_color=["#2563EB", "#64748B", "#D97706", "#16A34A" if res["net_profit"] >= 0 else "#DC2626"],
                    text=[fmt_pul(v, "") for v in [res["rev"], res["cogs"], res["opex"], res["net_profit"]]],
                    textposition="outside",
                )
            )
            fig.update_layout(
                height=340,
                margin=dict(l=10, r=10, t=20, b=20),
                plot_bgcolor="#FFFFFF",
                paper_bgcolor="#FFFFFF",
                yaxis_title=curr,
            )
            st.plotly_chart(fig, use_container_width=True)

        with right:
            st.subheader("🚨 Eng muhim 3 ta masala")
            for idx, m in enumerate(res["muammolar"][:3], start=1):
                render_issue_card(idx, m)

        st.caption("Batafsil jadvallar va grafiklarni ko'rish uchun chap menyudan kerakli bo'limni tanlang.")

    # =====================================================
    # 2-BO'LIM: MA'LUMOT KIRITISH (EXCEL + QO'LDA + PROFIL)
    # =====================================================
    elif menu == "📥 Ma'lumot kiritish":
        t_excel, t_manual, t_prof = st.tabs([
            "📂 Excel yuklash (Eng oson)",
            "✍️ Jadvalda qo'lda kiritish",
            "🏢 Mijozlar, Jamoa va Sifat",
        ])

        with t_excel:
            st.markdown(
                """
                <div class="hint-box">
                    <b>Excel orqali yuklash tartibi:</b> Avval tayyor shablonni yuklab olib to'ldiring, so'ng shu yerga tashlang.
                    Bo'sh qatorlar yoki to'ldirilmagan kataklar bo'lsa ham tizim o'zi tozalab xatosiz qabul qiladi.
                </div>
                """,
                unsafe_allow_html=True,
            )
            col_dl, col_demo = st.columns(2)
            col_dl.download_button(
                "⬇️ Tayyor Excel shablonini yuklab olish",
                data=build_excel_template(),
                file_name="biznes_shablon.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            if col_demo.button("✨ Tayyor namuna ma'lumotlarni yuklash", use_container_width=True):
                load_demo_data(company["id"])
                st.success("Namuna ma'lumotlar yuklandi! Endi 'Bosh sahifa'ga o'ting.")
                st.rerun()

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            uploaded = st.file_uploader("Excel faylingizni (.xlsx) tanlang:", type=["xlsx", "xls"])
            mode = st.radio(
                "Yuklanganda eski ma'lumotlar nima bo'lsin?",
                ["Eskisini yangisiga almashtirish", "Eskisining ustiga qo'shish (faqat savdo)"],
                horizontal=True,
            )
            if uploaded is not None:
                if st.button("📥 Faylni o'qish va saqlash", type="primary"):
                    try:
                        parsed = parse_uploaded_excel(uploaded.getvalue())
                        if parsed["tx"].empty and parsed["debts"].empty and parsed["inv"].empty:
                            st.warning("Fayl ichidan mos ma'lumot topilmadi. Yuqoridagi shablondan foydalanib ko'ring.")
                        else:
                            if not parsed["tx"].empty:
                                if mode.startswith("Eskisini"):
                                    replace_transactions(company["id"], parsed["tx"])
                                else:
                                    append_transactions(company["id"], parsed["tx"])
                            if not parsed["debts"].empty:
                                replace_debts(company["id"], parsed["debts"])
                            if not parsed["inv"].empty:
                                replace_inventory(company["id"], parsed["inv"])
                            st.success("Muvaffaqiyatli yuklandi! " + " ".join(parsed["messages"]))
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Faylni o'qishda xatolik: {exc}")

        with t_manual:
            st.caption("Quyidagi jadvallarda Excel kabi to'g'ridan-to'g'ri yozishingiz, yangi qator (+) qo'shishingiz va saqlashingiz mumkin.")
            m1, m2, m3 = st.tabs(["Savdo ro'yxati", "Qarzlar ro'yxati", "Ombor ro'yxati"])

            with m1:
                edit_tx = tx_df[["tx_date", "category", "item_name", "qty", "revenue", "cogs", "opex"]].copy() if not tx_df.empty else pd.DataFrame(
                    columns=["tx_date", "category", "item_name", "qty", "revenue", "cogs", "opex"]
                )
                edit_tx.columns = ["Sana", "Bo'lim", "Mahsulot nomi", "Miqdor", "Tushum", "Tannarx", "Boshqa xarajat"]
                edited_tx = st.data_editor(edit_tx, num_rows="dynamic", use_container_width=True, key="ed_tx")
                if st.button("💾 Savdo jadvalini saqlash", type="primary"):
                    save_df = edited_tx.rename(columns={
                        "Sana": "tx_date", "Bo'lim": "category", "Mahsulot nomi": "item_name",
                        "Miqdor": "qty", "Tushum": "revenue", "Tannarx": "cogs", "Boshqa xarajat": "opex"
                    })
                    replace_transactions(company["id"], save_df)
                    st.success("Savdo ma'lumotlari saqlandi!")
                    st.rerun()

            with m2:
                edit_d = debts_df[["counterparty", "debt_type", "amount", "due_date", "status"]].copy() if not debts_df.empty else pd.DataFrame(
                    columns=["counterparty", "debt_type", "amount", "due_date", "status"]
                )
                edit_d.columns = ["Hamkor nomi", "Qarz turi", "Summa", "To'lov muddati", "Holati"]
                edited_d = st.data_editor(
                    edit_d,
                    num_rows="dynamic",
                    use_container_width=True,
                    column_config={
                        "Qarz turi": st.column_config.SelectboxColumn(options=["Bizga qarzdor", "Bizning qarzimiz"]),
                        "Holati": st.column_config.SelectboxColumn(options=["Muddatida", "Kechikkan", "To'langan"]),
                    },
                    key="ed_debts",
                )
                if st.button("💾 Qarzlar jadvalini saqlash", type="primary"):
                    save_d = edited_d.rename(columns={
                        "Hamkor nomi": "counterparty", "Qarz turi": "debt_type",
                        "Summa": "amount", "To'lov muddati": "due_date", "Holati": "status"
                    })
                    replace_debts(company["id"], save_d)
                    st.success("Qarzlar saqlandi!")
                    st.rerun()

            with m3:
                edit_i = inv_df[["item_name", "category", "qty", "unit_cost", "last_sale_date"]].copy() if not inv_df.empty else pd.DataFrame(
                    columns=["item_name", "category", "qty", "unit_cost", "last_sale_date"]
                )
                edit_i.columns = ["Mahsulot nomi", "Bo'lim", "Qoldiq soni", "Birlik tannarxi", "Oxirgi sotilgan sana"]
                edited_i = st.data_editor(edit_i, num_rows="dynamic", use_container_width=True, key="ed_inv")
                if st.button("💾 Ombor jadvalini saqlash", type="primary"):
                    save_i = edited_i.rename(columns={
                        "Mahsulot nomi": "item_name", "Bo'lim": "category",
                        "Qoldiq soni": "qty", "Birlik tannarxi": "unit_cost", "Oxirgi sotilgan sana": "last_sale_date"
                    })
                    replace_inventory(company["id"], save_i)
                    st.success("Ombor ma'lumotlari saqlandi!")
                    st.rerun()

        with t_prof:
            st.caption("Bu oddiy savollarga javob bersangiz, tizim faqat pulingizni emas, jamoa, mijozlar va xavfsizlikni ham aniq baholab beradi.")
            with st.form("profile_form"):
                st.markdown("#### 👥 Mijozlar va Reklama")
                p1, p2, p3, p4 = st.columns(4)
                davr = p1.number_input("Tahlil davri (necha kun?)", 7, 365, int(prof["davr_kun"]))
                j_mijoz = p2.number_input("Jami mijozlar soni", 1, 100000, int(prof["jami_mijozlar"]))
                y_mijoz = p3.number_input("Yangi kelgan mijozlar", 0, 100000, int(prof["yangi_mijozlar"]))
                q_mijoz = p4.number_input("Qayta xarid qilganlar", 0, 100000, int(prof["qayta_mijozlar"]))

                p5, p6, p7 = st.columns(3)
                rek = p5.number_input(f"Reklama xarajati ({curr})", 0.0, value=float(prof["reklama_xarajati"]), step=500_000.0)
                davom = p6.number_input("Mijoz o'rtacha necha oy xarid qiladi?", 1.0, 120.0, float(prof["mijoz_davomiyligi_oy"]))
                top3 = p7.slider("Eng yirik 3 ta mijoz savdoning necha % ini oladi?", 0, 100, int(prof["top3_mijoz_ulushi"]))

                st.markdown("#### 🧑‍💼 Xodimlar va Ish sifati")
                h1, h2, h3, h4 = st.columns(4)
                xodim = h1.number_input("Xodimlar soni", 1, 10000, int(prof["xodimlar_soni"]))
                oylik = h2.number_input(f"Jami oylik fondi ({curr})", 0.0, value=float(prof["oylik_fondi"]), step=1_000_000.0)
                ketgan = h3.number_input("Ishdan ketgan xodimlar", 0, 1000, int(prof["ketgan_xodimlar"]))
                reja = h4.slider("Jamoa oylik rejani necha % bajardi?", 0, 100, int(prof["reja_bajarilishi"]))

                o1, o2, o3 = st.columns(3)
                brak = o1.number_input("Qaytarilish / nuqson foizi (%)", 0.0, 100.0, float(prof["brak_qaytarilish"]), step=0.5)
                band = o2.slider("Ish quvvati necha % band?", 0, 100, int(prof["quvvat_bandligi"]))
                yetkaz = o3.slider("Asosiy yetkazib beruvchi ulushi (%)", 0, 100, int(prof["asosiy_yetkazuvchi_ulushi"]))

                if st.form_submit_button("💾 Ma'lumotlarni saqlash", type="primary"):
                    save_profile(company["id"], {
                        "davr_kun": davr, "jami_mijozlar": j_mijoz, "yangi_mijozlar": y_mijoz,
                        "qayta_mijozlar": q_mijoz, "reklama_xarajati": rek, "mijoz_davomiyligi_oy": davom,
                        "top3_mijoz_ulushi": top3, "xodimlar_soni": xodim, "oylik_fondi": oylik,
                        "ketgan_xodimlar": ketgan, "reja_bajarilishi": reja, "brak_qaytarilish": brak,
                        "bajarilish_vaqti_kun": float(prof["bajarilish_vaqti_kun"]),
                        "quvvat_bandligi": band, "asosiy_yetkazuvchi_ulushi": yetkaz,
                    })
                    st.success("Korxona ko'rsatkichlari yangilandi!")
                    st.rerun()

    # =====================================================
    # 3-BO'LIM: SAVDO VA MAHSULOTLAR
    # =====================================================
    elif menu == "📊 Savdo va Mahsulotlar":
        if tx_df.empty:
            st.info("Avval '📥 Ma'lumot kiritish' bo'limidan savdo ma'lumotlarini yuklang.")
            st.stop()

        s1, s2, s3 = st.tabs([
            "🏆 Eng foydali va zararli mahsulotlar",
            "⚖️ Zararsiz ishlash chegarasi",
            "📦 Bo'limlar bo'yicha tahlil",
        ])

        with s1:
            prod = res["prod_df"]
            k1, k2, k3 = st.columns(3)
            k1.metric("Asosiy (Top) mahsulotlar", f"{int((prod['Daraja'] == 'Asosiy (Top)').sum())} ta", help="Tushumning 80% ini beruvchi eng muhim tovarlar")
            mid_weak_cnt = int(prod["Daraja"].isin(["O'rtacha", "Zaif"]).sum())
            k2.metric("O'rtacha va zaif mahsulotlar", f"{mid_weak_cnt} ta")
            k3.metric("Zarar keltirayotganlar", f"{int((prod['Daraja'] == 'Zararli').sum())} ta")

            fig_p = go.Figure()
            fig_p.add_bar(
                x=prod["item_name"],
                y=prod["tushum"],
                name="Savdo (Tushum)",
                marker_color="#2563EB",
            )
            fig_p.add_bar(
                x=prod["item_name"],
                y=prod["sof_foyda"],
                name="Sof foyda",
                marker_color=["#16A34A" if v >= 0 else "#DC2626" for v in prod["sof_foyda"]],
            )
            fig_p.update_layout(
                title="Mahsulotlar bo'yicha Savdo va Sof Foyda",
                barmode="group",
                height=380,
                plot_bgcolor="#FFFFFF",
                paper_bgcolor="#FFFFFF",
                legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(fig_p, use_container_width=True)

            show_prod = prod[["item_name", "miqdor", "tushum", "sof_foyda", "Daraja", "Talab holati", "Maslahat"]].rename(
                columns={"item_name": "Mahsulot", "miqdor": "Sotilgan soni", "tushum": f"Savdo ({curr})", "sof_foyda": f"Sof foyda ({curr})"}
            )
            st.dataframe(show_prod, use_container_width=True, hide_index=True)

        with s2:
            st.markdown(
                """
                <div class="hint-box">
                    <b>Bu nima?</b> Korxonangiz zarar qilmasligi uchun kamida qancha savdo qilishi kerakligini ko'rsatadi.
                    Pastdagi raqamlarni o'zgartirib, xarajat oshsa yoki kamaysa nima bo'lishini tekshirib ko'ring.
                </div>
                """,
                unsafe_allow_html=True,
            )
            sl1, sl2 = st.columns(2)
            doimiy = sl1.number_input(f"Doimiy xarajatlar — ijara, oylik ({curr})", 0.0, value=float(res["opex"]), step=500_000.0)
            tannarx_foiz = sl2.slider("Tannarx savdoning necha % ini oladi?", 5, 95, int(clamp(res["var_ratio"] * 100, 5, 95)))

            cmr = 1.0 - (tannarx_foiz / 100.0)
            bep = (doimiy / cmr) if cmr > 0 else float("inf")
            zaxira = res["rev"] - bep if np.isfinite(bep) else -doimiy

            b1, b2, b3 = st.columns(3)
            b1.metric("Minimal kerakli savdo", fmt_pul(bep, curr) if np.isfinite(bep) else "Hisoblanmadi")
            b2.metric("Hozirgi savdongiz", fmt_pul(res["rev"], curr))
            b3.metric("Xavfsizlik zaxirasi", fmt_pul(zaxira, curr), help="Savdo shuncha tushsa ham hali zarar qilmaysiz")

            if np.isfinite(bep) and bep > 0:
                max_x = max(res["rev"], bep) * 1.35
                x_v = np.linspace(0, max_x, 40)
                y_cost = doimiy + x_v * (tannarx_foiz / 100.0)
                fig_b = go.Figure()
                fig_b.add_scatter(x=x_v, y=x_v, name="Savdo (Tushum)", line=dict(color="#16A34A", width=3))
                fig_b.add_scatter(x=x_v, y=y_cost, name="Jami xarajat", line=dict(color="#DC2626", width=3))
                fig_b.add_scatter(
                    x=[bep], y=[bep], mode="markers+text", name="Zararsizlik nuqtasi",
                    text=[f"Chegara: {fmt_pul(bep, curr)}"], textposition="top left",
                    marker=dict(size=12, color="#1E3A8A", symbol="diamond"),
                )
                fig_b.update_layout(
                    height=380, xaxis_title=f"Savdo hajmi ({curr})", yaxis_title=f"Summa ({curr})",
                    plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF", legend=dict(orientation="h", y=1.12)
                )
                st.plotly_chart(fig_b, use_container_width=True)

        with s3:
            grp = res["tdf"].groupby("category", as_index=False).agg(
                Savdo=("revenue", "sum"),
                Tannarx=("cogs", "sum"),
                Xarajat=("opex", "sum"),
                Sof_foyda=("foyda", "sum"),
            ).sort_values("Savdo", ascending=False)
            fig_g = go.Figure(
                go.Bar(
                    x=grp["category"], y=grp["Sof_foyda"],
                    marker_color=["#16A34A" if v >= 0 else "#DC2626" for v in grp["Sof_foyda"]],
                    text=[fmt_pul(v, "") for v in grp["Sof_foyda"]], textposition="outside",
                )
            )
            fig_g.update_layout(title="Bo'limlar bo'yicha Sof Foyda", height=360, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF")
            st.plotly_chart(fig_g, use_container_width=True)
            st.dataframe(grp.rename(columns={"category": "Bo'lim", "Sof_foyda": "Sof foyda"}), use_container_width=True, hide_index=True)

    # =====================================================
    # 4-BO'LIM: PUL, QARZ VA OMBOR
    # =====================================================
    elif menu == "💰 Pul, Qarz va Ombor":
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Bizga qarzdorlar", fmt_pul(res["receivables"], curr), delta=f"Kechikkan: {fmt_pul(res['overdue_rec'], curr)}" if res["overdue_rec"] > 0 else "Hammasi muddatida", delta_color="inverse" if res["overdue_rec"] > 0 else "normal")
        q2.metric("Bizning qarzlarimiz", fmt_pul(res["payables"], curr))
        q3.metric("Ombordagi tovar qiymati", fmt_pul(res["inv_val"], curr))
        q4.metric("Pul aylanish vaqti", f"{res['pul_aylanish_kun']:.0f} kun", help="Tovarga tikilgan pul o'rtacha necha kunda naqd bo'lib qaytadi")

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        p_tab1, p_tab2, p_tab3 = st.tabs(["🔄 Pul qayerda to'xtab qolyapti?", "📋 Qarzlar nazorati", "📦 Ombor va sotilmagan tovarlar"])

        with p_tab1:
            st.caption("Tovar omborda qancha uzoq yotsa va mijozlar qarzni qancha kech to'lasa, kassangizda naqd pul shuncha kamayadi.")
            fig_ccc = go.Figure(
                go.Bar(
                    x=["Tovar omborda yotishi", "Mijozdan qarz yig'ish", "Yetkazib beruvchiga kechiktirish", "Jami pul qaytish vaqti"],
                    y=[res["ombor_kun"], res["qarz_olish_kun"], -res["qarz_berish_kun"], res["pul_aylanish_kun"]],
                    marker_color=["#2563EB", "#D97706", "#16A34A", "#DC2626" if res["pul_aylanish_kun"] > 35 else "#1E3A8A"],
                    text=[f"{v:.0f} kun" for v in [res["ombor_kun"], res["qarz_olish_kun"], -res["qarz_berish_kun"], res["pul_aylanish_kun"]]],
                    textposition="outside",
                )
            )
            fig_ccc.update_layout(height=360, yaxis_title="Kunlar", plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF")
            st.plotly_chart(fig_ccc, use_container_width=True)

        with p_tab2:
            if res["ddf"].empty:
                st.info("Hozircha qarzlar kiritilmagan.")
            else:
                show_d = res["ddf"][["counterparty", "debt_type", "amount", "due_date", "status"]].rename(
                    columns={"counterparty": "Hamkor", "debt_type": "Qarz turi", "amount": f"Summa ({curr})", "due_date": "To'lov muddati", "status": "Holati"}
                )
                st.dataframe(show_d, use_container_width=True, hide_index=True)

        with p_tab3:
            if res["idf"].empty:
                st.info("Hozircha ombor ma'lumotlari kiritilmagan.")
            else:
                if not res["dead_items"].empty:
                    st.warning(f"Diqqat! Omborda {len(res['dead_items'])} ta tovar uzoq vaqtdan beri sotilmay yotibdi (jami {fmt_pul(res['dead_stock_val'], curr)}).")
                show_i = res["idf"][["item_name", "category", "qty", "unit_cost", "jami_qiymat", "yotgan_kun"]].rename(
                    columns={
                        "item_name": "Mahsulot", "category": "Bo'lim", "qty": "Qoldiq",
                        "unit_cost": "Birlik tannarxi", "jami_qiymat": f"Jami qiymat ({curr})", "yotgan_kun": "Necha kundan beri sotilmadi"
                    }
                )
                st.dataframe(show_i, use_container_width=True, hide_index=True)

    # =====================================================
    # 5-BO'LIM: MUAMMOLAR, REJA, PROGNOZ VA HISOBOT
    # =====================================================
    elif menu == "🩺 Muammolar, Reja va Hisobot":
        r1, r2, r3, r4 = st.tabs([
            "🎯 Biznes bahosi va Muammolar",
            "🗺️ 3 Oylik Harakatlar Rejasi",
            "📈 Kelgusi 12 Oylik Prognoz",
            "📄 Tayyor Hisobot (PDF / Excel)",
        ])

        with r1:
            col_rad, col_tbl = st.columns([1.2, 1])
            with col_rad:
                cats = list(res["ballar"].keys())
                vals = list(res["ballar"].values())
                fig_rad = go.Figure()
                fig_rad.add_trace(go.Scatterpolar(r=vals + [vals[0]], theta=cats + [cats[0]], fill="toself", name="Sizning korxonangiz", line=dict(color="#1E3A8A", width=2.5), fillcolor="rgba(37,99,235,0.22)"))
                fig_rad.add_trace(go.Scatterpolar(r=[80] * (len(cats) + 1), theta=cats + [cats[0]], name="Yaxshi daraja (80)", line=dict(color="#16A34A", dash="dash")))
                fig_rad.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), height=360, margin=dict(l=40, r=40, t=30, b=30), legend=dict(orientation="h", y=-0.12))
                st.plotly_chart(fig_rad, use_container_width=True)

            with col_tbl:
                st.subheader(f"Umumiy baho: {res['umumiy_ball']:.0f} / 100")
                b_df = pd.DataFrame([
                    {"Yo'nalish": k, "Ball": v, "Izoh": "Yaxshi" if v >= 75 else ("Yaxshilash kerak" if v >= 55 else "Zaif joy!")}
                    for k, v in res["ballar"].items()
                ])
                st.dataframe(b_df, use_container_width=True, hide_index=True)

            st.subheader("🔍 Aniqlangan muammolar va aniq yechimlar")
            for idx, m in enumerate(res["muammolar"], start=1):
                render_issue_card(idx, m)

        with r2:
            st.caption("Barcha muammolar muhimligiga qarab 3 oyga bo'lib berildi — birinchi oyda eng shoshilinch ishlardan boshlang.")
            c30, c60, c90 = st.columns(3)
            stages = [
                ("1-oy (Shoshilinch)", c30, "🚨 1-oy: Tezkor natija"),
                ("2-oy (Tartibga solish)", c60, "🔧 2-oy: Tizimni sozlash"),
                ("3-oy (Rivojlanish)", c90, "🚀 3-oy: Barqaror o'sish"),
            ]
            for key, col_box, title in stages:
                with col_box:
                    st.markdown(f"### {title}")
                    items = [x for x in res["muammolar"] if x["bosqich"] == key]
                    if not items:
                        st.info("Bu bosqichda shoshilinch muammo yo'q.")
                    for item in items:
                        with st.container(border=True):
                            st.markdown(f"**{item['bolim']}:** {item['muammo']}")
                            st.write(item["yechim"])
                            st.caption(f"Kutilayotgan foyda: {item['samara_matn']}")

        with r3:
            if res["rev"] <= 0:
                st.info("Prognoz ko'rish uchun avval savdo ma'lumotlarini kiriting.")
            else:
                fc = res["forecast_df"]
                f1, f2, f3 = st.columns(3)
                f1.metric("Hozirgi holatda (1 yilda)", fmt_pul(fc["Hozirgi holat"].sum(), curr))
                f2.metric("Reja bajarilganda (1 yilda)", fmt_pul(fc["Reja bajarilganda"].sum(), curr), delta=fmt_pul(fc["Reja bajarilganda"].sum() - fc["Hozirgi holat"].sum(), curr))
                f3.metric("Yomon holatda (ehtiyot chorasi)", fmt_pul(fc["Yomon holat"].sum(), curr))

                fig_f = go.Figure()
                fig_f.add_scatter(x=fc["Oy"], y=fc["Reja bajarilganda"], name="Reja bajarilganda (Yaxshi)", mode="lines+markers", line=dict(color="#16A34A", width=3))
                fig_f.add_scatter(x=fc["Oy"], y=fc["Hozirgi holat"], name="Hozirgi holat (O'rtacha)", mode="lines+markers", line=dict(color="#2563EB", width=2.5))
                fig_f.add_scatter(x=fc["Oy"], y=fc["Yomon holat"], name="Yomon holat (Bozor tushsa)", mode="lines+markers", line=dict(color="#DC2626", dash="dash"))
                fig_f.add_hline(y=0, line_dash="dot", line_color="#64748B")
                fig_f.update_layout(title="Kelgusi 12 oyda oylik sof foyda qanday o'zgaradi?", height=400, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF", legend=dict(orientation="h", y=1.12))
                st.plotly_chart(fig_f, use_container_width=True)

        with r4:
            st.markdown(
                """
                <div class="hint-box">
                    Rahbar, hamkor yoki investorlarga ko'rsatish uchun barcha natijalar, baholar va yechimlar jamlangan tayyor hisobotni bir tugma bilan yuklab oling.
                </div>
                """,
                unsafe_allow_html=True,
            )
            dl1, dl2 = st.columns(2)
            safe_fn = re.sub(r"[^A-Za-z0-9_-]", "_", company["name"])
            with dl1:
                if FPDF_AVAILABLE:
                    pdf_data = build_pdf_report(company, res)
                    st.download_button(
                        "📄 Tayyor PDF hisobotni yuklab olish",
                        data=pdf_data,
                        file_name=f"{safe_fn}_hisobot.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )
                else:
                    st.warning("PDF uchun GitHub'dagi requirements.txt faylida 'fpdf2' bo'lishi kerak.")
            with dl2:
                xl_data = build_excel_report(company, res)
                st.download_button(
                    "📊 To'liq Excel hisobotni yuklab olish",
                    data=xl_data,
                    file_name=f"{safe_fn}_tahlil.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )


if __name__ == "__main__":
    main()
