# GCS Data Browser v0.8.10

Read-only browser for configured Google Cloud Storage buckets.

## Configuration

The configuration is intentionally separated into three areas:

- `config/storages.json`: functional configuration — Storage profiles, allowed buckets, local credential paths, Secret Manager secret names and the environment variable used by Cloud Run.
- `credentials/`: Service Account JSON files used only for local execution. These files must never be committed.
- `.env`: application/runtime parameters such as preview and search limits.

### `config/storages.json`

Example:

```json
{
  "tacticas-prod": {
    "label": "Tacticas Producción",
    "buckets": [
      "tacticas-moviles-prod"
    ],
    "credentials": "credentials/tacticas-prod.json",
    "secret": "tacticas-prod",
    "secret_env": "GCS_SECRET_TACTICAS_PROD"
  },
  "tacticas-dev": {
    "label": "Tacticas Desarrollo",
    "buckets": [
      "tacticas-moviles-dev"
    ],
    "credentials": "credentials/tacticas-dev.json",
    "secret": "tacticas-dev",
    "secret_env": "GCS_SECRET_TACTICAS_DEV"
  },
  "bj-prod": {
    "label": "BJ Producción",
    "buckets": [
      "bj-acacia-prod-gcp-gcs-uest4-traficotemis"
    ],
    "credentials": "credentials/bj-prod.json",
    "secret": "bj-prod",
    "secret_env": "GCS_SECRET_BJ_PROD"
  }
}
```

The application only exposes buckets listed in this file. The backend validates
the selected Storage profile and bucket on every request.

`credentials` is the local fallback path. `secret_env` is used when Cloud Run injects
the corresponding Secret Manager value as an environment variable.

### `.env`

```text
MAX_PREVIEW_ROWS=100
MAX_SEARCH_RESULTS=200
```

Do not put Service Account credentials or secrets in `.env`.

## Main features

- Multiple GCS storage profiles.
- Fixed bucket allowlist per storage.
- Separate Service Account JSON per storage profile.
- Folder explorer and breadcrumb navigation.
- Lazy-loaded hierarchical tree.
- Search and sorting.
- File metadata.
- Parquet schema.
- Parquet statistics.
- Parquet preview using the first row group.
- Remote Parquet access through PyArrow.
- No full-file download for the preview.
- Light, dark and premium themes.
- `/api/test-gcs` diagnostic endpoint.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

## Despliegue en Google Cloud Run

La configuración local no cambia. En local, `config/storages.json` sigue usando los archivos JSON de `credentials/`.

En Cloud Run, Secret Manager inyecta los JSON como variables de entorno secretas. La aplicación detecta esas variables y construye las credenciales directamente en memoria; no necesita montar los secretos como archivos.

Secretos configurados actualmente:

- `tacticas-prod` → `GCS_SECRET_TACTICAS_PROD`
- `tacticas-dev` → `GCS_SECRET_TACTICAS_DEV`
- `bj-prod` → `GCS_SECRET_BJ_PROD`

La Service Account `gcpbrowser-cloudrun` debe tener `roles/secretmanager.secretAccessor` sobre los secrets utilizados. Ese permiso se configura como prerrequisito de infraestructura y no forma parte del deploy.

### Deploy

`deploy/cloudrun/deploy-cloud-run.ps1` no crea secrets ni modifica permisos IAM. Verifica que los secrets definidos en `storages.json` existan, construye la imagen con Cloud Build, la publica en Artifact Registry y despliega esa imagen en Cloud Run.

```powershell
.\deploy\cloudrun\deploy-cloud-run.ps1 `
  -ProjectId TU_PROJECT_ID `
  -Region us-east4 `
  -RuntimeServiceAccount "gcpbrowser-cloudrun@TU_PROJECT_ID.iam.gserviceaccount.com"
```

Por defecto, el servicio queda privado. Para habilitar acceso público explícitamente:

```powershell
.\deploy\cloudrun\deploy-cloud-run.ps1 `
  -ProjectId TU_PROJECT_ID `
  -Region us-east4 `
  -RuntimeServiceAccount "gcpbrowser-cloudrun@TU_PROJECT_ID.iam.gserviceaccount.com" `
  -AllowUnauthenticated
```

Las claves privadas nunca forman parte de la imagen ni del código fuente desplegado.


## v0.8.7 — listado bajo demanda

- El navegador solicita únicamente los objetos y subcarpetas inmediatos del prefijo actual de Cloud Storage (`delimiter="/"`). Ya no recorre recursivamente todos los objetos descendientes al abrir una carpeta.
- Las subcarpetas se consultan al expandirlas en el árbol de navegación.
- Se corrigió la solicitud del árbol para enviar `storage_id` y `bucket` junto con el prefijo.

Esto reduce considerablemente el consumo de memoria en buckets con muchos niveles y objetos. Una carpeta que contenga por sí sola miles de archivos todavía puede requerir paginación de resultados en una mejora posterior.


## v0.8.7
- Navegación de archivos paginada en bloques de hasta 500 elementos.
- Controles de página anterior, siguiente e ingreso directo de número de página.
- La API conserva en memoria únicamente los elementos de la página solicitada.


## v0.8.8 — corrección de paginación

- Corrige el acceso al token de continuación de Google Cloud Storage: se consulta en el iterador y no en el objeto `Page`.
- Evita el error HTTP 400 al cargar carpetas.


## v0.8.10 — paginación y tema

- Corregido el cálculo de páginas y el estado de navegación anterior/siguiente.
- El indicador muestra `Página actual de total`.
- Se incorpora la versión en el título y el encabezado.
- El campo de página respeta los fondos de los temas oscuro y premium.
