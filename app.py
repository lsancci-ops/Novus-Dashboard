# -*- coding: utf-8 -*-
"""
NOVUS ASSET MANAGEMENT — Dashboard de Contrapartes
Estilo visual: novus web (dark header + green accent + white cards)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os

st.set_page_config(
    page_title="novus | agentes",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# PALETA — extraída del sitio web de Novus
# ─────────────────────────────────────────────
DARK_BG    = "#1A1C1A"   # fondo hero oscuro (casi negro con tinte verde)
DARK_CARD  = "#222522"   # card oscura
GREEN      = "#5DBB63"   # verde acento principal
GREEN_DIM  = "#3D8C42"   # verde más oscuro
LIGHT_BG   = "#F0F2F0"   # fondo sección clara
WHITE      = "#FFFFFF"
GRAY_TEXT  = "#888888"
DARK_TEXT  = "#1A1C1A"
BORDER     = "#E8EBE8"

ASSET_COLORS = {
    "Fixed Income":          "#2D6A4F",   # verde oscuro
    "Renta Variable":        "#5DBB63",   # verde principal
    "Licitaciones":          "#95D5A0",   # verde claro
    "Cauciones Colocadoras": "#1B4332",   # verde muy oscuro
    "Pases Colocadores":     "#74C69D",   # verde menta
    "Futuros":               "#B7E4C7",   # verde muy claro
    "CPD y Pagarés":         "#40916C",   # verde medio
}

CHART_FONT = dict(family="'DM Sans', 'Helvetica Neue', Arial, sans-serif", color="#1A1C1A")

# ─────────────────────────────────────────────
# CSS — estilo Novus web
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap');

  html, body, .stApp {{
      font-family: 'DM Sans', 'Segoe UI', sans-serif !important;
      background-color: {LIGHT_BG} !important;
  }}

  /* ── HERO / HEADER dark ── */
  .novus-hero {{
      background: linear-gradient(135deg, {DARK_BG} 0%, #1E2B1E 60%, #162416 100%);
      padding: 36px 48px 32px;
      margin: -1rem -1rem 0 -1rem;
      position: relative;
      overflow: hidden;
  }}
  .novus-hero::after {{
      content: '';
      position: absolute;
      right: -80px; top: -80px;
      width: 340px; height: 340px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(93,187,99,.12) 0%, transparent 70%);
  }}
  .novus-eyebrow {{
      font-size: .7rem; font-weight: 600; letter-spacing: 2px;
      color: {GREEN}; text-transform: uppercase; margin-bottom: 10px;
  }}
  .novus-hero h1 {{
      font-size: 2rem; font-weight: 300; color: {WHITE};
      line-height: 1.25; margin: 0 0 6px; letter-spacing: -.5px;
  }}
  .novus-hero h1 span {{ color: {GREEN}; font-weight: 600; }}
  .novus-hero p {{ color: #9AADA9; font-size: .85rem; margin: 8px 0 16px; max-width: 520px; }}
  .novus-badge {{
      display: inline-flex; align-items: center; gap: 7px;
      border: 1px solid rgba(93,187,99,.4);
      border-radius: 20px; padding: 5px 14px;
      font-size: .75rem; color: {GREEN}; font-weight: 500;
  }}
  .novus-badge::before {{
      content: '●'; font-size: .5rem;
  }}

  /* ── FILTROS BAR ── */
  .filter-bar {{
      background: {DARK_BG};
      padding: 12px 48px;
      margin: 0 -1rem 24px -1rem;
      display: flex; align-items: center; gap: 24px;
      border-bottom: 1px solid rgba(93,187,99,.2);
  }}
  .filter-label {{
      font-size: .7rem; font-weight: 600; letter-spacing: 1.5px;
      color: {GRAY_TEXT}; text-transform: uppercase;
  }}

  /* ── KPI CARDS ── */
  .kpi-card {{
      background: {WHITE};
      border-radius: 10px;
      padding: 20px 22px 16px;
      box-shadow: 0 1px 8px rgba(0,0,0,.06);
      border: 1px solid {BORDER};
      height: 100%;
  }}
  .kpi-label {{
      font-size: .65rem; font-weight: 600; letter-spacing: 1.5px;
      color: {GRAY_TEXT}; text-transform: uppercase; margin-bottom: 8px;
  }}
  .kpi-value {{
      font-size: 1.9rem; font-weight: 600; color: {GREEN};
      line-height: 1; margin-bottom: 4px;
  }}
  .kpi-sub {{
      font-size: .75rem; color: {GRAY_TEXT}; margin-top: 4px;
  }}
  .kpi-name {{
      font-size: .95rem; font-weight: 500; color: {DARK_TEXT};
      line-height: 1.2; margin-bottom: 4px;
  }}

  /* ── SECTION TITLES ── */
  .section-title {{
      font-size: 1.3rem; font-weight: 400; color: {DARK_TEXT};
      letter-spacing: -.3px; margin-bottom: 4px;
  }}
  .section-title span {{ font-weight: 600; }}
  .section-underline {{
      width: 32px; height: 2px; background: {GREEN};
      margin-bottom: 20px;
  }}

  /* ── VAR TABLE ── */
  .var-table {{ width:100%; border-collapse: collapse; font-size: .82rem; }}
  .var-table th {{
      font-size: .65rem; letter-spacing: 1.2px; text-transform: uppercase;
      color: {GRAY_TEXT}; font-weight: 600;
      padding: 8px 12px; border-bottom: 1px solid {BORDER};
      text-align: right;
  }}
  .var-table th:first-child {{ text-align: left; }}
  .var-table td {{
      padding: 9px 12px; border-bottom: 1px solid {BORDER};
      color: {DARK_TEXT};
  }}
  .var-table td:not(:first-child) {{ text-align: right; }}
  .var-table tr:hover td {{ background: #F8FBF8; }}
  .pos {{ color: {GREEN}; font-weight: 600; }}
  .neg {{ color: #E05555; font-weight: 600; }}
  .neu {{ color: {GRAY_TEXT}; }}

  /* ── BADGE PILL ── */
  .pill {{
      display: inline-block;
      border: 1px solid {BORDER}; border-radius: 20px;
      padding: 2px 10px; font-size: .65rem; font-weight: 600;
      letter-spacing: 1px; text-transform: uppercase; color: {GRAY_TEXT};
  }}

  /* ── MULTISELECT — eliminar rojo, reemplazar por dark+green ── */
  .stMultiSelect [data-baseweb="tag"] {{
      background-color: {DARK_BG} !important;
      border: 1px solid rgba(93,187,99,.5) !important;
      border-radius: 6px !important;
  }}
  .stMultiSelect [data-baseweb="tag"] span {{
      color: {GREEN} !important;
      font-size: .75rem !important;
      font-weight: 500 !important;
      letter-spacing: .3px;
  }}
  .stMultiSelect [data-baseweb="tag"] button svg {{
      fill: {GREEN} !important;
  }}
  .stMultiSelect [data-baseweb="tag"] button:hover svg {{
      fill: #FFFFFF !important;
  }}
  /* Dropdown del multiselect */
  .stMultiSelect [data-baseweb="select"] > div {{
      border-color: {BORDER} !important;
      border-radius: 8px !important;
      background: white !important;
  }}
  .stMultiSelect [data-baseweb="select"] > div:focus-within {{
      border-color: {GREEN} !important;
      box-shadow: 0 0 0 2px rgba(93,187,99,.2) !important;
  }}

  /* Date input — quitar rojo */
  .stDateInput input {{
      border-color: {BORDER} !important;
      border-radius: 8px !important;
  }}
  .stDateInput input:focus {{
      border-color: {GREEN} !important;
      box-shadow: 0 0 0 2px rgba(93,187,99,.2) !important;
  }}

  /* Labels de filtros */
  .stMultiSelect label, .stDateInput label {{
      font-size: .65rem !important;
      font-weight: 600 !important;
      letter-spacing: 1.5px !important;
      color: {GRAY_TEXT} !important;
      text-transform: uppercase !important;
  }}

  /* ocultar branding streamlit */
  #MainMenu, footer {{ visibility: hidden; }}
  header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
  .block-container {{ padding-top: 0 !important; padding-bottom: 2rem !important; }}
  section[data-testid="stSidebar"] {{ display: none; }}
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
  <h1>control de <span>contrapartes</span><br>y flujo de agentes.</h1>
  <p>Volumen operado, participación de mercado y variación por asset category.<br>
     Dolarizado con FX MEP/CCL.</p>
  <div class="novus-badge">datos al {max_date.strftime('%d/%m/%Y')}</div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# FILTROS (sobre fondo oscuro, minimalistas)
# ─────────────────────────────────────────────
fc1, fc2, fc3 = st.columns([3, 3, 2])
with fc1:
    assets_all = sorted(df_raw["Asset_Category"].unique())
    assets_sel = st.multiselect("asset category", assets_all,
                                default=assets_all, label_visibility="visible")
with fc2:
    fondos_all = sorted(df_raw["Fondo"].unique())
    fondos_sel = st.multiselect("fondo", fondos_all,
                                default=fondos_all, label_visibility="visible")
with fc3:
    fmin, fmax = df_raw["Fecha"].min().date(), df_raw["Fecha"].max().date()
    fecha_rango = st.date_input("período", value=(fmin, fmax),
                                min_value=fmin, max_value=fmax,
                                label_visibility="visible")

# Aplicar filtros
df = df_raw.copy()
if len(fecha_rango) == 2:
    df = df[(df["Fecha"].dt.date >= fecha_rango[0]) & (df["Fecha"].dt.date <= fecha_rango[1])]
if assets_sel: df = df[df["Asset_Category"].isin(assets_sel)]
if fondos_sel: df = df[df["Fondo"].isin(fondos_sel)]

if df.empty:
    st.warning("Sin datos para los filtros seleccionados.")
    st.stop()

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# MÉTRICAS
# ─────────────────────────────────────────────
max_d  = df["Fecha"].max()
ytd_s  = pd.Timestamp(year=max_d.year, month=1, day=1)
d30    = max_d - pd.Timedelta(days=30)
d60    = max_d - pd.Timedelta(days=60)
d365   = max_d - pd.Timedelta(days=365)

vol_total = df["Volumen_USD"].sum()
vol_ytd   = df[df["Fecha"] >= ytd_s]["Volumen_USD"].sum()
vol_30d   = df[df["Fecha"] >= d30]["Volumen_USD"].sum()
gas_total = df["Gastos_USD"].sum()
cost_bps  = gas_total / vol_total * 10_000 if vol_total > 0 else 0

asset_30d = df[df["Fecha"] >= d30].groupby("Asset_Category")["Volumen_USD"].sum()
asset_dom = asset_30d.idxmax() if not asset_30d.empty else "—"
asset_dom_pct = asset_30d.max() / asset_30d.sum() * 100 if not asset_30d.empty else 0

ag_vol = df.groupby("Agente")["Volumen_USD"].sum()
agente_lider = ag_vol.idxmax() if not ag_vol.empty else "—"
agente_lider_pct = ag_vol.max() / vol_total * 100 if vol_total > 0 else 0

shares = (ag_vol / vol_total * 100) ** 2
hhi = shares.sum()
conc_label = "baja" if hhi < 1500 else ("media" if hhi < 2500 else "alta")

def fmt_usd(v):
    if v >= 1e9:  return f"USD {v/1e9:,.2f}B"
    if v >= 1e6:  return f"USD {v/1e6:,.1f}M"
    return f"USD {v:,.0f}"

# ─────────────────────────────────────────────
# SECCIÓN: KPI CARDS
# ─────────────────────────────────────────────
st.markdown("""
<div class="section-title">métricas <span>clave</span></div>
<div class="section-underline"></div>
""", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-label">volumen ytd</div>
      <div class="kpi-value">{fmt_usd(vol_ytd)}</div>
      <div class="kpi-sub">año {max_d.year} acumulado</div>
    </div>""", unsafe_allow_html=True)

