# -*- coding: utf-8 -*-
"""
NOVUS ASSET MANAGEMENT — Dashboard de Contrapartes / Middle Office
=================================================================
v3 — Correcciones de cálculo + análisis de costos (bps) + ranking de agentes

Cambios vs v2:
  [FIX] Var% ya no se rompe al filtrar por Año/Mes: las ventanas móviles
        (30/60/365d) se calculan siempre sobre la historia completa.
  [FIX] Ventanas sin historia suficiente muestran "n/d" en lugar de un % falso
        (365d necesita 730 días de historia y hoy hay ~580).
  [FIX] HHI y concentración se miden sobre el universo de agentes del scope,
        no sobre el subconjunto elegido en el filtro de agente.
  [FIX] fmt_usd soporta negativos, cero y NaN.
  [FIX] El mes en curso incompleto se marca explícitamente en la serie mensual.
  [NEW] Costos de ejecución en bps por asset category y por agente.
  [NEW] Ranking de agentes con share, gastos, bps y variación 30d + export.
  [NEW] Apertura por moneda de liquidación (ARS / USDMEP / USDC).
  [NEW] Barra de concentración Top1 / Top2-3 / Top4-5 / Resto.
  [NEW] Presets de período + filtro por agente.
  [NEW] Aviso de calidad de datos donde no hay gastos cargados.
"""

import os
import io
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="novus | agentes",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ═══════════════════════════════════════════════════════════════
# PALETA CORPORATIVA NOVUS
# ═══════════════════════════════════════════════════════════════
DARK_BG   = "#1A1C1A"
GREEN     = "#5DBB63"
GREEN_DIM = "#2D6A4F"
LIGHT_BG  = "#F0F2F0"
WHITE     = "#FFFFFF"
GRAY_TEXT = "#666666"
DARK_TEXT = "#1A1C1A"
BORDER    = "#E2E8E2"
RED       = "#E05555"
AMBER     = "#E8A020"

ASSET_COLORS = {
    "Fixed Income":          "#1B4332",
    "Renta Variable":        "#5DBB63",
    "Licitaciones":          "#D97706",
    "Cauciones Colocadoras": "#0284C7",
    "Pases Colocadores":     "#10B981",
    "Futuros":               "#8B5CF6",
    "CPD y Pagarés":         "#06B6D4",
}

AGENT_PALETTE = [
    "#1B4332", "#5DBB63", "#2D6A4F", "#95D5A0", "#40916C",
    "#74C69D", "#0F2E20", "#B7E4C7", "#527A5E", "#D3E8D7",
]
OTROS_COLOR   = "#BFC7C1"
MONEDA_COLORS = {"ARS": "#1B4332", "USDMEP": "#5DBB63", "USDC": "#95D5A0"}

FONT_FAMILY = "'DM Sans', Arial, sans-serif"
PLOTLY_CFG  = {"displayModeBar": False, "responsive": True}
BASE_LAYOUT = dict(
    font=dict(family=FONT_FAMILY, color=DARK_TEXT),
    paper_bgcolor="white",
    plot_bgcolor="white",
)


def chart(fig, key=None):
    """st.plotly_chart compatible con Streamlit viejo y nuevo."""
    try:
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CFG, key=key)
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG, key=key)


