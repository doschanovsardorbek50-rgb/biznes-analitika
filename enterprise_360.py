import os
import sqlite3
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB_PATH = "enterprise_360.db"


# =========================================================
# 1. SQLITE BAZA (KORXONA BO'YICHA 360° KO'RSATKICHLAR)
# =========================================================
def _init_360_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS enterprise_360_profile (
            company_name TEXT PRIMARY KEY,
            period_days INTEGER DEFAULT 30,
            total_customers INTEGER DEFAULT 120,
            new_customers INTEGER DEFAULT 25,
            repeat_customers INTEGER DEFAULT 55,
            marketing_spend REAL DEFAULT 8000000,
            avg_lifetime_months REAL DEFAULT 8.0,
            top3_clients_share_pct REAL DEFAULT 35.0,
            employees_count INTEGER DEFAULT 12,
            payroll_total REAL DEFAULT 48000000,
            employees_left INTEGER DEFAULT 1,
            kpi_achievement_pct REAL DEFAULT 78.0,
            defect_return_pct REAL DEFAULT 3.5,
            avg_lead_time_days REAL DEFAULT 3.0,
            capacity_util_pct REAL DEFAULT 72.0,
            top_supplier_share_pct REAL DEFAULT 45.0,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


DEFAULT_PROFILE = {
    "period_days": 30,
    "total_customers": 120,
    "new_customers": 25,
    "repeat_customers": 55,
    "marketing_spend": 8_000_000.0,
    "avg_lifetime_months": 8.0,
    "top3_clients_share_pct": 35.0,
    "employees_count": 12,
    "payroll_total": 48_000_000.0,
    "employees_left": 1,
    "kpi_achievement_pct": 78.0,
    "defect_return_pct": 3.5,
    "avg_lead_time_days": 3.0,
    "capacity_util_pct": 72.0,
    "top_supplier_share_pct": 45.0,
}


def load_360_profile(company_name: str) -> dict:
    _init_360_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM enterprise_360_profile WHERE company_name = ?",
        (str(company_name),),
    ).fetchone()
    conn.close()
    if row is None:
        return dict(DEFAULT_PROFILE)
    data = dict(DEFAULT_PROFILE)
    for k in DEFAULT_PROFILE:
        if k in row.keys() and row[k] is not None:
            data[k] = row[k]
    return data


