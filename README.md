# Novus Dashboard — Middle Office

Dashboard interno de Novus Asset Management. Dos módulos:

- **Dashboard y métricas** — volumen operado por contraparte, participación de mercado, costos de ejecución en bps, concentración (HHI) y variación por asset category.
- **Seguimiento de apertura** — estado de onboarding de cuentas comitentes (ALyCs) y remuneradas (bancos), editable desde la web.

---

## Qué es cada archivo

| Archivo | Para qué sirve |
|---|---|
| `app.py` | Toda la aplicación. Es el único archivo que vas a editar seguido. |
| `base_historica_acumulada.csv` | Datos de operaciones. Lo genera tu script de Spyder. |
| `seguimiento_cuentas.xlsx` | Semilla inicial del seguimiento de cuentas. Después la fuente de verdad pasa a ser la rama `data`. |
| `requirements.txt` | Las librerías con versión exacta. |
| `Dockerfile` | Receta del entorno. Railway lo usa para construir la app. |
| `docker-compose.yml` | Atajo para correr local con un comando. |
| `.env.example` | Plantilla de las variables. Se copia a `.env`. |
| `.env` | **Tus claves reales. Nunca se sube al repo.** |
| `.streamlit/config.toml` | Tema visual (paleta Novus, elimina el rojo de Streamlit). |
| `.vscode/` | Configuración del editor y extensiones sugeridas. |

---

## Primera vez

### 1. Instalar lo necesario

- **VS Code** → https://code.visualstudio.com
- **Git** → https://git-scm.com/downloads
- **Docker Desktop** → https://www.docker.com/products/docker-desktop

Después de instalar Docker Desktop, abrilo y dejalo corriendo. Tiene que decir "Engine running".

### 2. Bajar el proyecto

Abrí VS Code → menú **Terminal → New Terminal** → pegá:

```bash
git clone https://github.com/lsancci-ops/Novus-Dashboard.git
cd Novus-Dashboard
code .
```

Se abre una ventana nueva de VS Code con el proyecto. Cuando te ofrezca instalar las extensiones recomendadas, aceptá.

### 3. Crear tu archivo de claves

En la terminal de VS Code:

```bash
cp .env.example .env
```

Abrí `.env` desde el explorador de VS Code (panel izquierdo) y completá los valores. Está en `.gitignore`, así que git lo ignora y nunca se sube.

---

## Correr local

```bash
docker compose up
```

La primera vez tarda unos minutos porque construye la imagen. Después arranca en segundos.

Abrí **http://localhost:8501**

Para cortarlo: `Ctrl+C` en la terminal.

**Mientras está corriendo, editás `app.py` en VS Code, guardás, y el navegador recarga solo.** No hace falta reconstruir nada.

Solo si cambiás `requirements.txt` tenés que reconstruir:

```bash
docker compose up --build
```

### Sin Docker (alternativa)

Si Docker te da problemas:

```bash
python -m venv .venv
source .venv/bin/activate       # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Funciona igual, pero el entorno no es idéntico al de producción.

---

## Variables de entorno

| Variable | Qué hace | Si falta |
|---|---|---|
| `NOVUS_APP_PASSWORD` | Contraseña de acceso | La app abre sin pedir nada |
| `GITHUB_TOKEN` | Permite guardar los cambios de cuentas | El módulo queda en solo lectura y lo avisa |
| `GITHUB_REPO` | `usuario/repositorio` | Igual que arriba |
| `GITHUB_BRANCH` | Rama donde vive el Excel (`data`) | Usa `data` por defecto |

La app las busca primero en los Secrets de Streamlit Cloud y después en variables de entorno. Por eso el mismo código funciona en Streamlit Cloud, en Docker local y en Railway sin cambiar una línea.

El token se genera en https://github.com/settings/personal-access-tokens/new con permiso **Contents: Read and write** sobre este repositorio.

---

## Flujo de trabajo diario

```bash
git pull                          # traer lo último antes de empezar
# ... editás en VS Code, probás con docker compose up ...
git add .
git commit -m "Descripción corta del cambio"
git push
```

El `push` dispara el deploy en Railway automáticamente. En 2-3 minutos está en producción.

En VS Code también podés hacer todo esto desde el panel **Source Control** (el ícono de las ramas), sin escribir comandos.

---

## Deploy en Railway

**Una sola vez:**

1. https://railway.app → **New Project** → **Deploy from GitHub repo** → `Novus-Dashboard`
2. Railway detecta el `Dockerfile` y construye con él
3. Pestaña **Variables** → agregás las cuatro de la tabla de arriba (sin comillas)
4. **Settings → Networking → Generate Domain** para tener la URL

**Después de eso:** cada `git push` a `main` redeploya solo. No tocás nada más.

---

## Actualizar los datos

**Operaciones (el dashboard):** corrés tu script de Spyder, que regenera `base_historica_acumulada.csv`. Reemplazás el archivo en la carpeta del proyecto, y:

```bash
git add base_historica_acumulada.csv
git commit -m "Actualización de base al DD/MM/AAAA"
git push
```

**Cuentas (el seguimiento):** no se toca ningún archivo. Editás desde la web y apretás **Guardar cambios**. Va a la rama `data` con tus iniciales y la fecha. El historial completo está en GitHub → rama `data` → History.

---

## Problemas comunes

**`docker compose up` dice que no encuentra Docker**
Docker Desktop no está abierto. Abrilo y esperá que diga "Engine running".

**El puerto 8501 está ocupado**
Ya tenés otra instancia corriendo. `docker compose down` y volvé a intentar.

**El módulo de cuentas dice "solo lectura"**
Falta `GITHUB_TOKEN` o `GITHUB_REPO` en el `.env` (local) o en Variables (Railway). Si están, puede que el token haya vencido: generá otro.

**Cambié `app.py` y no veo el cambio**
Refrescá con `Ctrl+Shift+R`. Si sigue igual, `docker compose restart`.

**Railway falla al construir**
Mirá los logs en la pestaña **Deployments**. Casi siempre es una versión de `requirements.txt` que no existe.

---

## Notas de diseño

Algunas decisiones que no son obvias y conviene no revertir sin pensarlo:

- **El Excel de cuentas se guarda en la rama `data`, no en `main`.** Si se guardara en `main`, cada guardado dispararía un redeploy y la app se reiniciaría en la cara del usuario.
- **Las ventanas de variación (30/60/90/180d) se calculan siempre sobre la historia completa**, no sobre el período filtrado. Si no, filtrar por un mes rompía la comparación contra la ventana anterior.
- **El HHI ignora el filtro por agente** a propósito: la concentración se mide sobre el universo, no sobre un subconjunto elegido a mano.
- **Con filtros activos no se pueden agregar ni borrar filas** en la grilla. Lo editado se reinserta por índice en su fila original; agregar filas ahí sería ambiguo. Para eso está el formulario de alta.
- **La columna FCI es desplegable solo cuando todos los valores están en el catálogo.** Un `SelectboxColumn` con valores fuera de su lista puede vaciar celdas.
- **La fecha se oculta con `column_order`, no borrando la columna.** Borrarla la eliminaría del Excel al guardar.
