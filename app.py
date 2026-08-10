# -*- coding: utf-8 -*-
"""
NOVUS ASSET MANAGEMENT — Dashboard de Contrapartes
Streamlit app que lee base_historica_acumulada.csv
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

# ─────────────────────────────────────────────
# CONFIG PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Novus AM | Dashboard Contrapartes",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# COLORES NOVUS
# ─────────────────────────────────────────────
NAVY   = "#1B365D"
STEEL  = "#2C4D75"
GOLD   = "#E8B84B"
LIGHT  = "#EBF1F5"
WHITE  = "#FFFFFF"
GRAY   = "#4A5568"

PALETTE_ASSETS = {
    "Fixed Income":          "#1B365D",
    "Renta Variable":        "#2C7BE5",
    "Licitaciones":          "#E8B84B",
    "Cauciones Colocadoras": "#27AE60",
    "Pases Colocadores":     "#8E44AD",
    "Futuros":               "#E74C3C",
    "CPD y Pagarés":         "#F39C12",
}

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
  /* fondo general */
  .stApp {{ background-color: #F4F6F9; }}

  /* header */
  .novus-header {{
      background: linear-gradient(135deg, {NAVY} 0%, {STEEL} 100%);
      padding: 20px 32px;
      border-radius: 12px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      gap: 16px;
  }}
  .novus-header h1 {{
      color: {GOLD};
      font-size: 1.6rem;
      font-weight: 800;
      margin: 0;
      font-family: 'Segoe UI', sans-serif;
  }}
  .novus-header p {{
      color: #CBD5E0;
      font-size: .85rem;
      margin: 2px 0 0;
  }}

  /* KPI cards */
  .kpi-card {{
      background: {WHITE};
      border-radius: 12px;
      padding: 18px 22px;
      box-shadow: 0 2px 12px rgba(0,0,0,.08);
      border-top: 4px solid {NAVY};
  }}
  .kpi-label {{
      font-size: .78rem;
      color: {GRAY};
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .5px;
  }}
  .kpi-value {{
      font-size: 1.55rem;
      font-weight: 800;
      color: {NAVY};
      margin-top: 4px;
  }}
  .kpi-sub {{
      font-size: .75rem;
      color: {GRAY};
      margin-top: 2px;
  }}

  /* sidebar */
  section[data-testid="stSidebar"] {{
      background: {NAVY} !important;
  }}
  section[data-testid="stSidebar"] * {{
      color: #E2E8F0 !important;
  }}
  section[data-testid="stSidebar"] .stMultiSelect > div > div {{
      background: {STEEL} !important;
      border-color: {STEEL} !important;
  }}

  /* hide streamlit branding */
  #MainMenu, footer {{ visibility: hidden; }}
  header[data-testid="stHeader"] {{ background: transparent; }}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CARGA DE DATOS
# ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Fecha"])
    df["Año_Mes"] = df["Fecha"].dt.to_period("M").astype(str)
    df["Año"]     = df["Fecha"].dt.year
    return df

# Busca el CSV en la misma carpeta que app.py
CSV_DEFAULT = os.path.join(os.path.dirname(__file__), "base_historica_acumulada.csv")

if os.path.exists(CSV_DEFAULT):
    df_raw = load_data(CSV_DEFAULT)
else:
    st.error("⚠️  No se encontró `base_historica_acumulada.csv` en la misma carpeta que `app.py`. "
             "Ejecutá tu script de Python primero para generarlo.")
    st.stop()

# ─────────────────────────────────────────────
# SIDEBAR — FILTROS
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style='text-align:center; padding: 12px 0 20px;'>
      <div style='font-size:1.3rem; font-weight:800; color:{GOLD};'>NOVUS AM</div>
      <div style='font-size:.75rem; color:#A0AEC0;'>Middle Office · Contrapartes</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🗓 Período")
    fecha_min = df_raw["Fecha"].min().date()
    fecha_max = df_raw["Fecha"].max().date()
    fecha_desde, fecha_hasta = st.date_input(
        "Rango de fechas",
        value=(fecha_min, fecha_max),
        min_value=fecha_min,
        max_value=fecha_max,
        label_visibility="collapsed",
    )

    st.markdown("### 🏦 Agente")
    agentes_opts = sorted(df_raw["Agente"].unique())
    agentes_sel  = st.multiselect("Agentes", agentes_opts, placeholder="Todos", label_visibility="collapsed")

    st.markdown("### 📂 Asset")
    assets_opts = sorted(df_raw["Asset_Category"].unique())
    assets_sel  = st.multiselect("Assets", assets_opts, placeholder="Todos", label_visibility="collapsed")

    st.markdown("### 💼 Fondo")
    fondos_opts = sorted(df_raw["Fondo"].unique())
    fondos_sel  = st.multiselect("Fondos", fondos_opts, placeholder="Todos", label_visibility="collapsed")

    st.markdown("---")
    top_n = st.slider("Top N agentes en gráficos", 5, 20, 10)

# ─────────────────────────────────────────────
# FILTRADO
# ─────────────────────────────────────────────
df = df_raw.copy()
df = df[(df["Fecha"].dt.date >= fecha_desde) & (df["Fecha"].dt.date <= fecha_hasta)]
if agentes_sel: df = df[df["Agente"].isin(agentes_sel)]
if assets_sel:  df = df[df["Asset_Category"].isin(assets_sel)]
if fondos_sel:  df = df[df["Fondo"].isin(fondos_sel)]

if df.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown(f"""
<div class="novus-header">
  <div>
    <h1>📊 Control & Flujo de Contrapartes</h1>
    <p>NOVUS ASSET MANAGEMENT — Middle Office &nbsp;·&nbsp;
       {fecha_desde.strftime('%d/%m/%Y')} → {fecha_hasta.strftime('%d/%m/%Y')}</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# KPIs