with k2:
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-label">asset dominante · 30d</div>
      <div class="kpi-name">{asset_dom}</div>
      <div class="kpi-value" style="font-size:1.5rem;">{asset_dom_pct:.1f}%</div>
      <div class="kpi-sub">del volumen últimos 30 días</div>
    </div>""", unsafe_allow_html=True)

with k3:
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-label">agente líder</div>
      <div class="kpi-name">{agente_lider}</div>
      <div class="kpi-value" style="font-size:1.5rem;">{agente_lider_pct:.1f}%</div>
      <div class="kpi-sub">del volumen total operado</div>
    </div>""", unsafe_allow_html=True)

with k4:
    hhi_color = GREEN if hhi < 1500 else ("#E8A020" if hhi < 2500 else "#E05555")
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-label">concentración · HHI</div>
      <div class="kpi-value" style="color:{hhi_color}; font-size:1.5rem;">{conc_label}</div>
      <div class="kpi-sub">índice {hhi:,.0f} · &lt;1500 baja · &gt;2500 alta</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br><br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SECCIÓN: TORTA + VAR TABLE
# ─────────────────────────────────────────────
st.markdown("""
<div class="section-title">participación <span>por agente</span></div>
<div class="section-underline"></div>
""", unsafe_allow_html=True)

col_pie, col_var = st.columns([55, 45])

