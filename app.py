import io
import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Universal Biznes Analitika Platformasi v3.0",
    page_icon="🏢",
    layout="wide",
)

DB_PATH = "biznes_analitika.db"

# ---------------------------------------------------------
# 1. FAOLIYAT TURLARI KONFIGURATSIYASI (SOHAVIY MANTIQLAR)
# ---------------------------------------------------------
INDUSTRY_CONFIG = {
    "Savdo (Chakana / Ulgurji)": {
        "group_label": "Filial / Do'kon",
        "item_label": "Mahsulot (SKU)",
        "qty_label": "Sotilgan soni",
        "cogs_label": "Tovar tannarxi (COGS)",
        "extra_label": "Qaytarilgan soni (Vozvrat)",
        "extra_type": "qty",
        "uses_inventory": True,
        "expenses": ["Ijara", "Ish haqi", "Logistika", "Marketing", "Kommunal", "Soliq", "Boshqa"],
        "norms": {"min_net_margin": 12.0, "max_cogs_pct": 70.0, "max_extra_pct": 5.0},
    },
    "Ishlab chiqarish (Zavod / Sex)": {
        "group_label": "Sex / Ishlab chiqarish liniyasi",
        "item_label": "Tayyor mahsulot",
        "qty_label": "Ishlab chiqarilgan soni",
        "cogs_label": "Xomashyo va material sarfi",
        "extra_label": "Brak (yaroqsiz) soni",
        "extra_type": "qty",
        "uses_inventory": True,
        "expenses": ["Ish haqi (ishchilar)", "Elektr va Gaz", "Uskuna ta'miri", "Logistika", "Ijara", "Qadoqlash", "Boshqa"],
        "norms": {"min_net_margin": 15.0, "max_cogs_pct": 65.0, "max_extra_pct": 3.0},
    },
    "Xizmat ko'rsatish (IT, Klinika, Ta'lim, Servis)": {
        "group_label": "Bo'lim / Mutaxassis",
        "item_label": "Xizmat turi",
        "qty_label": "Mijoz / Buyurtma soni",
        "cogs_label": "To'g'ridan-to'g'ri xarajat (sarflanuvchi)",
        "extra_label": "Sarflangan ish soati",
        "extra_type": "hours",
        "uses_inventory": False,
        "expenses": ["Mutaxassislar ish haqi", "Ofis ijarasi", "Reklama va Marketing", "Dasturiy ta'minot", "Kommunal", "Boshqa"],
        "norms": {"min_net_margin": 25.0, "max_cogs_pct": 30.0, "max_extra_pct": 0.0},
    },
    "Umumiy ovqatlanish (Restoran / Kafe / HoReCa)": {
        "group_label": "Filial / Zal",
        "item_label": "Taom / Menyu bo'limi",
        "qty_label": "Cheklar / Porsiya soni",
        "cogs_label": "Mahsulot sarfi (Food Cost)",
        "extra_label": "Isrof / Spisaniye summasi",
        "extra_type": "money",
        "uses_inventory": True,
        "expenses": ["Xodimlar ish haqi (Labor)", "Ijara", "Kommunal", "Yetkazib berish", "Marketing", "Boshqa"],
        "norms": {"min_net_margin": 15.0, "max_cogs_pct": 35.0, "max_extra_pct": 4.0},
    },
    "Qurilish va Loyihaviy biznes": {
        "group_label": "Obyekt / Loyiha nomi",
        "item_label": "Ish bosqichi / Yo'nalish",
        "qty_label": "Hajm (m² / birlik)",
        "cogs_label": "Qurilish materiali va subpudrat",
        "extra_label": "Rejadan ortiqcha xarajat / Jarima",
        "extra_type": "money",
        "uses_inventory": True,
        "expenses": ["Usta va muhandislar ish haqi", "Texnika ijarasi", "Transport/Logistika", "Ofis va boshqaruv", "Soliq", "Boshqa"],
        "norms": {"min_net_margin": 18.0, "max_cogs_pct": 68.0, "max_extra_pct": 5.0},
    },
}


# ---------------------------------------------------------
# 2. SQLITE MA'LUMOTLAR BAZASI QATLAMI
# ---------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                industry TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'UZS',
                start_cash REAL NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                tx_date TEXT NOT NULL,
                group_name TEXT NOT NULL,
                item_name TEXT NOT NULL,
                expense_type TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 1,
                revenue REAL NOT NULL DEFAULT 0,
                cogs REAL NOT NULL DEFAULT 0,
                opex REAL NOT NULL DEFAULT 0,
                extra_metric REAL NOT NULL DEFAULT 0,
                notes TEXT DEFAULT '',
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                partner TEXT NOT NULL,
                debt_type TEXT NOT NULL,
                due_date TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                notes TEXT DEFAULT '',
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                warehouse TEXT NOT NULL DEFAULT 'Asosiy ombor',
                qty REAL NOT NULL DEFAULT 0,
                unit_cost REAL NOT NULL DEFAULT 0,
                last_sale_date TEXT NOT NULL,
                monthly_sales REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            );
            """
        )


def get_companies() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM companies ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def create_company(name: str, industry: str, currency: str, start_cash: float) -> tuple[bool, str]:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO companies (name, industry, currency, start_cash) VALUES (?, ?, ?, ?)",
                (name.strip(), industry, currency, float(start_cash)),
            )
        return True, "Korxona muvaffaqiyatli yaratildi!"
    except sqlite3.IntegrityError:
        return False, "Bunday nomli korxona bazada allaqachon mavjud."


def update_company_cash(company_id: int, new_cash: float) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE companies SET start_cash = ? WHERE id = ?", (float(new_cash), company_id))


def delete_company(company_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM transactions WHERE company_id = ?", (company_id,))
        conn.execute("DELETE FROM debts WHERE company_id = ?", (company_id,))
        conn.execute("DELETE FROM inventory WHERE company_id = ?", (company_id,))
        conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))


def load_table(table: str, company_id: int) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query(f"SELECT * FROM {table} WHERE company_id = ?", conn, params=(company_id,))


def insert_transaction(company_id: int, rec: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO transactions
            (company_id, tx_date, group_name, item_name, expense_type, quantity, revenue, cogs, opex, extra_metric, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                str(rec["tx_date"]),
                str(rec["group_name"]),
                str(rec["item_name"]),
                str(rec["expense_type"]),
                float(rec["quantity"]),
                float(rec["revenue"]),
                float(rec["cogs"]),
                float(rec["opex"]),
                float(rec["extra_metric"]),
                str(rec.get("notes", "")),
            ),
        )


def replace_transactions(company_id: int, df: pd.DataFrame) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM transactions WHERE company_id = ?", (company_id,))
        for _, r in df.iterrows():
            if pd.isna(r["tx_date"]) or str(r["item_name"]).strip() == "":
                continue
            dt_str = pd.to_datetime(r["tx_date"]).strftime("%Y-%m-%d")
            conn.execute(
                """
                INSERT INTO transactions
                (company_id, tx_date, group_name, item_name, expense_type, quantity, revenue, cogs, opex, extra_metric, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    dt_str,
                    str(r.get("group_name", "Asosiy") or "Asosiy"),
                    str(r["item_name"]),
                    str(r.get("expense_type", "Boshqa") or "Boshqa"),
                    float(pd.to_numeric(r.get("quantity", 1), errors="coerce") or 0),
                    float(pd.to_numeric(r.get("revenue", 0), errors="coerce") or 0),
                    float(pd.to_numeric(r.get("cogs", 0), errors="coerce") or 0),
                    float(pd.to_numeric(r.get("opex", 0), errors="coerce") or 0),
                    float(pd.to_numeric(r.get("extra_metric", 0), errors="coerce") or 0),
                    str(r.get("notes", "") or ""),
                ),
            )