def save_360_profile(company_name: str, data: dict):
    _init_360_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO enterprise_360_profile (
            company_name, period_days, total_customers, new_customers, repeat_customers,
            marketing_spend, avg_lifetime_months, top3_clients_share_pct,
            employees_count, payroll_total, employees_left, kpi_achievement_pct,
            defect_return_pct, avg_lead_time_days, capacity_util_pct, top_supplier_share_pct,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_name) DO UPDATE SET
            period_days=excluded.period_days,
            total_customers=excluded.total_customers,
            new_customers=excluded.new_customers,
            repeat_customers=excluded.repeat_customers,
            marketing_spend=excluded.marketing_spend,
            avg_lifetime_months=excluded.avg_lifetime_months,
            top3_clients_share_pct=excluded.top3_clients_share_pct,
            employees_count=excluded.employees_count,
            payroll_total=excluded.payroll_total,
            employees_left=excluded.employees_left,
            kpi_achievement_pct=excluded.kpi_achievement_pct,
            defect_return_pct=excluded.defect_return_pct,
            avg_lead_time_days=excluded.avg_lead_time_days,
            capacity_util_pct=excluded.capacity_util_pct,
            top_supplier_share_pct=excluded.top_supplier_share_pct,
            updated_at=excluded.updated_at
        """,
        (
            str(company_name),
            int(data["period_days"]),
            int(data["total_customers"]),
            int(data["new_customers"]),
            int(data["repeat_customers"]),
            float(data["marketing_spend"]),
            float(data["avg_lifetime_months"]),
            float(data["top3_clients_share_pct"]),
            int(data["employees_count"]),
            float(data["payroll_total"]),
            int(data["employees_left"]),
            float(data["kpi_achievement_pct"]),
            float(data["defect_return_pct"]),
            float(data["avg_lead_time_days"]),
            float(data["capacity_util_pct"]),
            float(data["top_supplier_share_pct"]),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()


# =========================================================
# 2. YORDAMCHI FUNKSIYALAR
# =========================================================
def _detect_col(df: pd.DataFrame, candidates: list):
    if df is None or df.empty:
        return None
    cols_lower = {str(c).lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    for cand in candidates:
        cl = cand.lower()
        for k, orig in cols_lower.items():
            if cl in k:
                return orig
    return None


def _fmt_money(val: float, curr: str = "UZS") -> str:
    try:
        return f"{float(val):,.0f} {curr}".replace(",", " ")
    except Exception:
        return f"0 {curr}"


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, val)))


# =========================================================
# 3. MOLIYAVIY + PUL AYLANISH SIKLI (CCC) HISOB-KITOBI
# =========================================================
def extract_financial_core(tx_df: pd.DataFrame, debts_df: pd.DataFrame, inv_df: pd.DataFrame, period_days: int = 30) -> dict:
    days = max(int(period_days), 1)
    rev = cogs = opex = 0.0

    if tx_df is not None and not tx_df.empty:
        rev_col = _detect_col(tx_df, ["revenue", "tushum", "savdo"])
        cogs_col = _detect_col(tx_df, ["cogs", "tannarx"])
        opex_col = _detect_col(tx_df, ["opex", "operatsion xarajat", "xarajat"])

        if rev_col:
            rev = float(pd.to_numeric(tx_df[rev_col], errors="coerce").fillna(0).sum())
        if cogs_col:
            cogs = float(pd.to_numeric(tx_df[cogs_col], errors="coerce").fillna(0).sum())
        if opex_col:
            opex = float(pd.to_numeric(tx_df[opex_col], errors="coerce").fillna(0).sum())

    gross_profit = rev - cogs
    net_profit = rev - cogs - opex
    gross_margin = (gross_profit / rev * 100.0) if rev > 0 else 0.0
    net_margin = (net_profit / rev * 100.0) if rev > 0 else 0.0

    # Debitor & Kreditor qarzlar
    receivables = payables = overdue_receivables = 0.0
    if debts_df is not None and not debts_df.empty:
        type_col = _detect_col(debts_df, ["debt_type", "type", "turi"])
        amt_col = _detect_col(debts_df, ["amount", "summa", "qoldiq"])
        status_col = _detect_col(debts_df, ["status", "holati"])
        if amt_col:
            d_tmp = debts_df.copy()
            d_tmp["_amt"] = pd.to_numeric(d_tmp[amt_col], errors="coerce").fillna(0.0)
            if type_col:
                t_str = d_tmp[type_col].astype(str).str.lower()
                is_deb = t_str.str.contains("deb|olish|mijoz|receiv")
                is_cred = t_str.str.contains("kred|cred|berish|yetkaz|payab")
                receivables = float(d_tmp.loc[is_deb, "_amt"].sum())
                payables = float(d_tmp.loc[is_cred, "_amt"].sum())
                if status_col:
                    s_str = d_tmp[status_col].astype(str).str.lower()
                    is_over = s_str.str.contains("kechik|over|muddat")
                    overdue_receivables = float(d_tmp.loc[is_deb & is_over, "_amt"].sum())
            else:
                receivables = float(d_tmp["_amt"].sum())

    # Ombor qiymati
    inventory_value = 0.0
    if inv_df is not None and not inv_df.empty:
        qty_col = _detect_col(inv_df, ["qty", "quantity", "qoldiq miqdor", "qoldiq", "miqdor"])
        cost_col = _detect_col(inv_df, ["unit_cost", "birlik tannarxi", "tannarx", "cost", "narx"])
        val_col = _detect_col(inv_df, ["total_value", "jami qiymat", "qiymat"])
        if val_col:
            inventory_value = float(pd.to_numeric(inv_df[val_col], errors="coerce").fillna(0.0).sum())
        elif qty_col and cost_col:
            q = pd.to_numeric(inv_df[qty_col], errors="coerce").fillna(0.0)
            c = pd.to_numeric(inv_df[cost_col], errors="coerce").fillna(0.0)
            inventory_value = float((q * c).sum())

    # Pul aylanish sikli: CCC = DIO + DSO - DPO
    daily_rev = rev / days if rev > 0 else 0.0
    daily_cogs = cogs / days if cogs > 0 else (daily_rev * 0.7 if daily_rev > 0 else 0.0)

    dio = (inventory_value / daily_cogs) if daily_cogs > 0 else 0.0
    dso = (receivables / daily_rev) if daily_rev > 0 else 0.0
    dpo = (payables / daily_cogs) if daily_cogs > 0 else 0.0
    ccc = dio + dso - dpo

    return {
        "period_days": days,
        "revenue": rev,
        "cogs": cogs,
        "opex": opex,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "gross_margin_pct": gross_margin,
        "net_margin_pct": net_margin,
        "receivables": receivables,
        "payables": payables,
        "overdue_receivables": overdue_receivables,
        "inventory_value": inventory_value,
        "daily_rev": daily_rev,
        "daily_cogs": daily_cogs,
        "dio": dio,
        "dso": dso,
        "dpo": dpo,
        "ccc": ccc,
    }


# =========================================================
# 4. 360° SOG'LOMLIK INDEKSI (5 USTUN) VA UNIT ECONOMICS
# =========================================================
def evaluate_enterprise_360(fin: dict, prof: dict) -> dict:
    rev = fin["revenue"]
    net_margin = fin["net_margin_pct"]
    gross_margin = fin["gross_margin_pct"]
    ccc = fin["ccc"]

    # --- Unit Economics & Mijozlar ---
    total_cust = max(int(prof["total_customers"]), 1)
    new_cust = max(int(prof["new_customers"]), 0)
    rep_cust = min(max(int(prof["repeat_customers"]), 0), total_cust)
    mkt_spend = max(float(prof["marketing_spend"]), 0.0)
    lifetime_m = max(float(prof["avg_lifetime_months"]), 1.0)

    repeat_rate = (rep_cust / total_cust) * 100.0
    arpu_period = rev / total_cust if rev > 0 else 0.0
    arpu_monthly = arpu_period * (30.0 / fin["period_days"])
    cac = (mkt_spend / new_cust) if new_cust > 0 else 0.0
    gm_ratio = max(gross_margin / 100.0, 0.05) if rev > 0 else 0.25
    ltv = arpu_monthly * lifetime_m * gm_ratio
    ltv_cac = (ltv / cac) if cac > 0 else (4.0 if rev > 0 else 0.0)

    # --- HR & Jamoa ---
    emp = max(int(prof["employees_count"]), 1)
    payroll = max(float(prof["payroll_total"]), 0.0)
    emp_left = max(int(prof["employees_left"]), 0)
    kpi_pct = _clamp(float(prof["kpi_achievement_pct"]))

    rev_per_emp = rev / emp if rev > 0 else 0.0
    profit_per_emp = fin["net_profit"] / emp if rev > 0 else 0.0
    fot_share_pct = (payroll / rev * 100.0) if rev > 0 else 0.0
    turnover_pct = (emp_left / emp) * 100.0

    # --- Operatsiyalar & Risk ---
    defect_pct = max(float(prof["defect_return_pct"]), 0.0)
    lead_days = max(float(prof["avg_lead_time_days"]), 0.0)
    cap_util = _clamp(float(prof["capacity_util_pct"]))
    top3_share = _clamp(float(prof["top3_clients_share_pct"]))
    top_sup_share = _clamp(float(prof["top_supplier_share_pct"]))

    # === 5 USTUN BALLARI (0 - 100) ===
    # 1. Moliya & Pul Aylanishi
    margin_score = _clamp(50.0 + net_margin * 2.5) if rev > 0 else 25.0
    ccc_penalty = max(0.0, (ccc - 20.0) * 0.9) if ccc > 20 else 0.0
    overdue_ratio = (fin["overdue_receivables"] / fin["receivables"] * 100.0) if fin["receivables"] > 0 else 0.0
    overdue_penalty = overdue_ratio * 0.35
    score_finance = _clamp(margin_score - ccc_penalty * 0.6 - overdue_penalty * 0.4)

    # 2. Mijozlar & Sotuv (Unit Economics)
    ltv_score = _clamp((ltv_cac / 3.5) * 100.0) if cac > 0 else 75.0
    rep_score = _clamp((repeat_rate / 55.0) * 100.0)
    score_customers = _clamp(ltv_score * 0.55 + rep_score * 0.45)

    # 3. Operatsiyalar & Sifat
    defect_score = _clamp(100.0 - defect_pct * 8.0)
    # Optimal quvvat yuklanishi 75% - 90% oralig'i; juda past (<50%) bo'sh turish, juda baland (>95%) zo'riqish
    if cap_util < 75:
        cap_score = _clamp((cap_util / 75.0) * 100.0)
    elif cap_util <= 92:
        cap_score = 100.0
    else:
        cap_score = _clamp(100.0 - (cap_util - 92.0) * 4.0)
    lead_score = _clamp(100.0 - max(0.0, lead_days - 2.0) * 6.0)
    score_ops = _clamp(defect_score * 0.45 + cap_score * 0.35 + lead_score * 0.20)

    # 4. Jamoa & HR Unumdorligi
    fot_score = _clamp(100.0 - max(0.0, fot_share_pct - 22.0) * 2.2) if rev > 0 else 50.0
    turn_score = _clamp(100.0 - turnover_pct * 4.5)
    score_hr = _clamp(fot_score * 0.40 + kpi_pct * 0.35 + turn_score * 0.25)

    # 5. Barqarorlik & Risklar
    client_risk_score = _clamp(100.0 - max(0.0, top3_share - 25.0) * 1.4)
    sup_risk_score = _clamp(100.0 - max(0.0, top_sup_share - 35.0) * 1.3)
    profit_buf_score = _clamp(50.0 + net_margin * 2.0) if rev > 0 else 30.0
    score_risk = _clamp(client_risk_score * 0.40 + sup_risk_score * 0.35 + profit_buf_score * 0.25)

    scores = {
        "Moliya va Pul Aylanishi": round(score_finance, 1),
        "Mijozlar (Unit Economics)": round(score_customers, 1),
        "Operatsiyalar va Sifat": round(score_ops, 1),
        "Jamoa va HR": round(score_hr, 1),
        "Barqarorlik va Risklar": round(score_risk, 1),
    }

    overall = round(
        score_finance * 0.28
        + score_customers * 0.22
        + score_ops * 0.18
        + score_hr * 0.17
        + score_risk * 0.15,
        1,
    )

    if overall >= 80:
        grade = ("Barqaror va Kuchli", "success")
    elif overall >= 62:
        grade = ("Rivojlanish Zonasida (Optimallashtirish kerak)", "info")
    elif overall >= 45:
        grade = ("Xavf Zonasida (Tizimli muammolar bor)", "warning")
    else:
        grade = ("Kritik Holat (Shoshilinch chora zarur)", "error")

    metrics = {
        "repeat_rate_pct": repeat_rate,
        "arpu_monthly": arpu_monthly,
        "cac": cac,
        "ltv": ltv,
        "ltv_cac": ltv_cac,
        "rev_per_emp": rev_per_emp,
        "profit_per_emp": profit_per_emp,
        "fot_share_pct": fot_share_pct,
        "turnover_pct": turnover_pct,
        "overdue_ratio_pct": overdue_ratio,
        "defect_loss_est": rev * (defect_pct / 100.0),
    }

    return {
        "scores": scores,
        "overall": overall,
        "grade": grade,
        "metrics": metrics,
    }


# =========================================================
# 5. SABAB-OQIBAT DIAGNOSTIKA DVIGATELI + TA'SIR KALKULYATORI
# =========================================================
def run_root_cause_engine(fin: dict, prof: dict, eval_res: dict, curr: str = "UZS") -> list:
    """Aniqlangan muammolar, ularning ildiz sababi, yechimi va so'mdagi kutilayotgan samarasini qaytaradi."""
    findings = []
    m = eval_res["metrics"]
    rev = fin["revenue"]

    # 1. Foyda / Marja zanjiri
    if rev > 0 and fin["net_margin_pct"] < 10.0:
        if fin["gross_margin_pct"] < 20.0:
            root = f"Yalpi marja juda past ({fin['gross_margin_pct']:.1f}%) — xarid tannarxi baland yoki sotuv narxi bozordan past qo'yilgan."
            action = "Eng past marjali 20% tovarlarda narxni 5-8% oshirish yoki yetkazib beruvchidan hajm chegirmasi olish."
            impact = rev * 0.04
            horizon = "30 kun"
        else:
            root = f"Yalpi marja yetarli ({fin['gross_margin_pct']:.1f}%), lekin operatsion xarajatlar (OPEX) foydani yeb qo'ymoqda."
            action = "Doimiy xarajatlarni (ijara, ma'muriy xarajatlar, samarasiz obunalar) 12-15% qisqartirish."
            impact = fin["opex"] * 0.12
            horizon = "30 kun"
        findings.append({
            "severity": "Yuqori" if fin["net_profit"] < 0 else "O'rta",
            "area": "Moliya (P&L)",
            "symptom": f"Sof marja past ({fin['net_margin_pct']:.1f}%)",
            "root_cause": root,
            "solution": action,
            "impact_money": impact,
            "impact_text": f"+{_fmt_money(impact, curr)} / davr qo'shimcha sof foyda",
            "horizon": horizon,
        })

    # 2. Pul aylanish sikli (CCC) zanjiri
    if rev > 0 and fin["ccc"] > 30.0:
        bottleneck_parts = []
        free_cash = 0.0
        if fin["dso"] > 25.0:
            cut_dso = fin["dso"] - 20.0
            free_cash += cut_dso * fin["daily_rev"]
            bottleneck_parts.append(f"debitor qarzlar {fin['dso']:.0f} kunda yig'ilmoqda")
        if fin["dio"] > 35.0:
            cut_dio = fin["dio"] - 25.0
            free_cash += cut_dio * fin["daily_cogs"]
            bottleneck_parts.append(f"tovarlar omborda {fin['dio']:.0f} kun yotibdi")
        if not bottleneck_parts:
            free_cash = (fin["ccc"] - 25.0) * fin["daily_cogs"]
            bottleneck_parts.append(f"yetkazib beruvchilarga to'lov muddati (DPO={fin['dpo']:.0f} kun) juda qisqa")

        findings.append({
            "severity": "Yuqori" if fin["ccc"] > 50 else "O'rta",
            "area": "Pul Aylanishi (CCC)",
            "symptom": f"Naqd pul sikli cho'zilgan (CCC = {fin['ccc']:.0f} kun)",
            "root_cause": "Pul aylanmada muzlab qolmoqda: " + "; ".join(bottleneck_parts) + ".",
            "solution": "Shartnomalarga 30-50% oldindan to'lov kiritish, sekin aylanuvchi tovarlarga chegirma berish va yetkazib beruvchi bilan to'lovni +10 kunga uzaytirish.",
            "impact_money": max(free_cash, 0.0),
            "impact_text": f"+{_fmt_money(max(free_cash, 0.0), curr)} aylanma naqd pul bo'shaydi",
            "horizon": "30 kun",
        })

    # 3. Mijozlar va Unit Economics zanjiri
    if m["cac"] > 0 and m["ltv_cac"] < 3.0:
        target_spend_save = prof["marketing_spend"] * 0.25
        findings.append({
            "severity": "Yuqori" if m["ltv_cac"] < 1.5 else "O'rta",
            "area": "Mijozlar & Sotuv",
            "symptom": f"LTV / CAC nisbati past ({m['ltv_cac']:.2f}x; me'yor >= 3.0x)",
            "root_cause": f"1 ta mijoz jalb qilish ({_fmt_money(m['cac'], curr)}) uning keltiradigan yalpi foydasiga ({_fmt_money(m['ltv'], curr)}) nisbatan qimmat.",
            "solution": "Samarasiz reklama kanallarini o'chirish, CRM orqali qayta sotuv skriptlari va sodiqlik dasturini ishga tushirish.",
            "impact_money": target_spend_save,
            "impact_text": f"+{_fmt_money(target_spend_save, curr)} marketing tejami + LTV o'sishi",
            "horizon": "60 kun",
        })
    elif m["repeat_rate_pct"] < 35.0 and rev > 0:
        lift = rev * 0.10
        findings.append({
            "severity": "O'rta",
            "area": "Mijozlar & Sotuv",
            "symptom": f"Qayta xarid ulushi past ({m['repeat_rate_pct']:.1f}%)",
            "root_cause": "Mijozlar 1 marta xarid qilib qaytib kelmayapti — xizmatdan keyingi aloqa (follow-up) yo'q.",
            "solution": "Xariddan 7 va 21 kun o'tib Telegram/SMS eslatma hamda ikkinchi xaridga 5% keshbek berish.",
            "impact_money": lift,
            "impact_text": f"+{_fmt_money(lift, curr)} / davr barqaror takroriy savdo",
            "horizon": "60 kun",
        })

    # 4. HR va Jamoa unumdorligi zanjiri
    if rev > 0 and m["fot_share_pct"] > 28.0:
        excess = prof["payroll_total"] - (rev * 0.24)
        findings.append({
            "severity": "Yuqori" if m["fot_share_pct"] > 38.0 else "O'rta",
            "area": "Jamoa & HR",
            "symptom": f"Ish haqi fondi (FOT) tushumning {m['fot_share_pct']:.1f}% ini egallagan",
            "root_cause": f"Xodim boshiga tushum ({_fmt_money(m['rev_per_emp'], curr)}) ish haqi yukini qoplash uchun yetarli emas yoki KPI tizimi ({prof['kpi_achievement_pct']:.0f}%) zaif.",
            "solution": "Oylikning 30-40% qismini aniq KPI/natijaga (bonusga) bog'lash va takrorlanuvchi ishlarni avtomatlashtirish.",
            "impact_money": max(excess * 0.5, 0.0),
            "impact_text": f"+{_fmt_money(max(excess * 0.5, 0.0), curr)} / davr unumdorlik samarasi",
            "horizon": "60 kun",
        })

    if m["turnover_pct"] >= 10.0:
        rehire_cost = prof["employees_left"] * (prof["payroll_total"] / max(prof["employees_count"], 1)) * 1.5
        findings.append({
            "severity": "O'rta",
            "area": "Jamoa & HR",
            "symptom": f"Kadrlar qo'nimsizligi yuqori ({m['turnover_pct']:.1f}%)",
            "root_cause": "Xodimlar ketishi yangi xodim qidirish, o'qitish va mijoz yo'qotish xarajatlarini oshirmoqda.",
            "solution": "Chiqish suhbati (exit interview) joriy qilish, asosiy xodimlar uchun choraklik bonus va aniq o'sish rejasini tuzish.",
            "impact_money": rehire_cost,
            "impact_text": f"~{_fmt_money(rehire_cost, curr)} yashirin kadr yo'qotishining oldini olish",
            "horizon": "60 kun",
        })

    # 5. Operatsiyalar (Brak / Qaytarilish / Quvvat)
    if prof["defect_return_pct"] > 3.0 and rev > 0:
        save_defect = m["defect_loss_est"] * 0.6
        findings.append({
            "severity": "Yuqori" if prof["defect_return_pct"] > 7.0 else "O'rta",
            "area": "Operatsiyalar",
            "symptom": f"Brak / qaytarilish ulushi baland ({prof['defect_return_pct']:.1f}%)",
            "root_cause": f"Sifat nazorati sustligi sababli har davrda taxminan {_fmt_money(m['defect_loss_est'], curr)} yo'qotilmoqda.",
            "solution": "Yuklash/topshirishdan oldin 5 bandli sifat chek-listini majburiy qilish va brak sabablarini haftalik tahlil qilish.",
            "impact_money": save_defect,
            "impact_text": f"+{_fmt_money(save_defect, curr)} / davr to'g'ridan-to'g'ri tejam",
            "horizon": "30 kun",
        })

    if prof["capacity_util_pct"] < 60.0 and rev > 0:
        extra_rev = rev * 0.15
        findings.append({
            "severity": "O'rta",
            "area": "Operatsiyalar",
            "symptom": f"Quvvat yuklanishi past ({prof['capacity_util_pct']:.0f}%)",
            "root_cause": "Mavjud uskuna, xodim yoki maydonning katta qismi bo'sh turibdi, lekin doimiy xarajat to'lanmoqda.",
            "solution": "Bo'sh soatlarda B2B ulgurji buyurtmalar, aksiyali paketlar yoki qo'shimcha xizmat turlarini kiritish.",
            "impact_money": extra_rev,
            "impact_text": f"+{_fmt_money(extra_rev, curr)} qo'shimcha tushum potensiali",
            "horizon": "90 kun",
        })

    # 6. Barqarorlik va Konsentratsiya Risklari
    if prof["top3_clients_share_pct"] > 45.0:
        risk_amt = rev * (prof["top3_clients_share_pct"] / 100.0) / 3.0
        findings.append({
            "severity": "Yuqori" if prof["top3_clients_share_pct"] > 65.0 else "O'rta",
            "area": "Barqarorlik & Risk",
            "symptom": f"Top-3 mijozga yuqori qaramlik ({prof['top3_clients_share_pct']:.0f}%)",
            "root_cause": f"Bitta yirik mijoz ketsa, tushum bir kunda ~{_fmt_money(risk_amt, curr)} ga qulashi mumkin.",
            "solution": "Yangi o'rta segment mijozlar bazasini kengaytirish va bitta mijoz ulushini 15% dan oshirmaslik maqsadini qo'yish.",
            "impact_money": risk_amt,
            "impact_text": f"{_fmt_money(risk_amt, curr)} lik tushum xavfini sug'urtalash",
            "horizon": "90 kun",
        })

    if prof["top_supplier_share_pct"] > 55.0:
        findings.append({
            "severity": "O'rta",
            "area": "Barqarorlik & Risk",
            "symptom": f"Asosiy yetkazib beruvchiga qaramlik ({prof['top_supplier_share_pct']:.0f}%)",
            "root_cause": "Yetkazib beruvchi narxni oshirsa yoki kechiksa, butun savdo/ishlab chiqarish to'xtab qoladi.",
            "solution": "Kamida 2 ta zaxira yetkazib beruvchi bilan sinov shartnomasi tuzib, hajmning 25-30% ini ularga taqsimlash.",
            "impact_money": fin["cogs"] * 0.05,
            "impact_text": f"~{_fmt_money(fin['cogs'] * 0.05, curr)} xarid narxi bo'yicha savdolashish ustunligi",
            "horizon": "90 kun",
        })

    # Agar jiddiy muammo topilmasa — masshtablash tavsiyasi
    if not findings:
        findings.append({
            "severity": "Past",
            "area": "Strategik O'sish",
            "symptom": "Asosiy ko'rsatkichlar me'yorida",
            "root_cause": "Korxonada kritik uzilishlar aniqlanmadi — endi o'sishni tizimli masshtablash bosqichiga o'tish mumkin.",
            "solution": "Eng yuqori marjali 'A' toifa mahsulotlarda marketing byudjetini 15-20% oshirish va yangi hudud/kanal ochish.",
            "impact_money": rev * 0.15,
            "impact_text": f"+{_fmt_money(rev * 0.15, curr)} barqaror o'sish potensiali",
            "horizon": "90 kun",
        })

    order = {"Yuqori": 0, "O'rta": 1, "Past": 2}
    findings.sort(key=lambda x: (order.get(x["severity"], 3), -x["impact_money"]))
    return findings


