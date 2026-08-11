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

st.set_page_config(
    page_title="novus | agentes",
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

  /* ── SIDEBAR / NAVEGACION ── */
  section[data-testid="stSidebar"] {{
      background: {DARK_BG} !important;
      border-right: 1px solid rgba(93,187,99,.15) !important;
  }}
  section[data-testid="stSidebar"] * {{ color: #C9D4CC !important; }}
  section[data-testid="stSidebar"] .stRadio label {{
      color: {GREEN} !important; letter-spacing: 1.4px !important;
  }}
  section[data-testid="stSidebar"] div[role="radiogroup"] {{ flex-direction: column !important; gap: 6px !important; }}
  section[data-testid="stSidebar"] div[role="radiogroup"] label {{
      background: rgba(255,255,255,.04) !important;
      border: 1px solid rgba(255,255,255,.10) !important;
      border-radius: 8px !important; width: 100%; padding: 9px 14px !important;
  }}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
      border-color: rgba(93,187,99,.5) !important;
  }}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
      background: rgba(93,187,99,.14) !important; border-color: {GREEN} !important;
  }}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) * {{
      color: {GREEN} !important; font-weight: 600 !important;
  }}
  .sidebar-brand {{
      color: {GREEN}; font-size: .95rem; font-weight: 700; padding: 6px 2px 2px;
  }}
  .sidebar-brand span {{ color: #9AADA9; font-weight: 300; }}
  .sidebar-tag {{ color: #7A857D !important; font-size: .65rem; letter-spacing: 1.5px;
      text-transform: uppercase; padding: 0 2px 14px; }}

  #MainMenu, footer, header {{ visibility: hidden; height: 0; }}
  .block-container {{ padding-top: 0 !important; padding-bottom: 1.5rem !important; }}
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
            '<div class="login-sub">Dashboard de contrapartes · acceso restringido</div>'
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
M_DASH = "📊  Dashboard y métricas"
M_CTAS = "📋  Seguimiento de apertura"

st.sidebar.markdown(
    '<div class="sidebar-brand">novus <span>asset management</span></div>'
    '<div class="sidebar-tag">middle office</div>', unsafe_allow_html=True)

# El label del radio hace de encabezado temático del grupo: el CSS del sidebar
# lo pinta en verde, mayúsculas y con tracking, así queda como título de sección.
modulo = st.sidebar.radio("Contrapartes", [M_DASH, M_CTAS], key="nav_modulo")

# Recordatorio discreto del estado de acceso, al pie del sidebar.
st.sidebar.markdown(
    '<div style="margin-top:22px;padding-top:12px;border-top:1px solid rgba(255,255,255,.08)">'
    + ('<div style="font-size:.68rem;color:#7A857D">acceso · <span style="color:#5DBB63">'
       'protegido con contraseña</span></div>'
       if AUTH_ACTIVA else
       '<div style="font-size:.68rem;color:#7A857D">acceso · <span style="color:#E8A020">'
       'sin contraseña</span><br><span style="font-size:.62rem">quien tenga el link entra</span></div>')
    + '</div>', unsafe_allow_html=True)

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
    ESTADOS    = ["En proceso", "Abierta", "Rechazada", "De baja"]

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

    # ── Lectura de las tres hojas ────────────────────────────────────
    def _leer_hojas(contenido_bytes):
        """Parsea el xlsx. Devuelve (df_com, df_rem, df_fci, error)."""
        try:
            xl = pd.ExcelFile(io.BytesIO(contenido_bytes), engine="openpyxl")
            faltan = [h for h in (HOJA_COM, HOJA_REM, HOJA_FCI) if h not in xl.sheet_names]
            if faltan:
                return None, None, None, (
                    f"Al Excel le faltan estas hojas: {', '.join(faltan)}. "
                    f"Hojas encontradas: {', '.join(xl.sheet_names)}.")
            return (xl.parse(HOJA_COM), xl.parse(HOJA_REM), xl.parse(HOJA_FCI), None)
        except Exception as e:
            return None, None, None, f"No se pudo leer el Excel: {e}"

    @st.cache_data(ttl=120, show_spinner="Cargando seguimiento de cuentas…")
    def cargar_cuentas(_modo, _nonce):
        """Trae el Excel de GitHub (rama data). Si no existe ahí, lo siembra
        con la copia del repo. En modo lectura usa directamente la copia local."""
        if _modo == "edicion":
            ok, err = _asegurar_rama()
            if not ok:
                return None, None, None, None, err
            contenido, sha, err = _bajar_excel()
            if err:
                return None, None, None, None, err
            if contenido is None:
                # Primera vez: sembrar la rama data con la copia del repo
                if not os.path.exists(XLS_LOCAL):
                    return None, None, None, None, (
                        f"No hay `{XLS_NAME}` ni en la rama '{GH_BRANCH}' ni en el repo. "
                        f"Subí el archivo al repo una vez para inicializar.")
                with open(XLS_LOCAL, "rb") as f:
                    contenido = f.read()
                ok, err = _subir_excel(contenido, None,
                                       "Inicializar seguimiento de cuentas desde el repo")
                if not ok:
                    return None, None, None, None, err
                _, sha, err = _bajar_excel()
                if err:
                    return None, None, None, None, err
        else:
            if not os.path.exists(XLS_LOCAL):
                return None, None, None, None, f"No se encontró `{XLS_NAME}` junto a app.py."
            with open(XLS_LOCAL, "rb") as f:
                contenido = f.read()
            sha = None

        c, r, f_, err = _leer_hojas(contenido)
        return c, r, f_, sha, err

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
      <h1>apertura y seguimiento de <span>cuentas</span> fci</h1>
      <p>Estado de onboarding de cuentas comitentes en ALyCs y cuentas remuneradas en bancos.</p>
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
    df_com, df_rem, df_fci, sha_actual, error = cargar_cuentas(
        "edicion" if MODO_EDICION else "lectura", nonce)

    if error:
        st.error(error)
        st.stop()

    df_com, av1 = _normalizar(df_com, "Comitentes")
    df_rem, av2 = _normalizar(df_rem, "Remuneradas")
    avisos = av1 + av2

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

    # ── ESTADOS CON COLOR ───────────────────────────────────────────
    # st.data_editor no admite pintar celdas (no soporta Styler), así que el
    # color va en el valor: se muestra "🟢 Abierta" mientras se edita y se
    # guarda "Abierta" limpio en el Excel. La vista consolidada, que es de
    # solo lectura, sí usa Styler con fondo de color real.
    EST_ICONO = {"Abierta": "🟢", "En proceso": "🟡", "Rechazada": "🔴", "De baja": "⚪"}
    EST_FONDO = {"Abierta": "#E9F6EC", "En proceso": "#FFF6E6",
                 "Rechazada": "#FDECEC", "De baja": "#F0F2F0"}
    EST_TEXTO = {"Abierta": GREEN_DIM, "En proceso": "#9A6A10",
                 "Rechazada": "#B03030", "De baja": "#77817A"}
    ESTADOS_VIS = [f"{EST_ICONO[e]} {e}" for e in ESTADOS]

    def _limpiar_estado(v):
        """Saca el emoji del principio y deja el texto puro."""
        if pd.isna(v):
            return v
        s = str(v)
        for ic in EST_ICONO.values():
            s = s.replace(ic, "")
        return s.strip() or None

    def a_vista(df):
        """Copia con el Estado decorado, para mostrar en el editor."""
        if df is None or df.empty or "Estado" not in df.columns:
            return df
        d = df.copy()
        d["Estado"] = d["Estado"].map(
            lambda v: f"{EST_ICONO.get(str(v).strip(), '⚫')} {str(v).strip()}"
            if pd.notna(v) and str(v).strip() else v)
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

    fondos_disp  = _valores(COL_FONDO, df_com, df_rem)
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
        for col, sel in ((COL_FONDO, f_fondo), ("Estado", f_estado), ("Contraparte", f_ctp)):
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
    fondos_vis = set(_valores(COL_FONDO, vis_com, vis_rem))

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

    # ── AVANCE POR ESTADO ───────────────────────────────────────────
    if total:
        est_tot = {e: _cuenta(vis_com, e) + _cuenta(vis_rem, e) for e in ESTADOS}
        colores_est = {"Abierta": GREEN_DIM, "En proceso": AMBER,
                       "Rechazada": RED, "De baja": "#9AA5A0"}
        fig_est = go.Figure()
        for e in ESTADOS:
            v = est_tot.get(e, 0)
            if not v:
                continue
            fig_est.add_trace(go.Bar(
                x=[v / total * 100], y=["e"], orientation="h",
                name=f"{EST_ICONO[e]} {e} ({v})", marker_color=colores_est.get(e, GREEN),
                text=[f"{v}"] if v / total * 100 >= 6 else [""],
                textposition="inside", insidetextanchor="middle",
                textfont=dict(size=11, color="white", family=FONT_FAMILY),
                hovertemplate=f"<b>{e}</b>: {v} de {total} (%{{x:.1f}}%)<extra></extra>",
            ))
        fig_est.update_layout(
            **BASE_LAYOUT, barmode="stack", height=112, showlegend=True,
            legend=dict(orientation="h", y=-0.5, x=0, traceorder="normal",
                        font=dict(size=9.5, family=FONT_FAMILY)),
            xaxis=dict(visible=False, range=[0, 100]), yaxis=dict(visible=False),
            margin=dict(l=0, r=0, t=26, b=0),
            title=dict(text="Distribución por estado", x=0, xanchor="left",
                       font=dict(size=11.5, family=FONT_FAMILY, color=GRAY_TEXT)),
        )
        chart(fig_est, key="estados")

    # ── AVANCE POR FONDO ────────────────────────────────────────────
    if COL_FONDO and len(fondos_vis) > 1:
        filas_f = []
        for fondo in sorted(fondos_vis):
            conteo = {e: 0 for e in ESTADOS}
            tt = 0
            for d in (vis_com, vis_rem):
                if d is None or d.empty or COL_FONDO not in d.columns:
                    continue
                sub = d[d[COL_FONDO].astype(str).str.strip() == fondo]
                tt += len(sub)
                if "Estado" in sub.columns:
                    for e in ESTADOS:
                        conteo[e] += int((sub["Estado"] == e).sum())
            filas_f.append((fondo, tt, conteo))
        filas_f.sort(key=lambda r: r[1], reverse=True)
        fig_f = go.Figure()
        for e in ESTADOS:
            vals = [r[2][e] for r in filas_f]
            if not any(vals):
                continue
            fig_f.add_trace(go.Bar(
                y=[r[0] for r in filas_f], x=vals, orientation="h",
                name=f"{EST_ICONO[e]} {e}",
                marker_color={"Abierta": GREEN_DIM, "En proceso": AMBER,
                              "Rechazada": RED, "De baja": "#9AA5A0"}[e],
                hovertemplate="<b>%{y}</b><br>" + e + ": %{x}<extra></extra>",
            ))
        fig_f.update_layout(
            **BASE_LAYOUT, barmode="stack", height=max(200, 30 * len(filas_f) + 95),
            legend=dict(orientation="h", y=-0.16, x=0, traceorder="normal",
                        font=dict(size=9.5, family=FONT_FAMILY)),
            xaxis=dict(gridcolor="#EDEFED", zeroline=False, dtick=1,
                       tickfont=dict(size=9, color=GRAY_TEXT, family=FONT_FAMILY)),
            yaxis=dict(autorange="reversed",
                       tickfont=dict(size=9.5, color=DARK_TEXT, family=FONT_FAMILY)),
            margin=dict(l=0, r=10, t=30, b=38),
            title=dict(text=f"Cuentas por {ETIQ_FONDO.lower()}", x=0, xanchor="left",
                       font=dict(size=11.5, family=FONT_FAMILY, color=GRAY_TEXT)),
        )
        chart(fig_f, key="por_fondo")

    if avisos:
        st.markdown('<div class="note warn"><b>Para revisar en el Excel:</b><br>' +
                    "<br>".join(f"· {a}" for a in avisos) + '</div>', unsafe_allow_html=True)

    # ── TABLAS ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Detalle</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)

    if filtro_filas:
        st.markdown(
            '<div class="note"><b>Con filtros de fila activos podés cambiar celdas, pero no '
            'agregar ni borrar filas.</b> Al guardar, lo editado vuelve a su fila original del '
            'Excel y el resto queda intacto. Para dar de alta una cuenta nueva, limpiá los '
            'filtros primero.</div>', unsafe_allow_html=True)

    cfg = {
        "Estado": st.column_config.SelectboxColumn(
            "Estado", options=ESTADOS_VIS, required=False, width="medium",
            help="Elegí el estado de la lista"),
    }
    if COL_FONDO:
        cfg[COL_FONDO] = st.column_config.TextColumn(COL_FONDO, width="medium")
    modo_filas = "fixed" if filtro_filas else "dynamic"

    # Se arranca con las hojas COMPLETAS: si un editor no se renderiza porque
    # el filtro de tipo lo escondió, su hoja se guarda tal cual estaba.
    res_com, res_rem, res_fci = df_com, df_rem, df_fci

    nombres = []
    if ver_com:
        nombres.append("  Comitentes (ALyCs)  ")
    if ver_rem:
        nombres.append("  Remuneradas (bancos)  ")
    nombres += ["  Vista consolidada  ", f"  Matrículas CNV  "]
    tabs = list(st.tabs(nombres))
    k = 0

    def _editar(df_full, vis, clave, etiqueta):
        st.markdown(f'<div class="chart-label">{etiqueta}</div>', unsafe_allow_html=True)
        ed = st.data_editor(a_vista(vis), column_config=cfg, num_rows=modo_filas,
                            hide_index=True, key=clave)
        ed = a_datos(ed)
        if filtro_filas:
            base = df_full.copy()
            if len(ed):
                base.loc[ed.index, ed.columns] = ed
            return base
        return ed

    if ver_com:
        with tabs[k]:
            res_com = _editar(df_com, vis_com, "ed_com", f"{n_com} cuentas comitentes")
        k += 1
    if ver_rem:
        with tabs[k]:
            res_rem = _editar(df_rem, vis_rem, "ed_rem", f"{n_rem} cuentas remuneradas")
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

    with tabs[k]:
        st.markdown('<div class="chart-label">Matrículas de fondos en CNV</div>',
                    unsafe_allow_html=True)
        vis_fci = df_fci
        col_fci_hoja = _primera_col(CAND_FONDO, df_fci)
        if f_fondo and col_fci_hoja:
            vis_fci = df_fci[df_fci[col_fci_hoja].astype(str).str.strip().isin(f_fondo)]
        ed_fci = st.data_editor(vis_fci, num_rows="fixed" if f_fondo else "dynamic",
                                hide_index=True, key="ed_fci")
        if f_fondo and col_fci_hoja and df_fci is not None:
            base = df_fci.copy()
            if len(ed_fci):
                base.loc[ed_fci.index, ed_fci.columns] = ed_fci
            res_fci = base
        else:
            res_fci = ed_fci

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
        return buf.getvalue()

    st.markdown('<div class="section-title">Guardar</div>'
                '<div class="section-underline"></div>', unsafe_allow_html=True)

    if MODO_EDICION:
        g1, g2, _g3 = st.columns([1.4, 1.1, 3])
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
    # El botón de salir solo tiene sentido si hay contraseña configurada.
    if AUTH_ACTIVA:
        _, col_out2 = st.columns([5, 1])
        with col_out2:
            if st.button("Cerrar sesión", key="logout2"):
                for k in ("_auth_ok", "_intentos"):
                    st.session_state.pop(k, None)
                st.rerun()

    st.markdown(f"""
    <div style="background:{DARK_BG}; margin: 1rem -1rem -1rem -1rem; padding: 16px 36px;
                display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
      <div style="color:{GREEN}; font-size:.85rem; font-weight:600;">
        novus <span style="color:#9AADA9; font-weight:300;">asset management</span></div>
      <div style="color:#777; font-size:.7rem;">middle office · onboarding de cuentas</div>
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

# El botón de salir solo tiene sentido si hay contraseña configurada.
if AUTH_ACTIVA:
    _, col_out = st.columns([5, 1])
    with col_out:
        if st.button("Cerrar sesión", key="logout"):
            for k in ("_auth_ok", "_intentos"):
                st.session_state.pop(k, None)
            st.rerun()

st.markdown(f"""
<div style="background:{DARK_BG}; margin: 1rem -1rem -1rem -1rem; padding: 16px 36px;
            display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
  <div style="color:{GREEN}; font-size:.85rem; font-weight:600;">
    novus <span style="color:#9AADA9; font-weight:300;">asset management</span></div>
  <div style="color:#777; font-size:.7rem;">
    middle office · datos al {HIST_MAX:%d/%m/%Y} · {len(df_raw):,} operaciones en base</div>
</div>
""", unsafe_allow_html=True)
