# GCS Data Browser v0.7

Read-only browser for configured Google Cloud Storage buckets.

## Configuration

The configuration is intentionally separated into three areas:

- `config/storages.json`: functional configuration — Storage profiles, allowed buckets and credential file paths.
- `credentials/`: Service Account JSON files. These are local secrets and must never be committed.
- `.env`: application/runtime parameters such as preview and search limits.

### `config/storages.json`

Example:

```json
{
  "prod": {
    "label": "Producción",
    "buckets": [
      "tacticas-moviles-prod"
    ],
    "credentials": "credentials/prod.json"
  },
  "dev": {
    "label": "Desarrollo",
    "buckets": [
      "tacticas-moviles-dev",
      "tacticas-moviles-test"
    ],
    "credentials": "credentials/dev.json"
  }
}
```

The application only exposes buckets listed in this file. The backend validates
the selected Storage profile and bucket on every request.

Credential paths can be relative to the project root or absolute Windows paths.

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
