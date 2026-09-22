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
import hmac
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ═══════════════════════════════════════════════════════════════
# PERFIL DE LA INSTANCIA
# ═══════════════════════════════════════════════════════════════
# El mismo repo se despliega DOS veces en Railway y cada servicio define su
# variable NOVUS_APP:
#   · "analytics"  → Flujos & Fondos + Contrapartes  (solo lectura)
#   · "onboarding" → Onboarding                      (escribe sobre el Excel)
# Se separan porque Onboarding es el único módulo que MODIFICA datos: así el
# link de analítica se puede compartir sin dar de baja cuentas por accidente,
# y cada servicio lleva su propia contraseña.
# Sin la variable vale "completo" (los tres módulos), que es como corre en
# local y como venía corriendo hasta ahora: nada se rompe si no se configura.
APP_PERFIL = (os.environ.get("NOVUS_APP") or "completo").strip().lower()
if APP_PERFIL not in ("completo", "analytics", "onboarding"):
    APP_PERFIL = "completo"

TITULO_PESTANA = {
    "completo":   "Novus AM | Dashboards",
    "analytics":  "Novus AM | Dashboards",
    "onboarding": "Novus AM | Onboarding",
}[APP_PERFIL]

# Lo primero que se ve al abrir el link, así que tiene que decir a qué entrás.
SUBTITULO_LOGIN = {
    "completo":   "Dashboards de middle office · acceso restringido",
    "analytics":  "Flujos, fondos y contrapartes · acceso restringido",
    "onboarding": "Onboarding de cuentas · acceso restringido",
}[APP_PERFIL]