def df_show(data, **kw):
    """st.dataframe tolerante a versiones sin column_config."""
    try:
        st.dataframe(data, **kw)
    except Exception:
        st.dataframe(data, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap');

  html, body, .stApp {{
      font-family: {FONT_FAMILY} !important;
      background-color: {LIGHT_BG} !important;
  }}

  /* ── HERO ── */
  .novus-hero {{
      background: linear-gradient(135deg, {DARK_BG} 0%, #162416 100%);
      padding: 26px 36px 24px;
      margin: -1rem -1rem 1.1rem -1rem;
      border-radius: 0 0 12px 12px;
  }}
  .novus-eyebrow {{
      font-size: .68rem; font-weight: 700; letter-spacing: 2px;
      color: {GREEN}; text-transform: uppercase; margin-bottom: 6px;
  }}
  .novus-hero h1 {{ font-size: 1.8rem; font-weight: 300; color: {WHITE}; margin: 0 0 4px; }}
  .novus-hero h1 span {{ color: {GREEN}; font-weight: 700; }}
  .novus-hero p {{ color: #9AADA9; font-size: .85rem; margin: 4px 0 12px; }}
  .novus-badge {{
      display: inline-block; border: 1px solid rgba(93,187,99,.4);
      border-radius: 20px; padding: 3px 12px; font-size: .75rem;
      color: {GREEN}; font-weight: 500; margin-right: 6px;
  }}
  .novus-badge.warn {{ border-color: rgba(232,160,32,.5); color: {AMBER}; }}

  /* ── FILTROS ── */
  div[data-testid="stExpander"] {{
      background-color: {WHITE} !important;
      border: 1px solid {BORDER} !important;
      border-radius: 10px !important;
      box-shadow: 0 2px 8px rgba(0,0,0,.03) !important;
      margin-bottom: 1rem !important;
      overflow: hidden;
  }}
  div[data-testid="stExpander"] summary {{
      padding: 12px 20px !important; font-weight: 600 !important;
      color: {DARK_TEXT} !important; font-size: .88rem !important;
  }}
  div[data-testid="stExpander"] summary:hover {{ color: {GREEN} !important; }}

  .stMultiSelect label, .stSelectbox label, .stRadio label, .stDateInput label {{
      font-size: .68rem !important; font-weight: 700 !important;
      letter-spacing: 1px !important; text-transform: uppercase !important;
      color: {GRAY_TEXT} !important; margin-bottom: 4px !important;
  }}
  .stMultiSelect [data-baseweb="select"] > div,
  .stSelectbox   [data-baseweb="select"] > div,
  .stDateInput   [data-baseweb="input"] {{
      background-color: #FAFAFA !important;
      border: 1px solid {BORDER} !important;
      border-radius: 8px !important; min-height: 40px !important;
  }}
  .stMultiSelect [data-baseweb="select"] > div:focus-within,
  .stSelectbox   [data-baseweb="select"] > div:focus-within {{
      border-color: {GREEN} !important;
      box-shadow: 0 0 0 2px rgba(93,187,99,.15) !important;
  }}
  .stMultiSelect [data-baseweb="tag"] {{
      background-color: {DARK_BG} !important;
      border: 1px solid rgba(93,187,99,.4) !important;
      border-radius: 6px !important; padding: 2px 8px !important;
  }}
  .stMultiSelect [data-baseweb="tag"] span {{
      color: {GREEN} !important; font-size: .75rem !important; font-weight: 600 !important;
  }}
  .stMultiSelect [data-baseweb="tag"] svg {{ fill: {GREEN} !important; }}

  /* Radio como pills */
  div[role="radiogroup"] {{ gap: 6px !important; flex-wrap: wrap; }}
  div[role="radiogroup"] label {{
      background: #FAFAFA; border: 1px solid {BORDER}; border-radius: 20px;
      padding: 5px 14px !important; margin: 0 !important;
      text-transform: none !important; letter-spacing: 0 !important;
      font-size: .78rem !important; font-weight: 500 !important;
      color: {DARK_TEXT} !important; cursor: pointer; transition: all .15s;
  }}
  div[role="radiogroup"] label:hover {{ border-color: {GREEN}; }}
  div[role="radiogroup"] label:has(input:checked) {{
      background: {DARK_BG} !important; border-color: {GREEN} !important;
  }}
  div[role="radiogroup"] label:has(input:checked) div,
  div[role="radiogroup"] label:has(input:checked) p {{ color: {GREEN} !important; }}
  div[role="radiogroup"] label > div:first-child {{ display: none !important; }}

  /* ── KPI CARDS ── */
  .kpi-card {{
      background: {WHITE}; border-radius: 10px; padding: 15px 18px;
      border: 1px solid {BORDER}; box-shadow: 0 1px 4px rgba(0,0,0,.02);
      height: 100%;
  }}
  .kpi-card.accent {{ border-left: 3px solid {GREEN}; }}
  .kpi-label {{
      font-size: .63rem; font-weight: 700; letter-spacing: 1.2px;
      color: {GRAY_TEXT}; text-transform: uppercase; margin-bottom: 6px;
  }}
  .kpi-value {{ font-size: 1.5rem; font-weight: 700; color: {GREEN}; line-height: 1.15; }}
  .kpi-value.sm {{ font-size: 1.22rem; }}
  .kpi-name {{
      font-size: .9rem; font-weight: 600; color: {DARK_TEXT};
      line-height: 1.2; margin-bottom: 2px;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .kpi-delta {{ font-size: .72rem; font-weight: 600; margin-top: 4px; }}
  .kpi-sub   {{ font-size: .7rem; color: {GRAY_TEXT}; margin-top: 4px; }}

  /* ── SECCIONES ── */
  .section-title {{ font-size: 1.12rem; font-weight: 700; color: {DARK_TEXT}; margin-top: 10px; }}
  .section-underline {{ width: 28px; height: 3px; background: {GREEN}; margin-bottom: 14px; border-radius: 2px; }}
  .chart-label {{
      font-size: .63rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 1px; color: {GRAY_TEXT}; margin-bottom: 8px;
  }}

  /* ── TABLA VAR% ── */
  .var-table {{ width: 100%; border-collapse: collapse; font-size: .78rem; }}
  .var-table th {{
      font-size: .61rem; font-weight: 700; letter-spacing: .8px; text-transform: uppercase;
      color: {GRAY_TEXT}; padding: 7px 5px; border-bottom: 2px solid {BORDER}; text-align: right;
  }}
  .var-table th:first-child {{ text-align: left; }}
  .var-table td {{ padding: 7px 5px; border-bottom: 1px solid {BORDER}; text-align: right; color: {DARK_TEXT}; }}
  .var-table td:first-child {{ text-align: left; font-weight: 500; }}
  .var-table tbody tr:hover {{ background: #FAFBFA; }}
  .pos {{ color: {GREEN_DIM}; font-weight: 700; }}
  .neg {{ color: {RED}; font-weight: 700; }}
  .nd  {{ color: #AAB2AC; font-weight: 400; cursor: help; }}
  .swatch {{
      display: inline-block; width: 8px; height: 8px; border-radius: 2px;
      margin-right: 7px; vertical-align: middle;
  }}

  /* ── TABS ── */
  .stTabs [data-baseweb="tab-list"] {{ gap: 4px; background: transparent; border-bottom: 1px solid {BORDER}; }}
  .stTabs [data-baseweb="tab"] {{
      background: transparent; border-radius: 8px 8px 0 0;
      padding: 8px 16px; font-size: .82rem; font-weight: 600; color: {GRAY_TEXT};
  }}
  .stTabs [aria-selected="true"] {{ background: {WHITE} !important; color: {DARK_TEXT} !important; }}
  /* Subrayado de la tab activa: Streamlit lo pinta rojo por defecto.
     El fix de fondo está en .streamlit/config.toml (primaryColor);
     esto cubre las versiones que usan estos selectores internos. */
  .stTabs [data-baseweb="tab-highlight"],
  .stTabs [data-baseweb="tab-border"],
  .react-aria-SelectionIndicator,
  div[role="tablist"] .react-aria-SelectionIndicator {{
      background-color: {GREEN} !important;
  }}

  /* ── BOTONES ── */
  .stDownloadButton button, .stButton button {{
      background: {DARK_BG} !important; color: {GREEN} !important;
      border: 1px solid rgba(93,187,99,.4) !important; border-radius: 8px !important;
      font-size: .78rem !important; font-weight: 600 !important; padding: 6px 16px !important;
  }}
  .stDownloadButton button:hover, .stButton button:hover {{
      background: {GREEN_DIM} !important; color: {WHITE} !important; border-color: {GREEN} !important;
  }}

  div[data-testid="stDataFrame"] {{
      border: 1px solid {BORDER} !important; border-radius: 10px !important; overflow: hidden;
  }}

  /* ── NOTAS ── */
  .note {{
      background: {WHITE}; border-left: 3px solid {BORDER}; border-radius: 6px;
      padding: 9px 14px; font-size: .72rem; color: {GRAY_TEXT}; line-height: 1.55;
  }}
  .note.warn {{ border-left-color: {AMBER}; background: #FFFCF5; }}
  .note b {{ color: {DARK_TEXT}; }}

  #MainMenu, footer, header {{ visibility: hidden; height: 0; }}
  .block-container {{ padding-top: 0 !important; padding-bottom: 1.5rem !important; }}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# CARGA DE DATOS
# ═══════════════════════════════════════════════════════════════
MESES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
         7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
MESES_ORD = list(MESES.values())


@st.cache_data(ttl=600, show_spinner="Cargando base histórica…")
def load_data(path, _mtime):
    """_mtime en la firma invalida el cache cuando se sube un CSV nuevo."""
    df = pd.read_csv(path, parse_dates=["Fecha"])
    for c in ("Agente", "Asset_Category", "Moneda", "Fondo"):
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
    df["Volumen_USD"] = pd.to_numeric(df["Volumen_USD"], errors="coerce").fillna(0.0)
    if "Gastos_USD" not in df.columns:
        df["Gastos_USD"] = 0.0
    df["Gastos_USD"] = pd.to_numeric(df["Gastos_USD"], errors="coerce").fillna(0.0)
    df["Año"] = df["Fecha"].dt.year
    df["Mes_Num"] = df["Fecha"].dt.month
    df["Mes_Nombre"] = df["Mes_Num"].map(MESES)
    df["MesInicio"] = df["Fecha"].dt.to_period("M").dt.to_timestamp()
    return df.sort_values("Fecha").reset_index(drop=True)


CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "base_historica_acumulada.csv")
if not os.path.exists(CSV_PATH):
    st.error("No se encontró `base_historica_acumulada.csv` junto a `app.py`.")
    st.stop()

df_raw = load_data(CSV_PATH, os.path.getmtime(CSV_PATH))
if df_raw.empty:
    st.error("La base está vacía.")
    st.stop()

HIST_MIN = df_raw["Fecha"].min()
HIST_MAX = df_raw["Fecha"].max()
MES_PARCIAL = HIST_MAX != (HIST_MAX + pd.offsets.MonthEnd(0))


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def fmt_usd(v):
    """Monto en USD, soporta negativos, cero y NaN."""
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if np.isnan(v):
        return "—"
    s, a = ("-" if v < 0 else ""), abs(v)
    if a >= 1e9:
        return f"{s}USD {a/1e9:,.2f}B"
    if a >= 1e6:
        return f"{s}USD {a/1e6:,.1f}M"
    if a >= 1e3:
        return f"{s}USD {a/1e3:,.1f}K"
    return f"{s}USD {a:,.0f}"


def fmt_pct_html(pct, nd_reason=None):
    """% con signo y color, o 'n/d' con tooltip explicando por qué."""
    if nd_reason:
        return f'<span class="nd" title="{nd_reason}">n/d</span>'
    if pct is None or (isinstance(pct, float) and np.isnan(pct)):
        return '<span class="nd">—</span>'
    cls = "pos" if pct >= 0 else "neg"
    sign = "+" if pct >= 0 else ""
    return f'<span class="{cls}">{sign}{pct:.1f}%</span>'


def bps(gastos, volumen):
    try:
        return (float(gastos) / float(volumen) * 10_000) if volumen and float(volumen) > 0 else np.nan
    except (TypeError, ValueError, ZeroDivisionError):
        return np.nan


# ═══════════════════════════════════════════════════════════════
# HERO
# ═══════════════════════════════════════════════════════════════
badge_parcial = (
    f'<span class="novus-badge warn">⚠ {MESES[HIST_MAX.month].lower()} en curso · mes parcial</span>'
    if MES_PARCIAL else ""
)
st.markdown(f"""
<div class="novus-hero">
  <div class="novus-eyebrow">middle office</div>
  <h1>control de <span>contrapartes</span> y flujo de agentes</h1>
  <p>Volumen operado, participación de mercado, costos de ejecución y variación por asset category (USD MEP/CCL).</p>
  <span class="novus-badge">datos al {HIST_MAX.strftime('%d/%m/%Y')}</span>{badge_parcial}
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# FILTROS
# ═══════════════════════════════════════════════════════════════
PRESETS = ["Todo", "YTD", "Últimos 30d", "Últimos 90d", "Últimos 12m", "Personalizado"]

with st.expander("🔍  Filtros  ·  vacío = todos", expanded=False):
    preset = st.radio("Período", PRESETS, index=0, horizontal=True, key="preset")

    rango_custom = None
    if preset == "Personalizado":
        rango_custom = st.date_input(
            "Rango de fechas",
            value=(HIST_MIN.date(), HIST_MAX.date()),
            min_value=HIST_MIN.date(), max_value=HIST_MAX.date(),
            key="rango",
        )

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        anos_sel = st.multiselect("Año", sorted(df_raw["Año"].unique(), reverse=True), placeholder="Todos")
    with c2:
        meses_disp = [m for m in MESES_ORD if m in set(df_raw["Mes_Nombre"])]
        meses_sel = st.multiselect("Mes", meses_disp, placeholder="Todos")
    with c3:
        assets_sel = st.multiselect("Asset Category", sorted(df_raw["Asset_Category"].unique()),
                                    placeholder="Todas")
    with c4:
        fondos_sel = st.multiselect("Fondo", sorted(df_raw["Fondo"].unique()), placeholder="Todos")
    with c5:
        agentes_sel = st.multiselect("Agente", sorted(df_raw["Agente"].unique()), placeholder="Todos")

# ── Resolver rango de fechas ────────────────────────────────────
fecha_desde, fecha_hasta = HIST_MIN, HIST_MAX
if preset == "YTD":
    fecha_desde = pd.Timestamp(year=HIST_MAX.year, month=1, day=1)
elif preset == "Últimos 30d":
    fecha_desde = HIST_MAX - pd.Timedelta(days=30)
elif preset == "Últimos 90d":
    fecha_desde = HIST_MAX - pd.Timedelta(days=90)
elif preset == "Últimos 12m":
    fecha_desde = HIST_MAX - pd.DateOffset(months=12)
elif preset == "Personalizado" and rango_custom:
    if isinstance(rango_custom, (tuple, list)):
        if len(rango_custom) == 2:
            fecha_desde, fecha_hasta = pd.Timestamp(rango_custom[0]), pd.Timestamp(rango_custom[1])
        elif len(rango_custom) == 1:
            fecha_desde = pd.Timestamp(rango_custom[0])
    else:
        fecha_desde = pd.Timestamp(rango_custom)

filtro_fecha_activo = (preset != "Todo") or bool(anos_sel) or bool(meses_sel)


def aplicar(base, fechas=True, cats=True, agente=True):
    """Construye scopes distintos aplicando subconjuntos de filtros."""
    d = base
    if fechas:
        d = d[(d["Fecha"] >= fecha_desde) & (d["Fecha"] <= fecha_hasta)]
        if anos_sel:
            d = d[d["Año"].isin(anos_sel)]
        if meses_sel:
            d = d[d["Mes_Nombre"].isin(meses_sel)]
    if cats:
        if assets_sel:
            d = d[d["Asset_Category"].isin(assets_sel)]
        if fondos_sel:
            d = d[d["Fondo"].isin(fondos_sel)]
    if agente and agentes_sel:
        d = d[d["Agente"].isin(agentes_sel)]
    return d


df       = aplicar(df_raw)                 # vista principal
df_scope = aplicar(df_raw, agente=False)   # concentración: universo completo de agentes
df_hist  = aplicar(df_raw, fechas=False)   # ventanas móviles: historia completa

if df.empty:
    st.warning("No hay datos para la combinación de filtros seleccionada. Probá ampliar el período.")
    st.stop()


# ═══════════════════════════════════════════════════════════════
# MÉTRICAS
# ═══════════════════════════════════════════════════════════════
max_d = df["Fecha"].max()
ytd_start = pd.Timestamp(year=HIST_MAX.year, month=1, day=1)
ytd_prev_start = ytd_start - pd.DateOffset(years=1)
ytd_prev_end = HIST_MAX - pd.DateOffset(years=1)
ytd_hist_ok = ytd_prev_start >= HIST_MIN

vol_total = float(df["Volumen_USD"].sum())
gas_total = float(df["Gastos_USD"].sum())
bps_total = bps(gas_total, vol_total)

vol_ytd = float(df_hist[(df_hist["Fecha"] >= ytd_start) & (df_hist["Fecha"] <= HIST_MAX)]["Volumen_USD"].sum())
vol_ytd_prev = float(df_hist[(df_hist["Fecha"] >= ytd_prev_start) &
                             (df_hist["Fecha"] <= ytd_prev_end)]["Volumen_USD"].sum())
ytd_delta = ((vol_ytd - vol_ytd_prev) / vol_ytd_prev * 100) if (vol_ytd_prev > 0 and ytd_hist_ok) else None

# Asset dominante últimos 30d
d30 = max_d - pd.Timedelta(days=30)
asset_30d = df[df["Fecha"] > d30].groupby("Asset_Category")["Volumen_USD"].sum()
if len(asset_30d) and asset_30d.sum() > 0:
    asset_dom = asset_30d.idxmax()
    asset_dom_pct = asset_30d.max() / asset_30d.sum() * 100
else:
    asset_dom, asset_dom_pct = "—", 0.0

# Concentración sobre el universo del scope (ignora filtro de agente)
vol_scope = float(df_scope["Volumen_USD"].sum())
ag_vol = df_scope.groupby("Agente")["Volumen_USD"].sum().sort_values(ascending=False)
ag_vol = ag_vol[ag_vol > 0]

if vol_scope > 0 and len(ag_vol):
    agente_lider = str(ag_vol.index[0])
    agente_lider_pct = ag_vol.iloc[0] / vol_scope * 100
    hhi = float(((ag_vol / vol_scope * 100) ** 2).sum())
    top3_pct = ag_vol.head(3).sum() / vol_scope * 100
    top5_pct = ag_vol.head(5).sum() / vol_scope * 100
else:
    agente_lider, agente_lider_pct, hhi, top3_pct, top5_pct = "—", 0.0, 0.0, 0.0, 0.0

conc_label = "Baja" if hhi < 1500 else ("Media" if hhi < 2500 else "Alta")
hhi_color = GREEN if hhi < 1500 else (AMBER if hhi < 2500 else RED)

n_agentes = int(df["Agente"].nunique())
n_fondos  = int(df["Fondo"].nunique())
n_ops     = int(len(df))
ticket_prom = vol_total / n_ops if n_ops else 0.0

# Var mes contra mes con el último mes COMPLETO
meses_serie = df_hist.groupby("MesInicio")["Volumen_USD"].sum().sort_index()
meses_comp = meses_serie.iloc[:-1] if (MES_PARCIAL and len(meses_serie)) else meses_serie
if len(meses_comp) >= 2 and meses_comp.iloc[-2] > 0:
    mom = (meses_comp.iloc[-1] - meses_comp.iloc[-2]) / meses_comp.iloc[-2] * 100
    mom_label = f"{MESES[meses_comp.index[-1].month][:3].lower()} {meses_comp.index[-1].year}"
else:
    mom, mom_label = None, ""


# ═══════════════════════════════════════════════════════════════
# 1 — MÉTRICAS CLAVE
# ═══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Métricas Clave</div><div class="section-underline"></div>',
            unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
with k1:
    if mom is not None:
        col = GREEN_DIM if mom >= 0 else RED
        d_html = (f'<div class="kpi-delta" style="color:{col}">{"▲" if mom >= 0 else "▼"} '
                  f'{abs(mom):.1f}% <span style="color:{GRAY_TEXT};font-weight:400">'
                  f'vs mes anterior ({mom_label})</span></div>')
    else:
        d_html = ""
    st.markdown(f'<div class="kpi-card accent"><div class="kpi-label">Volumen del período</div>'
                f'<div class="kpi-value">{fmt_usd(vol_total)}</div>{d_html}'
                f'<div class="kpi-sub">{n_ops:,} operaciones</div></div>', unsafe_allow_html=True)
with k2:
    if ytd_delta is not None:
        col = GREEN_DIM if ytd_delta >= 0 else RED
        d_html = (f'<div class="kpi-delta" style="color:{col}">{"▲" if ytd_delta >= 0 else "▼"} '
                  f'{abs(ytd_delta):.1f}% <span style="color:{GRAY_TEXT};font-weight:400">'
                  f'vs {ytd_prev_start.year}</span></div>')
    else:
        d_html = '<div class="kpi-delta nd">sin comparable del año anterior</div>'
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Volumen YTD {HIST_MAX.year}</div>'
                f'<div class="kpi-value">{fmt_usd(vol_ytd)}</div>{d_html}</div>', unsafe_allow_html=True)
with k3:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Agente líder</div>'
                f'<div class="kpi-name" title="{agente_lider}">{agente_lider}</div>'
                f'<div class="kpi-value sm">{agente_lider_pct:.1f}%</div>'
                f'<div class="kpi-sub">sobre {len(ag_vol)} agentes activos</div></div>', unsafe_allow_html=True)
with k4:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Concentración HHI</div>'
                f'<div class="kpi-value sm" style="color:{hhi_color}">{conc_label} · {hhi:,.0f}</div>'
                f'<div class="kpi-sub">Top 3: {top3_pct:.0f}%  ·  Top 5: {top5_pct:.0f}%</div></div>',
                unsafe_allow_html=True)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

k5, k6, k7, k8 = st.columns(4)
with k5:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Asset dominante (30d)</div>'
                f'<div class="kpi-name" title="{asset_dom}">{asset_dom}</div>'
                f'<div class="kpi-value sm">{asset_dom_pct:.1f}%</div></div>', unsafe_allow_html=True)
with k6:
    bps_txt = f"{bps_total:.2f} bps" if not np.isnan(bps_total) else "—"
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Costo de ejecución</div>'
                f'<div class="kpi-value sm">{bps_txt}</div>'
                f'<div class="kpi-sub">{fmt_usd(gas_total)} de gastos</div></div>', unsafe_allow_html=True)
with k7:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Ticket promedio</div>'
                f'<div class="kpi-value sm">{fmt_usd(ticket_prom)}</div>'
                f'<div class="kpi-sub">por operación</div></div>', unsafe_allow_html=True)
with k8:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Cobertura</div>'
                f'<div class="kpi-value sm">{n_agentes} · {n_fondos}</div>'
                f'<div class="kpi-sub">agentes · fondos operados</div></div>', unsafe_allow_html=True)

# ── Barra de concentración ──────────────────────────────────────
if len(ag_vol) >= 4 and vol_scope > 0:
    top1  = ag_vol.iloc[0] / vol_scope * 100
    t23   = ag_vol.iloc[1:3].sum() / vol_scope * 100
    t45   = ag_vol.iloc[3:5].sum() / vol_scope * 100
    resto = max(0.0, 100 - top1 - t23 - t45)
    tramos = [
        (f"#1  {ag_vol.index[0]}", top1, "#1B4332", "white"),
        ("#2–3", t23, GREEN_DIM, "white"),
        ("#4–5", t45, GREEN, "white"),
        (f"Resto ({max(0, len(ag_vol) - 5)} agentes)", resto, "#C8D4CA", DARK_TEXT),
    ]
    fig_conc = go.Figure()
    for nombre, val, color, txt_color in tramos:
        if val <= 0:
            continue
        fig_conc.add_trace(go.Bar(
            x=[val], y=["c"], orientation="h", name=nombre, marker_color=color,
            text=[f"{val:.0f}%"] if val >= 6 else [""],
            textposition="inside", insidetextanchor="middle",
            textfont=dict(size=11, color=txt_color, family=FONT_FAMILY),
            hovertemplate=f"<b>{nombre}</b><br>%{{x:.1f}}% del volumen<extra></extra>",
        ))
    fig_conc.update_layout(
        **BASE_LAYOUT, barmode="stack", height=118, showlegend=True,
        legend=dict(orientation="h", y=-0.5, x=0, traceorder="normal",
                    font=dict(size=9.5, family=FONT_FAMILY)),
        xaxis=dict(visible=False, range=[0, 100]),
        yaxis=dict(visible=False),
        margin=dict(l=0, r=0, t=28, b=0),
        title=dict(text="Cómo se reparte el volumen entre agentes", x=0, xanchor="left",
                   font=dict(size=11.5, family=FONT_FAMILY, color=GRAY_TEXT)),
    )
    chart(fig_conc, key="conc")


# ═══════════════════════════════════════════════════════════════
# 2 — PARTICIPACIÓN + VARIACIÓN
# ═══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Participación y Variación</div><div class="section-underline"></div>',
            unsafe_allow_html=True)

col_pie, col_var = st.columns([46, 54])

with col_pie:
    st.markdown('<div class="chart-label">Share por agente</div>', unsafe_allow_html=True)
    df_pie = df.groupby("Agente", as_index=False)["Volumen_USD"].sum()
    df_pie = df_pie[df_pie["Volumen_USD"] > 0].sort_values("Volumen_USD", ascending=False)
    umbral = df_pie["Volumen_USD"].sum() * 0.025
    df_pie["Label"] = np.where(df_pie["Volumen_USD"] >= umbral, df_pie["Agente"], "Otros")
    n_otros = int((df_pie["Label"] == "Otros").sum())
    df_pie_g = (df_pie.groupby("Label", as_index=False)["Volumen_USD"].sum()
                .sort_values("Volumen_USD", ascending=False))
    if n_otros:
        df_pie_g["Label"] = df_pie_g["Label"].replace({"Otros": f"Otros ({n_otros})"})

    colores, i = [], 0
    for lab in df_pie_g["Label"]:
        if str(lab).startswith("Otros"):
            colores.append(OTROS_COLOR)
        else:
            colores.append(AGENT_PALETTE[i % len(AGENT_PALETTE)])
            i += 1

    fig_pie = go.Figure(go.Pie(
        labels=df_pie_g["Label"], values=df_pie_g["Volumen_USD"],
        hole=0.58, sort=False, direction="clockwise",
        marker=dict(colors=colores, line=dict(color="white", width=2)),
        texttemplate="%{percent:.1%}", textposition="inside",
        textfont=dict(size=10.5, family=FONT_FAMILY, color="white"),
        insidetextorientation="horizontal",
        hovertemplate="<b>%{label}</b><br>%{percent:.2%} del volumen<br>USD %{value:,.0f}<extra></extra>",
    ))
    fig_pie.update_layout(
        **BASE_LAYOUT, height=318, showlegend=True,
        legend=dict(font=dict(size=9.5, family=FONT_FAMILY), orientation="v",
                    y=0.5, yanchor="middle", x=1.02),
        margin=dict(l=0, r=105, t=6, b=6),
        annotations=[dict(
            text=(f"<b>{fmt_usd(vol_total)}</b><br>"
                  f"<span style='font-size:9px;color:{GRAY_TEXT}'>volumen total</span>"),
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=13, family=FONT_FAMILY, color=DARK_TEXT),
        )],
    )
    chart(fig_pie, key="pie")

with col_var:
    st.markdown('<div class="chart-label">Variación de volumen por asset category</div>',
                unsafe_allow_html=True)

    def var_ventana(dias):
        """Ventana móvil sobre HISTORIA COMPLETA → (actual, previa, motivo_nd)."""
        fin = HIST_MAX
        ini = fin - pd.Timedelta(days=dias)
        prev_ini = ini - pd.Timedelta(days=dias)
        nd = None
        if prev_ini < HIST_MIN:
            falta = (HIST_MIN - prev_ini).days
            nd = (f"Historia insuficiente: faltan {falta} dias para completar "
                  f"la ventana comparable de {dias}d.")
        cur = df_hist[(df_hist["Fecha"] > ini) & (df_hist["Fecha"] <= fin)] \
            .groupby("Asset_Category")["Volumen_USD"].sum()
        prv = df_hist[(df_hist["Fecha"] > prev_ini) & (df_hist["Fecha"] <= ini)] \
            .groupby("Asset_Category")["Volumen_USD"].sum()
        return cur, prv, nd

    # Ventanas adaptativas: se muestran las que la historia disponible puede
    # comparar de verdad. Con ~580 días hoy salen 30/60/90/180; la de 365d
    # aparece sola cuando la base acumule 2 años.
    _ok = [d for d in (30, 60, 90, 180, 365)
           if (HIST_MAX - pd.Timedelta(days=2 * d)) >= HIST_MIN]
    if len(_ok) < 2:
        _ok = [30, 60]
    VENTANAS_DIAS = sorted(set(_ok[:2] + _ok[-2:]))
    ventanas = {d: var_ventana(d) for d in VENTANAS_DIAS}

    ytd_cur = df_hist[(df_hist["Fecha"] >= ytd_start) & (df_hist["Fecha"] <= HIST_MAX)] \
        .groupby("Asset_Category")["Volumen_USD"].sum()
    ytd_prv = df_hist[(df_hist["Fecha"] >= ytd_prev_start) & (df_hist["Fecha"] <= ytd_prev_end)] \
        .groupby("Asset_Category")["Volumen_USD"].sum()
    ytd_nd = None if ytd_hist_ok else "Historia insuficiente para comparar contra el año anterior."

    def celda(cur, prv, cat, nd):
        if nd:
            return fmt_pct_html(None, nd_reason=nd)
        c, p = float(cur.get(cat, 0.0)), float(prv.get(cat, 0.0))
        if p <= 0:
            razon = ("Sin volumen en la ventana comparable anterior."
                     if c > 0 else "Sin actividad en ninguna de las dos ventanas.")
            return fmt_pct_html(None, nd_reason=razon)
        return fmt_pct_html((c - p) / p * 100)

    cats = (df_hist.groupby("Asset_Category")["Volumen_USD"].sum()
            .sort_values(ascending=False).index.tolist())
    vol_por_cat = df_hist.groupby("Asset_Category")["Volumen_USD"].sum()

    filas = ""
    for cat in cats:
        sw = ASSET_COLORS.get(cat, GREEN)
        celdas = ""
        for d in VENTANAS_DIAS:
            cur, prv, nd = ventanas[d]
            celdas += f"<td>{celda(cur, prv, cat, nd)}</td>"
        celdas += f"<td>{celda(ytd_cur, ytd_prv, cat, ytd_nd)}</td>"
        filas += (f'<tr><td><span class="swatch" style="background:{sw}"></span>{cat}</td>'
                  f'<td style="color:{GRAY_TEXT}">{fmt_usd(vol_por_cat.get(cat, 0))}</td>'
                  f'{celdas}</tr>')

    ths = "".join(f"<th>{d}d</th>" for d in VENTANAS_DIAS)
    st.markdown(f"""
    <div style="background:{WHITE};border:1px solid {BORDER};border-radius:10px;padding:12px 16px;">
      <table class="var-table">
        <thead><tr><th>Asset Category</th><th>Vol. histórico</th>
        {ths}<th>YTD</th></tr></thead>
        <tbody>{filas}</tbody>
      </table>
    </div>
    <div class="note" style="margin-top:8px">
      Cada columna compara la ventana más reciente contra la ventana inmediata anterior de igual duración,
      siempre sobre la <b>historia completa</b> ({HIST_MIN.strftime('%m/%Y')}–{HIST_MAX.strftime('%m/%Y')}),
      así el resultado no depende del filtro de período. Solo se muestran las ventanas que la base puede
      comparar de verdad: con {(HIST_MAX - HIST_MIN).days} días de historia la de 365d aparecerá recién
      cuando haya 2 años cargados. <b>n/d</b> = sin actividad en la ventana comparable
      (pasá el mouse por encima para ver el motivo).
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# 3 — EVOLUCIÓN
# ═══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Evolución Mensual</div><div class="section-underline"></div>',
            unsafe_allow_html=True)

col_bar, col_line = st.columns([42, 58])

with col_bar:
    st.markdown('<div class="chart-label">Top 7 fondos por volumen</div>', unsafe_allow_html=True)
    df_fondo = (df.groupby("Fondo", as_index=False)["Volumen_USD"].sum()
                .sort_values("Volumen_USD", ascending=False).head(7)
                .sort_values("Volumen_USD", ascending=True))
    share_f = df_fondo["Volumen_USD"] / vol_total * 100 if vol_total else df_fondo["Volumen_USD"] * 0
    fig_bar = go.Figure(go.Bar(
        x=df_fondo["Volumen_USD"], y=df_fondo["Fondo"], orientation="h",
        marker=dict(color=df_fondo["Volumen_USD"],
                    colorscale=[[0, "#B7E4C7"], [1, GREEN_DIM]], showscale=False),
        text=[f"{fmt_usd(v)}  ·  {s:.1f}%" for v, s in zip(df_fondo["Volumen_USD"], share_f)],
        textposition="outside", cliponaxis=False,
        textfont=dict(size=9.5, family=FONT_FAMILY, color=DARK_TEXT),
        hovertemplate="<b>%{y}</b><br>USD %{x:,.0f}<extra></extra>",
    ))
    xmax = float(df_fondo["Volumen_USD"].max()) if len(df_fondo) else 1.0
    fig_bar.update_layout(
        **BASE_LAYOUT, height=388, showlegend=False,
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[0, xmax * 1.45]),
        yaxis=dict(tickfont=dict(size=10, color=DARK_TEXT, family=FONT_FAMILY)),
        margin=dict(l=0, r=10, t=8, b=8),
    )
    chart(fig_bar, key="bar_fondo")

with col_line:
    st.markdown('<div class="chart-label">Volumen mensual por asset category</div>', unsafe_allow_html=True)
    df_line = (df.groupby(["MesInicio", "Asset_Category"], as_index=False)["Volumen_USD"].sum()
               .sort_values("MesInicio"))
    df_line["Vol_MM"] = df_line["Volumen_USD"] / 1e6
    orden_cat = (df.groupby("Asset_Category")["Volumen_USD"].sum()
                 .sort_values(ascending=False).index.tolist())

    fig_line = go.Figure()
    for cat in orden_cat:
        d = df_line[df_line["Asset_Category"] == cat]
        fig_line.add_trace(go.Scatter(
            x=d["MesInicio"], y=d["Vol_MM"], name=cat, mode="lines+markers",
            line=dict(width=2.4, color=ASSET_COLORS.get(cat, GREEN), shape="spline", smoothing=0.4),
            marker=dict(size=5),
            hovertemplate="$%{y:,.1f}M<extra>" + str(cat) + "</extra>",
        ))

    if MES_PARCIAL and len(df_line):
        x0 = HIST_MAX.to_period("M").to_timestamp()
        fig_line.add_vrect(
            x0=x0, x1=x0 + pd.Timedelta(days=31), fillcolor="#FFF4E0",
            opacity=0.6, layer="below", line_width=0,
            annotation_text="mes parcial", annotation_position="top left",
            annotation_font=dict(size=8.5, color=AMBER, family=FONT_FAMILY),
        )

    fig_line.update_layout(
        **BASE_LAYOUT, height=388, hovermode="x unified",
        xaxis=dict(showgrid=False, tickformat="%b<br>%Y",
                   tickfont=dict(size=8.5, color=GRAY_TEXT, family=FONT_FAMILY)),
        yaxis=dict(gridcolor="#EDEFED", zeroline=False, rangemode="tozero",
                   tickprefix="$", ticksuffix="M",
                   tickfont=dict(size=9, color=GRAY_TEXT, family=FONT_FAMILY)),
        legend=dict(orientation="h", yanchor="top", y=-0.14, xanchor="center", x=0.5,
                    font=dict(size=8.5, family=FONT_FAMILY), title_text=""),
        margin=dict(l=0, r=12, t=14, b=62),
    )
    chart(fig_line, key="line_asset")


# ═══════════════════════════════════════════════════════════════
# 4 — TABS: RANKING / COSTOS / MONEDA
# ═══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Análisis Detallado</div><div class="section-underline"></div>',
            unsafe_allow_html=True)

rank = df.groupby("Agente").agg(
    Volumen=("Volumen_USD", "sum"),
    Gastos=("Gastos_USD", "sum"),
    Ops=("Volumen_USD", "size"),
).reset_index()
rank = rank[rank["Volumen"] > 0].copy()
rank["Share"] = rank["Volumen"] / vol_total * 100 if vol_total else 0.0
rank["bps"] = [bps(g, v) for g, v in zip(rank["Gastos"], rank["Volumen"])]
rank["Ticket"] = rank["Volumen"] / rank["Ops"]
# Versiones escaladas para mostrar: printf no soporta separador de miles,
# así que se muestran en millones / miles y quedan igual de ordenables.
rank["Vol_MM"] = rank["Volumen"] / 1e6
rank["Ticket_K"] = rank["Ticket"] / 1e3

cur30 = df_hist[df_hist["Fecha"] > HIST_MAX - pd.Timedelta(days=30)] \
    .groupby("Agente")["Volumen_USD"].sum()
prv30 = df_hist[(df_hist["Fecha"] > HIST_MAX - pd.Timedelta(days=60)) &
                (df_hist["Fecha"] <= HIST_MAX - pd.Timedelta(days=30))] \
    .groupby("Agente")["Volumen_USD"].sum()
rank["Var30d"] = [
    ((cur30.get(a, 0.0) - prv30.get(a, 0.0)) / prv30.get(a, 0.0) * 100)
    if prv30.get(a, 0.0) > 0 else np.nan
    for a in rank["Agente"]
]
rank = rank.sort_values("Volumen", ascending=False).reset_index(drop=True)
rank.insert(0, "#", range(1, len(rank) + 1))

tab_rank, tab_costos, tab_moneda = st.tabs(
    ["  Ranking de agentes  ", "  Costos de ejecución  ", "  Moneda de liquidación  "]
)

with tab_rank:
    st.markdown(f'<div class="chart-label">{len(rank)} agentes con actividad en el período seleccionado</div>',
                unsafe_allow_html=True)
    tabla = rank[["#", "Agente", "Vol_MM", "Share", "Ops", "Ticket_K", "Gastos", "bps", "Var30d"]]
    df_show(
        tabla, hide_index=True, height=int(min(430, 45 + 35 * max(len(tabla), 1))),
        column_config={
            "#": st.column_config.NumberColumn("#", width="small"),
            "Agente": st.column_config.TextColumn("Agente", width="medium"),
            "Vol_MM": st.column_config.NumberColumn("Volumen", format="$ %.1f M"),
            "Share": st.column_config.ProgressColumn(
                "Share", format="%.2f%%", min_value=0,
                max_value=float(max(rank["Share"].max() if len(rank) else 1, 1))),
            "Ops": st.column_config.NumberColumn("Ops", format="%d", width="small"),
            "Ticket_K": st.column_config.NumberColumn("Ticket prom.", format="$ %.0f K"),
            "Gastos": st.column_config.NumberColumn("Gastos USD", format="$ %.0f"),
            "bps": st.column_config.NumberColumn("Costo (bps)", format="%.2f", width="small"),
            "Var30d": st.column_config.NumberColumn("Var 30d", format="%.1f%%", width="small"),
        },
    )
    st.markdown('<div class="note">Ordenado por volumen. <b>Var 30d</b> compara los últimos 30 días '
                'contra los 30 anteriores sobre la historia completa (n/d si el agente no operó en la '
                'ventana previa). <b>Costo (bps)</b> = Gastos / Volumen × 10.000.</div>',
                unsafe_allow_html=True)

    cd1, cd2, _ = st.columns([1, 1, 3])
    with cd1:
        st.download_button(
            "⬇  Ranking (CSV)",
            rank.drop(columns=["Vol_MM", "Ticket_K"], errors="ignore")
                .to_csv(index=False, float_format="%.2f").encode("utf-8-sig"),
            file_name=f"novus_ranking_agentes_{HIST_MAX:%Y%m%d}.csv",
            mime="text/csv", key="dl_rank",
        )
    with cd2:
        try:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as xw:
                (rank.drop(columns=["Vol_MM", "Ticket_K"], errors="ignore")
                     .to_excel(xw, sheet_name="Ranking agentes", index=False))
                (df.drop(columns=["MesInicio"], errors="ignore")
                   .to_excel(xw, sheet_name="Detalle filtrado", index=False))
            st.download_button(
                "⬇  Reporte (Excel)", buf.getvalue(),
                file_name=f"novus_agentes_{HIST_MAX:%Y%m%d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_xlsx",
            )
        except Exception:
            st.caption("Export a Excel no disponible en este entorno.")

with tab_costos:
    cost = df.groupby("Asset_Category").agg(
        Volumen=("Volumen_USD", "sum"), Gastos=("Gastos_USD", "sum"), Ops=("Volumen_USD", "size"),
    ).reset_index()
    cost["bps"] = [bps(g, v) for g, v in zip(cost["Gastos"], cost["Volumen"])]
    sin_gasto_serie = df.assign(_z=(df["Gastos_USD"] == 0)).groupby("Asset_Category")["_z"].mean() * 100
    cost["sin_gasto_pct"] = cost["Asset_Category"].map(sin_gasto_serie).astype(float)
    cost = cost.sort_values("bps", ascending=True)

    cc1, cc2 = st.columns([54, 46])
    with cc1:
        st.markdown('<div class="chart-label">Costo de ejecución por asset category</div>',
                    unsafe_allow_html=True)
        cplot = cost.dropna(subset=["bps"])
        if cplot.empty:
            st.info("No hay gastos cargados en el período seleccionado.")
        else:
            fig_bps = go.Figure(go.Bar(
                x=cplot["bps"], y=cplot["Asset_Category"], orientation="h",
                marker_color=[ASSET_COLORS.get(c, GREEN) for c in cplot["Asset_Category"]],
                text=[f"{b:.2f}" for b in cplot["bps"]], textposition="outside", cliponaxis=False,
                textfont=dict(size=10, family=FONT_FAMILY, color=DARK_TEXT),
                hovertemplate="<b>%{y}</b><br>%{x:.2f} bps<extra></extra>",
            ))
            if not np.isnan(bps_total):
                fig_bps.add_vline(x=float(bps_total), line=dict(color=GRAY_TEXT, width=1, dash="dot"))
            rng = float(cplot["bps"].max()) or 1.0
            fig_bps.update_layout(
                **BASE_LAYOUT, height=332, showlegend=False,
                xaxis=dict(title=dict(text="bps sobre volumen operado",
                                      font=dict(size=9.5, color=GRAY_TEXT, family=FONT_FAMILY)),
                           gridcolor="#EDEFED", zeroline=False, range=[0, rng * 1.25],
                           tickfont=dict(size=9, color=GRAY_TEXT, family=FONT_FAMILY)),
                yaxis=dict(tickfont=dict(size=10, color=DARK_TEXT, family=FONT_FAMILY)),
                margin=dict(l=0, r=16, t=8, b=38),
            )
            chart(fig_bps, key="bps_asset")
            prom = f"{bps_total:.2f} bps" if not np.isnan(bps_total) else "—"
            st.markdown(f'<div class="note">La línea punteada es el costo promedio ponderado del '
                        f'período (<b>{prom}</b>). 1 bp = 0,01% del volumen operado. Renta Variable y '
                        f'Futuros suelen ser órdenes de magnitud más caros que cauciones y pases: '
                        f'comparar dentro de cada categoría, no entre categorías.</div>',
                        unsafe_allow_html=True)

    with cc2:
        st.markdown('<div class="chart-label">Agentes más caros (share ≥ 0,5%)</div>',
                    unsafe_allow_html=True)
        caros = rank[(rank["Share"] >= 0.5) & rank["bps"].notna() & (rank["bps"] > 0)] \
            .nlargest(8, "bps")[["Agente", "Vol_MM", "Share", "bps"]]
        if caros.empty:
            st.info("Ningún agente con gastos cargados y share suficiente en este período.")
        else:
            df_show(
                caros, hide_index=True, height=int(min(332, 45 + 35 * len(caros))),
                column_config={
                    "Agente": st.column_config.TextColumn("Agente"),
                    "Vol_MM": st.column_config.NumberColumn("Volumen", format="$ %.1f M"),
                    "Share": st.column_config.NumberColumn("Share", format="%.2f%%", width="small"),
                    "bps": st.column_config.ProgressColumn(
                        "Costo (bps)", format="%.2f", min_value=0,
                        max_value=float(caros["bps"].max())),
                },
            )
            st.markdown('<div class="note">Filtra agentes con menos de 0,5% de share para que un '
                        'gasto chico sobre un volumen mínimo no distorsione el ranking.</div>',
                        unsafe_allow_html=True)

    sin_gasto = cost[cost["sin_gasto_pct"] >= 50]
    if not sin_gasto.empty:
        lista = " · ".join(f"{r.Asset_Category} ({r.sin_gasto_pct:.0f}% sin gasto)"
                           for r in sin_gasto.itertuples())
        st.markdown(f'<div class="note warn" style="margin-top:12px">'
                    f'<b>Calidad de datos.</b> Estas categorías tienen la mayoría de sus operaciones '
                    f'con <code>Gastos_USD = 0</code>, así que su costo en bps está subestimado → {lista}. '
                    f'Si el gasto existe pero no se está cargando, conviene revisar el mapeo en el script '
                    f'de origen antes de usar estos bps para negociar comisiones.</div>',
                    unsafe_allow_html=True)

with tab_moneda:
    mon = (df.groupby("Moneda", as_index=False)["Volumen_USD"].sum()
           .sort_values("Volumen_USD", ascending=False))
    mc1, mc2 = st.columns([42, 58])
    with mc1:
        st.markdown('<div class="chart-label">Volumen por moneda de liquidación</div>',
                    unsafe_allow_html=True)
        fig_mon = go.Figure(go.Pie(
            labels=mon["Moneda"], values=mon["Volumen_USD"], hole=0.58, sort=False,
            marker=dict(colors=[MONEDA_COLORS.get(m, GREEN) for m in mon["Moneda"]],
                        line=dict(color="white", width=2)),
            texttemplate="%{percent:.1%}", textposition="inside",
            textfont=dict(size=11, family=FONT_FAMILY, color="white"),
            hovertemplate="<b>%{label}</b><br>%{percent:.2%}<br>USD %{value:,.0f}<extra></extra>",
        ))
        fig_mon.update_layout(
            **BASE_LAYOUT, height=302, showlegend=True,
            legend=dict(orientation="h", y=-0.06, x=0.5, xanchor="center",
                        font=dict(size=10, family=FONT_FAMILY)),
            margin=dict(l=0, r=0, t=6, b=6),
        )
        chart(fig_mon, key="pie_moneda")
    with mc2:
        st.markdown('<div class="chart-label">Evolución mensual por moneda</div>', unsafe_allow_html=True)
        dm = df.groupby(["MesInicio", "Moneda"], as_index=False)["Volumen_USD"].sum()
        dm["Vol_MM"] = dm["Volumen_USD"] / 1e6
        fig_mon_ev = go.Figure()
        for m in mon["Moneda"]:
            d = dm[dm["Moneda"] == m].sort_values("MesInicio")
            fig_mon_ev.add_trace(go.Bar(
                x=d["MesInicio"], y=d["Vol_MM"], name=str(m),
                marker_color=MONEDA_COLORS.get(m, GREEN),
                hovertemplate="$%{y:,.1f}M<extra>" + str(m) + "</extra>",
            ))
        fig_mon_ev.update_layout(
            **BASE_LAYOUT, height=302, barmode="stack", hovermode="x unified",
            xaxis=dict(showgrid=False, tickformat="%b<br>%Y",
                       tickfont=dict(size=8.5, color=GRAY_TEXT, family=FONT_FAMILY)),
            yaxis=dict(gridcolor="#EDEFED", zeroline=False, tickprefix="$", ticksuffix="M",
                       tickfont=dict(size=9, color=GRAY_TEXT, family=FONT_FAMILY)),
            legend=dict(orientation="h", y=-0.14, x=0.5, xanchor="center", traceorder="normal",
                        font=dict(size=9.5, family=FONT_FAMILY), title_text=""),
            margin=dict(l=0, r=10, t=8, b=46),
        )
        chart(fig_mon_ev, key="bar_moneda")


# ═══════════════════════════════════════════════════════════════
# NOTA METODOLÓGICA + FOOTER
# ═══════════════════════════════════════════════════════════════
periodo_txt = (f"{fecha_desde:%d/%m/%Y} – {fecha_hasta:%d/%m/%Y}" if filtro_fecha_activo
               else f"historia completa ({HIST_MIN:%m/%Y}–{HIST_MAX:%m/%Y})")
st.markdown(f"""
<div class="note" style="margin-top:16px">
  <b>Metodología.</b> Período analizado: {periodo_txt}. Volúmenes convertidos a USD con el TC MEP/CCL
  aplicado en cada operación. El <b>HHI</b> es la suma de los cuadrados de las participaciones
  porcentuales de cada agente sobre el universo del período (&lt;1500 baja · 1500–2500 media ·
  &gt;2500 alta concentración) e ignora el filtro por agente para no distorsionar la lectura.
  El <b>costo en bps</b> es Gastos_USD / Volumen_USD × 10.000. Las columnas de variación usan
  siempre la historia completa, no el período filtrado.
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div style="background:{DARK_BG}; margin: 1.6rem -1rem -1rem -1rem; padding: 16px 36px;
            display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
  <div style="color:{GREEN}; font-size:.85rem; font-weight:600;">
    novus <span style="color:#9AADA9; font-weight:300;">asset management</span></div>
  <div style="color:#777; font-size:.7rem;">
    middle office · datos al {HIST_MAX:%d/%m/%Y} · {len(df_raw):,} operaciones en base</div>
</div>
""", unsafe_allow_html=True)
