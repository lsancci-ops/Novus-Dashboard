# -*- coding: utf-8 -*-
"""
NOVUS ASSET MANAGEMENT — Dashboard de Contrapartes
Réplica del reporte Power BI "Agentes"
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Novus AM | Agentes",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# COLORES (extraídos del tema PBI)
# ─────────────────────────────────────────────
NAVY    = "#12239E"
BLUE    = "#118DFF"
ORANGE  = "#E66C37"
PURPLE  = "#6B007B"
PINK    = "#E044A7"
VIOLET  = "#744EC2"
GOLD    = "#D9B300"
RED     = "#D64550"
BG      = "#F4F6FB"
CARD_BG = "#FFFFFF"

ASSET_COLORS = {
    "Fixed Income":          NAVY,
    "Renta Variable":        BLUE,
    "Licitaciones":          GOLD,
    "Cauciones Colocadoras": "#27AE60",
    "Pases Colocadores":     VIOLET,
    "Futuros":               RED,
    "CPD y Pagarés":         ORANGE,
}

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
  .stApp {{ background-color: {BG}; }}

  /* header */
  .pbi-header {{
      background: linear-gradient(90deg, {NAVY} 0%, #1B365D 100%);
      padding: 14px 28px;
      border-radius: 8px;
      margin-bottom: 18px;
      display: flex; align-items: center; gap: 14px;
  }}
  .pbi-header h1 {{
      color: #FFFFFF; font-size: 1.25rem; font-weight: 700;
      margin: 0; font-family: 'Segoe UI', sans-serif; letter-spacing: .3px;
  }}
  .pbi-header p {{ color: #A0AEC0; font-size: .8rem; margin: 0; }}

  /* KPI cards — estilo Power BI */
  .kpi-wrap {{
      background: {CARD_BG};
      border-radius: 6px;
      padding: 16px 18px 14px;
      box-shadow: 0 1px 6px rgba(0,0,0,.08);
      border-left: 4px solid {BLUE};
      height: 100%;
  }}
  .kpi-title {{
      font-size: .7rem; color: #718096;
      text-transform: uppercase; letter-spacing: .6px; font-weight: 600;
  }}
  .kpi-main {{
      font-size: 1.6rem; font-weight: 800; color: {NAVY};
      line-height: 1.2; margin: 4px 0 2px;
  }}
  .kpi-sub {{
      font-size: .72rem; color: #A0AEC0;
  }}

  /* Tabla Var% */
  .var-table {{ width:100%; border-collapse: collapse; font-size: .82rem; }}
  .var-table th {{
      background: {NAVY}; color: white;
      padding: 7px 10px; text-align: center; font-weight: 600;
  }}
  .var-table td {{ padding: 6px 10px; border-bottom: 1px solid #EDF2F7; }}
  .var-table tr:nth-child(even) td {{ background: #F7FAFC; }}
  .var-table td:first-child {{ font-weight: 600; color: {NAVY}; text-align: left; }}
  .var-table td:not(:first-child) {{ text-align: right; }}
  .pos {{ color: #27AE60; font-weight: 700; }}
  .neg {{ color: {RED}; font-weight: 700; }}
  .neu {{ color: #718096; }}

  /* slicer label */
  .slicer-label {{
      font-size: .78rem; font-weight: 700; color: {NAVY};
      text-transform: uppercase; letter-spacing: .5px;
      margin-bottom: 6px;
  }}

  #MainMenu, footer {{ visibility: hidden; }}
  header[data-testid="stHeader"] {{ background: transparent; }}
  .block-container {{ padding-top: 1rem !important; }}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# DATOS
# ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data(path):
    df = pd.read_csv(path, parse_dates=["Fecha"])
    df["AñoMes"] = df["Fecha"].dt.to_period("M").astype(str)
    return df

CSV_PATH = os.path.join(os.path.dirname(__file__), "base_historica_acumulada.csv")
if not os.path.exists(CSV_PATH):
    st.error("No se encontró `base_historica_acumulada.csv`. Ejecutá el script de Python primero.")
    st.stop()

df_raw = load_data(CSV_PATH)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
max_date = df_raw["Fecha"].max()
st.markdown(f"""
<div class="pbi-header">
  <div>📊</div>
  <div>
    <h1>NOVUS ASSET MANAGEMENT — Control & Flujo de Contrapartes</h1>
    <p>Middle Office · Agentes · Datos al {max_date.strftime('%d/%m/%Y')}</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SLICER  (Asset Category — en la parte superior para simplicidad)
