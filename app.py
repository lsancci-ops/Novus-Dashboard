# -*- coding: utf-8 -*-
"""
NOVUS ASSET MANAGEMENT — Dashboard de Contrapartes
Versión Ultra-Optimizada
"""

import os
import colorsys
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="novus | agentes",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# PALETA Y CONFIGURACIÓN BASE
# ─────────────────────────────────────────────
DARK_BG   = "#1A1C1A"
GREEN     = "#5DBB63"
LIGHT_BG  = "#F0F2F0"
WHITE     = "#FFFFFF"
GRAY_TEXT = "#777777"
DARK_TEXT = "#1A1C1A"
BORDER    = "#E8EBE8"

ASSET_COLORS = {
    "Fixed Income":          "#2D6A4F",
    "Renta Variable":        "#5DBB63",
    "Licitaciones":          "#95D5A0",
    "Cauciones Colocadoras": "#1B4332",
    "Pases Colocadores":      "#74C69D",
    "Futuros":               "#B7E4C7",
    "CPD y Pagarés":         "#40916C",
}

FONT_FAMILY = "Arial, sans-serif"

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
  html, body, .stApp {{
      font-family: {FONT_FAMILY} !important;
      background-color: {LIGHT_BG} !important;
  }}
  .novus-hero {{
      background: linear-gradient(135deg, {DARK_BG} 0%, #162416 100%);
      padding: 28px 36px;
      margin: -1rem -1rem 1rem -1rem;
      border-radius: 0 0 12px 12px;
  }}
  .novus-eyebrow {{
      font-size: .7rem; font-weight: 700; letter-spacing: 2px;
      color: {GREEN}; text-transform: uppercase; margin-bottom: 6px;
  }}
  .novus-hero h1 {{
      font-size: 1.8rem; font-weight: 300; color: {WHITE}; margin: 0 0 4px;
  }}
  .novus-hero h1 span {{ color: {GREEN}; font-weight: 700; }}
  .novus-hero p {{ color: #9AADA9; font-size: .85rem; margin: 4px 0 12px; }}
  .novus-badge {{
      display: inline-block; border: 1px solid rgba(93,187,99,.4);
      border-radius: 20px; padding: 3px 10px; font-size: .75rem; color: {GREEN};
  }}
  .kpi-card {{
      background: {WHITE}; border-radius: 8px; padding: 14px 16px;
      border: 1px solid {BORDER}; height: 100%;
  }}
  .kpi-label {{
      font-size: .65rem; font-weight: 700; letter-spacing: 1px;
      color: {GRAY_TEXT}; text-transform: uppercase; margin-bottom: 4px;
  }}
  .kpi-value {{ font-size: 1.6rem; font-weight: 700; color: {GREEN}; }}
  .kpi-name {{ font-size: .9rem; font-weight: 600; color: {DARK_TEXT}; }}
  .section-title {{ font-size: 1.1rem; font-weight: 700; color: {DARK_TEXT}; margin-top: 10px; }}
  .section-underline {{ width: 28px; height: 3px; background: {GREEN}; margin-bottom: 14px; }}
  .var-table {{ width:100%; border-collapse: collapse; font-size: .8rem; }}
  .var-table th {{ font-size: .65rem; text-transform: uppercase; color: {GRAY_TEXT}; padding: 6px 8px; border-bottom: 2px solid {BORDER}; text-align: right; }}
  .var-table th:first-child {{ text-align: left; }}
  .var-table td {{ padding: 6px 8px; border-bottom: 1px solid {BORDER}; text-align: right; color: {DARK_TEXT}; }}
  .var-table td:first-child {{ text-align: left; }}
  .pos {{ color: {GREEN}; font-weight: 700; }}
  .neg {{ color: #E05555; font-weight: 700; }}
  #MainMenu, footer, header {{ visibility: hidden; height: 0; }}
  .block-container {{ padding-top: 0 !important; padding-bottom: 1.5rem !important; }}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CARGA Y FILTRADO RÁPIDO DE DATOS
# ─────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_data(path):
    df = pd.read_csv(path, parse_dates=["Fecha"])
    df["Año"] = df["Fecha"].dt.year
    df["Mes_Num"] = df["Fecha"].dt.month
    
    meses_nombre = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }
    df["Mes_Nombre"] = df["Mes_Num"].map(meses_nombre)
    df["AñoMes"] = df["Fecha"].dt.to_period("M").astype(str)
    return df

CSV_PATH = os.path.join(os.path.dirname(__file__), "base_historica_acumulada.csv")
if not os.path.exists(CSV_PATH):
    st.error("No se encontró `base_historica_acumulada.csv`.")
    st.stop()

df_raw = load_data(CSV_PATH)
max_date = df_raw["Fecha"].max()

# ─────────────────────────────────────────────
# HERO HEADER
# ─────────────────────────────────────────────
st.markdown(f"""
<div class="novus-hero">
  <div class="novus-eyebrow">middle office</div>
  <h1>control de <span>contrapartes</span> y flujo de agentes</h1>
  <p>Volumen operado, participación de mercado y variación por asset category (USD MEP/CCL).</p>
  <div class="novus-badge">datos al {max_date.strftime('%d/%m/%Y')}</div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# FILTROS DESPLEGABLES (OPTIMIZADOS)
# ─────────────────────────────────────────────
with st.expander("🔍 Filtrar datos (Vacío = Selecciona Todos)", expanded=False):
    f_col1, f_col2, f_col3, f_col4 = st.columns(4)
    
    with f_col1:
        anos_disponibles = sorted(df_raw["Año"].unique(), reverse=True)
        anos_sel = st.multiselect("Año", anos_disponibles, placeholder="Todos los años")
        
    with f_col2:
        meses_ordenados = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
                          "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        meses_disponibles = [m for m in meses_ordenados if m in df_raw["Mes_Nombre"].unique()]
        meses_sel = st.multiselect("Mes", meses_disponibles, placeholder="Todos los meses")
        
    with f_col3:
        assets_all = sorted(df_raw["Asset_Category"].unique())
        assets_sel = st.multiselect("Asset Category", assets_all, placeholder="Todas las categorías")
        
    with f_col4:
        fondos_all = sorted(df_raw["Fondo"].unique())
        fondos_sel = st.multiselect("Fondo", fondos_all, placeholder="Todos los fondos")

# Aplicar Filtros Efficiently
df = df_raw.copy()
if anos_sel:
    df = df[df["Año"].isin(anos_sel)]
if meses_sel:
    df = df[df["Mes_Nombre"].isin(meses_sel)]
if assets_sel:
    df = df[df["Asset_Category"].isin(assets_sel)]
if fondos_sel:
    df = df[df["Fondo"].isin(fondos_sel)]

if df.empty:
    st.warning("No hay datos para la combinación de filtros seleccionada.")
    st.stop()

# ─────────────────────────────────────────────
# MÉTRICAS
# ─────────────────────────────────────────────
max_d = df["Fecha"].max()
ytd_s = pd.Timestamp(year=max_d.year, month=1, day=1)
d30   = max_d - pd.Timedelta(days=30)

vol_total = df["Volumen_USD"].sum()
vol_ytd   = df[df["Fecha"] >= ytd_s]["Volumen_USD"].sum()

asset_30d = df[df["Fecha"] >= d30].groupby("Asset_Category")["Volumen_USD"].sum()
asset_dom = asset_30d.idxmax() if not asset_30d.empty else "—"
asset_dom_pct = (asset_30d.max() / asset_30d.sum() * 100) if not asset_30d.empty and asset_30d.sum() > 0 else 0

ag_vol = df.groupby("Agente")["Volumen_USD"].sum()
agente_lider = ag_vol.idxmax() if not ag_vol.empty else "—"
agente_lider_pct = (ag_vol.max() / vol_total * 100) if vol_total > 0 else 0

shares = (ag_vol / vol_total * 100) ** 2
hhi = shares.sum() if vol_total > 0 else 0
conc_label = "Baja" if hhi < 1500 else ("Media" if hhi < 2500 else "Alta")

def fmt_usd(v):
    if v >= 1e9:  return f"USD {v/1e9:,.2f}B"
    if v >= 1e6:  return f"USD {v/1e6:,.1f}M"
    return f"USD {v:,.0f}"

# ─────────────────────────────────────────────
# SECCIÓN: METRICAS CLAVE
# ─────────────────────────────────────────────
st.markdown('<div class="section-title">Métricas Clave</div><div class="section-underline"></div>', unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Volumen YTD</div><div class="kpi-value">{fmt_usd(vol_ytd)}</div></div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Asset Dominante (30d)</div><div class="kpi-name">{asset_dom}</div><div class="kpi-value" style="font-size:1.3rem;">{asset_dom_pct:.1f}%</div></div>', unsafe_allow_html=True)
with k3:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Agente Líder</div><div class="kpi-name">{agente_lider}</div><div class="kpi-value" style="font-size:1.3rem;">{agente_lider_pct:.1f}%</div></div>', unsafe_allow_html=True)
with k4:
    hhi_color = GREEN if hhi < 1500 else ("#E8A020" if hhi < 2500 else "#E05555")
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Concentración HHI</div><div class="kpi-value" style="color:{hhi_color}; font-size:1.3rem;">{conc_label} ({hhi:,.0f})</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SECCIÓN: TORTA + TABLA DE VARIACIÓN VECTORIAL
# ─────────────────────────────────────────────
st.markdown('<div class="section-title">Participación por Agente</div><div class="section-underline"></div>', unsafe_allow_html=True)

col_pie, col_var = st.columns([50, 50])

with col_pie:
    df_pie = df.groupby("Agente")["Volumen_USD"].sum().reset_index().sort_values("Volumen_USD", ascending=False)
    umbral = vol_total * 0.025
    df_pie["Label"] = df_pie.apply(lambda r: r["Agente"] if r["Volumen_USD"] >= umbral else "Otros", axis=1)
    df_pie_g = df_pie.groupby("Label")["Volumen_USD"].sum().reset_index().sort_values("Volumen_USD", ascending=False)

    fig_pie = px.pie(
        df_pie_g, names="Label", values="Volumen_USD",
        hole=0.4, color_discrete_sequence=px.colors.sequential.Greens_r
    )
    fig_pie.update_traces(textinfo="percent", hovertemplate="<b>%{label}</b><br>USD %{value:,.0f}<extra></extra>")
    fig_pie.update_layout(
        showlegend=True,
        legend=dict(font=dict(size=10), orientation="v", y=0.5, x=1.02),
        margin=dict(l=10, r=100, t=10, b=10),
        height=300,
        paper_bgcolor="white", plot_bgcolor="white"
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_var:
    st.markdown(f'<div style="font-size:.65rem; font-weight:700; text-transform:uppercase; color:{GRAY_TEXT}; margin-bottom:8px;">Variación por Asset Category</div>', unsafe_allow_html=True)

    # Cálculo Vectorizado de Períodos (Súper Rápido)
    d60  = max_d - pd.Timedelta(days=60)
    d365 = max_d - pd.Timedelta(days=365)

    c_30  = df[df["Fecha"] >= d30].groupby("Asset_Category")["Volumen_USD"].sum()
    p_30  = df[(df["Fecha"] >= d30 - pd.Timedelta(days=30)) & (df["Fecha"] < d30)].groupby("Asset_Category")["Volumen_USD"].sum()
    
    c_60  = df[df["Fecha"] >= d60].groupby("Asset_Category")["Volumen_USD"].sum()
    p_60  = df[(df["Fecha"] >= d60 - pd.Timedelta(days=60)) & (df["Fecha"] < d60)].groupby("Asset_Category")["Volumen_USD"].sum()

    c_365 = df[df["Fecha"] >= d365].groupby("Asset_Category")["Volumen_USD"].sum()
    p_365 = df[(df["Fecha"] >= d365 - pd.Timedelta(days=365)) & (df["Fecha"] < d365)].groupby("Asset_Category")["Volumen_USD"].sum()

    def calc_pct(curr, prev):
        if prev == 0 or np.isnan(prev) or prev is None:
            return '<span style="color:#777">—</span>'
        pct = ((curr - prev) / prev) * 100
        cls = "pos" if pct >= 0 else "neg"
        sign = "+" if pct >= 0 else ""
        return f'<span class="{cls}">{sign}{pct:.1f}%</span>'

    rows_var = ""
    all_cat = sorted(df["Asset_Category"].unique())
    for cat in all_cat:
        v30 = calc_pct(c_30.get(cat, 0), p_30.get(cat, 0))
        v60 = calc_pct(c_60.get(cat, 0), p_60.get(cat, 0))
        v365 = calc_pct(c_365.get(cat, 0), p_365.get(cat, 0))
        rows_var += f"<tr><td>{cat}</td><td>{v30}</td><td>{v60}</td><td>{v365}</td></tr>"

    st.markdown(f"""
    <div style="overflow-x:auto;">
        <table class="var-table">
          <thead><tr><th>Asset</th><th>30d</th><th>60d</th><th>365d</th></tr></thead>
          <tbody>{rows_var}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SECCIÓN: EVOLUCIÓN MENSUAL Y FONDO
# ─────────────────────────────────────────────
st.markdown('<div class="section-title">Evolución Mensual</div><div class="section-underline"></div>', unsafe_allow_html=True)

col_bar, col_line = st.columns([45, 55])

with col_bar:
    df_fondo = df.groupby("Fondo")["Volumen_USD"].sum().reset_index().sort_values("Volumen_USD", ascending=True)

    fig_bar = go.Figure(go.Bar(
        x=df_fondo["Volumen_USD"],
        y=df_fondo["Fondo"],
        orientation="h",
        marker_color=GREEN,
        text=[fmt_usd(v) for v in df_fondo["Volumen_USD"]],
        textposition="auto"
    ))
    fig_bar.update_layout(
        title=dict(text="Volumen por Fondo", font=dict(size=12)),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(showticklabels=False, showgrid=False),
        margin=dict(l=10, r=20, t=35, b=10),
        height=320
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with col_line:
    df_line = df.groupby(["AñoMes","Asset_Category"])["Volumen_USD"].sum().reset_index().sort_values("AñoMes")

    fig_line = px.line(
        df_line, x="AñoMes", y="Volumen_USD",
        color="Asset_Category",
        color_discrete_map=ASSET_COLORS,
        markers=True
    )
    fig_line.update_traces(line=dict(width=2), marker=dict(size=4))
    fig_line.update_layout(
        title=dict(text="Evolución Mensual por Asset", font=dict(size=12)),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(showgrid=False, tickangle=-45),
        yaxis=dict(gridcolor="#EDEFED", tickformat="$,.0f"),
        legend=dict(orientation="h", y=1.1, x=0, font=dict(size=8), title_text=""),
        margin=dict(l=10, r=10, t=35, b=30),
        height=320
    )
    st.plotly_chart(fig_line, use_container_width=True)

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown(f"""
<div style="background:{DARK_BG}; margin: 2rem -1rem -1rem -1rem; padding: 16px 36px; display:flex; justify-content:space-between; align-items:center;">
  <div style="color:{GREEN}; font-size:.85rem; font-weight:600;">novus <span style="color:#9AADA9; font-weight:300;">asset management</span></div>
  <div style="color:#666; font-size:.7rem;">middle office · datos al {max_date.strftime('%d/%m/%Y')}</div>
</div>
""", unsafe_allow_html=True)
