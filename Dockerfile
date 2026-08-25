# ═══════════════════════════════════════════════════════════════
# NOVUS ASSET MANAGEMENT — Dashboard de Middle Office
# ═══════════════════════════════════════════════════════════════
# La imagen fija el entorno completo: misma versión de Python y de cada
# librería en tu máquina y en Railway. Se termina el "en mi compu andaba".
# ═══════════════════════════════════════════════════════════════
FROM python:3.11-slim

# PYTHONDONTWRITEBYTECODE: no ensucia con archivos .pyc
# PYTHONUNBUFFERED: los logs salen al instante, no en bloques (clave para
#                   poder leer los logs de Railway en vivo)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Las dependencias van ANTES del código, a propósito: Docker guarda cada paso
# en caché. Si solo tocás app.py, este paso no se repite y el build tarda
# segundos en lugar de minutos.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# La app corre con un usuario sin privilegios en vez de root: si alguna vez
# algo se compromete, no tiene permisos sobre el sistema del contenedor.
RUN useradd --create-home --uid 1000 novus \
    && chown -R novus:novus /app
USER novus

# Documenta el puerto por defecto. Railway inyecta su propio $PORT.
EXPOSE 8501

# Forma "shell" (sin corchetes) a propósito: así ${PORT} se expande en tiempo
# de ejecución. Con la forma exec (["streamlit", ...]) llegaría el texto
# literal "$PORT" y el arranque fallaría en Railway.
CMD streamlit run app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