def insert_debt(company_id: int, rec: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO debts (company_id, partner, debt_type, due_date, amount, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (company_id, rec["partner"], rec["debt_type"], str(rec["due_date"]), float(rec["amount"]), rec.get("notes", "")),
        )


def replace_debts(company_id: int, df: pd.DataFrame) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM debts WHERE company_id = ?", (company_id,))
        for _, r in df.iterrows():
            if pd.isna(r["due_date"]) or str(r["partner"]).strip() == "":
                continue
            dt_str = pd.to_datetime(r["due_date"]).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO debts (company_id, partner, debt_type, due_date, amount, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    company_id,
                    str(r["partner"]),
                    str(r["debt_type"]),
                    dt_str,
                    float(pd.to_numeric(r["amount"], errors="coerce") or 0),
                    str(r.get("notes", "") or ""),
                ),
            )


def insert_inventory(company_id: int, rec: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO inventory (company_id, item_name, warehouse, qty, unit_cost, last_sale_date, monthly_sales)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                rec["item_name"],
                rec["warehouse"],
                float(rec["qty"]),
                float(rec["unit_cost"]),
                str(rec["last_sale_date"]),
                float(rec["monthly_sales"]),
            ),
        )


def replace_inventory(company_id: int, df: pd.DataFrame) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM inventory WHERE company_id = ?", (company_id,))
        for _, r in df.iterrows():
            if pd.isna(r["last_sale_date"]) or str(r["item_name"]).strip() == "":
                continue
            dt_str = pd.to_datetime(r["last_sale_date"]).strftime("%Y-%m-%d")
            conn.execute(
                """
                INSERT INTO inventory (company_id, item_name, warehouse, qty, unit_cost, last_sale_date, monthly_sales)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    str(r["item_name"]),
                    str(r.get("warehouse", "Asosiy ombor") or "Asosiy ombor"),
                    float(pd.to_numeric(r["qty"], errors="coerce") or 0),
                    float(pd.to_numeric(r["unit_cost"], errors="coerce") or 0),
                    dt_str,
                    float(pd.to_numeric(r["monthly_sales"], errors="coerce") or 0),
                ),
            )


# ---------------------------------------------------------
# 3. YORDAMCHI FORMATLASH VA SHABLON GENERATORLARI
# ---------------------------------------------------------
def fmt_money(val: float, curr: str) -> str:
    return f"{val:,.0f} {curr}".replace(",", " ")


def build_empty_template_excel(cfg: dict) -> bytes:
    """Tanlangan faoliyat turi uchun bo'sh Excel kiritish shablonini yaratadi."""
    buf = io.BytesIO()
    tx_cols = [
        "Sana (YYYY-MM-DD)",
        cfg["group_label"],
        cfg["item_label"],
        "Xarajat turi",
        cfg["qty_label"],
        "Tushum",
        cfg["cogs_label"],
        "Operatsion xarajat (OPEX)",
        cfg["extra_label"],
        "Izoh",
    ]
    debt_cols = ["Kontragent", "Tur (Debitor / Kreditor)", "Tolov muddati (YYYY-MM-DD)", "Summa", "Izoh"]
    inv_cols = ["Mahsulot", "Ombor", "Qoldiq soni", "Birlik tannarxi", "Oxirgi sotuv sanasi (YYYY-MM-DD)", "Oylik ortacha sotuv"]

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(columns=tx_cols).to_excel(writer, index=False, sheet_name="Operatsiyalar")
        pd.DataFrame(columns=debt_cols).to_excel(writer, index=False, sheet_name="Qarzlar")
        if cfg["uses_inventory"]:
            pd.DataFrame(columns=inv_cols).to_excel(writer, index=False, sheet_name="Ombor")
    return buf.getvalue()


def export_analysis_excel(tx_df: pd.DataFrame, item_df: pd.DataFrame, group_df: pd.DataFrame, debts_df: pd.DataFrame, inv_df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        if not item_df.empty:
            item_df.to_excel(writer, index=False, sheet_name="Mahsulot_Xizmat_Tahlili")
        if not group_df.empty:
            group_df.to_excel(writer, index=False, sheet_name="Filial_Loyiha_Tahlili")
        if not tx_df.empty:
            tx_df.to_excel(writer, index=False, sheet_name="Barcha_Operatsiyalar")
        if not debts_df.empty:
            debts_df.to_excel(writer, index=False, sheet_name="Qarzlar")
        if not inv_df.empty:
            inv_df.to_excel(writer, index=False, sheet_name="Ombor")
    return buf.getvalue()


# ---------------------------------------------------------
# 4. SOHAGA MOSLASHUVCHAN ANALITIKA VA DIAGNOSTIKA DVIGATELI
# ---------------------------------------------------------
def analyze_company(
    tx_df: pd.DataFrame,
    debts_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    industry: str,
    cfg: dict,
    start_cash: float,
    forecast_days: int,
    ar_recovery_pct: float,
    curr: str,
) -> dict:
    recs = []
    res = {"has_tx": not tx_df.empty}

    if tx_df.empty:
        return res

    df = tx_df.copy()
    df["tx_date"] = pd.to_datetime(df["tx_date"], errors="coerce")
    df = df.dropna(subset=["tx_date"]).sort_values("tx_date")
    df["Oy"] = df["tx_date"].dt.to_period("M").astype(str)
    df["Sof_foyda"] = df["revenue"] - df["cogs"] - df["opex"]
    ref_date = max(df["tx_date"].max(), pd.Timestamp(date.today()))

    total_rev = df["revenue"].sum()
    total_cogs = df["cogs"].sum()
    total_opex = df["opex"].sum()
    total_qty = df["quantity"].sum()
    total_extra = df["extra_metric"].sum()
    gross_profit = total_rev - total_cogs
    net_profit = gross_profit - total_opex
    net_margin = (net_profit / total_rev * 100) if total_rev > 0 else 0.0
    cogs_pct = (total_cogs / total_rev * 100) if total_rev > 0 else 0.0
    opex_pct = (total_opex / total_rev * 100) if total_rev > 0 else 0.0

    # 1) Mahsulot / Xizmat kesimida tahlil
    item_df = df.groupby("item_name", as_index=False).agg(
        Miqdor=("quantity", "sum"),
        Tushum=("revenue", "sum"),
        Tannarx=("cogs", "sum"),
        OPEX=("opex", "sum"),
        Qoshimcha=("extra_metric", "sum"),
    )
    item_df["Sof_foyda"] = item_df["Tushum"] - item_df["Tannarx"] - item_df["OPEX"]
    item_df["Marja_%"] = np.where(item_df["Tushum"] > 0, item_df["Sof_foyda"] / item_df["Tushum"] * 100, 0.0)
    item_df["Birlik_tannarx"] = np.where(item_df["Miqdor"] > 0, item_df["Tannarx"] / item_df["Miqdor"], 0.0)
    item_df = item_df.sort_values("Sof_foyda", ascending=True)
    loss_items = item_df[item_df["Sof_foyda"] < 0]

    # ABC tahlil
    abc_df = item_df.sort_values("Tushum", ascending=False).copy()
    abc_df["Ulush_%"] = (abc_df["Tushum"] / total_rev * 100) if total_rev > 0 else 0.0
    abc_df["Kumulyativ_%"] = abc_df["Ulush_%"].cumsum()
    abc_df["ABC"] = np.where(
        abc_df["Kumulyativ_%"] <= 80, "A (Asosiy)", np.where(abc_df["Kumulyativ_%"] <= 95, "B (O'rta)", "C (Past)")
    )

    # 2) Filial / Sex / Bo'lim / Obyekt tahlili
    group_df = df.groupby("group_name", as_index=False).agg(
        Tushum=("revenue", "sum"), Tannarx=("cogs", "sum"), OPEX=("opex", "sum"), Qoshimcha=("extra_metric", "sum")
    )
    group_df["Sof_foyda"] = group_df["Tushum"] - group_df["Tannarx"] - group_df["OPEX"]
    group_df["Marja_%"] = np.where(group_df["Tushum"] > 0, group_df["Sof_foyda"] / group_df["Tushum"] * 100, 0.0)
    group_df = group_df.sort_values("Marja_%", ascending=True)

    # 3) Oylik dinamika va Anomaliyalar
    monthly_df = df.groupby("Oy", as_index=False).agg(
        Tushum=("revenue", "sum"), Tannarx=("cogs", "sum"), OPEX=("opex", "sum")
    ).sort_values("Oy")
    monthly_df["Sof_foyda"] = monthly_df["Tushum"] - monthly_df["Tannarx"] - monthly_df["OPEX"]
    opex_mean = monthly_df["OPEX"].mean()
    opex_std = monthly_df["OPEX"].std(ddof=0)
    monthly_df["Z_score"] = (monthly_df["OPEX"] - opex_mean) / opex_std if (opex_std > 0 and len(monthly_df) >= 3) else 0.0
    anomalies = monthly_df[monthly_df["Z_score"] > 1.3]

    # 4) Xarajat moddalari
    exp_df = df.groupby("expense_type", as_index=False).agg(OPEX=("opex", "sum")).sort_values("OPEX", ascending=False)
    exp_df["Ulush_%"] = (exp_df["OPEX"] / total_opex * 100) if total_opex > 0 else 0.0

    # 5) SOHAGA XOS MAXSUS KO'RSATKICHLAR VA ME'YORLAR
    industry_kpis = []
    norms = cfg["norms"]

    if industry == "Umumiy ovqatlanish (Restoran / Kafe / HoReCa)":
        labor_cost = df[df["expense_type"].str.lower().str.contains("ish haqi|labor")]["opex"].sum()
        prime_cost_pct = ((total_cogs + labor_cost) / total_rev * 100) if total_rev > 0 else 0.0
        avg_check = (total_rev / total_qty) if total_qty > 0 else 0.0
        waste_pct = (total_extra / total_cogs * 100) if total_cogs > 0 else 0.0
        industry_kpis = [
            ("Food Cost %", f"{cogs_pct:.1f}%", f"Me'yor: ≤ {norms['max_cogs_pct']}%", cogs_pct <= norms["max_cogs_pct"]),
            ("Prime Cost (Food+Labor)", f"{prime_cost_pct:.1f}%", "Me'yor: ≤ 65%", prime_cost_pct <= 65),
            ("O'rtacha chek", fmt_money(avg_check, curr), f"Jami {total_qty:,.0f} chek", True),
            ("Isrof ulushi", f"{waste_pct:.1f}%", f"Me'yor: ≤ {norms['max_extra_pct']}%", waste_pct <= norms["max_extra_pct"]),
        ]
        if cogs_pct > norms["max_cogs_pct"]:
            recs.append(("Yuqori xavf", "HoReCa Food Cost", f"Food Cost {cogs_pct:.1f}% ni tashkil etmoqda (me'yor ≤35%).", "Texnologik kartalarni qayta tekshiring, yetkazib beruvchilarni almashtiring yoki menyu narxini oshiring."))
        if waste_pct > norms["max_extra_pct"]:
            recs.append(("Ogohlantirish", "Isrof nazorati", f"Mahsulot isrofi {fmt_money(total_extra, curr)} ({waste_pct:.1f}%) ga yetgan.", "Kunlik xarid hajmini cheklar soniga bog'lang va oshxona omborini nazorat qiling."))

    elif industry == "Ishlab chiqarish (Zavod / Sex)":
        defect_rate = (total_extra / total_qty * 100) if total_qty > 0 else 0.0
        unit_cost = (total_cogs / total_qty) if total_qty > 0 else 0.0
        unit_full_cost = ((total_cogs + total_opex) / total_qty) if total_qty > 0 else 0.0
        industry_kpis = [
            ("Brak (Yaroqsiz) darajasi", f"{defect_rate:.2f}%", f"Me'yor: ≤ {norms['max_extra_pct']}%", defect_rate <= norms["max_extra_pct"]),
            ("Xomashyo ulushi", f"{cogs_pct:.1f}%", f"Me'yor: ≤ {norms['max_cogs_pct']}%", cogs_pct <= norms["max_cogs_pct"]),
            ("O'rtacha xomashyo tannarxi", fmt_money(unit_cost, curr), "1 birlik uchun", True),
            ("To'liq birlik tannarxi", fmt_money(unit_full_cost, curr), "Xomashyo + OPEX", True),
        ]
        if defect_rate > norms["max_extra_pct"]:
            recs.append(("Yuqori xavf", "Ishlab chiqarish braki", f"Brak ulushi {defect_rate:.1f}% ({total_extra:,.0f} dona) bo'lib, me'yordan yuqori.", "Sifat nazorati (OTK) bosqichini kuchaytiring va brak ko'p chiqayotgan sex/uskunani ta'mirlang."))

    elif industry == "Xizmat ko'rsatish (IT, Klinika, Ta'lim, Servis)":
        rev_per_hour = (total_rev / total_extra) if total_extra > 0 else 0.0
        profit_per_hour = (net_profit / total_extra) if total_extra > 0 else 0.0
        avg_order = (total_rev / total_qty) if total_qty > 0 else 0.0
        industry_kpis = [
            ("1 soatlik tushum", fmt_money(rev_per_hour, curr), f"Jami {total_extra:,.1f} soat", True),
            ("1 soatlik sof foyda", fmt_money(profit_per_hour, curr), "Vaqt samaradorligi", profit_per_hour > 0),
            ("O'rtacha buyurtma narxi", fmt_money(avg_order, curr), f"{total_qty:,.0f} ta mijoz/xizmat", True),
            ("Sof marja", f"{net_margin:.1f}%", f"Me'yor: ≥ {norms['min_net_margin']}%", net_margin >= norms["min_net_margin"]),
        ]
        if net_margin < norms["min_net_margin"]:
            recs.append(("Ogohlantirish", "Xizmat marjasi", f"Sof marja ({net_margin:.1f}%) xizmat sohasi me'yoridan ({norms['min_net_margin']}%) past.", "1 soatlik daromadi past bo'lgan xizmatlar narxini ko'taring yoki bajarish vaqtini avtomatlashtiring."))

    elif industry == "Qurilish va Loyihaviy biznes":
        overrun_pct = (total_extra / total_rev * 100) if total_rev > 0 else 0.0
        industry_kpis = [
            ("Material/Subpudrat ulushi", f"{cogs_pct:.1f}%", f"Me'yor: ≤ {norms['max_cogs_pct']}%", cogs_pct <= norms["max_cogs_pct"]),
            ("Rejadan ortiqcha sarf", fmt_money(total_extra, curr), f"Tushumning {overrun_pct:.1f}% i", overrun_pct <= norms["max_extra_pct"]),
            ("Obyektlar soni", f"{df['group_name'].nunique()} ta", "Faol loyihalar", True),
            ("Loyiha sof marjasi", f"{net_margin:.1f}%", f"Me'yor: ≥ {norms['min_net_margin']}%", net_margin >= norms["min_net_margin"]),
        ]
        if overrun_pct > norms["max_extra_pct"]:
            recs.append(("Yuqori xavf", "Byudjetdan og'ish", f"Rejadan ortiqcha xarajat/jarima {fmt_money(total_extra, curr)} ni tashkil etdi.", "Smeta nazoratini haftalik rejimga o'tkazing va xaridlarda oldindan narx fiksatsiya qiling."))

    else:  # Savdo
        return_rate = (total_extra / total_qty * 100) if total_qty > 0 else 0.0
        gross_margin = (gross_profit / total_rev * 100) if total_rev > 0 else 0.0
        avg_sale = (total_rev / total_qty) if total_qty > 0 else 0.0
        industry_kpis = [
            ("Yalpi marja (Gross Margin)", f"{gross_margin:.1f}%", f"Me'yor: ≥ {100 - norms['max_cogs_pct']:.0f}%", gross_margin >= (100 - norms["max_cogs_pct"])),
            ("Qaytarish (Vozvrat) ulushi", f"{return_rate:.1f}%", f"Me'yor: ≤ {norms['max_extra_pct']}%", return_rate <= norms["max_extra_pct"]),
            ("O'rtacha sotuv narxi", fmt_money(avg_sale, curr), f"Jami {total_qty:,.0f} dona", True),
            ("OPEX yuklamasi", f"{opex_pct:.1f}%", "Tushumga nisbatan", opex_pct <= 25),
        ]
        if return_rate > norms["max_extra_pct"]:
            recs.append(("Ogohlantirish", "Tovar qaytarilishi", f"Vozvrat ulushi {return_rate:.1f}% ({total_extra:,.0f} dona).", "Eng ko'p qaytarilayotgan mahsulotlar sifatini va yetkazib beruvchisini tekshiring."))

    # Umumiy P&L tavsiyalari
    if not loss_items.empty:
        loss_sum = abs(loss_items["Sof_foyda"].sum())
        names = ", ".join(loss_items["item_name"].head(3).tolist())
        recs.append(("Yuqori xavf", f"Zararli {cfg['item_label']}", f"Zararga ishlayotganlar: {names}. Jami zarar: {fmt_money(loss_sum, curr)}.", "Ushbu pozitsiyalarning narxini qayta ko'ring yoki to'xtatib, foydani darhol oshiring."))
    if not anomalies.empty:
        for _, r in anomalies.iterrows():
            recs.append(("Ogohlantirish", "Xarajat anomaliyasi", f"{r['Oy']} oyida OPEX me'yordan keskin yuqori (Z={r['Z_score']:.2f}).", "O'sha oydagi barcha yirik xarajat moddalarini tekshiring."))
    if len(group_df) > 1:
        w, b = group_df.iloc[0], group_df.iloc[-1]
        if b["Marja_%"] - w["Marja_%"] > 8:
            recs.append(("Samaradorlik", cfg["group_label"], f"'{w['group_name']}' marjasi ({w['Marja_%']:.1f}%) yetakchi '{b['group_name']}' ({b['Marja_%']:.1f}%) dan past.", "Past samarali bo'limda xarajatlarni qisqartiring va yetakchi tajribasini qo'llang."))

    # 6) QARZLAR TAHLILI (A/R & A/P)
    debts_res = None
    if not debts_df.empty:
        ddf = debts_df.copy()
        ddf["due_date"] = pd.to_datetime(ddf["due_date"], errors="coerce")
        ddf = ddf.dropna(subset=["due_date"])
        ddf["Kechikish_kuni"] = (ref_date - ddf["due_date"]).dt.days
        ddf["Guruh"] = ddf["Kechikish_kuni"].apply(
            lambda d: "Muddati kelmagan" if d <= 0 else ("1-30 kun" if d <= 30 else ("31-60 kun" if d <= 60 else ("61-90 kun" if d <= 90 else "90+ kun (Kritik)")))
        )
        ar = ddf[ddf["debt_type"] == "Debitor (Bizga qarz)"]
        ap = ddf[ddf["debt_type"] == "Kreditor (Bizning qarz)"]
        ar_over = ar[ar["Kechikish_kuni"] > 0]["amount"].sum()
        ar_crit = ar[ar["Kechikish_kuni"] > 90]["amount"].sum()
        ap_over = ap[ap["Kechikish_kuni"] > 0]["amount"].sum()
        if ar_crit > 0:
            recs.append(("Yuqori xavf", "Debitor qarz", f"90+ kun kechikkan kritik qarzlar: {fmt_money(ar_crit, curr)}.", "Nasiyani to'xtating va qarzni undirish bo'yicha rasmiy talabnoma yuboring."))
        if ap_over > 0:
            recs.append(("Ogohlantirish", "Kreditor qarz", f"Muddati o'tgan to'lovlarimiz: {fmt_money(ap_over, curr)}.", "Yetkazib beruvchilar bilan to'lov grafigini kelishib oling."))
        debts_res = {
            "df": ddf, "ar": ar, "ap": ap,
            "ar_total": ar["amount"].sum(), "ar_over": ar_over, "ar_crit": ar_crit,
            "ap_total": ap["amount"].sum(), "ap_over": ap_over,
        }

    # 7) OMBOR VA DEAD STOCK TAHLILI
    inv_res = None
    if cfg["uses_inventory"] and not inv_df.empty:
        idf = inv_df.copy()
        idf["last_sale_date"] = pd.to_datetime(idf["last_sale_date"], errors="coerce")
        idf["Muzlatilgan_kapital"] = idf["qty"] * idf["unit_cost"]
        idf["Sotilmagan_kun"] = (ref_date - idf["last_sale_date"]).dt.days.fillna(180).clip(lower=0)
        daily_s = idf["monthly_sales"] / 30.0
        idf["DIO_kun"] = np.where(daily_s > 0, idf["qty"] / daily_s, 999.0).round(0)
        idf["Holat"] = idf.apply(
            lambda r: "O'lik tovar (Dead Stock)" if (r["Sotilmagan_kun"] >= 90 or r["monthly_sales"] <= 0)
            else ("Sekin aylanuvchi" if (r["Sotilmagan_kun"] >= 45 or r["DIO_kun"] > 120) else "Sog'lom zaxira"),
            axis=1,
        )
        dead_df = idf[idf["Holat"] == "O'lik tovar (Dead Stock)"]
        dead_val = dead_df["Muzlatilgan_kapital"].sum()
        tot_inv = idf["Muzlatilgan_kapital"].sum()
        if dead_val > 0:
            recs.append(("Yuqori xavf", "O'lik tovarlar", f"Omborda {fmt_money(dead_val, curr)} ({dead_val/tot_inv*100:.1f}%) kapital muzlab yotibdi.", f"25% chegirma bilan sotsangiz kassaga darhol {fmt_money(dead_val*0.75, curr)} qaytadi."))
        inv_res = {"df": idf.sort_values("Muzlatilgan_kapital", ascending=False), "dead_val": dead_val, "total_val": tot_inv, "dead_cnt": len(dead_df)}

    # 8) CASH FLOW PROGNOZI (KASSA UZILISHI)
    daily = df.groupby("tx_date", as_index=False).agg(Kirim=("revenue", "sum"), Tannarx=("cogs", "sum"), OPEX=("opex", "sum"))
    daily["Chiqim"] = daily["Tannarx"] + daily["OPEX"]
    avg_in = daily["Kirim"].mean()
    avg_out = daily["Chiqim"].mean()

    fut_dates = pd.date_range(ref_date + timedelta(days=1), periods=forecast_days, freq="D")
    fc = pd.DataFrame({"Sana": fut_dates, "Kirim": avg_in, "Chiqim": avg_out})

    if debts_res is not None:
        ddf = debts_res["df"]
        for _, r in ddf[(ddf["debt_type"] == "Debitor (Bizga qarz)") & (ddf["Kechikish_kuni"] <= 0)].iterrows():
            fc.loc[fc["Sana"] == r["due_date"], "Kirim"] += r["amount"] * (ar_recovery_pct / 100.0)
        for _, r in ddf[(ddf["debt_type"] == "Kreditor (Bizning qarz)") & (ddf["Kechikish_kuni"] <= 0)].iterrows():
            fc.loc[fc["Sana"] == r["due_date"], "Chiqim"] += r["amount"]
        if debts_res["ap_over"] > 0:
            p_days = min(10, forecast_days)
            fc.loc[: p_days - 1, "Chiqim"] += debts_res["ap_over"] / p_days
        if debts_res["ar_over"] > 0 and ar_recovery_pct > 0:
            s_i, e_i = min(7, forecast_days - 1), min(21, forecast_days - 1)
            fc.loc[s_i:e_i, "Kirim"] += (debts_res["ar_over"] * (ar_recovery_pct / 100.0)) / max(1, e_i - s_i + 1)

    fc["Sof_oqim"] = fc["Kirim"] - fc["Chiqim"]
    fc["Balans"] = start_cash + fc["Sof_oqim"].cumsum()
    gap_df = fc[fc["Balans"] < 0]
    if not gap_df.empty:
        recs.insert(0, ("Yuqori xavf", "Kassa uzilishi", f"{gap_df['Sana'].iloc[0].date()} dan boshlab {len(gap_df)} kun kassa manfiyga kiradi (min: {fmt_money(fc['Balans'].min(), curr)}).", "Debitor qarzni tezlashtiring, o'lik tovarlarni aksiyada soting yoki kreditor to'lovini kechiktiring."))

    if not recs:
        recs.append(("Barqaror", "Umumiy holat", "Kiritilgan ma'lumotlarda kritik zarar yoki xavf aniqlanmadi.", "A-toifadagi mahsulot/xizmatlarni kengaytirishda davom eting."))

    res.update(
        {
            "df": df,
            "kpi": {
                "rev": total_rev, "cogs": total_cogs, "opex": total_opex,
                "gross": gross_profit, "net": net_profit, "margin": net_margin,
            },
            "industry_kpis": industry_kpis,
            "item_df": item_df,
            "loss_items": loss_items,
            "abc_df": abc_df,
            "group_df": group_df,
            "monthly_df": monthly_df,
            "exp_df": exp_df,
            "debts": debts_res,
            "inventory": inv_res,
            "cf": {"fc": fc, "gap": gap_df, "min_bal": fc["Balans"].min(), "end_bal": fc["Balans"].iloc[-1]},
            "recs": recs,
        }
    )
    return res


# ---------------------------------------------------------
# 5. ILOVANI ISHGA TUSHIRISH VA SIDEBAR (KORXONA BOSHQARUVI)
# ---------------------------------------------------------
init_db()
companies = get_companies()

st.sidebar.title("🏢 Korxonalar Boshqaruvi")

with st.sidebar.expander("➕ Yangi korxona qo'shish", expanded=(len(companies) == 0)):
    with st.form("new_company_form", clear_on_submit=True):
        c_name = st.text_input("Korxona nomi *", placeholder="Masalan: Baraka Savdo MChJ")
        c_ind = st.selectbox("Faoliyat turi *", list(INDUSTRY_CONFIG.keys()))
        c_curr = st.selectbox("Asosiy valyuta", ["UZS", "USD", "EUR"])
        c_cash = st.number_input("Hozirgi kassa qoldig'i", min_value=0.0, value=0.0, step=1_000_000.0)
        if st.form_submit_button("Korxonani yaratish", type="primary", use_container_width=True):
            if not c_name.strip():
                st.error("Korxona nomini kiriting.")
            else:
                ok, msg = create_company(c_name, c_ind, c_curr, c_cash)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

if not companies:
    st.title("🏢 Universal Biznes Analitika Platformasi")
    st.info(
        "Platformada hech qanday oldindan yozilgan soxta ma'lumot yo'q. "
        "Ishni boshlash uchun **chap paneldan yangi korxona yarating** va uning faoliyat turini tanlang. "
        "Shundan so'ng barcha savdo, xarajat, qarz va ombor ma'lumotlarini to'g'ridan-to'g'ri sayt ichida kiritishingiz mumkin."
    )
    st.stop()

# Faol korxonani tanlash
comp_map = {f"{c['name']} ({c['industry'].split(' ')[0]})": c for c in companies}
selected_label = st.sidebar.selectbox("Faol korxonani tanlang", list(comp_map.keys()))
company = comp_map[selected_label]
cid = company["id"]
curr = company["currency"]
industry = company["industry"]
cfg = INDUSTRY_CONFIG[industry]

st.sidebar.caption(f"📌 Faoliyat turi: **{industry}**")

# Kassa va prognoz sozlamalari
st.sidebar.divider()
st.sidebar.subheader("💵 Cash Flow Sozlamalari")
new_cash = st.sidebar.number_input(
    f"Kassa qoldig'i ({curr})", min_value=0.0, value=float(company["start_cash"]), step=1_000_000.0
)
if new_cash != float(company["start_cash"]):
    update_company_cash(cid, new_cash)
    company["start_cash"] = new_cash

forecast_days = st.sidebar.slider("Prognoz davri (kun)", 15, 90, 45, step=15)
ar_recovery = st.sidebar.slider("Debitor qaytish ehtimoli (%)", 0, 100, 60, step=5)

# Bo'sh shablon yuklab olish
st.sidebar.divider()
st.sidebar.download_button(
    label="📥 Ushbu soha uchun bo'sh Excel shablon",
    data=build_empty_template_excel(cfg),
    file_name=f"{company['name'].replace(' ', '_')}_shablon.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

with st.sidebar.expander("🗑️ Korxonani o'chirish"):
    st.warning("Bu amal korxonaning bazadagi barcha yozuvlarini o'chiradi.")
    if st.button("Ha, butunlay o'chirish", type="secondary", use_container_width=True):
        delete_company(cid)
        st.rerun()

# Bazadan joriy korxona ma'lumotlarini yuklash
tx_df = load_table("transactions", cid)
debts_df = load_table("debts", cid)
inv_df = load_table("inventory", cid)

# Tahlilni hisoblash
analysis = analyze_company(
    tx_df, debts_df, inv_df, industry, cfg, float(company["start_cash"]), forecast_days, float(ar_recovery), curr
)

# ---------------------------------------------------------
# 6. ASOSIY INTERFEYS VA TABLAR
# ---------------------------------------------------------
st.title(f"🏢 {company['name']}")
st.caption(f"Faoliyat turi: **{industry}** | Valyuta: **{curr}** | Bazadagi operatsiyalar: **{len(tx_df)} ta**")

tab_titles = [
    "✍️ Ma'lumot Kiritish",
    "🏭 Soha Tahlili & P&L",
    "💵 Cash Flow & Qarzlar",
]
if cfg["uses_inventory"]:
    tab_titles.append("📦 Ombor & Dead Stock")
tab_titles.append("🎯 Diagnostika & Simulyator")

tabs = st.tabs(tab_titles)
tab_idx = 0

# =========================================================
# TAB 1: MA'LUMOT KIRITISH (FORMA + JADVAL MUHARRIRI + EXCEL)
# =========================================================
with tabs[tab_idx]:
    sub_tabs = ["📝 Operatsiya kiritish", "🧾 Qarzlar kiritish"]
    if cfg["uses_inventory"]:
        sub_tabs.append("📦 Ombor kiritish")
    sub_tabs.append("📤 Excel / CSV import")
    in_tabs = st.tabs(sub_tabs)

    # 1A: Operatsiyalar (Forma + Jonli jadval)
    with in_tabs[0]:
        st.subheader(f"Yangi yozuv qo'shish ({industry})")
        with st.form("add_tx_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            f_date = c1.date_input("Sana *", value=date.today())
            f_group = c2.text_input(f"{cfg['group_label']} *", value="Asosiy")
            f_item = c3.text_input(f"{cfg['item_label']} *")
            f_exp = c4.selectbox("Asosiy xarajat turi", cfg["expenses"])

            c5, c6, c7, c8, c9 = st.columns(5)
            f_qty = c5.number_input(cfg["qty_label"], min_value=0.0, value=1.0, step=1.0)
            f_rev = c6.number_input(f"Tushum ({curr})", min_value=0.0, value=0.0, step=100_000.0)
            f_cogs = c7.number_input(f"{cfg['cogs_label']}", min_value=0.0, value=0.0, step=100_000.0)
            f_opex = c8.number_input(f"OPEX ({curr})", min_value=0.0, value=0.0, step=50_000.0)
            f_extra = c9.number_input(cfg["extra_label"], min_value=0.0, value=0.0, step=1.0)
            f_note = st.text_input("Izoh (ixtiyoriy)")

            if st.form_submit_button("➕ Bazaga qo'shish", type="primary"):
                if not f_item.strip():
                    st.error(f"Iltimos, '{cfg['item_label']}' nomini kiriting.")
                else:
                    insert_transaction(
                        cid,
                        {
                            "tx_date": f_date, "group_name": f_group, "item_name": f_item,
                            "expense_type": f_exp, "quantity": f_qty, "revenue": f_rev,
                            "cogs": f_cogs, "opex": f_opex, "extra_metric": f_extra, "notes": f_note,
                        },
                    )
                    st.success("Yozuv bazaga saqlandi!")
                    st.rerun()

        st.divider()
        st.subheader("✏️ Jadval ko'rinishida tahrirlash (Excel kabi qator qo'shish / o'chirish)")
        edit_tx = tx_df[["tx_date", "group_name", "item_name", "expense_type", "quantity", "revenue", "cogs", "opex", "extra_metric", "notes"]].copy() if not tx_df.empty else pd.DataFrame(
            columns=["tx_date", "group_name", "item_name", "expense_type", "quantity", "revenue", "cogs", "opex", "extra_metric", "notes"]
        )
        edit_tx["tx_date"] = pd.to_datetime(edit_tx["tx_date"], errors="coerce").dt.date

        edited_tx = st.data_editor(
            edit_tx,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "tx_date": st.column_config.DateColumn("Sana", default=date.today()),
                "group_name": st.column_config.TextColumn(cfg["group_label"], default="Asosiy"),
                "item_name": st.column_config.TextColumn(cfg["item_label"]),
                "expense_type": st.column_config.SelectboxColumn("Xarajat turi", options=cfg["expenses"], default=cfg["expenses"][0]),
                "quantity": st.column_config.NumberColumn(cfg["qty_label"], min_value=0, default=1),
                "revenue": st.column_config.NumberColumn(f"Tushum ({curr})", min_value=0, default=0),
                "cogs": st.column_config.NumberColumn(cfg["cogs_label"], min_value=0, default=0),
                "opex": st.column_config.NumberColumn("OPEX", min_value=0, default=0),
                "extra_metric": st.column_config.NumberColumn(cfg["extra_label"], min_value=0, default=0),
                "notes": st.column_config.TextColumn("Izoh"),
            },
            key="tx_editor",
        )
        if st.button("💾 Operatsiyalar jadvalini bazaga saqlash", type="primary"):
            replace_transactions(cid, edited_tx)
            st.success("Barcha o'zgarishlar saqlandi!")
            st.rerun()

    # 1B: Qarzlar kiritish
    with in_tabs[1]:
        st.subheader("Debitor (bizga qarz) va Kreditor (bizning qarz) kiritish")
        with st.form("add_debt_form", clear_on_submit=True):
            d1, d2, d3, d4 = st.columns(4)
            d_part = d1.text_input("Kontragent (Mijoz / Yetkazuvchi) *")
            d_type = d2.selectbox("Qarz turi", ["Debitor (Bizga qarz)", "Kreditor (Bizning qarz)"])
            d_due = d3.date_input("To'lov muddati", value=date.today())
            d_amt = d4.number_input(f"Qoldiq summa ({curr})", min_value=0.0, step=100_000.0)
            d_note = st.text_input("Izoh", key="debt_note")
            if st.form_submit_button("➕ Qarzni qo'shish", type="primary"):
                if not d_part.strip():
                    st.error("Kontragent nomini kiriting.")
                else:
                    insert_debt(cid, {"partner": d_part, "debt_type": d_type, "due_date": d_due, "amount": d_amt, "notes": d_note})
                    st.success("Qarz yozuvi saqlandi!")
                    st.rerun()

        edit_d = debts_df[["partner", "debt_type", "due_date", "amount", "notes"]].copy() if not debts_df.empty else pd.DataFrame(
            columns=["partner", "debt_type", "due_date", "amount", "notes"]
        )
        edit_d["due_date"] = pd.to_datetime(edit_d["due_date"], errors="coerce").dt.date
        edited_d = st.data_editor(
            edit_d,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "partner": st.column_config.TextColumn("Kontragent"),
                "debt_type": st.column_config.SelectboxColumn("Tur", options=["Debitor (Bizga qarz)", "Kreditor (Bizning qarz)"]),
                "due_date": st.column_config.DateColumn("To'lov muddati", default=date.today()),
                "amount": st.column_config.NumberColumn(f"Summa ({curr})", min_value=0),
                "notes": st.column_config.TextColumn("Izoh"),
            },
            key="debt_editor",
        )
        if st.button("💾 Qarzlar jadvalini saqlash"):
            replace_debts(cid, edited_d)
            st.success("Qarzlar yangilandi!")
            st.rerun()

    # 1C: Ombor kiritish (agar sohaga tegishli bo'lsa)
    next_sub = 2
    if cfg["uses_inventory"]:
        with in_tabs[next_sub]:
            st.subheader("Ombor zaxiralari va o'lik tovarlarni kiritish")
            with st.form("add_inv_form", clear_on_submit=True):
                i1, i2, i3 = st.columns(3)
                i_item = i1.text_input("Mahsulot / Material nomi *")
                i_wh = i2.text_input("Ombor", value="Asosiy ombor")
                i_qty = i3.number_input("Qoldiq soni", min_value=0.0, value=1.0)
                i4, i5, i6 = st.columns(3)
                i_cost = i4.number_input(f"Birlik tannarxi ({curr})", min_value=0.0, step=10_000.0)
                i_last = i5.date_input("Oxirgi sotuv / harakat sanasi", value=date.today())
                i_mon = i6.number_input("Oylik o'rtacha sotuv/sarf soni", min_value=0.0, value=1.0)
                if st.form_submit_button("➕ Omborga qo'shish", type="primary"):
                    if not i_item.strip():
                        st.error("Mahsulot nomini kiriting.")
                    else:
                        insert_inventory(cid, {"item_name": i_item, "warehouse": i_wh, "qty": i_qty, "unit_cost": i_cost, "last_sale_date": i_last, "monthly_sales": i_mon})
                        st.success("Ombor yozuvi saqlandi!")
                        st.rerun()

            edit_i = inv_df[["item_name", "warehouse", "qty", "unit_cost", "last_sale_date", "monthly_sales"]].copy() if not inv_df.empty else pd.DataFrame(
                columns=["item_name", "warehouse", "qty", "unit_cost", "last_sale_date", "monthly_sales"]
            )
            edit_i["last_sale_date"] = pd.to_datetime(edit_i["last_sale_date"], errors="coerce").dt.date
            edited_i = st.data_editor(
                edit_i,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "item_name": st.column_config.TextColumn("Mahsulot"),
                    "warehouse": st.column_config.TextColumn("Ombor", default="Asosiy ombor"),
                    "qty": st.column_config.NumberColumn("Qoldiq soni", min_value=0),
                    "unit_cost": st.column_config.NumberColumn("Birlik tannarxi", min_value=0),
                    "last_sale_date": st.column_config.DateColumn("Oxirgi harakat", default=date.today()),
                    "monthly_sales": st.column_config.NumberColumn("Oylik o'rtacha sarf", min_value=0),
                },
                key="inv_editor",
            )
            if st.button("💾 Ombor jadvalini saqlash"):
                replace_inventory(cid, edited_i)
                st.success("Ombor yangilandi!")
                st.rerun()
        next_sub += 1

    # 1D: Excel / CSV orqali ommaviy yuklash
    with in_tabs[next_sub]:
        st.subheader("Tayyor Excel yoki CSV fayldan bazaga ommaviy import qilish")
        st.caption("Chap paneldan ushbu soha uchun bo'sh Excel shablonni yuklab olib to'ldirishingiz yoki o'zingizdagi faylni yuklab ustunlarni bog'lashingiz mumkin.")
        up_file = st.file_uploader("Operatsiyalar faylini tanlang (.xlsx / .csv)", type=["xlsx", "xls", "csv"])
        if up_file is not None:
            up_df = pd.read_csv(up_file) if up_file.name.lower().endswith(".csv") else pd.read_excel(up_file)
            st.write(f"Yuklangan fayl: **{len(up_df)} qator**", up_df.head(5))
            ucols = list(up_df.columns)
            opt_u = ["Yo'q"] + ucols
            m1, m2, m3, m4 = st.columns(4)
            mc_date = m1.selectbox("Sana ustuni *", ucols)
            mc_item = m2.selectbox(f"{cfg['item_label']} *", ucols)
            mc_rev = m3.selectbox("Tushum *", ucols)
            mc_group = m4.selectbox(cfg["group_label"], opt_u)

            m5, m6, m7, m8, m9 = st.columns(5)
            mc_cogs = m5.selectbox(cfg["cogs_label"], opt_u)
            mc_opex = m6.selectbox("OPEX", opt_u)
            mc_qty = m7.selectbox(cfg["qty_label"], opt_u)
            mc_exp = m8.selectbox("Xarajat turi", opt_u)
            mc_ext = m9.selectbox(cfg["extra_label"], opt_u)

            if st.button("📥 Bazaga qo'shish (Import)", type="primary"):
                added = 0
                for _, r in up_df.iterrows():
                    dt = pd.to_datetime(r[mc_date], errors="coerce")
                    if pd.isna(dt):
                        continue
                    insert_transaction(
                        cid,
                        {
                            "tx_date": dt.strftime("%Y-%m-%d"),
                            "group_name": str(r[mc_group]) if mc_group != "Yo'q" else "Asosiy",
                            "item_name": str(r[mc_item]),
                            "expense_type": str(r[mc_exp]) if mc_exp != "Yo'q" else cfg["expenses"][0],
                            "quantity": float(pd.to_numeric(r[mc_qty], errors="coerce") or 1) if mc_qty != "Yo'q" else 1.0,
                            "revenue": float(pd.to_numeric(r[mc_rev], errors="coerce") or 0),
                            "cogs": float(pd.to_numeric(r[mc_cogs], errors="coerce") or 0) if mc_cogs != "Yo'q" else 0.0,
                            "opex": float(pd.to_numeric(r[mc_opex], errors="coerce") or 0) if mc_opex != "Yo'q" else 0.0,
                            "extra_metric": float(pd.to_numeric(r[mc_ext], errors="coerce") or 0) if mc_ext != "Yo'q" else 0.0,
                            "notes": "Excel import",
                        },
                    )
                    added += 1
                st.success(f"{added} ta operatsiya bazaga muvaffaqiyatli qo'shildi!")
                st.rerun()

tab_idx += 1

# =========================================================
# TAB 2: SOHA TAHLILI VA P&L
# =========================================================
with tabs[tab_idx]:
    if not analysis["has_tx"]:
        st.info("Tahlil va grafiklar shakllanishi uchun avval **'✍️ Ma'lumot Kiritish'** bo'limidan kamida 1 ta operatsiya kiriting.")
    else:
        kpi = analysis["kpi"]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Jami Tushum", fmt_money(kpi["rev"], curr))
        k2.metric(cfg["cogs_label"], fmt_money(kpi["cogs"], curr))
        k3.metric("Operatsion Xarajat (OPEX)", fmt_money(kpi["opex"], curr))
        k4.metric("Sof Foyda", fmt_money(kpi["net"], curr), delta=f"{kpi['margin']:.1f}% marja")

        st.subheader(f"🏭 '{industry}' uchun maxsus ko'rsatkichlar")
        scols = st.columns(len(analysis["industry_kpis"]))
        for col, (lbl, val, norm_txt, is_ok) in zip(scols, analysis["industry_kpis"]):
            col.metric(lbl, val, delta=norm_txt, delta_color="normal" if is_ok else "inverse")

        st.divider()
        c_l, c_r = st.columns([3, 2])
        with c_l:
            st.subheader("Oylik Moliyaviy Dinamika")
            mdf = analysis["monthly_df"]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=mdf["Oy"], y=mdf["Tushum"], name="Tushum", marker_color="#2563EB"))
            fig.add_trace(go.Bar(x=mdf["Oy"], y=mdf["Tannarx"] + mdf["OPEX"], name="Jami Xarajat", marker_color="#F59E0B"))
            fig.add_trace(go.Scatter(x=mdf["Oy"], y=mdf["Sof_foyda"], name="Sof Foyda", mode="lines+markers", line=dict(color="#10B981", width=3)))
            fig.update_layout(barmode="group", height=360, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

        with c_r:
            st.subheader(f"{cfg['item_label']} Rentabelligi")
            idf = analysis["item_df"].copy()
            idf["Holat"] = np.where(idf["Sof_foyda"] < 0, "Zararli", "Foydali")
            fig_i = px.bar(idf, x="Sof_foyda", y="item_name", orientation="h", color="Holat", color_discrete_map={"Zararli": "#EF4444", "Foydali": "#10B981"}, text_auto=".2s")
            fig_i.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="")
            st.plotly_chart(fig_i, use_container_width=True)

        g1, g2 = st.columns(2)
        with g1:
            st.subheader(f"{cfg['group_label']} Samaradorligi")
            st.dataframe(analysis["group_df"].style.format({"Tushum": "{:,.0f}", "Tannarx": "{:,.0f}", "OPEX": "{:,.0f}", "Sof_foyda": "{:,.0f}", "Marja_%": "{:.1f}%"}), use_container_width=True)
        with g2:
            st.subheader("Xarajatlar Tarkibi")
            fig_e = px.pie(analysis["exp_df"], values="OPEX", names="expense_type", hole=0.45)
            fig_e.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_e, use_container_width=True)

        st.subheader(f"ABC (Pareto) va Birlik Tannarx Tahlili")
        st.dataframe(analysis["abc_df"][["item_name", "Miqdor", "Tushum", "Birlik_tannarx", "Sof_foyda", "Marja_%", "ABC"]].style.format({"Tushum": "{:,.0f}", "Birlik_tannarx": "{:,.0f}", "Sof_foyda": "{:,.0f}", "Marja_%": "{:.1f}%"}), use_container_width=True)