# ─────────────────────────────────────────────
total_vol   = df["Volumen_USD"].sum()
total_gas   = df["Gastos_USD"].sum()
n_ops       = len(df)
cost_bps    = (total_gas / total_vol * 10_000) if total_vol > 0 else 0
top_ag      = df.groupby("Agente")["Volumen_USD"].sum().idxmax()
top_ag_pct  = df.groupby("Agente")["Volumen_USD"].sum().max() / total_vol * 100
n_agentes   = df["Agente"].nunique()

def fmt_usd(v):
    if v >= 1e9:  return f"USD {v/1e9:,.2f}B"
    if v >= 1e6:  return f"USD {v/1e6:,.1f}M"
    return f"USD {v:,.0f}"

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-label">Volumen Total</div>
      <div class="kpi-value">{fmt_usd(total_vol)}</div>
      <div class="kpi-sub">{n_ops:,} operaciones</div>
    </div>""", unsafe_allow_html=True)

with k2:
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-label">Top Agente</div>
      <div class="kpi-value" style="font-size:1.1rem;">{top_ag}</div>
      <div class="kpi-sub">{top_ag_pct:.1f}% del volumen total</div>
    </div>""", unsafe_allow_html=True)

with k3:
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-label">Gastos / Comisiones</div>
      <div class="kpi-value">{fmt_usd(total_gas)}</div>
      <div class="kpi-sub">Cost/Fee: {cost_bps:.1f} bps</div>
    </div>""", unsafe_allow_html=True)

with k4:
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-label">Contrapartes Activas</div>
      <div class="kpi-value">{n_agentes}</div>
      <div class="kpi-sub">de {df['Fondo'].nunique()} fondos operados</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# FILA 1: Top Agentes  |  Por Asset Category
# ─────────────────────────────────────────────
col_left, col_right = st.columns([3, 2])

with col_left:
    df_ag = (df.groupby("Agente")["Volumen_USD"]
               .sum()
               .sort_values(ascending=True)
               .tail(top_n)
               .reset_index())
    df_ag["share"] = df_ag["Volumen_USD"] / total_vol * 100

    fig_ag = go.Figure(go.Bar(
        x=df_ag["Volumen_USD"],
        y=df_ag["Agente"],
        orientation="h",
        marker_color=NAVY,
        text=[f"  {fmt_usd(v)}  ({s:.1f}%)" for v, s in zip(df_ag["Volumen_USD"], df_ag["share"])],
        textposition="outside",
        textfont=dict(size=11, color=GRAY),
    ))
    fig_ag.update_layout(
        title=dict(text=f"Top {top_n} Agentes por Volumen USD", font=dict(color=NAVY, size=14)),
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=11)),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=10, r=120, t=40, b=10),
        height=420,
    )
    st.plotly_chart(fig_ag, use_container_width=True)

with col_right:
    df_asset = df.groupby("Asset_Category")["Volumen_USD"].sum().reset_index()
    colors   = [PALETTE_ASSETS.get(a, "#888") for a in df_asset["Asset_Category"]]

    fig_pie = go.Figure(go.Pie(
        labels=df_asset["Asset_Category"],
        values=df_asset["Volumen_USD"],
        hole=0.52,
        marker=dict(colors=colors, line=dict(color="white", width=2)),
        textinfo="label+percent",
        textfont=dict(size=11),
        insidetextorientation="radial",
    ))
    fig_pie.update_layout(
        title=dict(text="Volumen por Asset Category", font=dict(color=NAVY, size=14)),
        showlegend=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=0, r=0, t=40, b=0),
        height=420,
    )
    st.plotly_chart(fig_pie, use_container_width=True)

# ─────────────────────────────────────────────
# FILA 2: Evolución Mensual
# ─────────────────────────────────────────────
st.markdown(f"### 📈 Evolución Mensual")

tab1, tab2 = st.tabs(["Por Asset Category", "Top Agentes"])

with tab1:
    df_monthly_asset = (df.groupby(["Año_Mes", "Asset_Category"])["Volumen_USD"]
                          .sum()
                          .reset_index()
                          .sort_values("Año_Mes"))

    fig_month = px.bar(
        df_monthly_asset,
        x="Año_Mes", y="Volumen_USD",
        color="Asset_Category",
        color_discrete_map=PALETTE_ASSETS,
        barmode="stack",
        labels={"Volumen_USD": "Volumen USD", "Año_Mes": "Mes", "Asset_Category": "Asset"},
    )
    fig_month.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(title="", tickangle=-45),
        yaxis=dict(title="Volumen USD", tickformat="$,.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=20, b=60),
        height=380,
    )
    st.plotly_chart(fig_month, use_container_width=True)

with tab2:
    top_agents_list = (df.groupby("Agente")["Volumen_USD"]
                         .sum()
                         .sort_values(ascending=False)
                         .head(top_n)
                         .index.tolist())
    df_top_monthly = (df[df["Agente"].isin(top_agents_list)]
                        .groupby(["Año_Mes", "Agente"])["Volumen_USD"]
                        .sum()
                        .reset_index()
                        .sort_values("Año_Mes"))

    fig_agents_month = px.line(
        df_top_monthly,
        x="Año_Mes", y="Volumen_USD", color="Agente",
        markers=True,
        labels={"Volumen_USD": "Volumen USD", "Año_Mes": "Mes"},
    )
    fig_agents_month.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(title="", tickangle=-45),
        yaxis=dict(title="Volumen USD", tickformat="$,.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=20, b=60),
        height=380,
    )
    st.plotly_chart(fig_agents_month, use_container_width=True)

# ─────────────────────────────────────────────
# FILA 3: Tabla Resumen por Agente
# ─────────────────────────────────────────────
st.markdown("### 📋 Resumen por Agente")

df_table = df.groupby("Agente").agg(
    Volumen_Total=("Volumen_USD", "sum"),
    Gastos_USD=("Gastos_USD", "sum"),
    Operaciones=("Volumen_USD", "count"),
).reset_index()

# Períodos
max_date  = df["Fecha"].max()
ytd_start = pd.Timestamp(year=max_date.year, month=1, day=1)
d30 = max_date - pd.Timedelta(days=30)

vol_30d = df[df["Fecha"] >= d30].groupby("Agente")["Volumen_USD"].sum()
vol_ytd = df[df["Fecha"] >= ytd_start].groupby("Agente")["Volumen_USD"].sum()

df_table["Vol 30D USD"]   = df_table["Agente"].map(vol_30d).fillna(0)
df_table["Vol YTD USD"]   = df_table["Agente"].map(vol_ytd).fillna(0)
df_table["Share %"]       = df_table["Volumen_Total"] / total_vol * 100
df_table["Cost/Fee (bps)"]= np.where(
    df_table["Volumen_Total"] > 0,
    df_table["Gastos_USD"] / df_table["Volumen_Total"] * 10_000, 0
)
df_table = df_table.sort_values("Volumen_Total", ascending=False).reset_index(drop=True)

# Agrega fila TOTAL
totals = {
    "Agente": "TOTAL CONSOLIDADO",
    "Volumen_Total":  df_table["Volumen_Total"].sum(),
    "Gastos_USD":     df_table["Gastos_USD"].sum(),
    "Operaciones":    df_table["Operaciones"].sum(),
    "Vol 30D USD":    df_table["Vol 30D USD"].sum(),
    "Vol YTD USD":    df_table["Vol YTD USD"].sum(),
    "Share %":        df_table["Share %"].sum(),
    "Cost/Fee (bps)": cost_bps,
}
df_display = pd.concat([df_table, pd.DataFrame([totals])], ignore_index=True)

def style_table(df):
    is_total = df.index == len(df) - 1
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    styles.loc[is_total, :] = f"background-color: {NAVY}; color: white; font-weight: bold;"
    return styles

st.dataframe(
    df_display.style
        .apply(style_table, axis=None)
        .format({
            "Volumen_Total":   "${:,.0f}",
            "Gastos_USD":      "${:,.0f}",
            "Vol 30D USD":     "${:,.0f}",
            "Vol YTD USD":     "${:,.0f}",
            "Share %":         "{:.2f}%",
            "Cost/Fee (bps)":  "{:.1f}",
        }),
    use_container_width=True,
    height=500,
)

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown(f"""
<div style='text-align:center; color:#A0AEC0; font-size:.75rem; margin-top:40px; padding-bottom:20px;'>
  NOVUS ASSET MANAGEMENT · Middle Office · Dashboard generado con Python + Streamlit<br>
  Datos actualizados al {max_date.strftime('%d/%m/%Y')}
</div>
""", unsafe_allow_html=True)