with col_pie:
    df_pie = df.groupby("Agente")["Volumen_USD"].sum().reset_index()
    df_pie = df_pie.sort_values("Volumen_USD", ascending=False)
    umbral = vol_total * 0.02
    df_pie["Label"] = df_pie.apply(
        lambda r: r["Agente"] if r["Volumen_USD"] >= umbral else "otros", axis=1)
    df_pie_g = df_pie.groupby("Label")["Volumen_USD"].sum().reset_index()
    df_pie_g = df_pie_g.sort_values("Volumen_USD", ascending=False)

    n = len(df_pie_g)
    import colorsys
    def gen_greens(n):
        cols = []
        for i in range(n):
            h = 0.33
            s = 0.3 + (i / max(n-1,1)) * 0.55
            v = 0.95 - (i / max(n-1,1)) * 0.45
            r,g,b = colorsys.hsv_to_rgb(h, s, v)
            cols.append(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")
        return cols

    colors_pie = gen_greens(n)
    others_idx = df_pie_g[df_pie_g["Label"] == "otros"].index
    for i in others_idx:
        colors_pie[i] = "#CCCCCC"

    fig_pie = go.Figure(go.Pie(
        labels=df_pie_g["Label"],
        values=df_pie_g["Volumen_USD"],
        hole=0.0,
        marker=dict(colors=colors_pie, line=dict(color="white", width=2)),
        textinfo="label+percent",
        textfont=dict(size=11, family="'DM Sans', 'Helvetica Neue', Arial, sans-serif", color=WHITE),
        insidetextorientation="radial",
        hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
        customdata=[fmt_usd(v) for v in df_pie_g["Volumen_USD"]],
    ))
    fig_pie.update_layout(
        showlegend=True,
        legend=dict(
            font=dict(size=10, family="'DM Sans', 'Helvetica Neue', Arial, sans-serif", color=DARK_TEXT),
            orientation="v", x=1, y=0.5,
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=10, t=10, b=10),
        height=360,
        font=CHART_FONT,
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_var:
    st.markdown(f"""
    <div style="font-size:.65rem; font-weight:600; letter-spacing:1.5px;
                text-transform:uppercase; color:{GRAY_TEXT}; margin-bottom:14px;">
      variación por asset category
    </div>
    """, unsafe_allow_html=True)

    def var_pct(asset, d_ini, d_fin, d_prev_ini, d_prev_fin):
        curr = df[(df["Asset_Category"]==asset) & (df["Fecha"]>=d_ini) & (df["Fecha"]<=d_fin)]["Volumen_USD"].sum()
        prev = df[(df["Asset_Category"]==asset) & (df["Fecha"]>=d_prev_ini) & (df["Fecha"]<=d_prev_fin)]["Volumen_USD"].sum()
        if prev == 0: return None
        return (curr - prev) / prev * 100

    def fmt_pct(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return f'<span class="neu">—</span>'
        cls = "pos" if v >= 0 else "neg"
        sign = "+" if v >= 0 else ""
        return f'<span class="{cls}">{sign}{v:.1f}%</span>'

    rows_var = ""
    for asset in sorted(df["Asset_Category"].unique()):
        v30  = var_pct(asset, d30,  max_d, d30 - pd.Timedelta(days=30), d30)
        v60  = var_pct(asset, d60,  max_d, d60 - pd.Timedelta(days=60), d60)
        v365 = var_pct(asset, d365, max_d, d365 - pd.Timedelta(days=365), d365)
        ytd_prev_s = pd.Timestamp(year=max_d.year-1, month=1, day=1)
        ytd_prev_e = pd.Timestamp(year=max_d.year-1, month=max_d.month, day=max_d.day)
        vYTD = var_pct(asset, ytd_s, max_d, ytd_prev_s, ytd_prev_e)
        rows_var += f"""<tr>
          <td>{asset}</td>
          <td>{fmt_pct(v30)}</td>
          <td>{fmt_pct(v60)}</td>
          <td>{fmt_pct(v365)}</td>
          <td>{fmt_pct(vYTD)}</td>
        </tr>"""

    st.markdown(f"""
    <table class="var-table">
      <thead><tr>
        <th>asset</th><th>30d</th><th>60d</th><th>365d</th><th>ytd</th>
      </tr></thead>
      <tbody>{rows_var}</tbody>
    </table>
    """, unsafe_allow_html=True)

st.markdown("<br><br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SECCIÓN: BARRAS FONDO + LÍNEA ASSET
# ─────────────────────────────────────────────
st.markdown("""
<div class="section-title">evolución <span>mensual</span></div>
<div class="section-underline"></div>
""", unsafe_allow_html=True)

col_bar, col_line = st.columns([48, 52])

PLOTLY_BASE = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="DM Sans, Segoe UI, sans-serif", color=DARK_TEXT),
    margin=dict(l=10, r=10, t=36, b=50),
    height=340,
    xaxis=dict(showgrid=False, tickangle=-40, tickfont=dict(size=9, color=GRAY_TEXT)),
    yaxis=dict(gridcolor="#F0F2F0", tickfont=dict(size=9, color=GRAY_TEXT)),
)

with col_bar:
    df_fondo = df.groupby("Fondo")["Volumen_USD"].sum().reset_index()
    df_fondo = df_fondo.sort_values("Volumen_USD", ascending=True)

    fig_bar = go.Figure(go.Bar(
        x=df_fondo["Volumen_USD"],
        y=df_fondo["Fondo"],
        orientation="h",
        marker_color=GREEN,
        marker_line_width=0,
        text=[fmt_usd(v) for v in df_fondo["Volumen_USD"]],
        textposition="outside",
        textfont=dict(size=9, color=GRAY_TEXT,
                      family="'DM Sans', 'Helvetica Neue', Arial, sans-serif"),
    ))
    fig_bar.update_layout(
        title=dict(text="volumen por fondo",
                   font=dict(size=12, color=DARK_TEXT,
                             family="'DM Sans', 'Helvetica Neue', Arial, sans-serif")),
        plot_bgcolor="white", paper_bgcolor="white",
        font=CHART_FONT,
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=10, color=DARK_TEXT,
                                 family="'DM Sans', 'Helvetica Neue', Arial, sans-serif")),
        margin=dict(l=10, r=90, t=36, b=10),
        height=380,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with col_line:
    df_line = (df.groupby(["AñoMes","Asset_Category"])["Volumen_USD"]
                 .sum().reset_index().sort_values("AñoMes"))

    fig_line = px.line(
        df_line, x="AñoMes", y="Volumen_USD",
        color="Asset_Category",
        color_discrete_map=ASSET_COLORS,
        markers=True,
        labels={"Volumen_USD":"", "AñoMes":"", "Asset_Category":""},
    )
    fig_line.update_traces(line=dict(width=2.5), marker=dict(size=5))
    fig_line.update_layout(
        title=dict(text="evolución mensual por asset",
                   font=dict(size=12, color=DARK_TEXT,
                             family="'DM Sans', 'Helvetica Neue', Arial, sans-serif")),
        plot_bgcolor="white", paper_bgcolor="white",
        font=CHART_FONT,
        xaxis=dict(showgrid=False, tickangle=-40,
                   tickfont=dict(size=9, color=GRAY_TEXT,
                                 family="'DM Sans', 'Helvetica Neue', Arial, sans-serif")),
        yaxis=dict(gridcolor="#EDEFED", tickformat="$,.0f",
                   tickfont=dict(size=9, color=GRAY_TEXT,
                                 family="'DM Sans', 'Helvetica Neue', Arial, sans-serif")),
        legend=dict(orientation="h", y=1.14, x=0,
                    font=dict(size=9, family="'DM Sans', 'Helvetica Neue', Arial, sans-serif"),
                    title_text=""),
        margin=dict(l=10, r=10, t=50, b=50),
        height=380,
    )
    st.plotly_chart(fig_line, use_container_width=True)

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown(f"""
<div style="background:{DARK_BG}; margin: 2rem -1rem -1rem -1rem;
            padding: 20px 48px; display:flex; justify-content:space-between; align-items:center;">
  <div style="color:{GREEN}; font-size:.9rem; font-weight:600; letter-spacing:.5px;">
    novus <span style="color:#9AADA9; font-weight:300;">asset management</span>
  </div>
  <div style="color:#555; font-size:.72rem;">
    middle office · datos al {max_date.strftime('%d/%m/%Y')}
  </div>
</div>
""", unsafe_allow_html=True)