tab_idx += 1

# =========================================================
# TAB 3: CASH FLOW VA QARZLAR
# =========================================================
with tabs[tab_idx]:
    if not analysis["has_tx"]:
        st.info("Cash Flow prognozi uchun avval operatsiyalar kiriting.")
    else:
        cf = analysis["cf"]
        st.subheader(f"Keyingi {forecast_days} Kunlik Kassa Prognozi")
        if not cf["gap"].empty:
            st.error(f"🚨 Kassa uzilishi xavfi: **{len(cf['gap'])} kun** (eng past nuqta: **{fmt_money(cf['min_bal'], curr)}**).")
        else:
            st.success(f"✅ Kassa barqaror. Davr oxiridagi prognoz qoldiq: **{fmt_money(cf['end_bal'], curr)}**.")

        fig_cf = go.Figure()
        fig_cf.add_trace(go.Scatter(x=cf["fc"]["Sana"], y=cf["fc"]["Balans"], mode="lines+markers", name="Kassa Balansi", line=dict(color="#2563EB", width=3), fill="tozeroy"))
        fig_cf.add_hline(y=0, line_dash="dash", line_color="#EF4444")
        fig_cf.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_cf, use_container_width=True)

        st.divider()
        st.subheader("🧾 Debitor va Kreditor Qarzlar (Aging)")
        if analysis["debts"] is None:
            st.info("Qarzlar kiritilmagan. '✍️ Ma'lumot Kiritish' → '🧾 Qarzlar kiritish' bo'limidan qo'shing.")
        else:
            dr = analysis["debts"]
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Jami Debitor", fmt_money(dr["ar_total"], curr))
            d2.metric("Muddati o'tgan Debitor", fmt_money(dr["ar_over"], curr), delta=f"90+ kun: {fmt_money(dr['ar_crit'], curr)}", delta_color="inverse" if dr["ar_crit"] > 0 else "off")
            d3.metric("Jami Kreditor", fmt_money(dr["ap_total"], curr))
            d4.metric("Muddati o'tgan Kreditor", fmt_money(dr["ap_over"], curr))

            age_df = dr["df"].groupby(["Guruh", "debt_type"], as_index=False)["amount"].sum()
            fig_a = px.bar(age_df, x="Guruh", y="amount", color="debt_type", barmode="group", text_auto=".2s")
            fig_a.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_a, use_container_width=True)
            st.dataframe(dr["df"][["partner", "debt_type", "due_date", "Kechikish_kuni", "Guruh", "amount"]].style.format({"amount": "{:,.0f}"}), use_container_width=True)