# ─────────────────────────────────────────────
col_slicer, col_dates = st.columns([3, 2])
with col_slicer:
    st.markdown('<div class="slicer-label">🔽 Filtrar por Asset Category</div>', unsafe_allow_html=True)
    assets_all = sorted(df_raw["Asset_Category"].unique())
    assets_sel = st.multiselect(
        "asset", assets_all,
        default=assets_all,
        label_visibility="collapsed"
    )
with col_dates:
    st.markdown('<div class="slicer-label">🗓 Período</div>', unsafe_allow_html=True)
    fmin, fmax = df_raw["Fecha"].min().date(), df_raw["Fecha"].max().date()
    fecha_rango = st.date_input("rango", value=(fmin, fmax),
                                min_value=fmin, max_value=fmax,
                                label_visibility="collapsed")

st.markdown("---")

# Aplicar filtros
df = df_raw.copy()
if len(fecha_rango) == 2:
    df = df[(df["Fecha"].dt.date >= fecha_rango[0]) & (df["Fecha"].dt.date <= fecha_rango[1])]
if assets_sel:
    df = df[df["Asset_Category"].isin(assets_sel)]

if df.empty:
    st.warning("Sin datos para los filtros seleccionados.")
    st.stop()

# ─────────────────────────────────────────────
# MÉTRICAS CALCULADAS
# ─────────────────────────────────────────────
max_d   = df["Fecha"].max()
ytd_s   = pd.Timestamp(year=max_d.year, month=1, day=1)
d30     = max_d - pd.Timedelta(days=30)
d60     = max_d - pd.Timedelta(days=60)
d365    = max_d - pd.Timedelta(days=365)
prev30s = d30 - pd.Timedelta(days=30)

vol_ytd     = df[df["Fecha"] >= ytd_s]["Volumen_USD"].sum()
vol_30d     = df[df["Fecha"] >= d30]["Volumen_USD"].sum()
vol_total   = df["Volumen_USD"].sum()

# Asset dominante 30D
asset_30d = df[df["Fecha"] >= d30].groupby("Asset_Category")["Volumen_USD"].sum()
asset_dom = asset_30d.idxmax() if not asset_30d.empty else "—"
asset_dom_pct = asset_30d.max() / asset_30d.sum() * 100 if not asset_30d.empty else 0

# Agente líder (por volumen total)
ag_vol = df.groupby("Agente")["Volumen_USD"].sum()
agente_lider = ag_vol.idxmax() if not ag_vol.empty else "—"
agente_lider_pct = ag_vol.max() / vol_total * 100 if vol_total > 0 else 0

# Nivel concentración HHI (0-10000; <1500=baja, 1500-2500=media, >2500=alta)
shares = (ag_vol / vol_total * 100) ** 2
hhi = shares.sum()
if hhi < 1500:   concentracion = f"Baja  ({hhi:,.0f})"
elif hhi < 2500: concentracion = f"Media ({hhi:,.0f})"
else:            concentracion = f"Alta  ({hhi:,.0f})"

# Var% por asset y período
def var_pct(df_all, asset, d_ini, d_fin, d_prev_ini, d_prev_fin):
    curr = df_all[(df_all["Asset_Category"]==asset) & (df_all["Fecha"]>=d_ini) & (df_all["Fecha"]<=d_fin)]["Volumen_USD"].sum()
    prev = df_all[(df_all["Asset_Category"]==asset) & (df_all["Fecha"]>=d_prev_ini) & (df_all["Fecha"]<=d_prev_fin)]["Volumen_USD"].sum()
    if prev == 0: return None
    return (curr - prev) / prev * 100