st.set_page_config(
    page_title=TITULO_PESTANA,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
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

FONT_FAMILY = "'Quicksand', Arial, sans-serif"
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


# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Quicksand:wght@300;400;500;600;700&display=swap');

  html, body, .stApp {{
      font-family: {FONT_FAMILY} !important;
      background-color: {LIGHT_BG} !important;
      /* El fondo del header usa 100vw, que incluye el ancho de la barra de
         scroll: sin esto aparecería un scroll horizontal de unos píxeles. */
      overflow-x: hidden;
  }}
  /* Excepción al font-family de arriba: los iconos de Streamlit son
     ligaduras de la fuente Material Symbols. Si les imponemos Quicksand,
     la ligadura no resuelve y se ve el nombre del icono como texto
     ("logout" en vez del dibujito). */
  span[data-testid="stIconMaterial"],
  [class*="material-symbols"] {{
      font-family: 'Material Symbols Rounded', 'Material Symbols Outlined',
                   'Material Icons' !important;
  }}

  /* ── HERO ── */
  .novus-hero {{
      background: linear-gradient(135deg, {DARK_BG} 0%, #162416 100%);
      padding: 26px var(--novus-pad) 24px;
      margin: -1rem calc(-1 * var(--novus-pad)) 1.1rem calc(-1 * var(--novus-pad));
      border-radius: 0 0 12px 12px;
  }}
  .novus-eyebrow {{
      font-size: .68rem; font-weight: 700; letter-spacing: 2px;
      color: {GREEN}; text-transform: uppercase; margin-bottom: 6px;
  }}
  .novus-hero h1 {{ font-size: 1.8rem; font-weight: 300; color: {WHITE}; margin: 0 0 4px; }}
  /* Streamlit envuelve TODO el contenido del h1 en un <span> propio (para
     el link de anclaje del encabezado). Si el selector fuera "h1 span" a
     secas, pintaría ese span envolvente entero de verde en vez de solo la
     palabra resaltada — por eso apunta a un span ANIDADO (el nuestro). */
  .novus-hero h1 span span {{ color: {GREEN}; font-weight: 700; }}
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
  /* Fuera el circulito del radio. OJO con el selector: el primer hijo del
     label es un <span> oculto, no el círculo, así que `label > div:first-child`
     no pega nunca. El círculo cuelga dos niveles más abajo. */
  div[role="radiogroup"] label > div:first-child,
  div[role="radiogroup"] label[data-testid="stRadioOption"] > div > div > div:first-child {{
      display: none !important;
  }}

  /* ── KPI CARDS ── */
  .kpi-card {{
      background: {WHITE}; border-radius: 10px; padding: 15px 18px;
      border: 1px solid {BORDER}; box-shadow: 0 1px 4px rgba(0,0,0,.02);
      height: 100%;
  }}
  /* El height:100% de la tarjeta no llega a resolverse por la cadena de
     contenedores que Streamlit mete en medio, y las tarjetas de una misma
     fila quedaban de alturas distintas según cuánto texto tuviera cada una.
     Un min-height las nivela sin depender de esos contenedores internos.
     (En celular se apilan, así que ahí no hace falta.) */
  @media (min-width: 781px) {{
      .kpi-card {{ min-height: 104px; }}
      /* La cadena de descomposición es más compacta: solo etiqueta y valor. */
      div.st-key-novus_cadena .kpi-card {{ min-height: 72px; }}
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

  /* ── BARRA DE FILTRO DE ETAPA (chips) ── */
  /* Encabezado de la tabla: el total a la izquierda y, a la derecha, en qué
     etapa se está parado. Reemplaza la etiqueta suelta "N cuentas ...". */
  .onb-bar {{
      display: flex; align-items: baseline; justify-content: space-between;
      gap: 12px; flex-wrap: wrap; margin: 2px 0 10px;
      padding-bottom: 9px; border-bottom: 1px solid {BORDER};
  }}
  .onb-bar .tot {{ font-size: .95rem; font-weight: 700; color: {DARK_TEXT}; }}
  .onb-bar .tot span {{
      font-size: .63rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 1px; color: {GRAY_TEXT}; margin-left: 6px;
  }}
  .onb-bar .ctx {{ font-size: .74rem; color: {GRAY_TEXT}; }}
  .onb-bar .ctx b {{ color: {GREEN_DIM}; font-weight: 600; }}

  /* Los chips son un radio de Streamlit: se estilan por el contenedor con
     key, así no se pisa el resto de los radios de la app. */
  div[class*="st-key-"][class*="_chip"] div[role="radiogroup"] {{
      gap: 7px !important; margin-bottom: 2px;
  }}
  /* Streamlit deja el label en display:block, así que el badge del ::after
     caía a un renglón propio y el chip medía 57px de alto. En flex, texto y
     contador quedan en la misma línea. */
  div[class*="st-key-"][class*="_chip"] div[role="radiogroup"] label {{
      background: {WHITE}; border: 1px solid {BORDER}; border-radius: 8px;
      padding: 6px 13px !important; font-size: .76rem !important;
      box-shadow: 0 1px 2px rgba(0,0,0,.03);
      display: flex !important; align-items: center !important;
  }}
  div[class*="st-key-"][class*="_chip"] div[role="radiogroup"] label:hover {{
      border-color: {GREEN}; background: #F6FBF6;
  }}
  div[class*="st-key-"][class*="_chip"] div[role="radiogroup"] label:has(input:checked) {{
      background: {DARK_BG} !important; border-color: {DARK_BG} !important;
      box-shadow: 0 2px 6px rgba(26,28,26,.18);
  }}
  /* El contador de cada chip va por ::after. El número NO puede ir en el
     texto de la opción: cambia con cada alta o baja y el valor guardado en
     session_state dejaría de existir entre los options, que es justo lo que
     hace explotar a st.radio. Así que el estilo del badge vive acá y el
     número lo inyecta _css_conteo_chips() como reglas :nth-child. */
  div[class*="st-key-"][class*="_chip"] div[role="radiogroup"] label::after {{
      display: none; margin-left: 8px; padding: 1px 6px;
      border-radius: 5px; background: {LIGHT_BG}; color: {GRAY_TEXT};
      font-size: .68rem; font-weight: 700; font-variant-numeric: tabular-nums;
  }}
  div[class*="st-key-"][class*="_chip"] div[role="radiogroup"]
      label:has(input:checked)::after {{
      background: rgba(93,187,99,.18); color: {GREEN};
  }}

  /* El selector de página ocupaba una fila entera para un número de dos
     dígitos: se acota el ancho y se achica la etiqueta. */
  div[class*="st-key-"][class*="_pag_box"] {{ margin: -2px 0 6px; }}
  div[class*="st-key-"][class*="_pag_box"] div[data-testid="stNumberInput"] {{
      max-width: 168px;
  }}
  div[class*="st-key-"][class*="_pag_box"] label p {{
      font-size: .68rem !important; color: {GRAY_TEXT} !important;
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

  /* ── STEPPER DE ETAPA (onboarding) ── */
  /* El color de cada nodo/línea se pisa inline por paso (ver _stepper_html);
     estas reglas son solo el look base para los pasos todavía no alcanzados. */
  /* El stepper y el nombre de la etapa van uno al lado del otro. Apilados,
     la celda crecía a dos renglones y la fila quedaba alta y vacía. */
  .etapa-wrap {{ display: flex; align-items: center; gap: 10px; min-width: 0; }}
  .novus-stepper {{
      display: flex; align-items: center; gap: 0; flex: none; width: 104px;
  }}
  .novus-stepper .nodo {{
      width: 7px; height: 7px; border-radius: 50%; background: #e5e7eb; flex: none;
  }}
  .novus-stepper .linea {{ flex: 1 1 auto; height: 2px; background: #e5e7eb; min-width: 6px; }}
  /* El nombre de la etapa como pastilla tenue del color del paso: se lee de
     un vistazo sin que el color grite. */
  .etapa-tag {{
      font-size: .72rem; font-weight: 600; padding: 2px 9px; border-radius: 20px;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
  }}
  .etapa-paso {{ font-size: .68rem; color: {GRAY_TEXT}; flex: none; }}

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

  /* ── BOTONES ──
     Streamlit 1.4x+ usa data-testid="stBaseButton-*" para todos los botones
     (secondary, primary, formSubmit, download). Cubrir solo .stButton no alcanza. */
  button[data-testid="stBaseButton-secondary"],
  button[data-testid="stBaseButton-primary"],
  button[data-testid="stBaseButton-secondaryFormSubmit"],
  button[data-testid="stBaseButton-primaryFormSubmit"],
  .stDownloadButton button, .stButton button {{
      background: {DARK_BG} !important; color: {GREEN} !important;
      border: 1px solid rgba(93,187,99,.4) !important; border-radius: 8px !important;
      font-size: .78rem !important; font-weight: 600 !important; padding: 6px 16px !important;
      transition: all .15s;
  }}
  button[data-testid="stBaseButton-secondary"]:hover,
  button[data-testid="stBaseButton-primary"]:hover,
  button[data-testid="stBaseButton-secondaryFormSubmit"]:hover,
  button[data-testid="stBaseButton-primaryFormSubmit"]:hover,
  .stDownloadButton button:hover, .stButton button:hover {{
      background: {GREEN_DIM} !important; color: {WHITE} !important; border-color: {GREEN} !important;
  }}

  /* Los dos botones de cada fila de onboarding eran dos cuadrados negros
     idénticos: pesaban más que el dato y no distinguían editar de borrar.
     Van en versión fantasma, y el color aparece recién al pasar el mouse
     (verde para editar, rojo para eliminar). */
  div[class*="st-key-"][class*="_edit_"] button,
  div[class*="st-key-"][class*="_del_"] button {{
      background: transparent !important; border: 1px solid transparent !important;
      color: {GRAY_TEXT} !important; padding: 4px 8px !important;
      min-height: 0 !important; opacity: .55; transition: all .12s;
  }}
  div[data-testid="stHorizontalBlock"]:has(.fila-onb):hover
      div[class*="st-key-"][class*="_edit_"] button,
  div[data-testid="stHorizontalBlock"]:has(.fila-onb):hover
      div[class*="st-key-"][class*="_del_"] button {{ opacity: 1; }}
  div[class*="st-key-"][class*="_edit_"] button:hover {{
      background: rgba(93,187,99,.12) !important;
      border-color: rgba(93,187,99,.45) !important; opacity: 1;
  }}
  div[class*="st-key-"][class*="_del_"] button {{ font-size: .95rem !important; }}
  div[class*="st-key-"][class*="_del_"] button:hover {{
      background: rgba(224,85,85,.12) !important; color: {RED} !important;
      border-color: rgba(224,85,85,.45) !important; opacity: 1;
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

  /* ── PANTALLA DE LOGIN ── */
  .login-card {{
      background: linear-gradient(135deg, {DARK_BG} 0%, #162416 100%);
      border-radius: 14px; padding: 30px 32px 26px; margin: 8vh 0 18px;
      text-align: center;
  }}
  .login-eyebrow {{
      font-size: .62rem; font-weight: 700; letter-spacing: 2.2px;
      color: {GREEN}; text-transform: uppercase; margin-bottom: 10px;
  }}
  .login-title {{ font-size: 1.35rem; font-weight: 700; color: {GREEN}; line-height: 1.2; }}
  .login-title span {{ color: #9AADA9; font-weight: 300; }}
  .login-sub {{ font-size: .78rem; color: #9AADA9; margin-top: 6px; }}
  .login-err {{
      background: #FFF0F0; border-left: 3px solid {RED}; border-radius: 6px;
      padding: 8px 12px; font-size: .76rem; color: #A03030; font-weight: 600; margin-top: 10px;
  }}
  .login-foot {{ font-size: .7rem; color: {GRAY_TEXT}; text-align: center; margin-top: 16px; }}
  div[data-testid="stForm"] {{ border: none !important; padding: 0 !important; }}

  /* Input de contraseña: se estiliza el CONTENEDOR, no el <input>.
     Poner padding/borde en el <input> rompe el flex interno de Streamlit
     y el campo colapsa a ~30px de ancho. */
  div[data-testid="stTextInputRootElement"] {{
      background: {WHITE} !important;
      border: 1px solid {BORDER} !important;
      border-radius: 8px !important;
  }}
  div[data-testid="stTextInputRootElement"]:focus-within {{
      border-color: {GREEN} !important;
      box-shadow: 0 0 0 2px rgba(93,187,99,.15) !important;
  }}
  .stTextInput input {{
      flex: 1 1 auto !important; min-width: 0 !important;
      background: transparent !important; border: none !important; box-shadow: none !important;
      padding: 11px 6px 11px 14px !important; font-size: .88rem !important;
      color: {DARK_TEXT} !important;
  }}
  .stTextInput input::placeholder {{ color: #A8B0AA !important; }}

  /* El botón de submit del form viene ajustado al texto: hay que estirar
     toda la cadena de contenedores, no solo el <button>. */
  div[data-testid="stForm"] div[data-testid="stElementContainer"]:has([data-testid="stFormSubmitButton"]),
  div[data-testid="stForm"] div[data-testid="stElementContainer"]:has([data-testid="stFormSubmitButton"]) > div,
  div[data-testid="stFormSubmitButton"] {{
      width: 100% !important;
  }}
  div[data-testid="stFormSubmitButton"] button {{ width: 100% !important; padding: 10px 16px !important; }}

  /* ── ANCHO COMPLETO, SIN SIDEBAR ── */
  :root {{ --novus-pad: clamp(16px, 3vw, 48px); }}
  section[data-testid="stSidebar"],
  [data-testid="collapsedControl"] {{ display: none !important; }}
  .block-container {{
      padding-top: 0 !important; padding-bottom: 1.5rem !important;
      max-width: 100% !important;
      padding-left: var(--novus-pad) !important; padding-right: var(--novus-pad) !important;
  }}

  /* ── HEADER SUPERIOR (marca · pestañas · sesión) ── */
  /* El fondo oscuro se pinta con un pseudo-elemento de 100vw en vez de
     estirar el container: los contenedores de Streamlit son flex items con
     width:100% y volvían a encoger la barra, dejando una franja clara
     sobre el borde derecho. Con 100vw el fondo siempre llega punta a punta. */
  div.st-key-novus_header {{
      position: relative;
      padding: 10px 0 0;
      margin-bottom: 1.1rem;
      align-items: stretch !important;
  }}
  div.st-key-novus_header::before {{
      content: ""; position: absolute; top: 0; bottom: 0;
      left: 50%; transform: translateX(-50%); width: 100vw;
      background: linear-gradient(135deg, {DARK_BG} 0%, #162416 100%);
      z-index: 0;
  }}
  div.st-key-novus_header > * {{ position: relative; z-index: 1; }}
  /* La fila tiene que ocupar todo el ancho: si se encoge al contenido, las
     3 columnas quedan corridas y las pestañas no caen en el centro real. */
  div.st-key-novus_header [data-testid="stHorizontalBlock"] {{
      width: 100% !important; align-items: stretch;
  }}
  /* Las tres zonas a la misma altura: las columnas de Streamlit colapsan
     cuando el contenido es texto corto y quedaban desalineadas por píxeles. */
  div.st-key-novus_header [data-testid="stColumn"] {{
      display: flex; align-items: center; min-height: 56px;
  }}
  div.st-key-novus_header [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {{
      width: 100%;
      /* Es un flex en columna: esto centra el contenido verticalmente, que
         es lo que faltaba para que marca, pestañas y sesión queden a la
         misma altura en vez de cada una a la suya. */
      justify-content: center;
  }}
  .header-brand {{ font-size: .98rem; font-weight: 700; color: {WHITE}; white-space: nowrap; }}
  .header-brand span.sub {{ color: #9AADA9; font-weight: 300; }}
  .header-badge {{
      display: inline-block; margin-left: 10px; border: 1px solid rgba(93,187,99,.4);
      border-radius: 20px; padding: 2px 10px; font-size: .62rem; font-weight: 600;
      letter-spacing: 1px; text-transform: uppercase; color: {GREEN}; vertical-align: middle;
  }}
  .header-access {{ font-size: .68rem; color: #7A857D; white-space: nowrap; }}
  /* Estado de sesión y botón de salir en UNA línea, pegados a la derecha y
     centrados con la marca: apilados quedaban el texto arriba del todo y el
     botón flotando al medio, con los bordes derechos desparejos. */
  div.st-key-novus_header [data-testid="stColumn"]:last-child > [data-testid="stVerticalBlock"] {{
      flex-direction: row !important;
      align-items: center !important;
      justify-content: flex-end !important;
      flex-wrap: wrap;
      gap: 10px;
  }}
  div.st-key-novus_header [data-testid="stColumn"]:last-child [data-testid="stElementContainer"] {{
      width: auto !important;
  }}
  div.st-key-novus_header div[data-testid="stColumn"]:last-child .stButton {{ width: auto; }}
  /* Botón de salir: cuadrado, solo icono, discreto. */
  div.st-key-novus_header div[data-testid="stColumn"]:last-child button {{
      background: transparent !important; color: #9AADA9 !important;
      border: 1px solid rgba(255,255,255,.16) !important;
      padding: 4px 8px !important; min-height: 32px !important;
      font-size: .72rem !important; line-height: 1 !important;
  }}
  div.st-key-novus_header div[data-testid="stColumn"]:last-child button:hover {{
      color: {WHITE} !important; border-color: rgba(255,255,255,.35) !important; background: transparent !important;
  }}

  /* ── SELECTOR DE MÓDULO COMO PESTAÑAS, AL CENTRO DEL HEADER ── */
  /* El bloque de Streamlit no estira a sus hijos, así que el radio medía
     el ancho de las pestañas y el justify-content:center no tenía espacio
     que repartir: las pestañas quedaban corridas a la izquierda. */
  div.st-key-novus_topnav {{ align-items: stretch !important; }}
  div.st-key-novus_topnav [data-testid="stElementContainer"],
  div.st-key-novus_topnav div[data-testid="stRadio"] {{ width: 100% !important; }}
  div.st-key-novus_topnav div[data-testid="stRadio"] > label {{ display: none !important; }}
  div.st-key-novus_topnav div[role="radiogroup"] {{
      width: 100% !important;
      gap: 4px !important; flex-wrap: nowrap !important; flex-direction: row !important;
      justify-content: center !important;
  }}
  div.st-key-novus_topnav div[role="radiogroup"] label {{
      background: transparent !important;
      border: none !important;
      border-bottom: 3px solid transparent !important;
      border-radius: 0 !important;
      padding: 16px 20px !important;
      margin: 0 !important;
      font-size: .88rem !important; font-weight: 600 !important;
      letter-spacing: 0 !important; text-transform: none !important;
      color: #9AADA9 !important;
      transition: all .15s;
      white-space: nowrap;
  }}
  /* El texto de cada pestaña vive en un <p> interno que Streamlit pinta
     con su propio color por defecto (oscuro), que pisa la herencia del
     <label> — sin esto, el texto queda invisible sobre el header oscuro. */
  div.st-key-novus_topnav div[role="radiogroup"] label div,
  div.st-key-novus_topnav div[role="radiogroup"] label p {{
      color: #9AADA9 !important;
  }}
  div.st-key-novus_topnav div[role="radiogroup"] label:hover {{ color: {WHITE} !important; }}
  div.st-key-novus_topnav div[role="radiogroup"] label:hover div,
  div.st-key-novus_topnav div[role="radiogroup"] label:hover p {{
      color: {WHITE} !important;
  }}
  div.st-key-novus_topnav div[role="radiogroup"] label:has(input:checked) {{
      border-bottom-color: {GREEN} !important;
  }}
  div.st-key-novus_topnav div[role="radiogroup"] label:has(input:checked) div,
  div.st-key-novus_topnav div[role="radiogroup"] label:has(input:checked) p {{
      color: {GREEN} !important; font-weight: 700 !important;
  }}
  /* Fuera el circulito del radio: son pestañas, no una lista de opciones.
     El primer hijo del label es un <span> con el input escondido, así que
     un "label > div:first-child" no lo agarraba nunca — el círculo es el
     primer div de la fila interna. */
  div.st-key-novus_topnav label[data-testid="stRadioOption"] > div > div > div:first-child {{
      display: none !important;
  }}

  /* ── MENÚ HAMBURGUESA (solo pantallas chicas) ──
     Es un st.popover: el botón queda como la hamburguesa y el panel que
     abre tiene el radio de módulos. En desktop está escondido. */
  div.st-key-novus_hamburguesa {{ display: none; }}
  div.st-key-novus_hamburguesa button {{
      background: rgba(255,255,255,.06) !important;
      color: {WHITE} !important;
      border: 1px solid rgba(93,187,99,.45) !important;
      border-radius: 8px !important;
      font-size: .85rem !important; font-weight: 600 !important;
      padding: 8px 14px !important; width: 100% !important;
      justify-content: flex-start !important;
  }}
  div.st-key-novus_hamburguesa button p {{ color: {WHITE} !important; font-weight: 600 !important; }}
  div.st-key-novus_hamburguesa button:hover {{
      border-color: {GREEN} !important; background: rgba(93,187,99,.14) !important;
  }}
  /* El panel del popover: las opciones como lista vertical, no pills */
  div[data-testid="stPopoverBody"] div[role="radiogroup"] {{
      flex-direction: column !important; gap: 4px !important;
  }}
  div[data-testid="stPopoverBody"] div[role="radiogroup"] label {{
      width: 100%; border-radius: 8px !important; padding: 9px 14px !important;
  }}

  /* ── BOTONES DEL MODAL ──
     Ocupan todo el ancho de su columna: así quedan del mismo tamaño y
     alineados entre sí, en vez de dos botones sueltos de ancho distinto. */
  div[data-testid="stDialog"] div[data-testid="stColumn"] .stButton,
  div[data-testid="stDialog"] div[data-testid="stColumn"] .stButton button {{
      width: 100% !important;
  }}

  /* ── TABLAS ANCHAS ──
     Cualquier tabla HTML propia scrollea sola en horizontal antes de
     romper el layout de la página en pantallas chicas. */
  .tabla-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}

  /* ── FILA DE LA TABLA DE ONBOARDING ──
     Grid propio de 4 celdas: en pantalla grande van una al lado de la otra
     y en celular pasa a una sola columna, mostrando la etiqueta de cada
     campo (data-label) que en desktop la da el encabezado. */
  .fila-onb {{
      display: grid;
      grid-template-columns: 2.8fr 2.4fr 2fr;
      gap: 16px; align-items: center; min-height: 34px;
      font-size: .82rem; color: {DARK_TEXT};
      border-bottom: 1px solid #F0F2F0;
  }}
  .fila-onb .celda {{ min-width: 0; overflow-wrap: anywhere; }}
  /* Marca de excepción al lado de la contraparte: una cuenta cuyo tipo no es
     el de la pestaña ("Exterior" entre remuneradas) o que no lo tiene cargado. */
  .tag-excep {{
      display: inline-block; margin-left: 7px; padding: 1px 7px; border-radius: 20px;
      font-size: .64rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: .4px; color: {AMBER}; background: rgba(232,160,32,.14);
      vertical-align: middle;
  }}
  .fila-onb .celda::before {{ content: attr(data-label); display: none; }}
  .fila-onb-encab {{
      border-bottom: 1px solid {BORDER}; min-height: 0; padding-bottom: 5px;
      font-size: .63rem; font-weight: 700; letter-spacing: 1px;
      text-transform: uppercase; color: {GRAY_TEXT};
  }}
  /* Resaltado de fila completa. Tiene que ir sobre el bloque horizontal —no
     sobre .fila-onb— porque los botones viven en columnas aparte y si no el
     resaltado se cortaría justo antes de ellos. */
  div[data-testid="stHorizontalBlock"]:has(.fila-onb) {{
      border-radius: 6px; transition: background .12s;
  }}
  div[data-testid="stHorizontalBlock"]:has(.fila-onb):hover {{ background: #F7F9F7; }}

  /* ═══════════════ RESPONSIVE ═══════════════ */
  /* Notebook / tablet horizontal */
  @media (max-width: 1250px) {{
      :root {{ --novus-pad: 22px; }}
      .novus-hero h1 {{ font-size: 1.5rem; }}
      .kpi-value {{ font-size: 1.3rem; }}
      .kpi-value.sm {{ font-size: 1.08rem; }}
      div.st-key-novus_topnav div[role="radiogroup"] label {{
          padding: 13px 12px !important; font-size: .81rem !important;
      }}
      .var-table {{ font-size: .74rem; }}
      /* La cadena de 11 columnas no entra: se esconden los signos y las
         tarjetas se reparten en varias filas en vez de partir palabras. */
      div.st-key-novus_cadena [data-testid="stHorizontalBlock"] {{
          flex-wrap: wrap !important; row-gap: 10px;
      }}
      div.st-key-novus_cadena div[data-testid="stColumn"] {{
          flex: 1 1 30% !important; min-width: 150px !important;
      }}
      div.st-key-novus_cadena div[data-testid="stColumn"]:nth-child(even) {{
          display: none !important;
      }}
      .cadena-op {{ display: none !important; }}
  }}

  /* Header apilado: la marca, las 3 pestañas y el estado de sesión no
     conviven en una sola línea por debajo de ~1000px (el badge se montaba
     encima de las pestañas). */
  @media (max-width: 1000px) {{
      div.st-key-novus_header {{ padding: 12px 0 10px; }}
      div.st-key-novus_header [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
      div.st-key-novus_header div[data-testid="stColumn"] {{
          min-width: 100% !important; flex: 1 1 100% !important;
      }}
      div.st-key-novus_header div[data-testid="stColumn"]:last-child {{
          align-items: center !important; margin-top: 4px;
      }}
      .header-brand {{ text-align: center; font-size: .92rem; }}
      .header-access {{ text-align: center; margin-bottom: 4px; }}
      div.st-key-novus_header [data-testid="stColumn"] {{
          min-height: 0; justify-content: center;
      }}
      /* Acá las pestañas en línea dejan lugar a la hamburguesa */
      div.st-key-novus_topnav {{ display: none !important; }}
      div.st-key-novus_hamburguesa {{ display: block; }}
  }}

  /* Celular */
  @media (max-width: 780px) {{
      :root {{ --novus-pad: 14px; }}
      .novus-hero {{ padding: 18px var(--novus-pad) 16px; }}
      .novus-hero h1 {{ font-size: 1.22rem; }}
      .novus-hero p {{ font-size: .78rem; }}
      .section-title {{ font-size: 1rem; }}
      .kpi-card {{ padding: 12px 14px; }}
      .kpi-value {{ font-size: 1.18rem; }}
      .kpi-value.sm {{ font-size: 1rem; }}
      .var-table {{ font-size: .7rem; }}
      .var-table th, .var-table td {{ padding: 6px 4px; }}
      /* Apiladas de a una, las tarjetas de la cadena van a ancho completo */
      div.st-key-novus_cadena div[data-testid="stColumn"] {{
          flex: 1 1 100% !important;
      }}

      /* ── TABLA DE ONBOARDING EN CELULAR ──
         La fila pasa a una sola columna y cada campo muestra su etiqueta
         (el encabezado se esconde porque ya no alinea nada). */
      .fila-onb {{
          grid-template-columns: 1fr; gap: 2px;
          padding: 8px 0; min-height: 0;
      }}
      .fila-onb .celda::before {{
          display: inline-block; min-width: 78px; font-size: .58rem; font-weight: 700;
          letter-spacing: .8px; text-transform: uppercase; color: {GRAY_TEXT};
      }}
      /* Esconder solo el .fila-onb-encab dejaba su contenedor de columnas
         vacío pero ocupando lugar: una caja gris arriba de la primera fila.
         Se esconde el bloque entero. */
      div[class*="st-key-"][class*="_encab"] {{ display: none !important; }}
      /* Editar y eliminar, uno al lado del otro. Streamlit apila TODAS las
         columnas a ancho completo en celular y cada botón se comía un
         renglón propio. */
      div[data-testid="stHorizontalBlock"]:has(.fila-onb)
          > div[data-testid="stColumn"]:not(:first-child) {{
          flex: 0 0 auto !important; width: auto !important; min-width: 0 !important;
      }}
      div[class*="st-key-"][class*="_edit_"] button,
      div[class*="st-key-"][class*="_del_"] button {{ opacity: 1; }}
  }}

  #MainMenu, footer, header {{ visibility: hidden; height: 0; }}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# ACCESO — contraseña compartida
# ═══════════════════════════════════════════════════════════════
# La clave NUNCA va en el código. Se configura en:
#   Streamlit Cloud → tu app → Settings → Secrets → pegar:  app_password = "tu-clave"
# Para correr local, en .streamlit/secrets.toml (ese archivo está en .gitignore).
def _clave_configurada():
    try:
        v = st.secrets.get("app_password")
        if v:
            return str(v)
    except Exception:
        pass
    return os.environ.get("NOVUS_APP_PASSWORD") or None


# La contraseña es OPCIONAL y se activa sola.
#   · Si NO hay `app_password` en los Secrets  → la app abre directo, sin pedir nada.
#   · Si algún día se agrega `app_password`    → la pantalla de login se activa
#     automáticamente en el próximo reinicio, sin tocar una línea de código.
AUTH_ACTIVA = bool(_clave_configurada())


def login_gate():
    """Devuelve True solo si el visitante ingresó la contraseña correcta."""
    if st.session_state.get("_auth_ok"):
        return True

    clave = _clave_configurada()
    _, mid, _ = st.columns([1, 1.15, 1])
    with mid:
        st.markdown(
            '<div class="login-card">'
            '<div class="login-eyebrow">middle office</div>'
            '<div class="login-title">novus <span>asset management</span></div>'
            f'<div class="login-sub">{SUBTITULO_LOGIN}</div>'
            '</div>', unsafe_allow_html=True)

        if not clave:
            st.error("Falta configurar la contraseña de acceso.")
            st.markdown('<div class="note">En Streamlit Cloud: <b>Settings → Secrets</b> '
                        'y pegá esta línea:</div>', unsafe_allow_html=True)
            st.code('app_password = "la-clave-que-elijas"', language="toml")
            return False

        with st.form("login_form", clear_on_submit=False):
            ingresada = st.text_input("Contraseña", type="password",
                                      label_visibility="collapsed",
                                      placeholder="Contraseña de acceso")
            enviado = st.form_submit_button("Ingresar")

        if enviado:
            # compare_digest evita filtrar la clave por diferencias de tiempo
            if hmac.compare_digest(str(ingresada), clave):
                st.session_state["_auth_ok"] = True
                st.session_state.pop("_intentos", None)
                st.rerun()
            else:
                st.session_state["_intentos"] = st.session_state.get("_intentos", 0) + 1

        fallos = st.session_state.get("_intentos", 0)
        if fallos:
            extra = f" · {fallos} intentos fallidos" if fallos > 1 else ""
            st.markdown(f'<div class="login-err">Contraseña incorrecta{extra}</div>',
                        unsafe_allow_html=True)

        st.markdown('<div class="login-foot">Si no tenés la clave, pedila a Lucila Sancci '
                    '· Middle Office Novus AM</div>', unsafe_allow_html=True)
    return False


# Con contraseña configurada, nada de lo que sigue (ni la lectura del CSV) se
# ejecuta sin autenticar. Sin contraseña configurada, la app abre normalmente.
if AUTH_ACTIVA and not login_gate():
    st.stop()

# ═══════════════════════════════════════════════════════════════
# NAVEGACIÓN
# ═══════════════════════════════════════════════════════════════
# Nombres sin emoji: en un dashboard financiero se leían informales y cada
# navegador/resolución los dibuja de un tamaño distinto.
M_DASH = "Contrapartes"
M_CTAS = "Onboarding"
M_FCI  = "Flujos & Fondos"

# Sin sidebar: todo el header vive en una sola barra oscura arriba, con
# marca a la izquierda, pestañas al centro y sesión a la derecha. El
# key="novus_header" del container es lo que el CSS usa para pintar la
# barra full-bleed (ver "HEADER SUPERIOR" en el bloque de estilos).
# Qué módulos sirve ESTA instancia (ver APP_PERFIL arriba de todo).
MODULOS = {
    "completo":   [M_FCI, M_DASH, M_CTAS],
    "analytics":  [M_FCI, M_DASH],
    "onboarding": [M_CTAS],
}[APP_PERFIL]
# Con un solo módulo no hay nada que navegar: la barra de pestañas se omite
# entera (no se dibuja una pestaña única ni un menú de un solo ítem).
HAY_NAV = len(MODULOS) > 1

# Hay DOS navegadores para el mismo estado: las pestañas en línea (desktop)
# y un menú hamburguesa (celular/tablet). El CSS muestra uno solo según el
# ancho; los dos escriben en "modulo_actual", que es la única fuente de
# verdad, y cada uno sincroniza al otro para que nunca queden desfasados.
# El chequeo contra MODULOS evita que una sesión vieja (con los nombres
# anteriores guardados) le pase al radio un valor que ya no existe.
# MODULOS[0] y no M_FCI: en la instancia de Onboarding ese módulo no existe
# y dejaría la sesión apuntando a algo que esta instancia no sirve.
if st.session_state.get("modulo_actual") not in MODULOS:
    st.session_state["modulo_actual"] = MODULOS[0]
for _k in ("nav_pills", "nav_movil"):
    if st.session_state.get(_k) not in MODULOS:
        st.session_state[_k] = st.session_state["modulo_actual"]


def _nav_desde_pills():
    v = st.session_state["nav_pills"]
    st.session_state["modulo_actual"] = v
    st.session_state["nav_movil"] = v


def _nav_desde_movil():
    v = st.session_state["nav_movil"]
    st.session_state["modulo_actual"] = v
    st.session_state["nav_pills"] = v


with st.container(key="novus_header"):
    hc1, hc2, hc3 = st.columns([1.1, 2, 1.1], vertical_alignment="center")
    with hc1:
        st.markdown(
            '<div class="header-brand">novus <span class="sub">asset management</span>'
            '<span class="header-badge">middle office</span></div>',
            unsafe_allow_html=True)
    with hc2:
        if HAY_NAV:
            # Desktop: pestañas en línea.
            with st.container(key="novus_topnav"):
                st.radio("Navegación", MODULOS, horizontal=True,
                         label_visibility="collapsed", key="nav_pills",
                         on_change=_nav_desde_pills)
            # Celular/tablet: hamburguesa. El label muestra el módulo actual,
            # así se sabe dónde se está parado con el menú cerrado.
            with st.container(key="novus_hamburguesa"):
                with st.popover(f"☰   {st.session_state['modulo_actual']}"):
                    st.radio("Ir a", MODULOS, label_visibility="collapsed",
                             key="nav_movil", on_change=_nav_desde_movil)
    with hc3:
        # Texto corto: en el header conviven con el botón de salir, y
        # "acceso · protegido con contraseña" apretaba todo contra el borde.
        st.markdown(
            '<div class="header-access"><span style="color:#5DBB63">🔒 sesión protegida</span></div>'
            if AUTH_ACTIVA else
            '<div class="header-access"><span style="color:#E8A020">⚠ sin contraseña</span></div>',
            unsafe_allow_html=True)
        if AUTH_ACTIVA:
            # Compacto y discreto: se usa una vez por día y como botón con
            # texto largo se comía el header. El icono va por el parámetro
            # `icon` — puesto en la etiqueta, Streamlit lo imprime literal.
            if st.button("Salir", icon=":material/logout:", key="logout_header",
                         help="Cerrar sesión"):
                for k in ("_auth_ok", "_intentos"):
                    st.session_state.pop(k, None)
                st.rerun()

modulo = st.session_state["modulo_actual"]

# ═══════════════════════════════════════════════════════════════
# Se resuelve el módulo 2 primero y se corta con st.stop(), así el
# dashboard queda sin indentar y sin un solo cambio respecto de la
# versión ya probada.
# ═══════════════════════════════════════════════════════════════
if modulo == M_CTAS:
    # ═══════════════════════════════════════════════════════════════
    # MÓDULO 2 — APERTURA Y SEGUIMIENTO DE CUENTAS FCI
    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCIA: el Excel vive en una rama `data` del repo privado,
    # NO en el disco del contenedor. Streamlit Cloud reconstruye el
    # contenedor desde GitHub en cada reboot, así que cualquier archivo
    # escrito en disco se pierde. Escribir a GitHub es lo único que
    # sobrevive, y encima deja historial versionado de cada cambio.
    #
    # Configuración (Streamlit Cloud → Settings → Secrets):
    #     app_password = "..."
    #     github_token = "github_pat_..."     # fine-grained, Contents: Read+Write
    #     github_repo  = "lsancci-ops/Novus-Dashboard"
    #     github_branch = "data"              # opcional, default "data"
    #
    # Sin github_token la pantalla funciona en SOLO LECTURA y lo avisa,
    # en lugar de fingir que guarda.
    # ═══════════════════════════════════════════════════════════════
    import base64
    import json
    import urllib.error
    import urllib.request

    XLS_NAME   = "seguimiento_cuentas.xlsx"
    XLS_LOCAL  = os.path.join(os.path.dirname(os.path.abspath(__file__)), XLS_NAME)
    HOJA_COM   = "Cuentas comitentes"
    HOJA_REM   = "Cuentas remuneradas"
    HOJA_FCI   = "Lista FCI"
    HOJA_PRE   = "Préstamos de títulos"
    ESTADOS    = ["En proceso", "Abierta", "Rechazada", "De baja"]

    # ── PRÉSTAMOS DE TÍTULOS ────────────────────────────────────────
    # Venían de un Excel aparte con dos hojas ("Vigentes" / "Vencidos") que
    # obligaba a mover filas a mano al vencer. Acá es UNA sola hoja con una
    # columna Estado: el vencimiento sale de la fecha y la app avisa.
    CSV_PRE    = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "prestamos_titulos.csv")
    ESTADOS_PRE = ["Vigente", "Renovado", "Cobrado", "Cancelado", "Vencido"]
    # Se carga a mano                    ↓
    PRE_ENTRADA = ["Concertación", "Liquidación", "Deudor", "Fondo", "Contraparte",
                   "Especie", "Cantidad", "Tasa", "Precio", "Estado", "Observaciones"]
    # Fórmulas del Excel original, verificadas contra los datos con desvío cero.
    # No se editan: se recalculan en cada carga y antes de guardar.
    PRE_CALCULO = ["Plazo", "Monto", "Tasa Aplicada", "Interés", "Interés Diario",
                   "Ajuste", "A Cobrar"]
    # Sello de cuándo se actualizaba el archivo de vencidos. Queda para no
    # perder el histórico, pero el alta ya no lo pide: con una sola hoja
    # no hay nada que "pasar a vencidos".
    PRE_HISTORICO = ["Pasado a vencidos"]
    COLS_PRE = (["Concertación", "Liquidación", "Plazo", "Deudor", "Fondo",
                 "Contraparte", "Especie", "Cantidad", "Tasa", "Precio", "Monto",
                 "Tasa Aplicada", "Interés", "Interés Diario", "Ajuste", "A Cobrar",
                 "Estado", "Observaciones"] + PRE_HISTORICO)
    DIAS_AVISO_PRE = 2   # a cuántos días del vencimiento salta el cartel

    # Pipeline documental de onboarding (columna "Etapa", nueva — no existía
    # en el Excel). Es más granular que "Estado" y se muestra como stepper.
    ETAPAS_COM = ["1. Inicio / Solicitud", "2. Doc SG", "3. Doc SD", "4. Habilitada para operar"]
    ETAPAS_REM = ["1. Inicio / Solicitud", "2. Doc SG", "3. Doc SD", "4. Exención ARCA",
                  "5. Habilitada para operar"]

    def _cfg(clave, default=None):
        try:
            v = st.secrets.get(clave)
            if v:
                return str(v)
        except Exception:
            pass
        return os.environ.get(clave.upper()) or default

    GH_TOKEN  = _cfg("github_token")
    GH_REPO   = _cfg("github_repo")
    GH_BRANCH = _cfg("github_branch", "data")
    GH_PATH   = f"data/{XLS_NAME}"
    MODO_EDICION = bool(GH_TOKEN and GH_REPO)

    # ── Cliente mínimo de la API de GitHub (urllib, sin dependencias nuevas) ──
    def _gh(metodo, url, payload=None):
        req = urllib.request.Request(url, method=metodo)
        req.add_header("Authorization", f"Bearer {GH_TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        datos = None
        if payload is not None:
            datos = json.dumps(payload).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, datos, timeout=25) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode(errors="replace")
            try:
                cuerpo = json.loads(cuerpo)
            except Exception:
                pass
            return e.code, cuerpo
        except Exception as e:
            return 0, {"message": str(e)}

    def _diagnostico(code):
        """Traduce los errores típicos de la API en algo accionable."""
        if code in (401, 403):
            return ("El token de GitHub no es válido o no tiene permisos suficientes. En Secrets, "
                    "revisá que `github_token` esté completo y que sea un token *fine-grained* con "
                    "acceso a este repositorio y permiso **Contents: Read and write**.")
        if code == 404:
            return (f"GitHub no encuentra `{GH_REPO}`. Revisá que `github_repo` tenga el formato exacto "
                    f"`usuario/repositorio`. Ojo: si el repo es privado y el token no tiene acceso, "
                    f"GitHub también responde 404 en lugar de 403.")
        if code == 0:
            return "No hubo respuesta de GitHub. Puede ser un corte de red momentáneo: reintentá."
        return None

    def _asegurar_rama():
        """Crea la rama `data` a partir de la rama por defecto si no existe."""
        code, _ = _gh("GET", f"https://api.github.com/repos/{GH_REPO}/git/ref/heads/{GH_BRANCH}")
        if code == 200:
            return True, None
        if code != 404:
            return False, (_diagnostico(code)
                           or f"No se pudo consultar la rama '{GH_BRANCH}' (HTTP {code}).")
        code, repo = _gh("GET", f"https://api.github.com/repos/{GH_REPO}")
        if code != 200:
            return False, (_diagnostico(code)
                           or f"No se pudo leer el repo '{GH_REPO}' (HTTP {code}).")
        base = repo.get("default_branch", "main")
        code, ref = _gh("GET", f"https://api.github.com/repos/{GH_REPO}/git/ref/heads/{base}")
        if code != 200:
            return False, f"No se pudo leer la rama '{base}' (HTTP {code})."
        sha = ref["object"]["sha"]
        code, resp = _gh("POST", f"https://api.github.com/repos/{GH_REPO}/git/refs",
                         {"ref": f"refs/heads/{GH_BRANCH}", "sha": sha})
        if code not in (200, 201):
            return False, f"No se pudo crear la rama '{GH_BRANCH}' (HTTP {code}): {resp}"
        return True, None

    def _bajar_excel():
        """Devuelve (bytes, sha, error). sha=None si el archivo todavía no existe."""
        url = (f"https://api.github.com/repos/{GH_REPO}/contents/{GH_PATH}"
               f"?ref={GH_BRANCH}")
        code, resp = _gh("GET", url)
        if code == 200 and isinstance(resp, dict):
            if resp.get("content"):
                return base64.b64decode(resp["content"]), resp.get("sha"), None
            # Archivos grandes vienen sin content: usar el blob
            code2, blob = _gh("GET", f"https://api.github.com/repos/{GH_REPO}/git/blobs/{resp['sha']}")
            if code2 == 200:
                return base64.b64decode(blob["content"]), resp.get("sha"), None
            return None, None, f"No se pudo bajar el blob (HTTP {code2})."
        if code == 404:
            return None, None, None
        return None, None, f"No se pudo leer {GH_PATH} (HTTP {code}): {resp}"

    def _subir_excel(contenido, sha, mensaje):
        payload = {
            "message": mensaje,
            "content": base64.b64encode(contenido).decode(),
            "branch": GH_BRANCH,
        }
        if sha:
            payload["sha"] = sha
        code, resp = _gh("PUT",
                         f"https://api.github.com/repos/{GH_REPO}/contents/{GH_PATH}",
                         payload)
        if code in (200, 201):
            return True, None
        if code == 409:
            return False, ("CONFLICTO: alguien más guardó cambios mientras editabas. "
                           "Recargá la página para traer la última versión y volvé a aplicar lo tuyo.")
        return False, f"GitHub rechazó el guardado (HTTP {code}): {resp}"

    def _recalcular_pre(df):
        """Reescribe las columnas que en el Excel original eran fórmulas.
        Se corre al leer y antes de guardar, así el número nunca depende de
        que alguien haya arrastrado bien la fórmula: en el archivo que vino,
        69 de 77 filas tenían Monto e Interés en cero por falta de Precio."""
        if df is None or df.empty:
            return df
        d = df.copy()
        for c in COLS_PRE:
            if c not in d.columns:
                d[c] = pd.NA
        for c in ("Concertación", "Liquidación", "Pasado a vencidos"):
            d[c] = pd.to_datetime(d[c], errors="coerce")
        for c in ("Cantidad", "Tasa", "Precio"):
            d[c] = pd.to_numeric(d[c], errors="coerce")

        d["Plazo"] = (d["Liquidación"] - d["Concertación"]).dt.days
        d["Monto"] = d["Cantidad"] * d["Precio"]
        d["Tasa Aplicada"] = d["Tasa"] * d["Plazo"] / 365
        d["Interés"] = d["Monto"] * d["Tasa Aplicada"]
        plazo_ok = pd.to_numeric(d["Plazo"], errors="coerce")
        d["Interés Diario"] = np.where(plazo_ok.gt(0), d["Interés"] / plazo_ok, np.nan)
        d["A Cobrar"] = d["Interés"].round(2)
        d["Ajuste"] = d["A Cobrar"] - d["Interés"]
        # Float de verdad, no object: una columna object con NaN la grilla la
        # dibuja escribiendo "None" en cada celda vacía.
        for c in PRE_CALCULO:
            d[c] = pd.to_numeric(d[c], errors="coerce").astype("float64")
        return d[COLS_PRE]

    def _sembrar_pre():
        """Primera vez: la hoja de préstamos todavía no está en el Excel, así
        que se arma con el CSV migrado del archivo viejo. Al primer Guardar
        queda dentro del xlsx y este CSV no se vuelve a mirar."""
        if os.path.exists(CSV_PRE):
            try:
                return pd.read_csv(CSV_PRE)
            except Exception:
                pass
        return pd.DataFrame(columns=COLS_PRE)

    # ── Lectura de las hojas ─────────────────────────────────────────
    def _leer_hojas(contenido_bytes):
        """Parsea el xlsx. Devuelve (df_com, df_rem, df_fci, df_pre, error)."""
        try:
            xl = pd.ExcelFile(io.BytesIO(contenido_bytes), engine="openpyxl")
            faltan = [h for h in (HOJA_COM, HOJA_REM, HOJA_FCI) if h not in xl.sheet_names]
            if faltan:
                return None, None, None, None, (
                    f"Al Excel le faltan estas hojas: {', '.join(faltan)}. "
                    f"Hojas encontradas: {', '.join(xl.sheet_names)}.")
            # La de préstamos es opcional: si no está, se siembra. No se
            # considera error para no romper el Excel que ya está en uso.
            pre = xl.parse(HOJA_PRE) if HOJA_PRE in xl.sheet_names else _sembrar_pre()
            return (xl.parse(HOJA_COM), xl.parse(HOJA_REM), xl.parse(HOJA_FCI),
                    _recalcular_pre(pre), None)
        except Exception as e:
            return None, None, None, None, f"No se pudo leer el Excel: {e}"

    @st.cache_data(ttl=120, show_spinner="Cargando seguimiento de cuentas…")
    def cargar_cuentas(_modo, _nonce):
        """Trae el Excel de GitHub (rama data). Si no existe ahí, lo siembra
        con la copia del repo. En modo lectura usa directamente la copia local."""
        if _modo == "edicion":
            ok, err = _asegurar_rama()
            if not ok:
                return None, None, None, None, None, err
            contenido, sha, err = _bajar_excel()
            if err:
                return None, None, None, None, None, err
            if contenido is None:
                # Primera vez: sembrar la rama data con la copia del repo
                if not os.path.exists(XLS_LOCAL):
                    return None, None, None, None, None, (
                        f"No hay `{XLS_NAME}` ni en la rama '{GH_BRANCH}' ni en el repo. "
                        f"Subí el archivo al repo una vez para inicializar.")
                with open(XLS_LOCAL, "rb") as f:
                    contenido = f.read()
                ok, err = _subir_excel(contenido, None,
                                       "Inicializar seguimiento de cuentas desde el repo")
                if not ok:
                    return None, None, None, None, None, err
                _, sha, err = _bajar_excel()
                if err:
                    return None, None, None, None, None, err
        else:
            if not os.path.exists(XLS_LOCAL):
                return None, None, None, None, None, f"No se encontró `{XLS_NAME}` junto a app.py."
            with open(XLS_LOCAL, "rb") as f:
                contenido = f.read()
            sha = None

        c, r, f_, p, err = _leer_hojas(contenido)
        return c, r, f_, p, sha, err

    def _normalizar(df, nombre_hoja):
        """Limpia estados y avisa de columnas faltantes sin romper la app."""
        avisos = []
        if df is None:
            return df, avisos
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        if "Estado" in df.columns:
            df["Estado"] = (df["Estado"].astype("string").str.strip())
            # Normalizar capitalización contra la lista canónica
            mapa = {e.lower(): e for e in ESTADOS}
            df["Estado"] = df["Estado"].map(
                lambda v: mapa.get(str(v).lower(), v) if pd.notna(v) else v)
            raros = sorted(set(df["Estado"].dropna().unique()) - set(ESTADOS))
            if raros:
                avisos.append(f"{nombre_hoja}: estados no reconocidos → {', '.join(map(str, raros))}")
        else:
            avisos.append(f"{nombre_hoja}: falta la columna 'Estado'.")
        # Fechas a date (sin 00:00:00)
        for col in df.columns:
            if "fecha" in col.lower():
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        return df, avisos

    # ── HERO ────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="novus-hero">
      <div class="novus-eyebrow">middle office</div>
      <h1><span>onboarding</span></h1>
      <p>Seguimiento de altas de cuentas comitentes en ALyCs y cuentas remuneradas en bancos.</p>
      <span class="novus-badge">{'edición habilitada' if MODO_EDICION else 'solo lectura'}</span>
    </div>
    """, unsafe_allow_html=True)

    if not MODO_EDICION:
        st.markdown(
            '<div class="note warn"><b>Modo solo lectura.</b> No están configurados '
            '<code>github_token</code> y <code>github_repo</code> en los Secrets, así que la pantalla '
            'muestra la copia del repo y <b>no puede guardar</b>. Se prefiere avisarlo antes que '
            'ofrecer un botón de guardar que pierda los cambios en el próximo reinicio.</div>',
            unsafe_allow_html=True)

    nonce = st.session_state.get("_cuentas_nonce", 0)
    df_com, df_rem, df_fci, df_pre, sha_actual, error = cargar_cuentas(
        "edicion" if MODO_EDICION else "lectura", nonce)

    if error:
        st.error(error)
        st.stop()

    df_com, av1 = _normalizar(df_com, "Comitentes")
    df_rem, av2 = _normalizar(df_rem, "Remuneradas")
    avisos = av1 + av2

    # ── COLUMNAS NUEVAS DE ONBOARDING (Etapa, CBU, Alias) ────────────
    # No existían en el Excel. Se crean en memoria si faltan y quedan
    # firmes recién cuando se guarda por primera vez con la etapa cargada.
    def _asegurar_etapa(df, etapas):
        if df is None or df.empty:
            return df
        d = df.copy()
        if "Etapa" in d.columns:
            d["Etapa"] = d["Etapa"].astype(str).str.strip()
            d.loc[~d["Etapa"].isin(etapas), "Etapa"] = ""
            return d
        # Migración de las cuentas existentes: es una aproximación, no hay
        # forma de saber en qué paso documental está cada una hoy.
        # "Abierta" -> última etapa (ya está operativa). "En proceso" o
        # vacío -> primera etapa. "Rechazada"/"De baja" no tienen paso: el
        # stepper no aplica a una cuenta rechazada o dada de baja.
        def _default(estado):
            e = str(estado).strip() if pd.notna(estado) else ""
            if e == "Abierta":
                return etapas[-1]
            if e in ("", "En proceso"):
                return etapas[0]
            return ""
        d["Etapa"] = d["Estado"].map(_default) if "Estado" in d.columns else etapas[0]
        return d

    def _asegurar_columnas(df, columnas):
        if df is None or df.empty:
            return df
        d = df.copy()
        for c in columnas:
            if c not in d.columns:
                d[c] = ""
        return d

    df_com = _asegurar_etapa(df_com, ETAPAS_COM)
    df_rem = _asegurar_etapa(df_rem, ETAPAS_REM)
    df_rem = _asegurar_columnas(df_rem, ["CBU", "Alias"])

    # ── EDICIONES PENDIENTES DESDE EL MODAL ──────────────────────────
    # Se acumulan en sesión (mismo patrón que "nuevas_ctas") y se aplican acá
    # antes de mostrar, así el stepper refleja el cambio al instante y viajan
    # al Excel cuando se aprieta "Guardar cambios" más abajo.
    if "ediciones_ctas" not in st.session_state:
        st.session_state["ediciones_ctas"] = {"com": {}, "rem": {}}

    def _aplicar_ediciones(df, clave):
        ediciones = st.session_state["ediciones_ctas"].get(clave) or {}
        if df is None or not ediciones:
            return df
        d = df.copy()
        for idx, cambios in ediciones.items():
            if idx not in d.index:
                continue
            for col, val in cambios.items():
                if col not in d.columns:
                    d[col] = ""
                d.loc[idx, col] = val
        return d

    df_com = _aplicar_ediciones(df_com, "com")
    df_rem = _aplicar_ediciones(df_rem, "rem")

    # ── DETECCIÓN DE COLUMNAS ───────────────────────────────────────
    # El Excel real de Novus llama a la columna de fondo "FCI", no "Fondo".
    # En lugar de asumir un nombre, se busca cuál existe. Si mañana cambia,
    # basta agregar el candidato a la lista.
    CAND_FONDO = ("FCI", "Fondo", "Fondo/FCI", "FCI/Fondo", "Fondo FCI")
    CAND_TIPO  = ("Tipo de cuenta", "Tipo", "Tipo cuenta")

    def _primera_col(cands, *frames):
        for c in cands:
            for d in frames:
                if d is not None and c in d.columns:
                    return c
        return None

    COL_FONDO = _primera_col(CAND_FONDO, df_com, df_rem)
    COL_TIPO  = _primera_col(CAND_TIPO, df_com, df_rem)
    ETIQ_FONDO = COL_FONDO or "Fondo"

    def _col_fondo(df):
        """Nombre de la columna de fondo EN ESA hoja: Comitentes la llama
        "FCI" y Remuneradas "Fondo". Todo lo que recorra las dos hojas tiene
        que resolverla por hoja; con un único nombre global, la mitad de las
        operaciones (filtrar, unificar, contar) se salteaban Remuneradas."""
        return _primera_col(CAND_FONDO, df)

    # ── ESTADOS CON COLOR ───────────────────────────────────────────
    # EST_ICONO se usa como badge de respaldo cuando una fila no tiene una
    # Etapa válida para el stepper (Rechazada/De baja). EST_FONDO/EST_TEXTO
    # pintan la Vista consolidada, que es de solo lectura y sí admite Styler.
    EST_ICONO = {"Abierta": "🟢", "En proceso": "🟡", "Rechazada": "🔴", "De baja": "⚪"}
    EST_FONDO = {"Abierta": "#E9F6EC", "En proceso": "#FFF6E6",
                 "Rechazada": "#FDECEC", "De baja": "#F0F2F0"}
    EST_TEXTO = {"Abierta": GREEN_DIM, "En proceso": "#9A6A10",
                 "Rechazada": "#B03030", "De baja": "#77817A"}

    def _limpiar_estado(v):
        """Saca el emoji del principio y deja el texto puro."""
        if pd.isna(v):
            return v
        s = str(v)
        for ic in EST_ICONO.values():
            s = s.replace(ic, "")
        return s.strip() or None

    # ═══════════════════════════════════════════════════════════════
    # CATÁLOGO DE FCI
    # La hoja "Lista FCI" es la fuente de verdad de qué fondos existen.
    # Su columna de nombre se normaliza a "FCI" para que sea igual que en
    # las hojas de cuentas. De ahí salen las opciones de los desplegables.
    # ═══════════════════════════════════════════════════════════════
    import difflib
    import re
    import unicodedata

    COL_FCI_CAT = _primera_col(CAND_FONDO, df_fci)
    if df_fci is not None and COL_FCI_CAT and COL_FCI_CAT != "FCI":
        df_fci = df_fci.rename(columns={COL_FCI_CAT: "FCI"})
        COL_FCI_CAT = "FCI"

    CATALOGO = []
    if df_fci is not None and "FCI" in df_fci.columns:
        vistos = set()
        for v in df_fci["FCI"].dropna().astype(str).str.strip():
            if v and v not in vistos:      # conserva el orden de la hoja
                vistos.add(v)
                CATALOGO.append(v)

    def _norm_fci(s):
        """Clave de comparación: sin acentos, sin mayúsculas, sin puntuación
        y sin el sufijo 'FCI'. Así 'Novus liquidez FCI', 'NOVUS LIQUIDEZ' y
        'Novus  Liquidez' colapsan todas a la misma clave."""
        s = str(s).strip().lower()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = re.sub(r"\bf\.?c\.?i\.?\b", " ", s)
        s = re.sub(r"[^a-z0-9 ]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    SIN_TOCAR = "— dejar como está —"

    IDX_CAT = {}
    for c in CATALOGO:
        IDX_CAT.setdefault(_norm_fci(c), c)

    def _sugerir_fci(valor):
        """Devuelve (canónico, etiqueta, ratio). Nunca decide sola: el ratio
        se muestra en pantalla para que la persona confirme."""
        n = _norm_fci(valor)
        if not n:
            return None, "vacío", 0.0
        if n in IDX_CAT:
            return IDX_CAT[n], "exacta", 1.0
        cerca = difflib.get_close_matches(n, list(IDX_CAT), n=1, cutoff=0.78)
        if cerca:
            r = difflib.SequenceMatcher(None, n, cerca[0]).ratio()
            return IDX_CAT[cerca[0]], f"{r:.0%}", r
        return None, "sin match", 0.0

    # Unificaciones confirmadas en esta sesión, aplicadas antes de mostrar.
    if "mapa_fci" not in st.session_state:
        st.session_state["mapa_fci"] = {}

    def _aplicar_mapa(df):
        mapa = st.session_state.get("mapa_fci") or {}
        col = _col_fondo(df)
        if df is None or df.empty or not mapa or not col:
            return df
        d = df.copy()
        d[col] = d[col].map(
            lambda v: mapa.get(str(v).strip(), v) if pd.notna(v) else v)
        return d

    # ── UNIFICACIÓN DE CONTRAPARTES ──────────────────────────────────
    # Mismo mecanismo que el de FCI: lo confirmado en esta sesión se guarda
    # acá y se aplica antes de mostrar; recién queda firme al Guardar.
    if "mapa_ctp" not in st.session_state:
        st.session_state["mapa_ctp"] = {}

    def _aplicar_mapa_ctp(df):
        mapa = st.session_state.get("mapa_ctp") or {}
        if df is None or df.empty or not mapa or "Contraparte" not in df.columns:
            return df
        d = df.copy()
        d["Contraparte"] = d["Contraparte"].map(
            lambda v: mapa.get(str(v).strip(), v) if pd.notna(v) else v)
        return d

    def a_datos(df):
        """Copia con el Estado limpio, para guardar."""
        if df is None or df.empty or "Estado" not in df.columns:
            return df
        d = df.copy()
        d["Estado"] = d["Estado"].map(_limpiar_estado)
        return d

    def _enteros(df):
        """Dos arreglos de tipos que se notan mucho al usarlo:
        1) Columnas numéricas enteras → Int64, para que las celdas vacías se
           vean vacías en vez de mostrar 'None'.
        2) Columnas 100% vacías (caso típico: Comentarios) → texto. Si quedan
           como numéricas, el editor las trata como número y no te deja
           escribir un comentario adentro."""
        if df is None or df.empty:
            return df
        # Se descartan las filas totalmente vacías (relleno del final del Excel)
        # ANTES de rellenar, para que no terminen contadas como solicitudes.
        # dropna conserva las etiquetas de índice, que es lo que necesita el
        # guardado con filtros para reinsertar cada fila en su lugar.
        # Columnas que son IDENTIFICADORES, no cantidades. Se guardan como
        # texto: así las celdas sin asignar quedan vacías en vez de "None",
        # no aparecen separadores de miles ni notación científica, y no se
        # pierden ceros a la izquierda.
        PAT_ID = ("n°", "nro", "numero", "número", "cuenta", "cbu",
                  "matricula", "matrícula", "cuit", "cuil")

        d = df.dropna(how="all").copy()
        for c in d.columns:
            col = d[c]
            if col.isna().all():
                d[c] = ""          # columna entera vacía → texto editable
                continue
            if any(p in str(c).lower() for p in PAT_ID):
                try:
                    d[c] = col.map(
                        lambda v: "" if pd.isna(v)
                        else (str(int(v)) if isinstance(v, float) and v.is_integer()
                              else str(v).strip())).astype("string")
                    continue
                except Exception:
                    pass
            if col.dtype.kind == "f":
                s = col.dropna()
                if len(s) and (s % 1 == 0).all():
                    try:
                        d[c] = col.astype("Int64")
                    except Exception:
                        pass
                continue
            try:
                if pd.api.types.is_string_dtype(col) or col.dtype == object:
                    d[c] = col.fillna("")   # evita que el editor muestre "None"
            except Exception:
                pass
        return d

    # ── COLUMNAS QUE NO SE MUESTRAN ─────────────────────────────────
    # Se ocultan de la Vista consolidada pero no se borran de las hojas.
    # Para volver a mostrar la fecha, vaciá esta tupla: OCULTAR = ()
    OCULTAR = ("fecha",)

    # ── CUENTAS NUEVAS PENDIENTES DE GUARDAR ────────────────────────
    # Las altas se acumulan en la sesión y se suman a la hoja antes de
    # mostrarla, así aparecen en la tabla y se guardan junto con todo lo demás
    # cuando apretás Guardar. Se vacían recién cuando el guardado sale bien.
    if "nuevas_ctas" not in st.session_state:
        st.session_state["nuevas_ctas"] = {"com": [], "rem": []}

    def _sumar_nuevas(df, clave):
        pend = st.session_state["nuevas_ctas"].get(clave) or []
        if df is None or not pend:
            return df
        # Etiquetas nuevas que siguen a las existentes, en vez de
        # ignore_index=True: ese renumeraba TODA la hoja y las ediciones y
        # bajas pendientes (que se guardan por etiqueta de fila) pasaban a
        # apuntar a la cuenta equivocada.
        inicio = (int(df.index.max()) + 1) if len(df.index) else 0
        nuevas = pd.DataFrame(pend, index=range(inicio, inicio + len(pend)))
        return pd.concat([df, nuevas], sort=False)

    # ── CUENTAS ELIMINADAS PENDIENTES DE GUARDAR ────────────────────
    # Mismo criterio que las altas y las ediciones: la baja se ve al toque
    # en la tabla, pero recién se escribe en el Excel al Guardar.
    if "bajas_ctas" not in st.session_state:
        st.session_state["bajas_ctas"] = {"com": [], "rem": []}

    def _aplicar_bajas(df, clave):
        bajas = [i for i in (st.session_state["bajas_ctas"].get(clave) or [])
                 if df is not None and i in df.index]
        if df is None or not bajas:
            return df
        return df.drop(index=bajas)

    df_com = _aplicar_bajas(_aplicar_mapa_ctp(_aplicar_mapa(_sumar_nuevas(df_com, "com"))), "com")
    df_rem = _aplicar_bajas(_aplicar_mapa_ctp(_aplicar_mapa(_sumar_nuevas(df_rem, "rem"))), "rem")
    n_pendientes = (len(st.session_state["nuevas_ctas"]["com"]) +
                    len(st.session_state["nuevas_ctas"]["rem"]))
    n_bajas = (len(st.session_state["bajas_ctas"]["com"]) +
               len(st.session_state["bajas_ctas"]["rem"]))

    df_com, df_rem, df_fci = _enteros(df_com), _enteros(df_rem), _enteros(df_fci)

    # ── FILTROS ─────────────────────────────────────────────────────
    TIPO_COM, TIPO_REM = "Comitente", "Remunerada"

    def _valores(col, *frames):
        vals = set()
        if not col:
            return []
        for d in frames:
            if d is not None and col in d.columns:
                vals |= set(d[col].dropna().astype(str).str.strip())
        vals.discard("")
        return sorted(vals)

    def _valores_fondo(*frames):
        """La columna de fondo se llama distinto en cada hoja ("FCI" en
        Comitentes, "Fondo" en Remuneradas): hay que resolverla por hoja.
        Usando el nombre global se perdían los fondos que solo existen en
        Remuneradas, que ni aparecían en el desplegable."""
        vals = set()
        for d in frames:
            c = _primera_col(CAND_FONDO, d)
            if d is not None and c:
                vals |= set(d[c].dropna().astype(str).str.strip())
        vals.discard("")
        return sorted(vals)

    fondos_disp  = _valores_fondo(df_com, df_rem)
    estados_disp = [e for e in ESTADOS if e in set(_valores("Estado", df_com, df_rem))]
    ctp_disp     = _valores("Contraparte", df_com, df_rem)

    with st.expander("🔍  Filtros  ·  vacío = todos", expanded=True):
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            f_tipo = st.multiselect("Tipo de cuenta", [TIPO_COM, TIPO_REM],
                                    placeholder="Ambos", key="fc_tipo")
        with fc2:
            f_fondo = st.multiselect(ETIQ_FONDO, fondos_disp,
                                     placeholder="Todos", key="fc_fondo",
                                     disabled=not fondos_disp)
        with fc3:
            f_estado = st.multiselect("Estado", estados_disp, placeholder="Todos", key="fc_estado")
        with fc4:
            f_ctp = st.multiselect("Contraparte", ctp_disp, placeholder="Todas", key="fc_ctp")

    ver_com = (not f_tipo) or (TIPO_COM in f_tipo)
    ver_rem = (not f_tipo) or (TIPO_REM in f_tipo)
    filtro_filas = bool(f_fondo or f_estado or f_ctp)
    filtro_activo = bool(f_tipo) or filtro_filas

    def filtrar(df):
        """Filtra conservando el índice original: es la clave para que al
        guardar lo editado vuelva a su fila exacta del Excel."""
        if df is None or df.empty:
            return df
        d = df
        # El nombre de la columna de fondo se resuelve para ESTA hoja. Con el
        # nombre global ("FCI") el filtro no encontraba la columna en
        # Remuneradas y esa hoja quedaba sin filtrar: el filtro parecía andar
        # a veces sí y a veces no según la pestaña que estuvieras mirando.
        col_fondo_hoja = _primera_col(CAND_FONDO, df)
        for col, sel in ((col_fondo_hoja, f_fondo), ("Estado", f_estado),
                         ("Contraparte", f_ctp)):
            if not sel or not col or col not in d.columns:
                continue
            d = d[d[col].astype(str).str.strip().isin(sel)]
        return d

    vacio_com = df_com.iloc[0:0] if df_com is not None else None
    vacio_rem = df_rem.iloc[0:0] if df_rem is not None else None
    vis_com = filtrar(df_com) if ver_com else vacio_com
    vis_rem = filtrar(df_rem) if ver_rem else vacio_rem

    # ── MÉTRICAS ────────────────────────────────────────────────────
    def _cuenta(df, estado):
        if df is None or df.empty or "Estado" not in df.columns:
            return 0
        return int((df["Estado"] == estado).sum())

    def _filas(df):
        return 0 if df is None or df.empty else int(df.dropna(how="all").shape[0])

    n_com, n_rem = _filas(vis_com), _filas(vis_rem)
    total = n_com + n_rem
    abiertas = _cuenta(vis_com, "Abierta") + _cuenta(vis_rem, "Abierta")
    proceso  = _cuenta(vis_com, "En proceso") + _cuenta(vis_rem, "En proceso")
    pct_ab   = (abiertas / total * 100) if total else 0.0
    total_sin_filtro = _filas(df_com) + _filas(df_rem)
    contrapartes = set(_valores("Contraparte", vis_com, vis_rem))
    fondos_vis = set(_valores_fondo(vis_com, vis_rem))

    titulo = "Estado del Onboarding"
    if filtro_activo:
        titulo += f" · {total} de {total_sin_filtro} solicitudes"
    st.markdown(f'<div class="section-title">{titulo}</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)

    if total == 0:
        st.warning("Ninguna solicitud coincide con los filtros. Probá borrar alguno.")

    q1, q2, q3, q4 = st.columns(4)
    with q1:
        det = []
        if ver_com:
            det.append(f"{n_com} comitentes")
        if ver_rem:
            det.append(f"{n_rem} remuneradas")
        st.markdown(f'<div class="kpi-card accent"><div class="kpi-label">Solicitudes</div>'
                    f'<div class="kpi-value">{total}</div>'
                    f'<div class="kpi-sub">{" · ".join(det) or "—"}</div></div>', unsafe_allow_html=True)
    with q2:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">🟢 Abiertas</div>'
                    f'<div class="kpi-value">{abiertas}</div>'
                    f'<div class="kpi-sub">{pct_ab:.0f}% de lo filtrado</div></div>',
                    unsafe_allow_html=True)
    with q3:
        color = AMBER if proceso else GREEN
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">🟡 En proceso</div>'
                    f'<div class="kpi-value" style="color:{color}">{proceso}</div>'
                    f'<div class="kpi-sub">pendientes de apertura</div></div>', unsafe_allow_html=True)
    with q4:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Alcance</div>'
                    f'<div class="kpi-value">{len(contrapartes)} · {len(fondos_vis)}</div>'
                    f'<div class="kpi-sub">contrapartes · {ETIQ_FONDO.lower()}</div></div>',
                    unsafe_allow_html=True)

    # NOTA: acá había una tira apilada "Distribución por estado". Se quitó a
    # pedido: los KPI de arriba ya dan abiertas y pendientes, y el reparto
    # fino ahora se lee en los chips de etapa de cada tabla, que muestran
    # cuántas cuentas hay en cada paso.

    # NOTA: acá había un gráfico de barras "Cuentas por FCI". Se quitó a
    # pedido: con 93 fondos eran 93 barras y no se leía nada. Si alguna vez
    # se quiere volver a mostrar, conviene limitarlo a un Top 10 por volumen
    # de solicitudes en vez de listarlos todos.

    if avisos:
        st.markdown('<div class="note warn"><b>Para revisar en el Excel:</b><br>' +
                    "<br>".join(f"· {a}" for a in avisos) + '</div>', unsafe_allow_html=True)

    # ── TABLAS ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Detalle</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)


    # ── ALTA DE UNA CUENTA NUEVA ────────────────────────────────────
    # Con 700+ filas, buscar la fila vacía del final de la grilla es
    # impracticable. El formulario agrega la cuenta sin depender de scrollear
    # ni de que los filtros estén limpios.
    with st.expander("➕  Agregar una cuenta nueva", expanded=False):
        alta_tipo = st.radio("¿Qué tipo de cuenta?", [TIPO_COM, TIPO_REM],
                             horizontal=True, key="alta_tipo")
        destino = df_com if alta_tipo == TIPO_COM else df_rem
        clave_hoja = "com" if alta_tipo == TIPO_COM else "rem"
        etapas_alta = ETAPAS_COM if alta_tipo == TIPO_COM else ETAPAS_REM
        # Misma columna de fondo por hoja que en la tabla y el modal: "FCI"
        # en Comitentes, "Fondo" en Remuneradas — no una global compartida.
        col_fondo_alta = _primera_col(CAND_FONDO, destino)

        if destino is None or not len(destino.columns):
            st.info("No se puede dar de alta: la hoja no tiene columnas definidas.")
        else:
            with st.form("form_alta", clear_on_submit=True):
                campos = list(destino.columns)
                valores = {}
                fci_multiples = []
                for i in range(0, len(campos), 3):
                    grupo = campos[i:i + 3]
                    cols_ui = st.columns(len(grupo))
                    for cu, nombre_col in zip(cols_ui, grupo):
                        with cu:
                            bajo = str(nombre_col).lower()
                            if nombre_col == "Estado":
                                valores[nombre_col] = st.selectbox(
                                    nombre_col, ESTADOS, index=0)
                            elif nombre_col == "Etapa":
                                valores[nombre_col] = st.selectbox(
                                    nombre_col, etapas_alta, index=0,
                                    help="Etapa inicial del onboarding para esta cuenta.")
                            elif col_fondo_alta and nombre_col == col_fondo_alta:
                                if CATALOGO:
                                    # Multiselect: se genera una fila por cada
                                    # FCI elegido, todas con los mismos datos
                                    # de contraparte — así se cargan de una
                                    # varios fondos para la misma contraparte.
                                    fci_multiples = st.multiselect(
                                        f"{nombre_col} (podés elegir varios)", CATALOGO,
                                        placeholder="Elegí uno o más FCI de la lista")
                                else:
                                    valores[nombre_col] = st.text_input(nombre_col, placeholder="—")
                            elif COL_TIPO and nombre_col == COL_TIPO:
                                st.text_input(nombre_col, value=alta_tipo, disabled=True)
                                valores[nombre_col] = alta_tipo
                            elif "fecha" in bajo:
                                valores[nombre_col] = st.date_input(
                                    nombre_col, value=pd.Timestamp.today().date())
                            else:
                                valores[nombre_col] = st.text_input(nombre_col, placeholder="—")
                sumar = st.form_submit_button("Agregar a la tabla")

            if sumar:
                if col_fondo_alta and CATALOGO and not fci_multiples:
                    st.warning("Elegí al menos un FCI antes de agregar.")
                else:
                    base = {}
                    for c, v in valores.items():
                        if isinstance(v, str):
                            v = v.strip()
                        base[c] = v if v not in ("", None) else pd.NA
                    if COL_TIPO:
                        base[COL_TIPO] = alta_tipo
                    if fci_multiples:
                        for fci in fci_multiples:
                            fila = dict(base)
                            fila[col_fondo_alta] = fci
                            st.session_state["nuevas_ctas"][clave_hoja].append(fila)
                    else:
                        st.session_state["nuevas_ctas"][clave_hoja].append(base)
                    st.rerun()

    if n_pendientes:
        st.markdown(
            f'<div class="note warn"><b>{n_pendientes} cuenta(s) nueva(s) agregada(s) a la '
            f'tabla, todavía sin guardar.</b> Aparecen al final de su pestaña. Apretá '
            f'<b>Guardar cambios</b> abajo para que queden en el repo.</div>',
            unsafe_allow_html=True)

    if n_bajas:
        bj1, bj2 = st.columns([3, 1], vertical_alignment="center")
        with bj1:
            st.markdown(
                f'<div class="note warn"><b>{n_bajas} cuenta(s) eliminada(s), todavía sin '
                f'guardar.</b> Desaparecieron de la tabla pero siguen en el Excel hasta que '
                f'apretes <b>Guardar cambios</b>.</div>', unsafe_allow_html=True)
        with bj2:
            if st.button("↩  Deshacer bajas", key="btn_deshacer_bajas"):
                st.session_state["bajas_ctas"] = {"com": [], "rem": []}
                st.rerun()

    # El FCI pasa a desplegable SOLO cuando todos los valores ya están en el
    # catálogo. Si quedan variantes sueltas, un SelectboxColumn las tomaría
    # como inválidas y podría vaciarlas: se deja como texto hasta unificar.
    fci_sueltos = set()
    if CATALOGO:
        for d in (df_com, df_rem):
            col = _col_fondo(d)
            if d is not None and not d.empty and col:
                fci_sueltos |= {v for v in d[col].dropna().astype(str).str.strip()
                                if v and v not in CATALOGO}

    # ── GRUPOS DE CONTRAPARTES CON DISTINTA ESCRITURA ───────────────
    # "Supervielle", "Banco Supervielle" y "Banco Supervielle S.A." son la
    # misma contraparte escrita de tres formas. Se agrupan ignorando
    # mayúsculas, acentos, puntuación y las palabras que no distinguen a
    # una contraparte de otra (banco, valores, securities, S.A., etc.).
    RUIDO_CTP = {"banco", "bank", "sa", "s", "a", "sau", "srl", "alyc", "cia",
                 "y", "de", "valores", "securities", "sociedad", "bolsa",
                 "capital", "capitales", "inversiones", "group", "grupo",
                 "hnos", "financiera", "financial"}

    def _sin_acentos(s):
        s = unicodedata.normalize("NFKD", str(s).strip().lower())
        return "".join(c for c in s if not unicodedata.combining(c))

    def _clave_ctp(s):
        s = re.sub(r"[^a-z0-9 ]", " ", _sin_acentos(s))
        return " ".join(sorted(p for p in s.split() if p and p not in RUIDO_CTP))

    # El riesgo real al preseleccionar no es "Supervielle" vs "Banco
    # Supervielle" (son lo mismo), sino el banco y su ALyC, que en el mercado
    # local comparten el nombre y son dos contrapartes distintas: "Banco
    # Santander" / "Santander Valores", "Banco Macro" / "Macro Securities".
    # Por eso el único caso que queda sin elegir es el grupo donde conviven
    # una variante con "banco" y otra con "valores"/"securities".
    PAL_BANCO = {"banco", "bank"}
    PAL_ALYC = {"valores", "securities", "bursatil", "bolsa"}

    def _palabras_ctp(s):
        return set(re.sub(r"[^a-z0-9 ]", " ", _sin_acentos(s)).split())

    def _conflicto_banco_alyc(variantes):
        palabras = [_palabras_ctp(v) for v in variantes]
        return (any(p & PAL_BANCO for p in palabras)
                and any(p & PAL_ALYC for p in palabras))

    ctp_conteo = {}
    for d in (df_com, df_rem):
        if d is not None and not d.empty and "Contraparte" in d.columns:
            for v in d["Contraparte"].dropna().astype(str).str.strip():
                if v:
                    ctp_conteo[v] = ctp_conteo.get(v, 0) + 1

    grupos_ctp = {}
    for v in ctp_conteo:
        grupos_ctp.setdefault(_clave_ctp(v), []).append(v)
    # Solo interesan los grupos con más de una escritura.
    grupos_ctp = {k: sorted(vs, key=lambda x: -ctp_conteo[x])
                  for k, vs in grupos_ctp.items() if len(vs) > 1}

    # Se arranca con las hojas COMPLETAS: los cambios del modal ya están
    # aplicados sobre df_com/df_rem más arriba, así que alcanza con esto.
    res_com, res_rem, res_fci = df_com, df_rem, df_fci
    res_pre = df_pre

    # ── PRÉSTAMOS: DÍAS AL VENCIMIENTO ──────────────────────────────
    # "Vigente" es lo que dice la fila; "vence en N días" sale de la fecha.
    # Se separan a propósito: un préstamo marcado Vigente cuya Liquidación ya
    # pasó es justamente lo que hay que ver, no algo para esconder.
    HOY_PRE = pd.Timestamp.now().normalize()

    def _fmt_num(v, dec=0):
        """Cantidad con separador de miles, sin moneda: los nominales de un
        préstamo no son dólares ni pesos, son unidades de la especie."""
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "—"
        if pd.isna(v):
            return "—"
        return f"{v:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")

    def _dias_al_vto(df):
        if df is None or df.empty or "Liquidación" not in df.columns:
            return pd.Series(dtype="float64")
        return (pd.to_datetime(df["Liquidación"], errors="coerce") - HOY_PRE).dt.days

    pre_abiertos = (df_pre[df_pre["Estado"].astype(str).str.strip() == "Vigente"]
                    if df_pre is not None and not df_pre.empty and "Estado" in df_pre.columns
                    else (df_pre.iloc[0:0] if df_pre is not None else None))
    dias_abiertos = _dias_al_vto(pre_abiertos)
    n_por_vencer = int(((dias_abiertos >= 0) & (dias_abiertos <= DIAS_AVISO_PRE)).sum()) \
        if len(dias_abiertos) else 0
    n_vencidos_abiertos = int((dias_abiertos < 0).sum()) if len(dias_abiertos) else 0

    nombres = []
    if ver_com:
        nombres.append("  Comitentes (ALyCs)  ")
    if ver_rem:
        nombres.append("  Remuneradas (bancos)  ")
    etiqueta_pre = "  Préstamos de títulos  "
    if n_por_vencer or n_vencidos_abiertos:
        etiqueta_pre = f"  ⚠ Préstamos de títulos ({n_por_vencer + n_vencidos_abiertos})  "
    nombres.append(etiqueta_pre)
    nombres += ["  Vista consolidada  ", "  FCI y matrículas  "]
    # Las pestañas de unificación aparecen SOLO si hay algo que unificar, y
    # se van solas cuando queda limpio.
    if fci_sueltos:
        nombres.append(f"  ⚠ Unificar FCI ({len(fci_sueltos)})  ")
    if grupos_ctp:
        nombres.append(f"  ⚠ Unificar contrapartes ({len(grupos_ctp)})  ")

    # ── CARTEL DE VENCIMIENTOS ──────────────────────────────────────
    # Va ACÁ arriba, fuera de la pestaña de préstamos: un aviso que solo se
    # ve entrando a la pestaña que corresponde no sirve de aviso.
    if n_por_vencer or n_vencidos_abiertos:
        partes = []
        if n_vencidos_abiertos:
            partes.append(f"<b>{n_vencidos_abiertos} préstamo(s) ya vencieron</b> y siguen "
                          f"marcados como vigentes")
        if n_por_vencer:
            plural = "n" if n_por_vencer > 1 else ""
            partes.append(f"<b>{n_por_vencer} vence{plural} dentro de "
                          f"{DIAS_AVISO_PRE} día(s)</b>")
        detalle = []
        for _i, _f in pre_abiertos.assign(_d=dias_abiertos).sort_values("_d").iterrows():
            d_ = _f["_d"]
            if pd.isna(d_) or d_ > DIAS_AVISO_PRE:
                continue
            cuando = ("vencido hace %d día(s)" % abs(int(d_))) if d_ < 0 else (
                "vence hoy" if d_ == 0 else "vence en %d día(s)" % int(d_))
            detalle.append(f"· {_f.get('Contraparte', '—')} · {_f.get('Especie', '—')} · "
                           f"{_fmt_num(_f.get('Cantidad'))} nominales — <b>{cuando}</b>")
        st.markdown(
            '<div class="note warn"><b>⚠ Préstamos de títulos próximos a vencer.</b><br>'
            + " y ".join(partes) + ".<br>" + "<br>".join(detalle) +
            '</div>', unsafe_allow_html=True)

    tabs = list(st.tabs(nombres))
    k = 0

    # ── STEPPER DE ETAPA ──────────────────────────────────────────────
    # Un color propio por paso (no todos verde parejo): así se distingue de
    # un vistazo en qué documentación está cada cuenta. El último paso
    # ("Habilitada para operar") siempre es este verde, sea cual sea el
    # total de pasos de la hoja (4 en ALyCs, 5 en Bancos).
    PASO_COLORES = ["#f59e0b", "#3b82f6", "#8b5cf6", "#06b6d4"]
    PASO_COLOR_FINAL = "#10b981"
    PENDIENTE_GRIS = "#e5e7eb"

    def _color_paso(i, total):
        return PASO_COLOR_FINAL if i == total - 1 else PASO_COLORES[i % len(PASO_COLORES)]

    def _stepper_html(etapa_actual, etapas):
        """None si la etapa no aplica (vacía o fuera de lista, típicamente
        una cuenta Rechazada/De baja) — ahí se muestra el badge de Estado
        en su lugar, no tendría sentido un "paso X de N"."""
        if not etapa_actual or etapa_actual not in etapas:
            return None
        idx, total = etapas.index(etapa_actual), len(etapas)
        nodos = []
        for i in range(total):
            color_nodo = _color_paso(i, total) if i <= idx else PENDIENTE_GRIS
            nodos.append(f'<span class="nodo" style="background:{color_nodo}"></span>')
            if i < total - 1:
                color_linea = _color_paso(i, total) if i < idx else PENDIENTE_GRIS
                nodos.append(f'<span class="linea" style="background:{color_linea}"></span>')
        c = _color_paso(idx, total)
        return (f'<div class="etapa-wrap">'
                f'<div class="novus-stepper">{"".join(nodos)}</div>'
                f'<div class="etapa-tag" style="color:{c};background:{c}1F" '
                f'title="{etapa_actual}">{etapa_actual}</div>'
                f'<div class="etapa-paso">{idx + 1}/{total}</div>'
                f'</div>')

    FILAS_POR_PAGINA = 25
    # Reparto de la fila: datos / editar / eliminar. Lo usan la fila y el
    # encabezado, que tienen que medir exactamente lo mismo para que los
    # títulos caigan sobre su columna.
    ANCHOS_FILA = [17, 1, 1]

    def _css_conteo_chips(clave, conteos):
        """Pinta el contador de cada chip. Va como regla :nth-child porque el
        número no puede formar parte del texto de la opción (ver el CSS del
        badge). El orden de `conteos` es el mismo que el de los options."""
        reglas = []
        for i, n in enumerate(conteos, start=1):
            sel = (f'div.st-key-{clave}_chip div[role="radiogroup"] '
                   f'label:nth-child({i})')
            reglas.append(f'{sel}::after{{content:"{n}";display:inline-block}}')
            if n == 0:
                # La etapa existe pero está vacía: se muestra apagada en vez
                # de esconderla, así se ve que el paso está previsto.
                reglas.append(f'{sel}{{opacity:.45}}')
        st.markdown("<style>" + "".join(reglas) + "</style>", unsafe_allow_html=True)

    def _tabla_onboarding(vis, etapas, clave, etiqueta, tipo_esperado):
        """Chips de etapa + tabla paginada con stepper por fila. Clic en una
        fila abre el modal de edición (st.dialog)."""
        # La columna de fondo no se llama igual en las dos hojas (Comitentes
        # usa "FCI", Remuneradas usa "Fondo") — se resuelve por esta hoja
        # puntual, no con el COL_FONDO global (que solo pega con Comitentes).
        col_fondo_local = _primera_col(CAND_FONDO, vis)

        col_etapa = vis["Etapa"].astype(str).str.strip() if "Etapa" in vis.columns else None
        conteos = [len(vis)] + [int((col_etapa == e).sum()) if col_etapa is not None else 0
                                for e in etapas]

        # El propio key del widget deja la clase st-key-<clave>_chip en su
        # contenedor, que es a lo que apuntan el CSS y los contadores.
        chip = st.radio("Etapa", ["Todos"] + etapas, horizontal=True,
                        label_visibility="collapsed", key=f"{clave}_chip")
        _css_conteo_chips(clave, conteos)
        d = vis if chip == "Todos" else vis[vis["Etapa"] == chip]

        # Encabezado: el total a la izquierda y, solo si hay un chip activo,
        # de qué etapa se trata. Sin filtro, "158 de 158" no dice nada.
        if chip == "Todos":
            izq, der = f'{len(d)}<span>{etiqueta}</span>', ""
        else:
            izq = f'{len(d)}<span>de {len(vis)} {etiqueta}</span>'
            der = f'<div class="ctx">etapa <b>{chip}</b></div>'
        st.markdown(f'<div class="onb-bar"><div class="tot">{izq}</div>{der}</div>',
                    unsafe_allow_html=True)

        if d.empty:
            st.info("Ninguna cuenta en esta etapa.")
            return

        n_paginas = max(1, -(-len(d) // FILAS_POR_PAGINA))
        pag_key = f"{clave}_pagina"
        pag_actual = min(st.session_state.get(pag_key, 1), n_paginas)
        # Con una sola página el control no aporta nada y ocupa una fila
        # entera; se muestra solo cuando hay algo que paginar.
        if n_paginas > 1:
            with st.container(key=f"{clave}_pag_box"):
                pc1, _ = st.columns([1, 4])
                with pc1:
                    pag_actual = st.number_input(
                        f"Página (de {n_paginas})", min_value=1, max_value=n_paginas,
                        value=pag_actual, step=1, key=f"{clave}_pag_input")
        st.session_state[pag_key] = pag_actual

        ini = (pag_actual - 1) * FILAS_POR_PAGINA
        pagina = d.iloc[ini: ini + FILAS_POR_PAGINA]

        etiq_fondo_col = col_fondo_local or "Fondo"

        # Cada fila es UN solo bloque HTML con grid propio (más el botón en
        # su columna). Antes eran 5 columnas de Streamlit por fila y al
        # apilarse en celular sus contenedores internos colapsaban a ~5px y
        # el texto se montaba sobre la fila siguiente. Con un grid propio el
        # reflow a una columna lo maneja el CSS y no depende de Streamlit.
        # El encabezado va dentro del MISMO reparto de columnas que las filas.
        # Suelto a ancho completo, su grilla medía ~200px más que la de los
        # datos y los títulos caían corridos respecto de la columna que nombran.
        with st.container(key=f"{clave}_encab"):
            h_info, _, _ = st.columns(ANCHOS_FILA, vertical_alignment="center")
        h_info.markdown(
            f'<div class="fila-onb fila-onb-encab">'
            f'<div class="celda">Contraparte</div><div class="celda">{etiq_fondo_col}</div>'
            f'<div class="celda">Etapa</div></div>',
            unsafe_allow_html=True)

        for idx, row in pagina.iterrows():
            etapa_val = str(row.get("Etapa", "")).strip()
            stepper = _stepper_html(etapa_val, etapas)
            if not stepper:
                estado_val = str(row.get("Estado", "")).strip()
                stepper = f'{EST_ICONO.get(estado_val, "⚫")} {estado_val or "—"}'

            # "Tipo" decía lo mismo en toda la pestaña (Remunerada / Comitente)
            # y se comía una columna entera. Ahora solo se marca la excepción
            # —la única cuenta "Exterior", o una fila sin tipo cargado—, que
            # antes pasaba desapercibida entre 157 filas idénticas.
            tipo_val = str(row.get(COL_TIPO, "") or "").strip() if COL_TIPO else ""
            excep = ("" if tipo_val == tipo_esperado else
                     f'<span class="tag-excep">{tipo_val or "sin tipo"}</span>')

            c_info, c_edit, c_del = st.columns(ANCHOS_FILA, vertical_alignment="center")
            c_info.markdown(
                f'<div class="fila-onb">'
                f'<div class="celda" data-label="Contraparte">'
                f'<b>{row.get("Contraparte", "—") or "—"}</b>{excep}</div>'
                f'<div class="celda" data-label="{etiq_fondo_col}">'
                f'{(row.get(col_fondo_local, "—") if col_fondo_local else "—") or "—"}</div>'
                f'<div class="celda" data-label="Etapa">{stepper}</div>'
                f'</div>', unsafe_allow_html=True)
            if c_edit.button("✏️", key=f"{clave}_edit_{idx}", help="Editar esta cuenta"):
                st.session_state["_abrir_modal"] = (clave, idx)
                st.rerun()
            # Borrar pide confirmación: son 600+ filas de datos reales y un
            # clic al lado del lápiz no puede borrar una cuenta sin más.
            if c_del.button("✕", key=f"{clave}_del_{idx}", help="Eliminar esta cuenta"):
                st.session_state["_confirmar_baja"] = (clave, idx)
                st.rerun()

    # ── MODAL DE EDICIÓN (sin drawer nativo en Streamlit: st.dialog es la
    # alternativa robusta — ventana centrada, sin recargar la página) ────
    @st.dialog("Editar cuenta")
    def _modal_editar_cuenta():
        clave, idx = st.session_state["_abrir_modal"]
        df_ref = df_com if clave == "com" else df_rem
        etapas = ETAPAS_COM if clave == "com" else ETAPAS_REM
        if idx not in df_ref.index:
            st.warning("Esta cuenta ya no está disponible (¿se filtró o se borró?).")
            if st.button("Cerrar"):
                del st.session_state["_abrir_modal"]
                st.rerun()
            return
        row = df_ref.loc[idx]
        col_fondo_local = _primera_col(CAND_FONDO, df_ref)

        st.markdown(f"**Contraparte:** {row.get('Contraparte', '—') or '—'}")
        st.markdown(f"**{col_fondo_local or 'Fondo'}:** "
                   f"{(row.get(col_fondo_local, '—') if col_fondo_local else '—') or '—'}")
        st.markdown(f"**Tipo de cuenta:** {(row.get(COL_TIPO, '—') if COL_TIPO else '—') or '—'}")

        etapa_actual = str(row.get("Etapa", "")).strip()
        idx_etapa = etapas.index(etapa_actual) if etapa_actual in etapas else 0
        nueva_etapa = st.selectbox("Etapa", etapas, index=idx_etapa, key="modal_etapa")

        obs_actual = str(row.get("Observaciones", "")) if pd.notna(row.get("Observaciones")) else ""
        nueva_obs = st.text_area("Observaciones / Comentarios", value=obs_actual, key="modal_obs")

        nuevo_com = None
        if clave == "com" and "Comentarios" in df_ref.columns:
            com_actual = str(row.get("Comentarios", "")) if pd.notna(row.get("Comentarios")) else ""
            nuevo_com = st.text_area("Comentarios internos", value=com_actual, key="modal_com")

        nuevo_ncuenta = nuevo_cbu = nuevo_alias = None
        cbu_invalido = False
        if nueva_etapa == etapas[-1]:
            st.markdown("**Habilitada para operar — completá el dato de cuenta:**")
            if clave == "com":
                actual_n = str(row.get("N° de Cuenta", "")) if pd.notna(row.get("N° de Cuenta")) else ""
                nuevo_ncuenta = st.text_input("N° de Cuenta Comitente", value=actual_n, key="modal_ncuenta")
            else:
                actual_cbu = str(row.get("CBU", "")) if pd.notna(row.get("CBU")) else ""
                actual_alias = str(row.get("Alias", "")) if pd.notna(row.get("Alias")) else ""
                nuevo_cbu = st.text_input("CBU Cuenta Remunerada", value=actual_cbu,
                                          max_chars=22, key="modal_cbu")
                cbu_invalido = bool(nuevo_cbu) and not (nuevo_cbu.isdigit() and len(nuevo_cbu) == 22)
                if cbu_invalido:
                    st.caption("⚠ El CBU debe tener 22 dígitos numéricos.")
                nuevo_alias = st.text_input("Alias", value=actual_alias, key="modal_alias")

        bc1, bc2 = st.columns(2)
        with bc1:
            guardar_modal = st.button("Guardar cambios", key="modal_guardar",
                                      type="primary", disabled=cbu_invalido)
        with bc2:
            cancelar_modal = st.button("Cancelar", key="modal_cancelar")

        if guardar_modal:
            cambios = {"Etapa": nueva_etapa, "Observaciones": nueva_obs}
            if nuevo_com is not None:
                cambios["Comentarios"] = nuevo_com
            if nuevo_ncuenta is not None:
                cambios["N° de Cuenta"] = nuevo_ncuenta
            if nuevo_cbu is not None:
                cambios["CBU"] = nuevo_cbu
            if nuevo_alias is not None:
                cambios["Alias"] = nuevo_alias
            st.session_state["ediciones_ctas"][clave][idx] = cambios
            del st.session_state["_abrir_modal"]
            st.rerun()
        if cancelar_modal:
            del st.session_state["_abrir_modal"]
            st.rerun()

    @st.dialog("Eliminar cuenta")
    def _modal_eliminar_cuenta():
        clave, idx = st.session_state["_confirmar_baja"]
        df_ref = df_com if clave == "com" else df_rem
        if idx not in df_ref.index:
            st.warning("Esta cuenta ya no está disponible.")
            if st.button("Cerrar", key="baja_cerrar"):
                del st.session_state["_confirmar_baja"]
                st.rerun()
            return
        row = df_ref.loc[idx]
        col_f = _col_fondo(df_ref)
        st.markdown("¿Eliminar esta cuenta de la hoja?")
        st.markdown(f"**Contraparte:** {row.get('Contraparte', '—') or '—'}")
        st.markdown(f"**{col_f or 'Fondo'}:** {(row.get(col_f, '—') if col_f else '—') or '—'}")
        st.markdown(f"**Estado:** {row.get('Estado', '—') or '—'}")
        st.markdown('<div class="note warn">Se saca de la tabla ahora, pero el Excel recién '
                    'cambia cuando apretás <b>Guardar cambios</b>. Hasta entonces podés '
                    'deshacerlo.</div>', unsafe_allow_html=True)

        bc1, bc2 = st.columns(2)
        with bc1:
            confirmar = st.button("Eliminar", key="baja_confirmar", type="primary")
        with bc2:
            cancelar = st.button("Cancelar", key="baja_cancelar")
        if confirmar:
            st.session_state["bajas_ctas"][clave].append(idx)
            # Si tenía ediciones pendientes, ya no aplican.
            st.session_state["ediciones_ctas"][clave].pop(idx, None)
            del st.session_state["_confirmar_baja"]
            st.rerun()
        if cancelar:
            del st.session_state["_confirmar_baja"]
            st.rerun()

    if "_abrir_modal" in st.session_state:
        _modal_editar_cuenta()
    if "_confirmar_baja" in st.session_state:
        _modal_eliminar_cuenta()

    if ver_com:
        with tabs[k]:
            _tabla_onboarding(vis_com, ETAPAS_COM, "com", "cuentas comitentes", TIPO_COM)
        k += 1
    if ver_rem:
        with tabs[k]:
            _tabla_onboarding(vis_rem, ETAPAS_REM, "rem", "cuentas remuneradas", TIPO_REM)
        k += 1

    # ── PRÉSTAMOS DE TÍTULOS ────────────────────────────────────────
    # Acá SÍ conviene una grilla editable y no el modal de las cuentas: son
    # 11 campos de carga, casi todos numéricos, y así se trabaja igual que
    # en el Excel del que vienen. Las 7 columnas de fórmula van bloqueadas.
    with tabs[k]:
        if res_pre is None:
            st.info("No hay hoja de préstamos todavía.")
        else:
            vig_pre = res_pre[res_pre["Estado"].astype(str).str.strip() == "Vigente"]
            d_vig = _dias_al_vto(vig_pre)
            nominales = pd.to_numeric(vig_pre["Cantidad"], errors="coerce").sum()
            a_cobrar = pd.to_numeric(vig_pre["A Cobrar"], errors="coerce").sum()
            prox = pd.to_datetime(vig_pre["Liquidación"], errors="coerce").min()

            p1, p2, p3, p4 = st.columns(4)
            with p1:
                st.markdown(f'<div class="kpi-card accent"><div class="kpi-label">Vigentes</div>'
                            f'<div class="kpi-value">{len(vig_pre)}</div>'
                            f'<div class="kpi-sub">de {len(res_pre)} en la hoja</div></div>',
                            unsafe_allow_html=True)
            with p2:
                st.markdown(f'<div class="kpi-card"><div class="kpi-label">Nominales prestados</div>'
                            f'<div class="kpi-value sm">{_fmt_num(nominales)}</div>'
                            f'<div class="kpi-sub">suma de cantidades vigentes</div></div>',
                            unsafe_allow_html=True)
            with p3:
                # "A cobrar" y no "rendimiento": es el interés pactado del
                # alquiler, no el retorno de ninguna cartera.
                st.markdown(f'<div class="kpi-card"><div class="kpi-label">Interés a cobrar</div>'
                            f'<div class="kpi-value sm">{_fmt_num(a_cobrar, 2)}</div>'
                            f'<div class="kpi-sub">de los préstamos vigentes</div></div>',
                            unsafe_allow_html=True)
            with p4:
                if pd.notna(prox):
                    faltan = int((prox - HOY_PRE).days)
                    txt = ("vencido" if faltan < 0 else
                           "es hoy" if faltan == 0 else f"en {faltan} día(s)")
                    color = RED if faltan <= 0 else (AMBER if faltan <= DIAS_AVISO_PRE else GREEN)
                    st.markdown(
                        f'<div class="kpi-card"><div class="kpi-label">Próximo vencimiento</div>'
                        f'<div class="kpi-value sm" style="color:{color}">'
                        f'{prox.strftime("%d/%m/%Y")}</div>'
                        f'<div class="kpi-sub">{txt}</div></div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="kpi-card"><div class="kpi-label">Próximo '
                                'vencimiento</div><div class="kpi-value sm">—</div>'
                                '<div class="kpi-sub">sin préstamos vigentes</div></div>',
                                unsafe_allow_html=True)

            fp1, fp2, fp3 = st.columns([1.4, 1.2, 1.2])
            with fp1:
                f_est_pre = st.multiselect("Estado", ESTADOS_PRE, default=["Vigente"],
                                           key="fp_estado", placeholder="Todos")
            with fp2:
                fondos_pre = sorted(res_pre["Fondo"].dropna().astype(str).str.strip().unique())
                f_fondo_pre = st.multiselect("Fondo", fondos_pre, key="fp_fondo",
                                             placeholder="Todos")
            with fp3:
                ctp_pre = sorted(res_pre["Contraparte"].dropna().astype(str).str.strip().unique())
                f_ctp_pre = st.multiselect("Contraparte", ctp_pre, key="fp_ctp",
                                           placeholder="Todas")

            mostrar = res_pre
            for col, sel in (("Estado", f_est_pre), ("Fondo", f_fondo_pre),
                             ("Contraparte", f_ctp_pre)):
                if sel:
                    mostrar = mostrar[mostrar[col].astype(str).str.strip().isin(sel)]

            st.markdown(f'<div class="chart-label">{len(mostrar)} préstamo(s) · '
                        f'las columnas grises se calculan solas</div>', unsafe_allow_html=True)

            # Se muestra con índice corrido y se guarda el original aparte:
            # con un índice salteado (72, 75, 76…) Streamlit ignora
            # hide_index y dibuja esos números como si fueran una columna más.
            idx_orig = list(mostrar.index)
            vista = mostrar.reset_index(drop=True).copy()
            # Las calculadas van como TEXTO ya formateado. La grilla dibuja
            # "None" en toda celda numérica vacía —da igual el format o que
            # esté bloqueada, lo comprobé— y acá 69 de 77 filas no tienen
            # precio. Como son de solo lectura, pasarlas a texto no cuesta
            # nada y de paso quedan con separador de miles argentino.
            DEC_PRE = {"Plazo": 0, "Monto": 2, "Tasa Aplicada": 6, "Interés": 2,
                       "Interés Diario": 2, "Ajuste": 4, "A Cobrar": 2}
            for c, dec in DEC_PRE.items():
                vista[c] = mostrar[c].map(lambda v: _fmt_num(v, dec)).values

            ed_pre = st.data_editor(
                vista, hide_index=True, num_rows="dynamic", key="ed_pre",
                height=int(min(520, 80 + 35 * max(len(mostrar), 3))),
                disabled=PRE_CALCULO + PRE_HISTORICO,
                column_config={
                    "Concertación": st.column_config.DateColumn("Concertación", format="DD/MM/YYYY"),
                    "Liquidación": st.column_config.DateColumn("Vencimiento", format="DD/MM/YYYY"),
                    "Plazo": st.column_config.TextColumn("Plazo", help="Vencimiento − concertación", width="small"),
                    "Deudor": st.column_config.TextColumn("Deudor"),
                    "Fondo": st.column_config.TextColumn("Fondo"),
                    "Contraparte": st.column_config.TextColumn("Contraparte"),
                    "Especie": st.column_config.TextColumn("Especie"),
                    "Cantidad": st.column_config.NumberColumn("Cantidad", format="%.0f"),
                    "Tasa": st.column_config.NumberColumn("Tasa", format="%.4f", help="Anual, en tanto por uno (0,03 = 3%)"),
                    "Precio": st.column_config.NumberColumn("Precio", format="%.6f"),
                    "Monto": st.column_config.TextColumn("Monto", help="Cantidad × Precio"),
                    "Tasa Aplicada": st.column_config.TextColumn("Tasa aplicada", help="Tasa × Plazo / 365"),
                    "Interés": st.column_config.TextColumn("Interés", help="Monto × Tasa aplicada"),
                    "Interés Diario": st.column_config.TextColumn("Interés diario", help="Interés / Plazo"),
                    "Ajuste": st.column_config.TextColumn("Ajuste", help="A cobrar − Interés"),
                    "A Cobrar": st.column_config.TextColumn("A cobrar", help="Interés redondeado"),
                    "Estado": st.column_config.SelectboxColumn("Estado", options=ESTADOS_PRE, required=False),
                    "Observaciones": st.column_config.TextColumn("Observaciones", width="medium"),
                    "Pasado a vencidos": st.column_config.DateColumn(
                        "Pasado a vencidos", format="DD/MM/YYYY",
                        help="Histórico del método viejo de dos hojas. Ya no se usa."),
                })

            # Streamlit devuelve la grilla conservando el índice de cada fila
            # que sobrevivió (las borradas simplemente no vienen) y numera las
            # altas a partir del final. Por eso se mapea por ÍNDICE y no por
            # posición: borrar una fila del medio corre todas las de abajo y
            # el mapeo posicional terminaría escribiendo en el préstamo
            # equivocado.
            n = len(idx_orig)
            vivas = [i for i in ed_pre.index if isinstance(i, (int, np.integer)) and i < n]
            nuevas = [i for i in ed_pre.index if i not in vivas]

            # Solo vuelven las columnas de carga: las calculadas se mostraron
            # como texto ya formateado ("1.678.982,48") y devolverlas sería
            # meter esa cadena en una columna numérica.
            EDITABLES = [c for c in PRE_ENTRADA + PRE_HISTORICO if c in ed_pre.columns]
            editadas = ed_pre.loc[vivas, EDITABLES].copy()
            editadas.index = [idx_orig[i] for i in vivas]
            altas = ed_pre.loc[nuevas, EDITABLES]

            base = res_pre.copy()
            borradas = [idx_orig[i] for i in range(n) if i not in set(vivas)]
            if borradas:
                base = base.drop(index=borradas, errors="ignore")
            if len(editadas):
                base.loc[editadas.index, EDITABLES] = editadas
            res_pre = (pd.concat([base, altas], ignore_index=True)
                       if len(altas) else base)
            res_pre = _recalcular_pre(res_pre)

            st.markdown(
                '<div class="note"><b>Cómo se carga un préstamo.</b> Escribí en la última fila '
                'vacía: concertación, vencimiento, deudor, fondo, contraparte, especie, cantidad, '
                'tasa y precio. El plazo, el monto, el interés y lo que hay a cobrar se calculan '
                'solos — por eso están en gris y no se pueden escribir. Para dar de baja una fila, '
                'seleccionala con el casillero de la izquierda y apretá la papelera. Todo queda '
                'pendiente hasta que aprietes <b>Guardar cambios</b> abajo.</div>',
                unsafe_allow_html=True)
            if len(vig_pre) and pd.to_numeric(vig_pre["Precio"], errors="coerce").isna().any():
                sin_precio = int(pd.to_numeric(vig_pre["Precio"], errors="coerce").isna().sum())
                st.markdown(
                    f'<div class="note warn"><b>{sin_precio} de {len(vig_pre)} préstamos vigentes '
                    f'no tienen precio cargado</b>, así que su monto e interés quedan en cero. '
                    f'Venían así del Excel original. Cargá el precio de la especie y los números '
                    f'se completan solos.</div>', unsafe_allow_html=True)
    k += 1

    # ── VISTA CONSOLIDADA (solo lectura, con fondo de color por estado) ──
    with tabs[k]:
        partes = []
        for d, tipo in ((vis_com, TIPO_COM), (vis_rem, TIPO_REM)):
            if d is None or d.empty:
                continue
            p = d.copy()
            if not COL_TIPO:
                p.insert(0, "Tipo", tipo)
            partes.append(p)
        if partes:
            cons = pd.concat(partes, ignore_index=True, sort=False)
            # Acá sí se puede recortar de verdad: esta vista es de solo lectura,
            # no se guarda, así que sacar la columna no toca el Excel.
            cons = cons[[c for c in cons.columns
                         if not any(p in str(c).lower() for p in OCULTAR)]]
            frente = [c for c in (COL_TIPO or "Tipo", "Contraparte", COL_FONDO, "Estado")
                      if c and c in cons.columns]
            cons = cons[frente + [c for c in cons.columns if c not in frente]]
            st.markdown(f'<div class="chart-label">{len(cons)} cuentas · comitentes y '
                        f'remuneradas juntas</div>', unsafe_allow_html=True)

            def _pintar(fila):
                e = str(fila.get("Estado", "")).strip()
                bg = EST_FONDO.get(e, "")
                return [f"background-color:{bg}" if bg else "" for _ in fila]

            def _pintar_estado(col):
                return [f"color:{EST_TEXTO.get(str(v).strip(), GRAY_TEXT)};font-weight:700"
                        for v in col]

            try:
                # na_rep="" es imprescindible: sin eso el Styler imprime
                # literalmente "None" en cada celda vacía.
                sty = cons.style.apply(_pintar, axis=1).format(na_rep="", precision=0)
                if "Estado" in cons.columns:
                    sty = sty.apply(_pintar_estado, subset=["Estado"])
                st.dataframe(sty, hide_index=True,
                             height=int(min(500, 45 + 35 * max(len(cons), 1))))
            except Exception:
                df_show(cons, hide_index=True)

            st.download_button(
                "⬇  Descargar esta vista (CSV)",
                cons.to_csv(index=False).encode("utf-8-sig"),
                file_name="novus_cuentas_filtrado.csv", mime="text/csv", key="dl_cons")
            st.markdown('<div class="note">Acá el color va en el fondo de la fila. Es de solo '
                        'lectura a propósito: mezcla las dos hojas, así que editar sería ambiguo. '
                        'Para cambiar datos usá las pestañas de Comitentes o Remuneradas.</div>',
                        unsafe_allow_html=True)
        else:
            st.info("Nada para mostrar con los filtros actuales.")
    k += 1

    # ── CATÁLOGO DE FCI (acá se dan de alta los fondos nuevos) ──────
    with tabs[k]:
        st.markdown(f'<div class="chart-label">{len(CATALOGO)} FCI en el catálogo · '
                    f'esta lista alimenta todos los desplegables</div>', unsafe_allow_html=True)
        vis_fci = df_fci
        if f_fondo and df_fci is not None and "FCI" in df_fci.columns:
            vis_fci = df_fci[df_fci["FCI"].astype(str).str.strip().isin(f_fondo)]
        ed_fci = st.data_editor(vis_fci, num_rows="fixed" if f_fondo else "dynamic",
                                hide_index=True, key="ed_fci")
        if f_fondo and df_fci is not None and "FCI" in df_fci.columns:
            base = df_fci.copy()
            if len(ed_fci):
                base.loc[ed_fci.index, ed_fci.columns] = ed_fci
            res_fci = base
        else:
            res_fci = ed_fci

        st.markdown(
            '<div class="note"><b>Acá se da de alta un FCI nuevo.</b> Escribilo en la última '
            'fila vacía junto con su número de CNV y guardá. Desde ese momento aparece en el '
            'desplegable de FCI del alta de cuentas y en el filtro. Es la única puerta de '
            'entrada de fondos nuevos, y por eso los nombres se mantienen unificados. '
            'Ojo con los repetidos: si un fondo figura dos veces con distinto nombre, van a '
            'convivir como si fueran dos.</div>', unsafe_allow_html=True)

        # Duplicados dentro del propio catálogo (mismo fondo, distinta escritura)
        if CATALOGO:
            por_clave = {}
            for nombre in CATALOGO:
                por_clave.setdefault(_norm_fci(nombre), []).append(nombre)
            repes = {k2: v for k2, v in por_clave.items() if len(v) > 1}
            if repes:
                detalle = " · ".join(" = ".join(v) for v in repes.values())
                st.markdown(f'<div class="note warn"><b>El catálogo tiene nombres repetidos:</b> '
                            f'{detalle}. Conviene dejar uno solo.</div>', unsafe_allow_html=True)
    k += 1

    # ── UNIFICAR NOMBRES DE FCI ─────────────────────────────────────
    if fci_sueltos:
        with tabs[k]:
            st.markdown(f'<div class="chart-label">{len(fci_sueltos)} nombres de FCI que no '
                        f'están en el catálogo</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="note warn"><b>Revisá una por una antes de aplicar.</b> La sugerencia '
                'automática compara ignorando acentos, mayúsculas, espacios de más y el sufijo '
                '"FCI". Las <b>exactas</b> vienen ya elegidas. Las que son solo <i>parecidas</i> '
                'quedan sin elegir a propósito: en las pruebas, "Novus Gestion 2" se parecía más a '
                '"Novus Gestión" que a "Novus Gestion II", así que decidir sola sería peligroso.'
                '</div>', unsafe_allow_html=True)

            filas_uni = []
            for valor in sorted(fci_sueltos):
                sug, etiqueta, ratio = _sugerir_fci(valor)
                n_filas = 0
                for d in (df_com, df_rem):
                    col = _col_fondo(d)
                    if d is not None and not d.empty and col:
                        n_filas += int((d[col].astype(str).str.strip() == valor).sum())
                # Solo se pre-elige lo exacto o casi idéntico (typos).
                elegido = sug if (ratio >= 0.95 and sug) else SIN_TOCAR
                filas_uni.append({"Nombre actual": valor, "Filas": n_filas,
                                  "Coincidencia": etiqueta,
                                  "Sugerencia": sug or "—", "Unificar con": elegido})
            df_uni = pd.DataFrame(filas_uni).sort_values(
                ["Filas"], ascending=False).reset_index(drop=True)

            ed_uni = st.data_editor(
                df_uni, hide_index=True, num_rows="fixed", key="ed_uni",
                height=int(min(430, 45 + 35 * max(len(df_uni), 1))),
                disabled=["Nombre actual", "Filas", "Coincidencia", "Sugerencia"],
                column_config={
                    "Nombre actual": st.column_config.TextColumn("Nombre actual", width="medium"),
                    "Filas": st.column_config.NumberColumn("Filas", width="small"),
                    "Coincidencia": st.column_config.TextColumn("Coincidencia", width="small"),
                    "Sugerencia": st.column_config.TextColumn("Sugerencia", width="medium"),
                    "Unificar con": st.column_config.SelectboxColumn(
                        "Unificar con", options=[SIN_TOCAR] + CATALOGO,
                        required=False, width="medium"),
                })

            a_cambiar = {}
            filas_afectadas = 0
            for _, r in ed_uni.iterrows():
                destino_fci = r.get("Unificar con")
                if destino_fci and destino_fci != SIN_TOCAR and destino_fci != r["Nombre actual"]:
                    a_cambiar[str(r["Nombre actual"])] = str(destino_fci)
                    filas_afectadas += int(r["Filas"] or 0)

            c_uni1, c_uni2 = st.columns([1.3, 3])
            with c_uni1:
                aplicar = st.button(f"🔗  Unificar {len(a_cambiar)} nombre(s)",
                                    key="btn_uni", disabled=not a_cambiar)
            with c_uni2:
                if a_cambiar:
                    st.markdown(f'<div class="note">Va a reescribir <b>{filas_afectadas} filas</b>. '
                                f'El cambio se ve en las tablas al instante, pero recién queda '
                                f'firme cuando apretás <b>Guardar cambios</b>.</div>',
                                unsafe_allow_html=True)
            if aplicar:
                st.session_state["mapa_fci"].update(a_cambiar)
                st.rerun()
        k += 1
    else:
        if CATALOGO:
            st.markdown('<div class="note" style="margin-top:8px">✅ Todos los FCI de las cuentas '
                        'coinciden con el catálogo, así que la columna FCI es un desplegable y no '
                        'se pueden escribir variantes nuevas.</div>', unsafe_allow_html=True)

    # ── UNIFICAR NOMBRES DE CONTRAPARTE ─────────────────────────────
    if grupos_ctp:
        with tabs[k]:
            st.markdown(f'<div class="chart-label">{len(grupos_ctp)} contrapartes escritas de '
                        f'más de una forma</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="note warn"><b>Elegí con qué nombre queda cada grupo.</b> Vienen ya '
                'elegidos con la variante más usada ("Supervielle" / "Banco Supervielle" / '
                '"Banco Supervielle S.A."). Quedan <i>sin elegir</i> a propósito los grupos donde '
                'conviven un banco y una ALyC del mismo nombre —"Banco Santander" y "Santander '
                'Valores", "Banco Macro" y "Macro Securities"—, porque suelen ser dos contrapartes '
                'distintas. Revisá igual cada línea antes de unificar.</div>', unsafe_allow_html=True)

            NO_UNIF = "— dejar como están —"
            elecciones = {}
            # Ordenados por el nombre más usado de cada grupo, no por la clave
            # interna: un grupo cuyas palabras son todas genéricas ("Banco de
            # Valores" / "Valores") tiene clave vacía y quedaría primero.
            for clave_g, variantes in sorted(grupos_ctp.items(),
                                             key=lambda kv: _sin_acentos(kv[1][0])):
                total_filas = sum(ctp_conteo[v] for v in variantes)
                detalle = " · ".join(f"{v} ({ctp_conteo[v]})" for v in variantes)
                # Preselección salvo que el grupo mezcle un banco con su ALyC.
                if _conflicto_banco_alyc(variantes):
                    por_defecto = NO_UNIF
                elif len({_sin_acentos(v) for v in variantes}) == 1:
                    # Se escriben igual salvo por los acentos ("Banco Nacion" /
                    # "Banco Nación"): gana la forma acentuada aunque sea la
                    # menos usada, porque es la ortografía correcta.
                    # Se compara en minúscula: si no, cada mayúscula contaría
                    # como acento y ganaría la variante escrita toda en altas.
                    por_defecto = max(variantes,
                                      key=lambda v: (sum(c != d for c, d in
                                                         zip(v.lower(), _sin_acentos(v))),
                                                     ctp_conteo[v]))
                else:
                    por_defecto = variantes[0]   # la variante más usada
                opciones = [NO_UNIF] + variantes
                gc1, gc2 = st.columns([2, 1.4], vertical_alignment="center")
                with gc1:
                    st.markdown(f'<div style="font-size:.8rem;padding-top:6px">{detalle}'
                                f'<br><span style="color:{GRAY_TEXT};font-size:.72rem">'
                                f'{total_filas} filas en total</span></div>',
                                unsafe_allow_html=True)
                with gc2:
                    elecciones[clave_g] = st.selectbox(
                        "Unificar con", opciones, index=opciones.index(por_defecto),
                        key=f"ctp_uni_{clave_g}", label_visibility="collapsed")

            a_cambiar_ctp, filas_ctp = {}, 0
            for clave_g, destino in elecciones.items():
                if destino == NO_UNIF:
                    continue
                for v in grupos_ctp[clave_g]:
                    if v != destino:
                        a_cambiar_ctp[v] = destino
                        filas_ctp += ctp_conteo[v]

            cu1, cu2 = st.columns([1.3, 3], vertical_alignment="center")
            with cu1:
                aplicar_ctp = st.button(f"🔗  Unificar {len(a_cambiar_ctp)} nombre(s)",
                                        key="btn_uni_ctp", disabled=not a_cambiar_ctp)
            with cu2:
                if a_cambiar_ctp:
                    st.markdown(f'<div class="note">Va a reescribir <b>{filas_ctp} filas</b>. '
                                f'El cambio se ve al instante, pero recién queda firme cuando '
                                f'apretás <b>Guardar cambios</b>.</div>', unsafe_allow_html=True)
            if aplicar_ctp:
                st.session_state["mapa_ctp"].update(a_cambiar_ctp)
                st.rerun()

    # ── GUARDAR ─────────────────────────────────────────────────────
    # Un solo botón escribe las TRES hojas completas. Un botón por pestaña
    # hacía que guardar en una pisara lo editado en la otra, porque el handler
    # corre antes de que exista la variable del editor siguiente.
    def _armar_excel():
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            a_datos(res_com).to_excel(w, sheet_name=HOJA_COM, index=False)
            a_datos(res_rem).to_excel(w, sheet_name=HOJA_REM, index=False)
            res_fci.to_excel(w, sheet_name=HOJA_FCI, index=False)
            # Se recalcula una vez más justo antes de escribir: si alguien
            # tocó cantidad o precio, el monto y el interés que van al Excel
            # tienen que ser los del dato nuevo, no los de la carga.
            pre_out = _recalcular_pre(res_pre)
            if pre_out is None:
                pre_out = pd.DataFrame(columns=COLS_PRE)
            for c in ("Concertación", "Liquidación", "Pasado a vencidos"):
                pre_out[c] = pd.to_datetime(pre_out[c], errors="coerce").dt.date
            pre_out.to_excel(w, sheet_name=HOJA_PRE, index=False)
        return buf.getvalue()

    st.markdown('<div class="section-title">Guardar</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)

    if MODO_EDICION:
        g1, g2, _g3 = st.columns([1.4, 1.1, 3], vertical_alignment="center")
        with g1:
            iniciales = st.text_input("Tus iniciales", max_chars=6, placeholder="LS",
                                      label_visibility="collapsed", key="firma")
        with g2:
            guardar = st.button("💾  Guardar cambios", key="btn_guardar")
        if guardar:
            if not (iniciales or "").strip():
                st.warning("Poné tus iniciales antes de guardar — quedan en el historial.")
            else:
                try:
                    sello = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                    ok, err = _subir_excel(
                        _armar_excel(), sha_actual,
                        f"Seguimiento de cuentas · {iniciales.strip().upper()} · {sello}")
                    if ok:
                        cargar_cuentas.clear()
                        # Recién ahora se limpia lo pendiente: si el guardado
                        # fallaba, se perdían las cuentas nuevas. Las bajas y
                        # las ediciones van por etiqueta de fila, y al releer
                        # el Excel esas etiquetas ya no son las mismas, así
                        # que también hay que vaciarlas o se aplicarían a la
                        # fila equivocada.
                        st.session_state["nuevas_ctas"] = {"com": [], "rem": []}
                        st.session_state["bajas_ctas"] = {"com": [], "rem": []}
                        st.session_state["ediciones_ctas"] = {"com": {}, "rem": {}}
                        st.session_state["mapa_fci"] = {}
                        st.session_state["mapa_ctp"] = {}
                        st.session_state["_cuentas_nonce"] = nonce + 1
                        st.success(f"Guardado en el repo a nombre de {iniciales.strip().upper()}. "
                                   f"Las filas que el filtro no mostraba quedaron intactas.")
                        st.rerun()
                    else:
                        st.error(err)
                except Exception as e:
                    st.error(f"No se pudo armar el Excel: {e}")
        st.markdown(
            f'<div class="note" style="margin-top:10px">Cada guardado hace un commit en la rama '
            f'<code>{GH_BRANCH}</code> del repo privado, con tus iniciales y la fecha. Se escriben '
            f'siempre las tres hojas completas, filtres o no. Si dos personas guardan a la vez, el '
            f'segundo recibe un aviso en lugar de pisar el trabajo del otro.</div>',
            unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="note warn"><b>Todavía no se puede guardar solo.</b> Editá lo que '
            'necesites y bajá el Excel actualizado con el botón de abajo; después lo subís al repo. '
            'Es un paso manual temporal: en cuanto estén <code>github_token</code> y '
            '<code>github_repo</code> en los Secrets, aparece un botón de <b>Guardar</b> y este '
            'ida y vuelta desaparece.</div>', unsafe_allow_html=True)
        try:
            st.download_button(
                "⬇  Descargar Excel actualizado",
                _armar_excel(), file_name="seguimiento_cuentas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_xls_ctas")
        except Exception as e:
            st.error(f"No se pudo armar el Excel: {e}")

    # ── FOOTER ──────────────────────────────────────────────────────
    # El botón de salir vive en el header, arriba; acá solo queda la franja de marca.
    st.markdown(f"""
    <div style="background:{DARK_BG}; margin: 1rem calc(-1 * var(--novus-pad)) -1rem calc(-1 * var(--novus-pad));
                padding: 16px var(--novus-pad);
                display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
      <div style="color:{GREEN}; font-size:.85rem; font-weight:600;">
        novus <span style="color:#9AADA9; font-weight:300;">asset management</span></div>
      <div style="color:#777; font-size:.7rem;">middle office · onboarding de cuentas</div>
    </div>
    """, unsafe_allow_html=True)

    st.stop()


if modulo == M_FCI:
    # ═══════════════════════════════════════════════════════════════
    # MÓDULO 3 — SUSCRIPCIONES Y RESCATES DE FCI
    # ═══════════════════════════════════════════════════════════════
    FCI_FLUJOS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fci_flujos.csv")
    FCI_AUM_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fci_patrimonio.csv")
    MESES_ABR = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
                 7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}

    def _col(df, candidatos):
        """Busca, sin distinguir mayúsculas ni espacios, la primera columna
        de `df` que matchee alguno de los `candidatos`. None si no hay match."""
        idx = {str(c).strip().lower().replace(" ", "_"): c for c in df.columns}
        for cand in candidatos:
            real = idx.get(cand.strip().lower().replace(" ", "_"))
            if real is not None:
                return real
        return None

    def _renombrar(df, mapa_candidatos, requeridas):
        """mapa_candidatos: {nombre_canónico: [candidatos]}. Renombra las
        columnas encontradas al nombre canónico; corta la app con un error
        legible si falta alguna de las `requeridas`."""
        resueltas, faltan = {}, []
        for canon, candidatos in mapa_candidatos.items():
            real = _col(df, candidatos)
            if real is not None:
                resueltas[real] = canon
            elif canon in requeridas:
                faltan.append(canon)
        if faltan:
            st.error(f"Al archivo le faltan columnas esperadas: {', '.join(faltan)}.")
            st.stop()
        return df.rename(columns=resueltas)

    @st.cache_data(ttl=600, show_spinner="Cargando suscripciones y rescates…")
    def _cargar_fci_flujos(path, _mtime):
        df = pd.read_csv(path)
        df = _renombrar(df, {
            "Fecha": ["fecha", "fecha_movimiento", "date"],
            "Fondo": ["fondo", "fci", "nombre_fondo"],
            "Tipo": ["tipo", "tipo_fondo", "categoria"],
            "Movimiento": ["movimiento", "tipo_operacion", "tipo_op"],
            "Moneda": ["moneda", "moneda_liquidacion", "simbolo"],
            "Cantidad_Cuotapartes": ["cantidad_cuotapartes", "cantidad", "cuotapartes"],
            "Valor_Cuotaparte": ["valor_cuotaparte", "vcp"],
            "Importe": ["importe", "monto", "importe_original"],
            "Importe_USD": ["importe_usd", "monto_usd", "importe_dolares"],
        }, requeridas={"Fecha", "Fondo", "Tipo", "Movimiento", "Importe_USD"})
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
        df = df.dropna(subset=["Fecha"])
        for c in ("Fondo", "Tipo", "Movimiento", "Moneda"):
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()
        for c in ("Cantidad_Cuotapartes", "Valor_Cuotaparte", "Importe", "Importe_USD"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        df["MesInicio"] = df["Fecha"].dt.to_period("M").dt.to_timestamp()
        return df.sort_values("Fecha").reset_index(drop=True)

    @st.cache_data(ttl=600, show_spinner="Cargando patrimonio de FCI…")
    def _cargar_fci_aum(path, _mtime):
        df = pd.read_csv(path)
        df = _renombrar(df, {
            "Fecha": ["fecha", "date"],
            "Fondo": ["fondo", "fci", "nombre_fondo"],
            "Tipo": ["tipo", "tipo_fondo", "categoria"],
            "Moneda": ["moneda", "moneda_patrimonio"],
            "PatrimonioNeto": ["patrimonioneto", "patrimonio_neto", "patrimonio", "aum"],
            "PatrimonioNeto_USD": ["patrimonioneto_usd", "patrimonio_neto_usd", "aum_usd", "patrimonio_usd"],
        }, requeridas={"Fecha", "Fondo", "Tipo", "PatrimonioNeto_USD"})
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
        df = df.dropna(subset=["Fecha"])
        for c in ("Fondo", "Tipo", "Moneda"):
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()
        for c in ("PatrimonioNeto", "PatrimonioNeto_USD"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        return df.sort_values("Fecha").reset_index(drop=True)

    st.markdown(f"""
    <div class="novus-hero">
      <div class="novus-eyebrow">middle office</div>
      <h1>flujos &amp; <span>fondos</span></h1>
      <p>Suscripciones, rescates y evolución de patrimonio.</p>
    </div>
    """, unsafe_allow_html=True)

    if not os.path.exists(FCI_FLUJOS_PATH) or not os.path.exists(FCI_AUM_PATH):
        st.warning("Todavía no están cargados `fci_flujos.csv` y/o `fci_patrimonio.csv` junto a `app.py`.")
        st.stop()

    df_flujos_raw = _cargar_fci_flujos(FCI_FLUJOS_PATH, os.path.getmtime(FCI_FLUJOS_PATH))
    df_aum_raw    = _cargar_fci_aum(FCI_AUM_PATH, os.path.getmtime(FCI_AUM_PATH))

    if df_flujos_raw.empty or df_aum_raw.empty:
        st.error("Alguna de las bases de FCI está vacía.")
        st.stop()

    FCI_MIN = min(df_flujos_raw["Fecha"].min(), df_aum_raw["Fecha"].min())
    FCI_MAX = max(df_flujos_raw["Fecha"].max(), df_aum_raw["Fecha"].max())

    # ── FILTROS ─────────────────────────────────────────────────────
    tipos_disp  = sorted(set(df_flujos_raw["Tipo"]) | set(df_aum_raw["Tipo"]))
    fondos_disp = sorted(set(df_flujos_raw["Fondo"]) | set(df_aum_raw["Fondo"]))
    # Color estable por tipo de fondo: se define una sola vez acá y se
    # reutiliza en el pie de participación y en los swatches de las tablas,
    # así el mismo tipo siempre tiene el mismo color en toda la solapa.
    TIPO_COLOR = {t: AGENT_PALETTE[i % len(AGENT_PALETTE)] for i, t in enumerate(tipos_disp)}

    with st.expander("🔍  Filtros  ·  vacío = todos", expanded=True):
        gc1, gc2, gc3 = st.columns([1, 1, 1.3])
        with gc1:
            f_tipo = st.multiselect("Tipo de fondo", tipos_disp, placeholder="Todos", key="fci_f_tipo")
        with gc2:
            f_fondo = st.multiselect("Fondo", fondos_disp, placeholder="Todos", key="fci_f_fondo")
        with gc3:
            f_fecha = st.date_input("Período", value=(FCI_MIN.date(), FCI_MAX.date()),
                                    min_value=FCI_MIN.date(), max_value=FCI_MAX.date(), key="fci_f_fecha")

    # Los fondos Money Market / T+0 mueven muchísimo más volumen diario que
    # el resto (el efectivo entra y sale todo el tiempo): este switch los
    # saca de la vista para poder ver la dinámica de las demás estrategias
    # sin que queden aplastadas en los gráficos y rankings.
    MM_TIPOS = {"Money Market", "Money Market USDMEP"}
    excluir_mm = st.checkbox("Excluir Money Market / T+0", value=True, key="fci_excluir_mm",
                             help="Activado por defecto: con suscripciones de USD 3,85B sobre un "
                                  "patrimonio de USD 226M, la vista sin filtrar es puro ida y vuelta "
                                  "de caja de corto plazo y tapa la dinámica del resto de los fondos.")

    fci_desde, fci_hasta = FCI_MIN, FCI_MAX
    if isinstance(f_fecha, (tuple, list)):
        if len(f_fecha) == 2:
            fci_desde, fci_hasta = pd.Timestamp(f_fecha[0]), pd.Timestamp(f_fecha[1])
        elif len(f_fecha) == 1:
            fci_desde = pd.Timestamp(f_fecha[0])
    elif f_fecha:
        fci_desde = pd.Timestamp(f_fecha)

    def _filtrar_fci(df):
        d = df[(df["Fecha"] >= fci_desde) & (df["Fecha"] <= fci_hasta)]
        if f_tipo:
            d = d[d["Tipo"].isin(f_tipo)]
        if f_fondo:
            d = d[d["Fondo"].isin(f_fondo)]
        if excluir_mm:
            d = d[~d["Tipo"].isin(MM_TIPOS)]
        return d

    df_flujos = _filtrar_fci(df_flujos_raw)
    df_aum    = _filtrar_fci(df_aum_raw)

    if df_flujos.empty or df_aum.empty:
        st.warning("Ningún dato coincide con los filtros elegidos.")
        st.stop()

    # ── KPIs DE FLUJO ───────────────────────────────────────────────
    susc = df_flujos.loc[df_flujos["Movimiento"] == "Suscripcion", "Importe_USD"].sum()
    resc = df_flujos.loc[df_flujos["Movimiento"] == "Rescate", "Importe_USD"].sum()
    neto = susc - resc

    st.markdown('<div class="section-title">Flujo del período</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f'<div class="kpi-card accent"><div class="kpi-label">🟢 Suscripciones</div>'
                    f'<div class="kpi-value">{fmt_usd(susc)}</div>'
                    f'<div class="kpi-sub">bruto, convertido a USD</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">🔴 Rescates</div>'
                    f'<div class="kpi-value" style="color:{RED}">{fmt_usd(resc)}</div>'
                    f'<div class="kpi-sub">bruto, convertido a USD</div></div>', unsafe_allow_html=True)
    with k3:
        color_neto = GREEN_DIM if neto >= 0 else RED
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Flujo neto</div>'
                    f'<div class="kpi-value" style="color:{color_neto}">{fmt_usd(neto)}</div>'
                    f'<div class="kpi-sub">suscripciones − rescates</div></div>', unsafe_allow_html=True)
    with k4:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Movimientos</div>'
                    f'<div class="kpi-value sm">{len(df_flujos):,}</div>'
                    f'<div class="kpi-sub">{df_flujos["Fondo"].nunique()} fondos con actividad</div></div>',
                    unsafe_allow_html=True)

    # ── DESCOMPOSICIÓN DEL PATRIMONIO (nivel total) ───────────────────
    st.markdown('<div class="section-title" style="margin-top:22px">Descomposición del patrimonio</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)

    pat_ini_total = df_aum.loc[df_aum["Fecha"] == df_aum["Fecha"].min(), "PatrimonioNeto_USD"].sum()
    pat_fin_total = df_aum.loc[df_aum["Fecha"] == df_aum["Fecha"].max(), "PatrimonioNeto_USD"].sum()
    # Residual contable: lo que no explica ni el patrimonio inicial ni el
    # flujo neto. Absorbe retorno de cartera, efecto cambiario (conversión
    # ARS/USD) y el timing de los flujos dentro del período — por eso NO se
    # llama "rendimiento": no es un cálculo de retorno de cuotaparte.
    efecto_mercado_tc_total = pat_fin_total - pat_ini_total - neto

    def _celda_cadena(label, valor, color=None):
        col_style = f"color:{color};" if color else ""
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
                    f'<div class="kpi-value sm" style="{col_style}">{fmt_usd(valor)}</div></div>',
                    unsafe_allow_html=True)

    def _op_cadena(simbolo):
        # La clase cadena-op es la que el CSS esconde en pantallas chicas,
        # donde las tarjetas se apilan y el signo ya no ubica nada.
        st.markdown(f'<div class="cadena-op" style="text-align:center;font-size:1.3rem;'
                    f'font-weight:700;color:{GRAY_TEXT};">{simbolo}</div>',
                    unsafe_allow_html=True)

    # El container con key es lo que le permite al CSS hacer que esta cadena
    # de 11 columnas se acomode en varias filas en pantallas medianas/chicas
    # (ver "RESPONSIVE" en los estilos) en vez de partir las palabras.
    cadena_box = st.container(key="novus_cadena")
    with cadena_box:
        cad = st.columns([2, 0.4, 2, 0.4, 2, 0.4, 2, 0.4, 2.3, 0.4, 2],
                         vertical_alignment="center")
    with cad[0]:  _celda_cadena("Patrimonio inicial", pat_ini_total)
    with cad[1]:  _op_cadena("+")
    with cad[2]:  _celda_cadena("Suscripciones", susc, GREEN_DIM)
    with cad[3]:  _op_cadena("−")
    with cad[4]:  _celda_cadena("Rescates", resc, RED)
    with cad[5]:  _op_cadena("=")
    with cad[6]:  _celda_cadena("Flujo neto", neto, GREEN_DIM if neto >= 0 else RED)
    with cad[7]:  _op_cadena("+")
    with cad[8]:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Efecto mercado + TC '
                    f'<span title="Residual contable: Patrimonio final − Patrimonio inicial − Flujo '
                    f'neto. Incluye retorno de cartera, efecto cambiario (conversión ARS/USD) y el '
                    f'timing de los flujos dentro del período — no es un cálculo exacto de retorno de '
                    f'cuotaparte." style="cursor:help;color:{GRAY_TEXT}">ⓘ</span></div>'
                    f'<div class="kpi-value sm" style="color:'
                    f'{GREEN_DIM if efecto_mercado_tc_total >= 0 else RED}">'
                    f'{fmt_usd(efecto_mercado_tc_total)}</div></div>', unsafe_allow_html=True)
    with cad[9]:  _op_cadena("=")
    with cad[10]: _celda_cadena("Patrimonio final", pat_fin_total)

    # ── MÉTRICAS ANALÍTICAS: TICKETS Y STRESS TEST ────────────────────
    st.markdown('<div class="section-title" style="margin-top:22px">Ticket promedio y stress test</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)

    n_susc = int((df_flujos["Movimiento"] == "Suscripcion").sum())
    n_resc = int((df_flujos["Movimiento"] == "Rescate").sum())
    ticket_susc = susc / n_susc if n_susc else np.nan
    ticket_resc = resc / n_resc if n_resc else np.nan
    ratio_rr = (ticket_resc / ticket_susc) if ticket_susc else np.nan

    # Peor mes: flujo neto mensual vs. patrimonio total al inicio de ese mes
    # (el patrimonio a la última fecha disponible ANTES de que arranque el
    # mes; si no hay fecha previa, se usa la primera disponible del mes).
    aum_diario_total = df_aum.groupby("Fecha")["PatrimonioNeto_USD"].sum().sort_index()

    def _patrimonio_inicio_mes(mes_inicio):
        anteriores = aum_diario_total[aum_diario_total.index < mes_inicio]
        if len(anteriores):
            return anteriores.iloc[-1]
        posteriores = aum_diario_total[aum_diario_total.index >= mes_inicio]
        return posteriores.iloc[0] if len(posteriores) else np.nan

    mensual = (df_flujos.groupby(["MesInicio", "Movimiento"])["Importe_USD"].sum()
               .unstack(fill_value=0.0).sort_index())
    for col in ("Suscripcion", "Rescate"):
        if col not in mensual.columns:
            mensual[col] = 0.0
    mensual["Neto"] = mensual["Suscripcion"] - mensual["Rescate"]

    # Monto y detalle separados: en una sola línea la tarjeta ocupaba tres
    # renglones y desalineaba la fila contra las otras tres.
    peor_monto_txt, peor_detalle_txt = "n/d", ""
    if len(mensual):
        peor_idx = mensual["Neto"].idxmin()
        peor_neto = mensual.loc[peor_idx, "Neto"]
        pat_inicio_peor = _patrimonio_inicio_mes(peor_idx)
        pct_peor = (peor_neto / pat_inicio_peor * 100) if pat_inicio_peor else np.nan
        pct_txt = f"{pct_peor:,.1f}% del patrimonio" if pd.notna(pct_peor) else "% n/d"
        peor_monto_txt = fmt_usd(peor_neto)
        peor_detalle_txt = f"{MESES_ABR[peor_idx.month]}-{peor_idx.year} · {pct_txt}"

    st1, st2, st3, st4 = st.columns(4)
    with st1:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Ticket promedio suscripción</div>'
                    f'<div class="kpi-value sm">{fmt_usd(ticket_susc)}</div>'
                    f'<div class="kpi-sub">{n_susc:,} movimientos</div></div>', unsafe_allow_html=True)
    with st2:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Ticket promedio rescate</div>'
                    f'<div class="kpi-value sm">{fmt_usd(ticket_resc)}</div>'
                    f'<div class="kpi-sub">{n_resc:,} movimientos</div></div>', unsafe_allow_html=True)
    with st3:
        color_ratio = RED if pd.notna(ratio_rr) and ratio_rr > 1 else DARK_TEXT
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Ratio rescate / suscripción</div>'
                    f'<div class="kpi-value sm" style="color:{color_ratio}">'
                    f'{f"{ratio_rr:,.2f}x" if pd.notna(ratio_rr) else "n/d"}</div>'
                    f'<div class="kpi-sub">ticket rescate ÷ ticket suscripción</div></div>',
                    unsafe_allow_html=True)
    with st4:
        st.markdown(f'<div class="kpi-card accent"><div class="kpi-label">Peor mes (stress test)</div>'
                    f'<div class="kpi-value sm" style="color:{RED}">{peor_monto_txt}</div>'
                    f'<div class="kpi-sub">{peor_detalle_txt}</div></div>',
                    unsafe_allow_html=True)

    if pd.notna(ratio_rr) and ratio_rr > 1:
        st.markdown(
            '<div class="note warn">⚠ <b>Alerta de pasivo:</b> se rescatan tenencias promedio más '
            'grandes que las que ingresan, lo que deteriora la base de clientes.</div>',
            unsafe_allow_html=True)

    # ── FLUJO MENSUAL (espejo) + NETO ACUMULADO ──────────────────────
    st.markdown('<div class="section-title" style="margin-top:22px">Evolución del flujo</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)

    fc1, fc2 = st.columns(2)
    with fc1:
        st.markdown('<div class="chart-label">Suscripciones vs. rescates por mes</div>', unsafe_allow_html=True)
        fig_mensual = go.Figure()
        fig_mensual.add_trace(go.Bar(
            x=mensual.index, y=mensual["Suscripcion"] / 1e6, name="Suscripciones",
            marker_color=GREEN, hovertemplate="$%{y:,.1f}M<extra>Suscripciones</extra>"))
        fig_mensual.add_trace(go.Bar(
            x=mensual.index, y=-mensual["Rescate"] / 1e6, name="Rescates",
            marker_color=RED, hovertemplate="$%{y:,.1f}M<extra>Rescates</extra>"))
        fig_mensual.update_layout(
            **BASE_LAYOUT, height=302, barmode="relative", hovermode="x unified",
            xaxis=dict(showgrid=False, tickformat="%b<br>%Y",
                       tickfont=dict(size=8.5, color=GRAY_TEXT, family=FONT_FAMILY)),
            yaxis=dict(gridcolor="#EDEFED", zeroline=True, zerolinecolor="#D8DED9",
                       tickprefix="$", ticksuffix="M",
                       tickfont=dict(size=9, color=GRAY_TEXT, family=FONT_FAMILY)),
            legend=dict(orientation="h", y=-0.14, x=0.5, xanchor="center",
                        font=dict(size=9.5, family=FONT_FAMILY), title_text=""),
            margin=dict(l=0, r=10, t=8, b=46),
        )
        chart(fig_mensual, key="fci_bar_mensual")
    with fc2:
        st.markdown('<div class="chart-label">Flujo neto acumulado</div>', unsafe_allow_html=True)
        diario = (df_flujos.groupby(["Fecha", "Movimiento"])["Importe_USD"].sum()
                  .unstack(fill_value=0.0).sort_index())
        for col in ("Suscripcion", "Rescate"):
            if col not in diario.columns:
                diario[col] = 0.0
        diario["Acumulado"] = (diario["Suscripcion"] - diario["Rescate"]).cumsum()
        fig_acum = go.Figure(go.Scatter(
            x=diario.index, y=diario["Acumulado"] / 1e6, mode="lines", fill="tozeroy",
            line=dict(color=GREEN, width=2), fillcolor="rgba(93,187,99,.12)",
            hovertemplate="$%{y:,.1f}M<extra></extra>"))
        fig_acum.update_layout(
            **BASE_LAYOUT, height=302,
            xaxis=dict(showgrid=False, tickfont=dict(size=8.5, color=GRAY_TEXT, family=FONT_FAMILY)),
            yaxis=dict(gridcolor="#EDEFED", zeroline=True, zerolinecolor="#D8DED9",
                       tickprefix="$", ticksuffix="M",
                       tickfont=dict(size=9, color=GRAY_TEXT, family=FONT_FAMILY)),
            margin=dict(l=0, r=10, t=8, b=10),
        )
        chart(fig_acum, key="fci_line_acumulado")

    rank = (df_flujos.groupby(["Fondo", "Tipo", "Movimiento"])["Importe_USD"].sum()
            .unstack(fill_value=0.0).rename_axis(columns=None).reset_index())
    for col in ("Suscripcion", "Rescate"):
        if col not in rank.columns:
            rank[col] = 0.0
    rank["Neto"] = rank["Suscripcion"] - rank["Rescate"]

    def _monto_signed_html(v):
        cls = "pos" if v >= 0 else "neg"
        txt = fmt_usd(v)
        return f'<span class="{cls}">{"+" + txt if v >= 0 else txt}</span>'

    # ── PATRIMONIO (AUM) ──────────────────────────────────────────────
    st.markdown('<div class="section-title" style="margin-top:22px">Patrimonio bajo administración</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)

    ult_fecha = df_aum["Fecha"].max()
    aum_total_actual = df_aum.loc[df_aum["Fecha"] == ult_fecha, "PatrimonioNeto_USD"].sum()
    st.markdown(f'<div class="kpi-card accent" style="max-width:360px">'
                f'<div class="kpi-label">Patrimonio total actual</div>'
                f'<div class="kpi-value">{fmt_usd(aum_total_actual)}</div>'
                f'<div class="kpi-sub">al {ult_fecha:%d/%m/%Y} · USD equivalente</div></div>',
                unsafe_allow_html=True)
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    a1, a2 = st.columns([55, 45])
    with a1:
        st.markdown('<div class="chart-label">Evolución del patrimonio total (USD)</div>', unsafe_allow_html=True)
        aum_diario = df_aum.groupby("Fecha", as_index=False)["PatrimonioNeto_USD"].sum()
        fig_aum = go.Figure(go.Scatter(
            x=aum_diario["Fecha"], y=aum_diario["PatrimonioNeto_USD"] / 1e6, mode="lines",
            line=dict(color=GREEN_DIM, width=2), fill="tozeroy", fillcolor="rgba(45,106,79,.10)",
            hovertemplate="$%{y:,.1f}M<extra></extra>"))
        fig_aum.update_layout(
            **BASE_LAYOUT, height=290,
            xaxis=dict(showgrid=False, tickfont=dict(size=8.5, color=GRAY_TEXT, family=FONT_FAMILY)),
            yaxis=dict(gridcolor="#EDEFED", tickprefix="$", ticksuffix="M",
                       tickfont=dict(size=9, color=GRAY_TEXT, family=FONT_FAMILY)),
            margin=dict(l=0, r=10, t=8, b=10),
        )
        chart(fig_aum, key="fci_aum_evol")
    with a2:
        st.markdown('<div class="chart-label">Participación por tipo de fondo (patrimonio actual)</div>',
                    unsafe_allow_html=True)
        share_tipo = (df_aum[df_aum["Fecha"] == ult_fecha]
                      .groupby("Tipo", as_index=False)["PatrimonioNeto_USD"].sum()
                      .sort_values("PatrimonioNeto_USD", ascending=False))
        # Los tipos con menos del 2% del patrimonio se agrupan en "Otros":
        # con 18 tipos posibles, las porciones chicas se pisaban las
        # etiquetas entre sí y el gráfico quedaba ilegible.
        total_share = share_tipo["PatrimonioNeto_USD"].sum()
        share_tipo["Pct"] = share_tipo["PatrimonioNeto_USD"] / total_share if total_share else 0.0
        grandes = share_tipo[share_tipo["Pct"] >= 0.02]
        chicos = share_tipo[share_tipo["Pct"] < 0.02]
        if len(chicos):
            otros = pd.DataFrame([{"Tipo": "Otros", "PatrimonioNeto_USD": chicos["PatrimonioNeto_USD"].sum()}])
            share_tipo = pd.concat([grandes[["Tipo", "PatrimonioNeto_USD"]], otros], ignore_index=True)
        else:
            share_tipo = grandes[["Tipo", "PatrimonioNeto_USD"]]
        colores_share = [TIPO_COLOR.get(t, OTROS_COLOR) if t != "Otros" else OTROS_COLOR
                         for t in share_tipo["Tipo"]]
        fig_share = go.Figure(go.Pie(
            labels=share_tipo["Tipo"], values=share_tipo["PatrimonioNeto_USD"], hole=0.58, sort=False,
            marker=dict(colors=colores_share, line=dict(color="white", width=2)),
            texttemplate="%{percent:.1%}", textposition="inside",
            textfont=dict(size=10, family=FONT_FAMILY, color="white"),
            hovertemplate="<b>%{label}</b><br>%{percent:.2%}<br>USD %{value:,.0f}<extra></extra>",
        ))
        fig_share.update_layout(
            **BASE_LAYOUT, height=290, showlegend=True,
            legend=dict(orientation="h", y=-0.10, x=0.5, xanchor="center",
                        font=dict(size=8.5, family=FONT_FAMILY)),
            margin=dict(l=0, r=0, t=6, b=6),
        )
        chart(fig_share, key="fci_pie_share")

    # ── DETALLE Y PERFORMANCE POR FONDO (tabla única) ─────────────────
    st.markdown('<div class="section-title" style="margin-top:22px">Detalle y performance por fondo</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)

    aum_prom = df_aum.groupby("Fondo")["PatrimonioNeto_USD"].mean()
    aum_fin_all = df_aum[df_aum["Fecha"] == ult_fecha].groupby("Fondo")["PatrimonioNeto_USD"].sum()
    # Meses reales que abarca el período filtrado: la tasa de rescate se
    # divide por esto para pasar de "acumulado de todo el período" (que en
    # 20 meses de un fondo de alta rotación da miles de %) a un promedio
    # mensual, mucho más legible y comparable entre fondos.
    n_meses = max((fci_hasta - fci_desde).days, 1) / 30.44

    detalle = rank.set_index("Fondo")[["Tipo", "Suscripcion", "Rescate", "Neto"]].copy()
    detalle["Patrimonio Actual"] = aum_fin_all.reindex(detalle.index).fillna(0.0)
    pat_prom = aum_prom.reindex(detalle.index).fillna(0.0)
    tasa_total = np.where(pat_prom > 0, detalle["Rescate"] / pat_prom * 100, np.nan)
    detalle["Tasa Rescate Mensual"] = tasa_total / n_meses
    aum_ini_all = df_aum[df_aum["Fecha"] == df_aum["Fecha"].min()].groupby("Fondo")["PatrimonioNeto_USD"].sum()
    variacion = aum_fin_all.reindex(detalle.index).fillna(0.0) - aum_ini_all.reindex(detalle.index).fillna(0.0)
    detalle["Efecto Mercado + TC"] = variacion - detalle["Neto"]
    detalle = detalle.reset_index().rename(
        columns={"Suscripcion": "Suscripciones", "Rescate": "Rescates", "Neto": "Flujo Neto"})

    # ── FLUJOS EXTREMOS (mayor entrada / mayor salida neta) ───────────
    # Umbral de materialidad: el mismo 2% del patrimonio total que ya se
    # usa para agrupar "Otros" en el donut, así no aparecen acá clases
    # residuales o inactivas con movimientos chicos pero % de flujo alto.
    umbral_materialidad = aum_total_actual * 0.02
    detalle_material = detalle[detalle["Patrimonio Actual"] >= umbral_materialidad]
    if len(detalle_material) >= 2:
        f_max = detalle_material.loc[detalle_material["Flujo Neto"].idxmax()]
        f_min = detalle_material.loc[detalle_material["Flujo Neto"].idxmin()]
        ex1, ex2 = st.columns(2)
        with ex1:
            st.markdown(f'<div class="kpi-card accent"><div class="kpi-label">📈 Mayor entrada neta</div>'
                        f'<div class="kpi-name">{f_max["Fondo"]}</div>'
                        f'<div class="kpi-value sm" style="color:{GREEN_DIM}">'
                        f'{_monto_signed_html(f_max["Flujo Neto"])}</div></div>', unsafe_allow_html=True)
        with ex2:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">📉 Mayor salida neta</div>'
                        f'<div class="kpi-name">{f_min["Fondo"]}</div>'
                        f'<div class="kpi-value sm">{_monto_signed_html(f_min["Flujo Neto"])}</div></div>',
                        unsafe_allow_html=True)
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    ORDEN_OPCIONES = {
        "Flujo neto": "Flujo Neto", "Patrimonio actual": "Patrimonio Actual",
        "Suscripciones": "Suscripciones", "Rescates": "Rescates",
        "Tasa de rescate mensual": "Tasa Rescate Mensual", "Efecto mercado + TC": "Efecto Mercado + TC",
        "Fondo (A-Z)": "Fondo",
    }
    oc1, oc2 = st.columns([3, 1], vertical_alignment="bottom")
    with oc1:
        orden_label = st.selectbox("Ordenar por", list(ORDEN_OPCIONES.keys()), index=0, key="fci_orden_col")
    with oc2:
        orden_desc = st.checkbox("Descendente", value=True, key="fci_orden_desc")
    detalle = detalle.sort_values(ORDEN_OPCIONES[orden_label], ascending=not orden_desc)

    filas_detalle = ""
    for _, r in detalle.iterrows():
        sw = TIPO_COLOR.get(r["Tipo"], GREEN)
        tasa = r["Tasa Rescate Mensual"]
        tasa_html = f"{tasa:,.1f}%" if pd.notna(tasa) else '<span class="nd">n/d</span>'
        filas_detalle += (
            f'<tr><td><span class="swatch" style="background:{sw}"></span>{r["Fondo"]}</td>'
            f'<td style="color:{GRAY_TEXT}">{r["Tipo"]}</td>'
            f'<td>{fmt_usd(r["Patrimonio Actual"])}</td>'
            f'<td>{fmt_usd(r["Suscripciones"])}</td>'
            f'<td>{fmt_usd(r["Rescates"])}</td>'
            f'<td>{_monto_signed_html(r["Flujo Neto"])}</td>'
            f'<td>{tasa_html}</td>'
            f'<td>{_monto_signed_html(r["Efecto Mercado + TC"])}</td></tr>'
        )
    st.markdown(f"""
    <div class="tabla-scroll" style="background:{WHITE};border:1px solid {BORDER};
                border-radius:10px;padding:12px 16px;">
      <table class="var-table">
        <thead><tr><th>Fondo</th><th>Tipo</th><th>Patrimonio actual</th><th>Suscripciones</th>
        <th>Rescates</th><th>Flujo neto</th><th>Tasa rescate (prom. mensual)</th>
        <th>Efecto mercado + TC (USD)</th></tr></thead>
        <tbody>{filas_detalle}</tbody>
      </table>
    </div>
    """, unsafe_allow_html=True)

    # ── NOTA METODOLÓGICA + FOOTER ────────────────────────────────────
    st.markdown(f"""
    <div class="note" style="margin-top:16px">
      <b>Metodología.</b> Montos convertidos a USD: los pesos usan el tipo de cambio del día de cada
      movimiento o fecha de patrimonio; los fondos en dólares (MEP/CCL) se toman tal cual, sin
      conversión. Los fondos lanzados después del inicio de la serie tienen menos historia — no es
      un error de datos. La <b>tasa de rescate</b> es Rescates / Patrimonio promedio del período,
      expresada como <b>promedio mensual</b> (dividida por los meses que abarca el filtro actual) para
      que sea comparable entre fondos y entre distintos rangos de fechas. El <b>efecto mercado + TC</b>
      es lo que queda de la variación de patrimonio una vez descontado el flujo neto — absorbe retorno
      de cartera, efecto cambiario y timing de los flujos; es una aproximación contable, no un cálculo
      exacto de retorno de cuotaparte. Las tarjetas de <b>mayor entrada/salida neta</b> excluyen fondos
      con menos del 2% del patrimonio total, para no mostrar clases residuales o inactivas (mismo
      umbral que agrupa "Otros" en el gráfico de participación).
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:{DARK_BG}; margin: 1rem calc(-1 * var(--novus-pad)) -1rem calc(-1 * var(--novus-pad));
                padding: 16px var(--novus-pad);
                display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
      <div style="color:{GREEN}; font-size:.85rem; font-weight:600;">
        novus <span style="color:#9AADA9; font-weight:300;">asset management</span></div>
      <div style="color:#777; font-size:.7rem;">middle office · suscripciones y rescates de FCI</div>
    </div>
    """, unsafe_allow_html=True)

    st.stop()


# ═══════════════════════════════════════════════════════════════
# MÓDULO 1 — DASHBOARD DE CONTRAPARTES Y FLUJO DE AGENTES
# ═══════════════════════════════════════════════════════════════


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
# fmt_usd y fmt_pct_html se movieron al principio del archivo (junto a
# chart()/df_show()) porque el módulo de FCI, que corre antes que este,
# también los necesita.
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
  <h1><span>contrapartes</span></h1>
  <p>Control de límites, riesgo y exposición.</p>
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
    <div class="tabla-scroll" style="background:{WHITE};border:1px solid {BORDER};
                border-radius:10px;padding:12px 16px;">
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
<div style="background:{DARK_BG}; margin: 1rem calc(-1 * var(--novus-pad)) -1rem calc(-1 * var(--novus-pad));
            padding: 16px var(--novus-pad);
            display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
  <div style="color:{GREEN}; font-size:.85rem; font-weight:600;">
    novus <span style="color:#9AADA9; font-weight:300;">asset management</span></div>
  <div style="color:#777; font-size:.7rem;">
    middle office · datos al {HIST_MAX:%d/%m/%Y} · {len(df_raw):,} operaciones en base</div>
</div>
""", unsafe_allow_html=True)
