
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .gcs_service import GCSService

app = FastAPI(title="GCS Data Browser", version="0.8.4")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
gcs = GCSService()


@app.get("/", response_class=HTMLResponse)
def index():
    return Path("app/templates/index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return gcs.config()


@app.get("/api/bucket-config")
def bucket_config(storage_id: str, bucket: str):
    try:
        return gcs.bucket_config(storage_id, bucket)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/objects")
def objects(storage_id: str, bucket: str, prefix: str = "",
            sort: str = Query("name"), direction: str = Query("asc")):
    try:
        return gcs.list_objects(storage_id, bucket, prefix, sort, direction)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/search")
def search(storage_id: str, bucket: str, q: str, prefix: str = ""):
    try:
        return gcs.search(storage_id, bucket, q, prefix)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/object")
def object_metadata(storage_id: str, bucket: str, name: str):
    try:
        return gcs.object_metadata(storage_id, bucket, name)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/schema")
def schema(storage_id: str, bucket: str, name: str):
    try:
        return gcs.schema(storage_id, bucket, name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/stats")
def stats(storage_id: str, bucket: str, name: str):
    try:
        return gcs.stats(storage_id, bucket, name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/preview")
def preview(storage_id: str, bucket: str, name: str,
            limit: int = Query(100, ge=1, le=1000)):
    try:
        return gcs.preview(storage_id, bucket, name, limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/test-gcs")
def test_gcs(storage_id: str, bucket: str):
    try:
        return gcs.test_gcs(storage_id, bucket)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
