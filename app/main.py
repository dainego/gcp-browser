from pathlib import Path

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .gcs_service import GCSService

app = FastAPI(title="GCS Data Browser", version="0.5")

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


@app.get("/api/objects")
def objects(
    prefix: str = "",
    sort: str = Query("name"),
    direction: str = Query("asc"),
):
    return gcs.list_objects(prefix=prefix, sort=sort, direction=direction)


@app.get("/api/search")
def search(q: str, prefix: str = ""):
    return gcs.search(q=q, prefix=prefix)


@app.get("/api/object")
def object_metadata(name: str):
    try:
        return gcs.object_metadata(name)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/schema")
def schema(name: str):
    try:
        return gcs.schema(name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/stats")
def stats(name: str):
    try:
        return gcs.stats(name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/preview")
def preview(name: str, limit: int = Query(100, ge=1, le=1000)):
    try:
        return gcs.preview(name, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/test-gcs")
def test_gcs():
    """Simple diagnostic endpoint; useful for validating bucket access."""
    result = []

    for blob in gcs.client.list_blobs(gcs.bucket_name):
        result.append({
            "name": blob.name,
            "size": blob.size or 0,
        })
        if len(result) >= 10:
            break

    return {
        "bucket": gcs.bucket_name,
        "objects_found": len(result),
        "objects": result,
    }
