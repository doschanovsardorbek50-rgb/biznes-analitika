import io
import re
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False


def _clean_pdf_text(text) -> str:
    """FPDF uchun matnni xavfsiz Latin-1 formatiga tozalash (o'zbek lotin harflari saqlanadi)."""
    if text is None:
        return ""
    s = str(text)
    replacements = {
        "‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "`": "'",
        "—": "-", "–": "-", "…": "...", "«": '"', "»": '"',
        "“": '"', "”": '"', "•": "-", "№": "No.",
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    # Emojilarni va Latin-1 dan tashqari belgilarni tozalash
    s = s.encode("latin-1", "ignore").decode("latin-1")
    return re.sub(r"\s+", " ", s).strip()


def _fmt_num(val: float, curr: str = "UZS") -> str:
    try:
        return f"{float(val):,.0f} {curr}".replace(",", " ")
    except Exception:
        return f"0 {curr}"


def _detect_col(df: pd.DataFrame, candidates: list):
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    return None


def compute_abc_xyz(tx_df: pd.DataFrame, metric: str = "revenue") -> pd.DataFrame:
    """ABC-XYZ tahlil jadvalini hisoblash."""
    if tx_df is None or tx_df.empty:
        return pd.DataFrame()

    df = tx_df.copy()
    item_col = _detect_col(df, ["item_name", "mahsulot nomi", "mahsulot", "product", "name"])
    rev_col = _detect_col(df, ["revenue", "tushum", "savdo"])
    cogs_col = _detect_col(df, ["cogs", "tannarx"])
    opex_col = _detect_col(df, ["opex", "operatsion xarajat", "xarajat"])

    if not item_col or not rev_col:
        return pd.DataFrame()

    df[rev_col] = pd.to_numeric(df[rev_col], errors="coerce").fillna(0.0)
    df["_cogs"] = pd.to_numeric(df[cogs_col], errors="coerce").fillna(0.0) if cogs_col else 0.0
    df["_opex"] = pd.to_numeric(df[opex_col], errors="coerce").fillna(0.0) if opex_col else 0.0
    df["_profit"] = df[rev_col] - df["_cogs"] - df["_opex"]

    target_col = rev_col if metric == "revenue" else "_profit"

    grouped = (
        df.groupby(item_col, as_index=False)
        .agg(
            tushum=(rev_col, "sum"),
            foyda=("_profit", "sum"),
            sotuv_soni=(rev_col, "count"),
            ortacha=(rev_col, "mean"),
            std_dev=(rev_col, "std"),
        )
    )

    # ABC tasnifi (faqat musbat qiymatlar ulushi bo'yicha Pareto 80/15/5)
    val_col = "tushum" if metric == "revenue" else "foyda"
    grouped = grouped.sort_values(by=val_col, ascending=False).reset_index(drop=True)

    positive_total = grouped.loc[grouped[val_col] > 0, val_col].sum()
    if positive_total > 0:
        grouped["ulush_%"] = np.where(grouped[val_col] > 0, grouped[val_col] / positive_total * 100, 0.0)
    else:
        grouped["ulush_%"] = 0.0

    grouped["jamlangan_%"] = grouped["ulush_%"].cumsum()
    grouped["_prev_cum"] = grouped["jamlangan_%"].shift(1, fill_value=0.0)

    def _abc_class(row):
        if row[val_col] <= 0:
            return "C"
        if row["_prev_cum"] < 80.0:
            return "A"
        elif row["_prev_cum"] < 95.0:
            return "B"
        return "C"

    grouped["ABC"] = grouped.apply(_abc_class, axis=1)

    # XYZ tasnifi (variatsiya koeffitsiyenti CV%)
    def _xyz_class(row):
        if row["sotuv_soni"] < 2 or pd.isna(row["std_dev"]) or row["ortacha"] <= 0:
            return "Z"
        cv = (row["std_dev"] / row["ortacha"]) * 100
        if cv <= 10:
            return "X"
        elif cv <= 25:
            return "Y"
        return "Z"

    grouped["CV_%"] = np.where(
        (grouped["sotuv_soni"] >= 2) & (grouped["ortacha"] > 0),
        (grouped["std_dev"].fillna(0) / grouped["ortacha"]) * 100,
        np.nan,
    )
    grouped["XYZ"] = grouped.apply(_xyz_class, axis=1)
    grouped["Guruh"] = grouped["ABC"] + grouped["XYZ"]

    rec_map = {
        "AX": "Oltin fond: omborda doim zaxira bo'lishi shart, narxni ushlab turing",
        "AY": "Yuqori foyda, o'rtacha tebranish: xavfsizlik zaxirasini oshiring",
        "AZ": "Katta tushum, tartibsiz talab: buyurtma asosida yetkazish ma'qul",
        "BX": "Barqaror o'rta mahsulot: avtomatik qayta buyurtma sozlang",
        "BY": "O'rtacha mahsulot: mavsumiy aksiyalar bilan savdoni tekislang",
        "BZ": "Tebranuvchan o'rta mahsulot: ortiqcha zaxira ushlamang",
        "CX": "Past ulush, barqaror talab: minimal zaxira bilan yuriting",
        "CY": "Past ulush: narx yoki tannarxni qayta ko'rib chiqing",
        "CZ": "Eng zaif pozitsiya: assortimentdan chiqarishni ko'rib chiqing",
    }
    grouped["Tavsiya"] = grouped["Guruh"].map(rec_map)
    grouped.rename(columns={item_col: "Mahsulot"}, inplace=True)
    return grouped


def compute_breakeven(tx_df: pd.DataFrame, custom_fixed: float = None, custom_var_pct: float = None) -> dict:
    """Zararsizlik nuqtasi (Break-Even Point) hisob-kitoblari."""
    if tx_df is None or tx_df.empty:
        return {}

    rev_col = _detect_col(tx_df, ["revenue", "tushum", "savdo"])
    cogs_col = _detect_col(tx_df, ["cogs", "tannarx"])
    opex_col = _detect_col(tx_df, ["opex", "operatsion xarajat", "xarajat"])

    total_rev = float(pd.to_numeric(tx_df[rev_col], errors="coerce").fillna(0).sum()) if rev_col else 0.0
    total_var = float(pd.to_numeric(tx_df[cogs_col], errors="coerce").fillna(0).sum()) if cogs_col else 0.0
    total_fix = float(pd.to_numeric(tx_df[opex_col], errors="coerce").fillna(0).sum()) if opex_col else 0.0

    fixed_cost = custom_fixed if custom_fixed is not None else total_fix
    var_ratio = (custom_var_pct / 100.0) if custom_var_pct is not None else (total_var / total_rev if total_rev > 0 else 0.7)
    cmr = 1.0 - var_ratio  # Contribution Margin Ratio

    bep_rev = (fixed_cost / cmr) if cmr > 0 else float("inf")
    safety_margin = total_rev - bep_rev if np.isfinite(bep_rev) else -fixed_cost
    safety_pct = (safety_margin / total_rev * 100) if (total_rev > 0 and np.isfinite(bep_rev)) else 0.0

    return {
        "total_rev": total_rev,
        "total_var": total_var,
        "fixed_cost": fixed_cost,
        "var_ratio": var_ratio,
        "cmr": cmr,
        "bep_rev": bep_rev,
        "safety_margin": safety_margin,
        "safety_pct": safety_pct,
    }


def generate_pdf_report(company_name: str, curr: str, tx_df: pd.DataFrame, analysis: dict, abc_df: pd.DataFrame, bep: dict) -> bytes:
    """Rahbarlar uchun tayyor PDF tahliliy hisobot generatsiyasi."""
    if not FPDF_AVAILABLE:
        raise RuntimeError("fpdf2 kutubxonasi o'rnatilmagan. requirements.txt ga 'fpdf2' qo'shing.")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header banner
    pdf.set_fill_color(31, 56, 100)
    pdf.rect(0, 0, 210, 32, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(12, 8)
    pdf.cell(0, 8, _clean_pdf_text("BIZNES MOLIYAVIY TAHLIL VA DIAGNOSTIKA HISOBOTI"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(12, 18)
    report_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    pdf.cell(0, 6, _clean_pdf_text(f"Korxona: {company_name}   |   Sana: {report_date}   |   Valyuta: {curr}"), ln=True)

    pdf.ln(14)
    pdf.set_text_color(26, 26, 26)

    # 1. KPI Summary
    rev_col = _detect_col(tx_df, ["revenue", "tushum", "savdo"])
    cogs_col = _detect_col(tx_df, ["cogs", "tannarx"])
    opex_col = _detect_col(tx_df, ["opex", "operatsion xarajat", "xarajat"])

    tot_rev = float(pd.to_numeric(tx_df[rev_col], errors="coerce").fillna(0).sum()) if rev_col else 0.0
    tot_cogs = float(pd.to_numeric(tx_df[cogs_col], errors="coerce").fillna(0).sum()) if cogs_col else 0.0
    tot_opex = float(pd.to_numeric(tx_df[opex_col], errors="coerce").fillna(0).sum()) if opex_col else 0.0
    net_profit = analysis.get("kpi", {}).get("net", tot_rev - tot_cogs - tot_opex) if isinstance(analysis, dict) else (tot_rev - tot_cogs - tot_opex)
    margin_pct = analysis.get("kpi", {}).get("margin", (net_profit / tot_rev * 100) if tot_rev > 0 else 0.0) if isinstance(analysis, dict) else ((net_profit / tot_rev * 100) if tot_rev > 0 else 0.0)

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(31, 56, 100)
    pdf.cell(0, 8, "1. Asosiy Moliyaviy Ko'rsatkichlar (P&L)", ln=True)
    pdf.set_text_color(26, 26, 26)

    kpi_rows = [
        ("Jami Tushum", _fmt_num(tot_rev, curr)),
        ("Jami Tannarx (COGS)", _fmt_num(tot_cogs, curr)),
        ("Yalpi Foyda", _fmt_num(tot_rev - tot_cogs, curr)),
        ("Operatsion Xarajatlar (OPEX)", _fmt_num(tot_opex, curr)),
        ("Sof Foyda", _fmt_num(net_profit, curr)),
        ("Sof Marja (%)", f"{margin_pct:.1f}%"),
    ]
    pdf.set_font("Helvetica", "", 10)
    for idx, (lbl, val) in enumerate(kpi_rows):
        fill = idx % 2 == 0
        pdf.set_fill_color(244, 247, 250)
        if lbl in ("Sof Foyda", "Sof Marja (%)"):
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_fill_color(217, 225, 242)
            fill = True
        else:
            pdf.set_font("Helvetica", "", 10)
        pdf.cell(110, 7, _clean_pdf_text(lbl), border=1, fill=fill)
        pdf.cell(75, 7, _clean_pdf_text(val), border=1, align="R", fill=fill, ln=True)

    pdf.ln(6)

    # 2. Break-Even Section
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(31, 56, 100)
    pdf.cell(0, 8, "2. Zararsizlik Nuqtasi (Break-Even Point)", ln=True)
    pdf.set_text_color(26, 26, 26)
    pdf.set_font("Helvetica", "", 10)

    if bep and np.isfinite(bep.get("bep_rev", float("inf"))):
        bep_rows = [
            ("Doimiy xarajatlar (Fixed Cost)", _fmt_num(bep["fixed_cost"], curr)),
            ("Marjalilik koeffitsiyenti (CMR)", f"{bep['cmr']*100:.1f}%"),
            ("Zararsizlik chegarasi (BEP)", _fmt_num(bep["bep_rev"], curr)),
            ("Xavfsizlik zaxirasi (Margin of Safety)", f"{_fmt_num(bep['safety_margin'], curr)} ({bep['safety_pct']:.1f}%)"),
        ]
        for lbl, val in bep_rows:
            pdf.cell(110, 7, _clean_pdf_text(lbl), border=1)
            pdf.cell(75, 7, _clean_pdf_text(val), border=1, align="R", ln=True)
    else:
        pdf.cell(0, 7, "Zararsizlik nuqtasini hisoblash uchun ijobiy marja talab etiladi.", ln=True)

    pdf.ln(6)

    # 3. ABC-XYZ Summary
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(31, 56, 100)
    pdf.cell(0, 8, "3. ABC-XYZ Tahlili (Top 10 Mahsulot)", ln=True)
    pdf.set_text_color(26, 26, 26)

    if abc_df is not None and not abc_df.empty:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(47, 85, 151)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(65, 7, "Mahsulot", border=1, fill=True)
        pdf.cell(35, 7, "Tushum", border=1, align="R", fill=True)
        pdf.cell(35, 7, "Sof Foyda", border=1, align="R", fill=True)
        pdf.cell(20, 7, "Ulush %", border=1, align="R", fill=True)
        pdf.cell(30, 7, "ABC-XYZ", border=1, align="C", fill=True, ln=True)

        pdf.set_text_color(26, 26, 26)
        pdf.set_font("Helvetica", "", 9)
        for _, r in abc_df.head(10).iterrows():
            pdf.cell(65, 6.5, _clean_pdf_text(str(r["Mahsulot"])[:32]), border=1)
            pdf.cell(35, 6.5, _clean_pdf_text(f"{r['tushum']:,.0f}".replace(",", " ")), border=1, align="R")
            pdf.cell(35, 6.5, _clean_pdf_text(f"{r['foyda']:,.0f}".replace(",", " ")), border=1, align="R")
            pdf.cell(20, 6.5, f"{r['ulush_%']:.1f}%", border=1, align="R")
            pdf.cell(30, 6.5, _clean_pdf_text(r["Guruh"]), border=1, align="C", ln=True)

    pdf.ln(6)

    # 4. Diagnostics & Recommendations
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(31, 56, 100)
    pdf.cell(0, 8, "4. Diagnostika va Tavsiyalar", ln=True)
    pdf.set_text_color(26, 26, 26)
    pdf.set_font("Helvetica", "", 10)

    notes = []
    if net_profit < 0:
        notes.append("- DIQQAT: Korxona hozirda zararda ishlamoqda. Xarajatlarni qisqartirish va narxlarni qayta ko'rib chiqish shart.")
    elif margin_pct < 10:
        notes.append(f"- OGOHLANTIRISH: Sof marja past ({margin_pct:.1f}%). Tannarx va operatsion xarajatlarni optimallashtiring.")
    else:
        notes.append(f"- YAXSHI HOLAT: Korxona barqaror foydada ({margin_pct:.1f}% marja).")

    if bep and np.isfinite(bep.get("bep_rev", float("inf"))):
        if bep["safety_margin"] < 0:
            notes.append(f"- Zararsizlikka chiqish uchun qo'shimcha {_fmt_num(abs(bep['safety_margin']), curr)} savdo kerak.")
        else:
            notes.append(f"- Xavfsizlik zaxirasi {bep['safety_pct']:.1f}% ni tashkil etadi (savdo shuncha tushsa ham zarar bo'lmaydi).")

    if abc_df is not None and not abc_df.empty:
        loss_cnt = int((abc_df["foyda"] < 0).sum())
        if loss_cnt > 0:
            notes.append(f"- Zarar keltirayotgan mahsulotlar soni: {loss_cnt} ta. Ularning narxini oshiring yoki sotuvdan chiqaring.")
        a_cnt = int((abc_df["ABC"] == "A").sum())
        notes.append(f"- 'A' toifadagi asosiy {a_cnt} ta mahsulot biznes tushumining asosiy qismini bermoqda - ular doim omborda bo'lsin.")

    for note in notes:
        pdf.multi_cell(0, 6, _clean_pdf_text(note))

    out = pdf.output(dest="S")
    return bytes(out) if isinstance(out, (bytes, bytearray)) else out.encode("latin-1")


def render_pro_analytics(tx_df: pd.DataFrame, analysis: dict, company_name: str, curr: str = "UZS"):
    """app.py ga 1 qator bilan ulanadigan PRO tahliliy blok (ABC-XYZ, Break-Even, PDF)."""
    st.divider()
    st.header("🚀 PRO Tahliliy Modullar (ABC-XYZ, Zararsizlik & PDF)")

    if tx_df is None or tx_df.empty:
        st.info("PRO tahlillar ishlashi uchun kamida bitta savdo operatsiyasi kiritilgan bo'lishi kerak.")
        return

    tab_abc, tab_bep, tab_pdf = st.tabs([
        "📊 ABC-XYZ Tahlili",
        "⚖️ Zararsizlik Nuqtasi (Break-Even)",
        "📄 Bir Tugmali PDF Hisobot",
    ])

    # --- TAB 1: ABC-XYZ ---
    with tab_abc:
        metric_choice = st.radio(
            "ABC guruhlash mezoni:",
            options=["revenue", "profit"],
            format_func=lambda x: "Tushum ulushi bo'yicha (Pareto)" if x == "revenue" else "Sof foyda ulushi bo'yicha",
            horizontal=True,
        )
        abc_df = compute_abc_xyz(tx_df, metric=metric_choice)

        if abc_df.empty:
            st.warning("ABC-XYZ tahlili uchun mahsulot va tushum ustunlari topilmadi.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("A toifa (Top 80%)", f"{int((abc_df['ABC'] == 'A').sum())} ta")
            c2.metric("B toifa (15%)", f"{int((abc_df['ABC'] == 'B').sum())} ta")
            c3.metric("C toifa (5% / Zaif)", f"{int((abc_df['ABC'] == 'C').sum())} ta")
            c4.metric("Zararli mahsulotlar", f"{int((abc_df['foyda'] < 0).sum())} ta")

            col_left, col_right = st.columns([3, 2])
            with col_left:
                # Pareto chart
                fig_p = go.Figure()
                val_col = "tushum" if metric_choice == "revenue" else "foyda"
                fig_p.add_bar(x=abc_df["Mahsulot"], y=abc_df[val_col], name="Qiymat", marker_color="#2F5597")
                fig_p.add_scatter(
                    x=abc_df["Mahsulot"],
                    y=abc_df["jamlangan_%"],
                    name="Jamlangan %",
                    yaxis="y2",
                    mode="lines+markers",
                    line=dict(color="#C00000", width=2.5),
                )
                fig_p.update_layout(
                    title="Pareto Grafigi (80/20 Qoidasi)",
                    yaxis=dict(title=curr),
                    yaxis2=dict(title="Jamlangan (%)", overlaying="y", side="right", range=[0, 105]),
                    height=380,
                    margin=dict(l=20, r=20, t=40, b=60),
                    legend=dict(orientation="h", y=1.12),
                )
                st.plotly_chart(fig_p, use_container_width=True)

            with col_right:
                # 3x3 ABC-XYZ Heatmap
                matrix = pd.crosstab(abc_df["ABC"], abc_df["XYZ"]).reindex(index=["A", "B", "C"], columns=["X", "Y", "Z"], fill_value=0)
                fig_m = go.Figure(
                    data=go.Heatmap(
                        z=matrix.values,
                        x=["X (Barqaror)", "Y (O'rtacha)", "Z (Tartibsiz)"],
                        y=["A (Muhim)", "B (O'rta)", "C (Past)"],
                        text=matrix.values,
                        texttemplate="%{text} ta",
                        colorscale="Blues",
                        showscale=False,
                    )
                )
                fig_m.update_layout(title="ABC-XYZ Matritsasi", height=380, margin=dict(l=20, r=20, t=40, b=40))
                st.plotly_chart(fig_m, use_container_width=True)

            st.dataframe(
                abc_df[["Mahsulot", "tushum", "foyda", "ulush_%", "ABC", "XYZ", "Guruh", "Tavsiya"]],
                use_container_width=True,
                hide_index=True,
            )

    # --- TAB 2: BREAK-EVEN ---
    with tab_bep:
        base_bep = compute_breakeven(tx_df)
        st.caption("Pastdagi slayderlar yordamida doimiy xarajat yoki tannarx o'zgarsa zararsizlik nuqtasi qanday siljishini sinab ko'ring:")
        sc1, sc2 = st.columns(2)
        custom_fix = sc1.number_input(
            f"Doimiy xarajatlar — ijara, oylik, OPEX ({curr})",
            min_value=0.0,
            value=float(base_bep.get("fixed_cost", 0.0)),
            step=500000.0,
        )
        custom_var = sc2.slider(
            "O'zgaruvchan xarajat / Tannarx ulushi (%)",
            min_value=5.0,
            max_value=95.0,
            value=float(min(max(base_bep.get("var_ratio", 0.7) * 100, 5.0), 95.0)),
            step=1.0,
        )
        bep = compute_breakeven(tx_df, custom_fixed=custom_fix, custom_var_pct=custom_var)

        m1, m2, m3 = st.columns(3)
        bep_val = bep["bep_rev"]
        m1.metric("Zararsizlik nuqtasi (BEP)", _fmt_num(bep_val, curr) if np.isfinite(bep_val) else "Hisoblanmadi")
        m2.metric("Joriy Tushum", _fmt_num(bep["total_rev"], curr))
        m3.metric(
            "Xavfsizlik zaxirasi",
            _fmt_num(bep["safety_margin"], curr),
            delta=f"{bep['safety_pct']:.1f}%",
        )

        if np.isfinite(bep_val) and bep_val > 0:
            max_x = max(bep["total_rev"], bep_val) * 1.35
            x_vals = np.linspace(0, max_x, 50)
            y_rev = x_vals
            y_cost = bep["fixed_cost"] + x_vals * bep["var_ratio"]
            y_fix = np.full_like(x_vals, bep["fixed_cost"])

            fig_b = go.Figure()
            fig_b.add_scatter(x=x_vals, y=y_rev, name="Tushum (Savdo)", line=dict(color="#1E8449", width=3))
            fig_b.add_scatter(x=x_vals, y=y_cost, name="Jami Xarajat", line=dict(color="#C00000", width=3))
            fig_b.add_scatter(x=x_vals, y=y_fix, name="Doimiy Xarajat", line=dict(color="#7F8C8D", dash="dash"))
            fig_b.add_scatter(
                x=[bep_val],
                y=[bep_val],
                mode="markers+text",
                name="Zararsizlik nuqtasi",
                text=[f"BEP: {_fmt_num(bep_val, curr)}"],
                textposition="top left",
                marker=dict(size=12, color="#1F3864", symbol="diamond"),
            )
            fig_b.update_layout(
                title="Zararsizlik Nuqtasi Grafigi (Break-Even Chart)",
                xaxis_title=f"Savdo hajmi ({curr})",
                yaxis_title=f"Summa ({curr})",
                height=420,
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_b, use_container_width=True)

    # --- TAB 3: ONE-CLICK PDF ---
    with tab_pdf:
        st.write("Rahbar yoki hamkorlarga yuborish uchun P&L, Zararsizlik nuqtasi, ABC-XYZ Top-10 va avtomatik tavsiyalar jamlangan tayyor PDF hisobot:")
        if not FPDF_AVAILABLE:
            st.error("PDF yaratish uchun GitHub'dagi `requirements.txt` fayliga `fpdf2` qatorini qo'shing.")
        else:
            abc_for_pdf = compute_abc_xyz(tx_df, metric="revenue")
            bep_for_pdf = compute_breakeven(tx_df)
            pdf_bytes = generate_pdf_report(company_name, curr, tx_df, analysis, abc_for_pdf, bep_for_pdf)
            safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", str(company_name))
            st.download_button(
                label="📄 Tayyor PDF Hisobotni Yuklab Olish",
                data=pdf_bytes,
                file_name=f"{safe_name}_moliyaviy_hisobot.pdf",
                mime="application/pdf",
                type="primary",
            )