tab_idx += 1

# =========================================================
# TAB 4 (IXTIYORIY): OMBOR & DEAD STOCK
# =========================================================
if cfg["uses_inventory"]:
    with tabs[tab_idx]:
        if not analysis["has_tx"] or analysis["inventory"] is None:
            st.info("Ombor tahlili uchun '✍️ Ma'lumot Kiritish' → '📦 Ombor kiritish' bo'limidan zaxiralarni kiriting.")
        else:
            inv = analysis["inventory"]
            i1, i2, i3 = st.columns(3)
            i1.metric("Jami Ombor Qiymati", fmt_money(inv["total_val"], curr))
            i2.metric("O'lik Tovarlar (90+ kun)", fmt_money(inv["dead_val"], curr), delta=f"{inv['dead_cnt']} ta pozitsiya", delta_color="inverse")
            i3.metric("Muzlatilgan Kapital Ulushi", f"{(inv['dead_val']/inv['total_val']*100) if inv['total_val'] > 0 else 0:.1f}%")

            fig_inv = px.bar(inv["df"], x="Muzlatilgan_kapital", y="item_name", color="Holat", orientation="h",
                             color_discrete_map={"O'lik tovar (Dead Stock)": "#EF4444", "Sekin aylanuvchi": "#F59E0B", "Sog'lom zaxira": "#10B981"})
            fig_inv.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_inv, use_container_width=True)
            st.dataframe(inv["df"][["item_name", "warehouse", "qty", "Muzlatilgan_kapital", "Sotilmagan_kun", "DIO_kun", "Holat"]].style.format({"Muzlatilgan_kapital": "{:,.0f}", "DIO_kun": "{:.0f} kun"}), use_container_width=True)
    tab_idx += 1

