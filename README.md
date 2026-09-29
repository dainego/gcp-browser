# GCS Data Browser v0.5

Read-only browser for a configured Google Cloud Storage bucket.

## Main features

- Direct access to a configured bucket; no bucket listing required.
- Folder explorer and breadcrumb navigation.
- Search and sorting.
- File metadata.
- Parquet schema.
- Parquet statistics.
- Parquet preview using the first row group.
- Remote Parquet access through PyArrow.
- No full-file download for the preview.
- `/api/test-gcs` diagnostic endpoint.

## Configuration

Copy `.env.example` to `.env` and configure:

```text
GCS_BUCKET_FILTER=tacticas-moviles-prod
GCS_ROOT_PREFIX=
GOOGLE_APPLICATION_CREDENTIALS=C:\ruta\service-account.json
```

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

## Navigation fix in v0.3.2

The object listing no longer relies on GCS `delimiter="/"` or the iterator's
`prefixes` collection.

The service retrieves the object names under the selected prefix and derives
the immediate child folders itself. This makes folder navigation deterministic
for buckets containing paths such as:

```text
bifurcador/parque_producto/fecha=2026-08-04/parque_producto.snappy.parquet
bifurcador/parque_producto/fecha=2026-08-05/parque_producto.snappy.parquet
```

At the root, the browser should therefore show:

```text
actividades/
bifurcador/
```

and entering `bifurcador/` should show:

```text
parque_producto/
```


## Tree Explorer in v0.4

The left Explorer is now a persistent hierarchical tree.

- `▶` expands a folder.
- `▼` collapses a folder.
- Clicking the folder name navigates to that folder.
- Children are loaded lazily from GCS when a folder is expanded.
- The complete path to the current folder remains expanded.
- The current folder is highlighted.
- Previously expanded branches remain expanded while navigating.


## Theme switcher in v0.5

The interface includes three visual themes:

- ☀ **Claro** — the current light theme.
- 🌙 **Oscuro** — dark gray/black interface.
- 🐂 **Premium** — black/deep green combination.

The selected theme is stored in the browser's `localStorage`, so it remains
selected after refreshing or reopening the application in the same browser.