# =========================================================
# 6. 12 OYLIK BARQAROR SAMARADORLIK PROGNOZI (3 SSENARIY)
# =========================================================
def build_12m_forecast(fin: dict, findings: list, base_growth_pct: float = 2.0) -> pd.DataFrame:
    scale_to_month = 30.0 / max(fin["period_days"], 1)
    m_rev = fin["revenue"] * scale_to_month
    m_cogs_ratio = (fin["cogs"] / fin["revenue"]) if fin["revenue"] > 0 else 0.70
    m_opex = fin["opex"] * scale_to_month

    # Tavsiyalar bajarilganda kutilayotgan marja yaxshilanishi va o'sish tezligi
    total_impact_m = sum(f["impact_money"] for f in findings if f["area"] != "Pul Aylanishi (CCC)") * scale_to_month
    margin_gain_ratio = min(0.08, (total_impact_m / m_rev) * 0.45) if m_rev > 0 else 0.03

    rows = []
    for m in range(1, 13):
        # Bazaviy ssenariy (hozirgi trend)
        rev_base = m_rev * ((1.0 + base_growth_pct / 100.0) ** (m - 1))
        prof_base = rev_base * (1.0 - m_cogs_ratio) - m_opex * ((1.0 + 0.008) ** (m - 1))

        # Pessimistik ssenariy (bozor pasayishi / xarajat inflyatsiyasi)
        rev_pess = m_rev * ((1.0 - 0.025) ** (m - 1))
        prof_pess = rev_pess * (1.0 - min(m_cogs_ratio + 0.03, 0.96)) - m_opex * ((1.0 + 0.015) ** (m - 1))

        # Maqsadli ssenariy (30/60/90 reja bajarilganda bosqichma-bosqich samara)
        ramp = min(1.0, m / 4.0)
        rev_opt = m_rev * ((1.0 + (base_growth_pct + 2.5) / 100.0) ** (m - 1))
        opt_cogs_ratio = max(0.10, m_cogs_ratio - margin_gain_ratio * 0.6 * ramp)
        opt_opex = m_opex * (1.0 - 0.08 * ramp) * ((1.0 + 0.005) ** (m - 1))
        prof_opt = rev_opt * (1.0 - opt_cogs_ratio) - opt_opex

        rows.append({
            "Oy": f"{m}-oy",
            "Pessimistik Foyda": prof_pess,
            "Bazaviy Foyda": prof_base,
            "Maqsadli Foyda": prof_opt,
            "Bazaviy Tushum": rev_base,
            "Maqsadli Tushum": rev_opt,
        })
    return pd.DataFrame(rows)