# =========================================================
# TAB 5: DIAGNOSTIKA, SIMULYATOR VA EXCEL HISOBOT EKSPORTI
# =========================================================
with tabs[tab_idx]:
    if not analysis["has_tx"]:
        st.info("Diagnostika va yechimlar uchun avval ma'lumotlaringizni kiriting.")
    else:
        st.subheader("🚨 Korxonani Pastga Tortayotgan Omillar va Aniq Yechimlar")
        for level, sec, prob, sol in analysis["recs"]:
            txt = f"**[{level} | {sec}]** {prob}\n\n✅ **Yechim:** {sol}"
            if level == "Yuqori xavf":
                st.error(txt)
            elif level == "Ogohlantirish":
                st.warning(txt)
            else:
                st.info(txt)

        st.divider()
        st.subheader("🎛️ 'Agar...' (What-If) Qaror Simulyatori")
        s1, s2, s3 = st.columns(3)
        p_chg = s1.slider("Narxni o'zgartirish (%)", -20, 30, 5)
        c_cut = s2.slider(f"{cfg['cogs_label']} ni kamaytirish (%)", 0, 30, 5)
        o_cut = s3.slider("OPEX ni qisqartirish (%)", 0, 40, 10)
        drop_bad = st.checkbox("Zararli pozitsiyalarni chiqarib tashlash", value=True)

        sdf = analysis["df"].copy()
        if drop_bad and not analysis["loss_items"].empty:
            sdf = sdf[~sdf["item_name"].isin(analysis["loss_items"]["item_name"].tolist())]
        s_rev = sdf["revenue"].sum() * (1 + p_chg / 100)
        s_cogs = sdf["cogs"].sum() * (1 - c_cut / 100)
        s_opex = sdf["opex"].sum() * (1 - o_cut / 100)
        s_net = s_rev - s_cogs - s_opex

        r1, r2, r3 = st.columns(3)
        r1.metric("Hozirgi Sof Foyda", fmt_money(analysis["kpi"]["net"], curr))
        r2.metric("Prognoz Sof Foyda", fmt_money(s_net, curr), delta=fmt_money(s_net - analysis["kpi"]["net"], curr))
        s_m = (s_net / s_rev * 100) if s_rev > 0 else 0.0
        r3.metric("Yangi Marja", f"{s_m:.1f}%", delta=f"{s_m - analysis['kpi']['margin']:.1f}%")

        st.divider()
        st.subheader("📤 Tayyor Tahliliy Hisobotni Yuklab Olish")
        st.download_button(
            label="📥 To'liq Tahlil Natijalarini Excel (.xlsx) qilib yuklab olish",
            data=export_analysis_excel(tx_df, analysis["item_df"], analysis["group_df"], debts_df, inv_df),
            file_name=f"{company['name'].replace(' ', '_')}_hisobot.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
        from pro_modules import render_pro_analytics
        render_pro_analytics(tx_df, analysis, company["name"], curr)
        from enterprise_360 import render_enterprise_360
        render_enterprise_360(tx_df, debts_df, inv_df, company["name"], curr)