rows_var = []
for asset in sorted(df["Asset_Category"].unique()):
    v30  = var_pct(df, asset, d30,  max_d, prev30s, d30)
    v60  = var_pct(df, asset, d60,  max_d, d60 - pd.Timedelta(days=60), d60)
    v365 = var_pct(df, asset, d365, max_d, d365 - pd.Timedelta(days=365), d365)
    # YTD vs año anterior
    ytd_prev_s = pd.Timestamp(year=max_d.year-1, month=1, day=1)
    ytd_prev_e = pd.Timestamp(year=max_d.year-1, month=max_d.month, day=max_d.day)
    vYTD = var_pct(df, asset, ytd_s, max_d, ytd_prev_s, ytd_prev_e)
    rows_var.append({"Asset": asset, "30D": v30, "60D": v60, "365D": v365, "YTD": vYTD})

df_var = pd.DataFrame(rows_var)

def fmt_usd(v):
    if v >= 1e9:  return f"USD {v/1e9:,.2f}B"
    if v >= 1e6:  return f"USD {v/1e6:,.1f}M"
    return f"USD {v:,.0f}"

def fmt_pct(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '<span class="neu">N/D</span>'
    cls = "pos" if v >= 0 else "neg"
    sign = "+" if v >= 0 else ""
    return f'<span class="{cls}">{sign}{v:.1f}%</span>'

# ─────────────────────────────────────────────
# FILA 1: KPI CARDS (igual al PBI)
# ─────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(f"""<div class="kpi-wrap" style="border-left-color:{BLUE};">
      <div class="kpi-title">Volumen YTD USD</div>
      <div class="kpi-main">{fmt_usd(vol_ytd)}</div>
      <div class="kpi-sub">Año {max_d.year} hasta hoy</div>
    </div>""", unsafe_allow_html=True)

with c2:
    st.markdown(f"""<div class="kpi-wrap" style="border-left-color:{GOLD};">
      <div class="kpi-title">Asset Dominante 30D</div>
      <div class="kpi-main" style="font-size:1.05rem;">{asset_dom}</div>
      <div class="kpi-sub">{asset_dom_pct:.1f}% del vol. últimos 30 días</div>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""<div class="kpi-wrap" style="border-left-color:{ORANGE};">
      <div class="kpi-title">Agente Líder</div>
      <div class="kpi-main" style="font-size:1.05rem;">{agente_lider}</div>
      <div class="kpi-sub">{agente_lider_pct:.1f}% del volumen total</div>
    </div>""", unsafe_allow_html=True)

with c4:
    color_hhi = "#27AE60" if hhi < 1500 else (GOLD if hhi < 2500 else RED)
    st.markdown(f"""<div class="kpi-wrap" style="border-left-color:{color_hhi};">
      <div class="kpi-title">Equidad por Contraparte</div>
      <div class="kpi-main" style="font-size:1.1rem; color:{color_hhi};">{concentracion}</div>
      <div class="kpi-sub">Índice HHI · &lt;1500 baja · &gt;2500 alta</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# FILA 2: Torta Agente | Tabla Var%
# ─────────────────────────────────────────────
col_izq, col_der = st.columns([55, 45])

with col_izq:
    # PIE CHART — Volumen por Agente (igual al PBI)
    df_pie = df.groupby("Agente")["Volumen_USD"].sum().reset_index()
    df_pie = df_pie.sort_values("Volumen_USD", ascending=False)
    # Agrupar agentes pequeños en "Otros" (menos del 2%)
    umbral = vol_total * 0.02
    df_pie["Label"] = df_pie.apply(
        lambda r: r["Agente"] if r["Volumen_USD"] >= umbral else "Otros", axis=1
    )
    df_pie_grouped = df_pie.groupby("Label")["Volumen_USD"].sum().reset_index()

    fig_pie = go.Figure(go.Pie(
        labels=df_pie_grouped["Label"],
        values=df_pie_grouped["Volumen_USD"],
        hole=0,
        textinfo="label+percent",
        textfont=dict(size=11),
        marker=dict(line=dict(color="white", width=1.5)),
        insidetextorientation="radial",
    ))
    fig_pie.update_layout(
        title=dict(text="Volumen USD por Agente", font=dict(color=NAVY, size=13, family="Segoe UI")),
        showlegend=True,
        legend=dict(font=dict(size=10), orientation="v", x=1, y=0.5),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=10, t=36, b=10),
        height=320,
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_der:
    # TABLA VAR% — réplica de la pivotTable del PBI
    st.markdown(f"**Variación por Asset Category**", )

    html_rows = ""
    for _, row in df_var.iterrows():
        html_rows += f"""<tr>
          <td>{row['Asset']}</td>
          <td>{fmt_pct(row['30D'])}</td>
          <td>{fmt_pct(row['60D'])}</td>
          <td>{fmt_pct(row['365D'])}</td>
          <td>{fmt_pct(row['YTD'])}</td>
        </tr>"""

    st.markdown(f"""
    <table class="var-table">
      <thead><tr>
        <th>Asset Category</th>
        <th>Var % 30D</th>
        <th>Var % 60D</th>
        <th>Var % 365D</th>
        <th>Var % YTD</th>
      </tr></thead>
      <tbody>{html_rows}</tbody>
    </table>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# FILA 3: Barras por Fondo | Línea mensual por Asset
# ─────────────────────────────────────────────
col_b1, col_b2 = st.columns([50, 50])

with col_b1:
    # BAR CHART — Volumen por Fondo
    df_fondo = df.groupby("Fondo")["Volumen_USD"].sum().reset_index()
    df_fondo = df_fondo.sort_values("Volumen_USD", ascending=True)

    fig_bar = go.Figure(go.Bar(
        x=df_fondo["Volumen_USD"],
        y=df_fondo["Fondo"],
        orientation="h",
        marker_color=BLUE,
        text=[fmt_usd(v) for v in df_fondo["Volumen_USD"]],
        textposition="outside",
        textfont=dict(size=10, color="#4A5568"),
    ))
    fig_bar.update_layout(
        title=dict(text="Volumen USD por Fondo", font=dict(color=NAVY, size=13, family="Segoe UI")),
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=10)),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=90, t=36, b=10),
        height=350,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with col_b2:
    # LINE CHART — Evolución mensual por Asset Category
    df_line = (df.groupby(["AñoMes", "Asset_Category"])["Volumen_USD"]
                 .sum().reset_index().sort_values("AñoMes"))

    fig_line = px.line(
        df_line,
        x="AñoMes", y="Volumen_USD",
        color="Asset_Category",
        color_discrete_map=ASSET_COLORS,
        markers=True,
        labels={"Volumen_USD": "Volumen USD", "AñoMes": "", "Asset_Category": "Asset"},
    )
    fig_line.update_traces(line=dict(width=2), marker=dict(size=5))
    fig_line.update_layout(
        title=dict(text="Evolución Mensual por Asset Category", font=dict(color=NAVY, size=13, family="Segoe UI")),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(tickangle=-45, tickfont=dict(size=9), showgrid=False),
        yaxis=dict(tickformat="$,.0f", gridcolor="#EDF2F7"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
        margin=dict(l=10, r=10, t=50, b=50),
        height=350,
    )
    st.plotly_chart(fig_line, use_container_width=True)

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown(f"""
<div style='text-align:center; color:#A0AEC0; font-size:.72rem; margin-top:24px; padding-bottom:16px;'>
  NOVUS ASSET MANAGEMENT · Middle Office · Dashboard replicado desde Power BI ·
  Datos al {max_date.strftime('%d/%m/%Y')}
</div>
""", unsafe_allow_html=True)