# =========================================================
# 7. STREAMLIT INTERFEYSI (app.py GA 1 QATOR BILAN ULANADI)
# =========================================================
def render_enterprise_360(
    tx_df: pd.DataFrame,
    debts_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    company_name: str,
    curr: str = "UZS",
):
    st.divider()
    st.header("🧭 360° Korxona Diagnostikasi, Muammo Ildizi va Barqaror Rivojlanish")
    st.caption(
        "Korxonaning nafaqat pul oqimi, balki mijozlar (Unit Economics), operatsiyalar, HR unumdorligi "
        "va barqarorlik risklarini kompleks tahlil qilib, aniq yechim va 12 oylik prognoz beradi."
    )

    prof = load_360_profile(company_name)

    # --- Ma'lumot kiritish (saqlanadigan forma) ---
    with st.expander("⚙️ Korxonaning 360° Operatsion, Mijoz, HR va Risk ma'lumotlarini kiritish / yangilash", expanded=False):
        with st.form(key=f"form_360_{company_name}"):
            st.markdown("**1. Davr va Mijozlar (Unit Economics)**")
            c1, c2, c3, c4 = st.columns(4)
            p_days = c1.number_input("Tahlil davri (kun)", min_value=7, max_value=365, value=int(prof["period_days"]), step=1)
            tot_c = c2.number_input("Faol mijozlar soni", min_value=1, value=int(prof["total_customers"]), step=1)
            new_c = c3.number_input("Yangi mijozlar (davrda)", min_value=0, value=int(prof["new_customers"]), step=1)
            rep_c = c4.number_input("Qayta xarid qilganlar", min_value=0, value=int(prof["repeat_customers"]), step=1)

            c5, c6, c7 = st.columns(3)
            mkt = c5.number_input(f"Marketing xarajati ({curr})", min_value=0.0, value=float(prof["marketing_spend"]), step=500000.0)
            lt_m = c6.number_input("Mijoz o'rtacha umr davri (oy)", min_value=1.0, max_value=120.0, value=float(prof["avg_lifetime_months"]), step=1.0)
            top3 = c7.slider("Top-3 mijozning tushumdagi ulushi (%)", 0.0, 100.0, float(prof["top3_clients_share_pct"]), 1.0)

            st.markdown("**2. Jamoa va HR Unumdorligi**")
            h1, h2, h3, h4 = st.columns(4)
            emp_cnt = h1.number_input("Xodimlar soni", min_value=1, value=int(prof["employees_count"]), step=1)
            fot = h2.number_input(f"Ish haqi fondi — FOT ({curr})", min_value=0.0, value=float(prof["payroll_total"]), step=1000000.0)
            emp_left = h3.number_input("Ishdan ketgan xodimlar", min_value=0, value=int(prof["employees_left"]), step=1)
            kpi_p = h4.slider("Jamoa KPI bajarilishi (%)", 0.0, 100.0, float(prof["kpi_achievement_pct"]), 1.0)

            st.markdown("**3. Operatsiyalar, Sifat va Yetkazib Berish Riski**")
            o1, o2, o3, o4 = st.columns(4)
            defect = o1.number_input("Brak / qaytarilish ulushi (%)", min_value=0.0, max_value=100.0, value=float(prof["defect_return_pct"]), step=0.5)
            lead_d = o2.number_input("Buyurtma bajarilish vaqti (kun)", min_value=0.0, max_value=180.0, value=float(prof["avg_lead_time_days"]), step=0.5)
            cap_u = o3.slider("Quvvat / Bandlik yuklanishi (%)", 0.0, 100.0, float(prof["capacity_util_pct"]), 1.0)
            sup_s = o4.slider("Asosiy yetkazib beruvchi ulushi (%)", 0.0, 100.0, float(prof["top_supplier_share_pct"]), 1.0)

            submitted = st.form_submit_button("💾 360° Ma'lumotlarni saqlash va qayta hisoblash", type="primary")
            if submitted:
                prof = {
                    "period_days": p_days,
                    "total_customers": tot_c,
                    "new_customers": new_c,
                    "repeat_customers": rep_c,
                    "marketing_spend": mkt,
                    "avg_lifetime_months": lt_m,
                    "top3_clients_share_pct": top3,
                    "employees_count": emp_cnt,
                    "payroll_total": fot,
                    "employees_left": emp_left,
                    "kpi_achievement_pct": kpi_p,
                    "defect_return_pct": defect,
                    "avg_lead_time_days": lead_d,
                    "capacity_util_pct": cap_u,
                    "top_supplier_share_pct": sup_s,
                }
                save_360_profile(company_name, prof)
                st.success("360° ko'rsatkichlar saqlandi!")

    # --- Hisob-kitoblar ---
    fin = extract_financial_core(tx_df, debts_df, inv_df, period_days=prof["period_days"])
    eval_res = evaluate_enterprise_360(fin, prof)
    findings = run_root_cause_engine(fin, prof, eval_res, curr=curr)

    tab_radar, tab_root, tab_plan, tab_fcast = st.tabs([
        "🕸️ 360° Sog'lomlik & CCC",
        "🔍 Muammo Ildizi (Root-Cause)",
        "🗺️ 30/60/90 Harakatlar Rejasi",
        "📈 12 Oylik Barqarorlik Prognozi",
    ])

    # --- TAB 1: RADAR & CCC ---
    with tab_radar:
        grade_text, grade_type = eval_res["grade"]
        overall = eval_res["overall"]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Umumiy Sog'lomlik Indeksi", f"{overall:.1f} / 100")
        k2.metric("Pul Aylanish Sikli (CCC)", f"{fin['ccc']:.0f} kun", help="CCC = DIO (Ombor) + DSO (Debitor) - DPO (Kreditor)")
        k3.metric("LTV / CAC Nisbati", f"{eval_res['metrics']['ltv_cac']:.2f}x", help="Barqaror biznes me'yori >= 3.0x")
        k4.metric("Xodim boshiga tushum", _fmt_money(eval_res["metrics"]["rev_per_emp"], curr))

        getattr(st, grade_type)(f"**Korxona holati ({overall:.1f} ball):** {grade_text}")

        col_r, col_c = st.columns([3, 2])
        with col_r:
            cats = list(eval_res["scores"].keys())
            vals = list(eval_res["scores"].values())
            fig_rad = go.Figure()
            fig_rad.add_trace(
                go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=cats + [cats[0]],
                    fill="toself",
                    name="Joriy Holat",
                    line=dict(color="#1F3864", width=2.5),
                    fillcolor="rgba(47, 85, 151, 0.28)",
                )
            )
            fig_rad.add_trace(
                go.Scatterpolar(
                    r=[80] * (len(cats) + 1),
                    theta=cats + [cats[0]],
                    name="Barqarorlik Me'yori (80)",
                    line=dict(color="#1E8449", dash="dash", width=1.8),
                )
            )
            fig_rad.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                title="5 Ustunli Korxona Sog'lomlik Radari",
                height=400,
                legend=dict(orientation="h", y=-0.12),
                margin=dict(l=40, r=40, t=45, b=40),
            )
            st.plotly_chart(fig_rad, use_container_width=True)

        with col_c:
            # CCC waterfall / bar breakdown
            fig_ccc = go.Figure(
                go.Bar(
                    x=["Ombor (DIO)", "Debitor (DSO)", "Kreditor (-DPO)", "Jami CCC"],
                    y=[fin["dio"], fin["dso"], -fin["dpo"], fin["ccc"]],
                    marker_color=["#2F5597", "#D97706", "#1E8449", "#C00000" if fin["ccc"] > 30 else "#1F3864"],
                    text=[f"{v:.0f} kun" for v in [fin["dio"], fin["dso"], -fin["dpo"], fin["ccc"]]],
                    textposition="outside",
                )
            )
            fig_ccc.update_layout(
                title="Pul Aylanish Sikli (CCC) Tuzilmasi",
                yaxis_title="Kunlar",
                height=400,
                margin=dict(l=20, r=20, t=45, b=40),
            )
            st.plotly_chart(fig_ccc, use_container_width=True)

        # 5 ustun jadvali
        score_df = pd.DataFrame(
            [
                {
                    "Yo'nalish": k,
                    "Ball (0-100)": v,
                    "Holat": "Yaxshi" if v >= 75 else ("O'rtacha" if v >= 55 else "Zaif nuqta"),
                }
                for k, v in eval_res["scores"].items()
            ]
        )
        st.dataframe(score_df, use_container_width=True, hide_index=True)

    # --- TAB 2: ROOT-CAUSE ENGINE ---
    with tab_root:
        st.subheader("Sabab-Oqibat Diagnostika Natijalari va Raqamli Yechimlar")
        total_potential = sum(f["impact_money"] for f in findings)
        st.info(
            f"Aniqlangan ustuvor nuqtalar soni: **{len(findings)} ta** | "
            f"Yechimlar joriy etilganda kutilayotgan umumiy moliyaviy samara/himoya: **{_fmt_money(total_potential, curr)}**"
        )

        for idx, f in enumerate(findings, start=1):
            badge = "🔴" if f["severity"] == "Yuqori" else ("🟠" if f["severity"] == "O'rta" else "🟢")
            with st.container(border=True):
                st.markdown(f"#### {badge} {idx}. [{f['area']}] {f['symptom']} *(Muhimlik: {f['severity']})*")
                st.markdown(f"**Ildiz sababi:** {f['root_cause']}")
                st.markdown(f"**Amaliy yechim:** {f['solution']}")
                st.markdown(f"**Kutilayotgan samara:** `{f['impact_text']}`  |  **Ijro muddati:** `{f['horizon']}`")

    # --- TAB 3: 30 / 60 / 90 REJA ---
    with tab_plan:
        st.subheader("Barqaror Samaradorlikka Chiqish: 30 / 60 / 90 Kunlik Yo'l Xaritasi")
        col30, col60, col90 = st.columns(3)

        buckets = {
            "30 kun": (col30, "🚨 1-30 kun: Qon ketishini to'xtatish"),
            "60 kun": (col60, "🔧 31-60 kun: Tizim va Jamoani sozlash"),
            "90 kun": (col90, "🚀 61-90 kun: Barqaror o'sish va himoya"),
        }
        for key, (col_ui, title) in buckets.items():
            with col_ui:
                st.markdown(f"### {title}")
                items = [f for f in findings if f["horizon"] == key]
                if not items:
                    st.caption("Bu bosqichda tanqidiy vazifa yo'q — oldingi natijalarni mustahkamlang.")
                for item in items:
                    with st.container(border=True):
                        st.markdown(f"**{item['area']}:** {item['symptom']}")
                        st.write(item["solution"])
                        st.caption(f"Samara: {item['impact_text']}")

    # --- TAB 4: 12 OYLIK PROGNOZ ---
    with tab_fcast:
        st.subheader("12 Oylik Ko'p Ssenariyli Barqaror Samaradorlik Prognozi")
        if fin["revenue"] <= 0:
            st.warning("12 oylik prognoz qurish uchun avval kamida bitta savdo operatsiyasi kiritilgan bo'lishi kerak.")
        else:
            base_g = st.slider("Kutilayotgan tabiiy oylik savdo o'sishi (%)", -5.0, 15.0, 2.0, 0.5)
            fc_df = build_12m_forecast(fin, findings, base_growth_pct=base_g)

            f1, f2, f3 = st.columns(3)
            f1.metric("12 oylik Bazaviy Sof Foyda", _fmt_money(fc_df["Bazaviy Foyda"].sum(), curr))
            f2.metric(
                "12 oylik Maqsadli Sof Foyda (Reja bilan)",
                _fmt_money(fc_df["Maqsadli Foyda"].sum(), curr),
                delta=_fmt_money(fc_df["Maqsadli Foyda"].sum() - fc_df["Bazaviy Foyda"].sum(), curr),
            )
            f3.metric("12 oylik Pessimistik (Stress-test)", _fmt_money(fc_df["Pessimistik Foyda"].sum(), curr))

            fig_fc = go.Figure()
            fig_fc.add_scatter(x=fc_df["Oy"], y=fc_df["Maqsadli Foyda"], name="Maqsadli (30/60/90 reja bilan)", mode="lines+markers", line=dict(color="#1E8449", width=3))
            fig_fc.add_scatter(x=fc_df["Oy"], y=fc_df["Bazaviy Foyda"], name="Bazaviy (hozirgi holat)", mode="lines+markers", line=dict(color="#2F5597", width=2.5))
            fig_fc.add_scatter(x=fc_df["Oy"], y=fc_df["Pessimistik Foyda"], name="Pessimistik (inqiroz stress-test)", mode="lines+markers", line=dict(color="#C00000", dash="dash", width=2))
            fig_fc.add_hline(y=0, line_dash="dot", line_color="#666")
            fig_fc.update_layout(
                title="Sof Foyda Dinamikasi: 3 ta Ssenariy Solishtiruvi (12 oy)",
                xaxis_title="Prognoz oylari",
                yaxis_title=f"Oylik Sof Foyda ({curr})",
                height=420,
                legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(fig_fc, use_container_width=True)

            st.dataframe(fc_df, use_container_width=True, hide_index=True)
