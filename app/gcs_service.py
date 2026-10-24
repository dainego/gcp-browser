
import json
import os
import re
import threading
import time
from pathlib import Path

import pyarrow.parquet as pq
from pyarrow import fs as pafs
from google.auth import load_credentials_from_file
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google.cloud import storage


class GCSService:
    def __init__(self):
        self.max_preview_rows = int(os.getenv("MAX_PREVIEW_ROWS", "100"))
        self.max_search_results = int(os.getenv("MAX_SEARCH_RESULTS", "200"))
        self.count_cache_ttl_seconds = max(0, int(os.getenv("COUNT_CACHE_TTL_SECONDS", "300")))
        self._count_cache = {}
        self._count_cache_lock = threading.Lock()
        self._count_inflight = {}
        self.storages = self._load_storages()

        if not self.storages:
            raise RuntimeError(
                "config/storages.json is required. Configure at least one storage."
            )

        self.clients = {}
        self.credentials = {}

        for storage_id, config in self.storages.items():
            self._initialize_storage(storage_id, config)

    def _load_storages(self):
        config_path = Path(__file__).resolve().parent.parent / "config" / "storages.json"

        if not config_path.exists():
            return {}

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Storage configuration contains invalid JSON: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError("config/storages.json must contain a JSON object")

        result = {}

        for storage_id, config in data.items():
            if not isinstance(config, dict):
                raise RuntimeError(
                    f"Storage '{storage_id}' must be an object"
                )

            buckets = config.get("buckets", [])
            if isinstance(buckets, str):
                buckets = [buckets]

            buckets = [
                str(bucket).strip()
                for bucket in buckets
                if str(bucket).strip()
            ]

            if not buckets:
                raise RuntimeError(
                    f"Storage '{storage_id}' must have at least one bucket"
                )

            result[str(storage_id)] = {
                "label": str(config.get("label") or storage_id),
                "buckets": buckets,
                "credentials": str(config.get("credentials") or "").strip(),
                "secret": str(config.get("secret") or "").strip(),
                "secret_env": str(config.get("secret_env") or "").strip(),
                "root_prefixes": config.get("root_prefixes") or {},
            }

        return result

    def _initialize_storage(self, storage_id, config):
        scopes = ["https://www.googleapis.com/auth/devstorage.read_only"]
        secret_env = config.get("secret_env", "")
        secret_value = os.getenv(secret_env) if secret_env else None

        # Cloud Run: Secret Manager injects the Service Account JSON as an env var.
        if secret_value:
            try:
                service_account_info = json.loads(secret_value)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Secret environment variable '{secret_env}' for '{storage_id}' contains invalid JSON: {exc}"
                ) from exc

            if not isinstance(service_account_info, dict):
                raise RuntimeError(
                    f"Secret environment variable '{secret_env}' for '{storage_id}' must contain a JSON object."
                )

            try:
                credentials = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=scopes,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Could not load Service Account credentials from secret for '{storage_id}': {exc}"
                ) from exc

            self.credentials[storage_id] = credentials
            self.clients[storage_id] = storage.Client(
                project=getattr(credentials, "project_id", None),
                credentials=credentials,
            )
            return

        # Local: keep using the JSON file under credentials/.
        credentials_file = config["credentials"]

        if credentials_file:
            path = Path(credentials_file)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent.parent / path

            if not path.exists():
                raise RuntimeError(
                    f"Credentials file not found for '{storage_id}': {credentials_file}"
                )

            credentials, _ = load_credentials_from_file(
                str(path),
                scopes=scopes,
            )

            self.credentials[storage_id] = credentials
            self.clients[storage_id] = storage.Client(
                project=getattr(credentials, "project_id", None),
                credentials=credentials,
            )
        else:
            self.clients[storage_id] = storage.Client()

    def _storage(self, storage_id):
        if storage_id not in self.storages:
            raise ValueError(f"Unknown storage profile: {storage_id}")
        return self.storages[storage_id]

    def _allowed_bucket(self, storage_id, bucket):
        config = self._storage(storage_id)
        bucket = str(bucket or "").strip()

        if bucket not in config["buckets"]:
            raise ValueError(
                f"Bucket '{bucket}' is not allowed for storage '{storage_id}'"
            )

        return bucket

    def _client(self, storage_id):
        return self.clients[storage_id]

    def _bucket(self, storage_id, bucket):
        return self._client(storage_id).bucket(
            self._allowed_bucket(storage_id, bucket)
        )

    def _root_prefix(self, storage_id, bucket):
        config = self._storage(storage_id)
        prefix = str(
            (config.get("root_prefixes") or {}).get(bucket, "") or ""
        ).strip().strip("/")
        return f"{prefix}/" if prefix else ""

    def _normalize_prefix(self, storage_id, bucket, prefix):
        root = self._root_prefix(storage_id, bucket)
        prefix = (prefix or "").strip().lstrip("/")

        if prefix and not prefix.endswith("/"):
            prefix += "/"

        if root:
            if prefix and not prefix.startswith(root):
                prefix = root + prefix
            elif not prefix:
                prefix = root

        return prefix

    def _validate_name(self, storage_id, bucket, name):
        self._allowed_bucket(storage_id, bucket)
        name = (name or "").strip().lstrip("/")

        if not name:
            raise ValueError("Object name is required")

        root = self._root_prefix(storage_id, bucket)
        if root and not name.startswith(root):
            raise ValueError("Object outside configured root prefix")

        return name

    def _relative_name(self, name, prefix):
        return name[len(prefix):] if name.startswith(prefix) else name

    def _parent_prefix(self, storage_id, bucket, prefix):
        prefix = (prefix or "").rstrip("/")
        root = self._root_prefix(storage_id, bucket)

        if not prefix:
            return ""
        if root and prefix == root.rstrip("/"):
            return ""

        parent = prefix.rsplit("/", 1)[0] if "/" in prefix else ""
        if parent and not parent.endswith("/"):
            parent += "/"

        if root:
            root_clean = root.rstrip("/")
            if parent and not parent.startswith(root_clean):
                return root
            if parent == root_clean:
                return root

        return parent

    def config(self):
        return {
            "storages": [
                {
                    "id": storage_id,
                    "label": config["label"],
                    "buckets": config["buckets"],
                }
                for storage_id, config in self.storages.items()
            ],
            "max_preview_rows": self.max_preview_rows,
        }

    def bucket_config(self, storage_id, bucket):
        bucket = self._allowed_bucket(storage_id, bucket)
        return {
            "storage_id": storage_id,
            "bucket": bucket,
            "root_prefix": self._root_prefix(storage_id, bucket),
        }

    def list_objects(self, storage_id, bucket, prefix="", sort="name", direction="asc", page_token=None, page_size=500):
        """Return one incremental batch of immediate children for a folder."""
        bucket = self._allowed_bucket(storage_id, bucket)
        prefix = self._normalize_prefix(storage_id, bucket, prefix)
        page_size = max(1, min(int(page_size or 500), 500))

        iterator = self._client(storage_id).list_blobs(
            self._bucket(storage_id, bucket),
            prefix=prefix,
            delimiter="/",
            max_results=page_size,
            page_token=page_token or None,
        )
        page = next(iterator.pages, None)
        selected_items = []

        if page is not None:
            for child_prefix in sorted(getattr(page, "prefixes", set()) or set()):
                if child_prefix == prefix:
                    continue
                relative = self._relative_name(child_prefix.rstrip("/"), prefix)
                if relative:
                    selected_items.append({
                        "name": child_prefix.rstrip("/"),
                        "relative_name": relative,
                        "is_folder": True,
                        "size": None,
                        "updated": None,
                        "content_type": None,
                        "storage_class": None,
                    })

            for blob in page:
                if blob.name == prefix:
                    continue
                relative = self._relative_name(blob.name, prefix)
                if not relative or "/" in relative:
                    continue
                selected_items.append({
                    "name": blob.name,
                    "relative_name": relative,
                    "size": blob.size or 0,
                    "updated": blob.updated.isoformat() if blob.updated else None,
                    "content_type": blob.content_type,
                    "storage_class": blob.storage_class,
                    "is_folder": False,
                })

        key_map = {
            "name": lambda x: x["relative_name"].lower(),
            "size": lambda x: x["size"] if x["size"] is not None else -1,
            "modified": lambda x: x["updated"] or "",
        }
        selected_items.sort(
            key=key_map.get(sort, key_map["name"]),
            reverse=direction.lower() == "desc",
        )
        next_page_token = iterator.next_page_token
        folders_data = [item for item in selected_items if item["is_folder"]]
        objects_data = [item for item in selected_items if not item["is_folder"]]
        return {
            "storage_id": storage_id,
            "bucket": bucket,
            "prefix": prefix,
            "parent_prefix": self._parent_prefix(storage_id, bucket, prefix),
            "folders": folders_data,
            "objects": objects_data,
            "items": selected_items,
            "count": len(selected_items),
            "next_page_token": next_page_token,
            "has_more": bool(next_page_token),
        }

    def count_folder_items(self, storage_id, bucket, prefix=""):
        """Return an exact immediate-child count, cached for a configurable TTL."""
        bucket = self._allowed_bucket(storage_id, bucket)
        prefix = self._normalize_prefix(storage_id, bucket, prefix)
        key = (storage_id, bucket, prefix)

        while True:
            with self._count_cache_lock:
                now = time.monotonic()
                cached = self._count_cache.get(key)
                if cached and now - cached[0] < self.count_cache_ttl_seconds:
                    result = dict(cached[1])
                    result["cached"] = True
                    result["cache_ttl_seconds"] = self.count_cache_ttl_seconds
                    return result

                pending = self._count_inflight.get(key)
                if pending is None:
                    pending = threading.Event()
                    self._count_inflight[key] = pending
                    owner = True
                else:
                    owner = False

            if owner:
                break
            # Avoid duplicate full listings when multiple requests count the same folder.
            pending.wait()

        try:
            result = self._count_folder_items_uncached(storage_id, bucket, prefix)
            with self._count_cache_lock:
                if self.count_cache_ttl_seconds > 0:
                    self._count_cache[key] = (time.monotonic(), dict(result))
            result["cached"] = False
            result["cache_ttl_seconds"] = self.count_cache_ttl_seconds
            return result
        finally:
            with self._count_cache_lock:
                event = self._count_inflight.pop(key, None)
                if event:
                    event.set()

    def _count_folder_items_uncached(self, storage_id, bucket, prefix):
        """Count immediate files and virtual folders without retaining all entries."""
        # Do not set max_results here: that parameter caps the TOTAL number of
        # objects returned by the iterator. Omitting it lets iterator.pages
        # traverse every API page, while each API request remains paginated.
        iterator = self._client(storage_id).list_blobs(
            self._bucket(storage_id, bucket), prefix=prefix, delimiter="/"
        )
        file_count = 0
        folder_prefixes = set()
        for page in iterator.pages:
            folder_prefixes.update(getattr(page, "prefixes", set()) or set())
            for blob in page:
                if blob.name == prefix:
                    continue
                relative = self._relative_name(blob.name, prefix)
                if relative and "/" not in relative:
                    file_count += 1
        folder_count = sum(1 for item in folder_prefixes if item != prefix)
        return {
            "storage_id": storage_id,
            "bucket": bucket,
            "prefix": prefix,
            "files": file_count,
            "folders": folder_count,
            "count": file_count + folder_count,
        }

    def search(self, storage_id, bucket, q, prefix=""):
        bucket = self._allowed_bucket(storage_id, bucket)
        q = (q or "").strip()
        prefix = self._normalize_prefix(storage_id, bucket, prefix)
        results = []

        if q:
            try:
                pattern = re.compile(q, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"Expresión regular inválida: {exc}") from exc

            for blob in self._client(storage_id).list_blobs(
                self._bucket(storage_id, bucket), prefix=prefix
            ):
                relative = self._relative_name(blob.name, prefix)
                if pattern.search(relative):
                    results.append({
                        "name": blob.name,
                        "relative_name": relative,
                        "size": blob.size or 0,
                        "updated": blob.updated.isoformat() if blob.updated else None,
                        "content_type": blob.content_type,
                        "storage_class": blob.storage_class,
                        "is_folder": False,
                    })

                if len(results) >= self.max_search_results:
                    break

        return {
            "query": q,
            "storage_id": storage_id,
            "bucket": bucket,
            "prefix": prefix,
            "results": results,
            "count": len(results),
            "max_results": self.max_search_results,
            "truncated": len(results) >= self.max_search_results,
        }

    def object_metadata(self, storage_id, bucket, name):
        name = self._validate_name(storage_id, bucket, name)
        blob = self._bucket(storage_id, bucket).blob(name)

        if not blob.exists():
            raise FileNotFoundError(f"Object not found: {name}")

        blob.reload()

        return {
            "name": blob.name,
            "bucket": bucket,
            "storage_id": storage_id,
            "size": blob.size or 0,
            "content_type": blob.content_type,
            "storage_class": blob.storage_class,
            "created": blob.time_created.isoformat() if blob.time_created else None,
            "updated": blob.updated.isoformat() if blob.updated else None,
            "etag": blob.etag,
            "md5_hash": blob.md5_hash,
            "crc32c": blob.crc32c,
            "generation": blob.generation,
            "metageneration": blob.metageneration,
        }

    def _arrow_fs(self, storage_id):
        credentials = self.credentials.get(storage_id)

        if credentials is None:
            return pafs.GcsFileSystem()

        # PyArrow requires access_token and credential_token_expiration
        # to be provided together when using an explicit OAuth token.
        if not credentials.valid or credentials.expiry is None:
            credentials.refresh(Request())

        if not credentials.token or credentials.expiry is None:
            raise RuntimeError(
                f"No se pudo obtener un access token válido para storage '{storage_id}'."
            )

        return pafs.GcsFileSystem(
            access_token=credentials.token,
            credential_token_expiration=credentials.expiry,
            project_id=getattr(credentials, "project_id", None),
        )

    def _parquet_file(self, storage_id, bucket, name):
        return pq.ParquetFile(
            f"{bucket}/{name}",
            filesystem=self._arrow_fs(storage_id),
        )

    def schema(self, storage_id, bucket, name):
        name = self._validate_name(storage_id, bucket, name)

        if not name.lower().endswith(".parquet"):
            raise ValueError("Schema is currently supported for Parquet files only")

        parquet = self._parquet_file(storage_id, bucket, name)

        return {
            "format": "parquet",
            "name": name,
            "num_rows": parquet.metadata.num_rows,
            "num_columns": parquet.metadata.num_columns,
            "num_row_groups": parquet.metadata.num_row_groups,
            "columns": [
                {
                    "name": field.name,
                    "type": str(field.type),
                    "nullable": field.nullable,
                }
                for field in parquet.schema_arrow
            ],
        }

    def stats(self, storage_id, bucket, name):
        name = self._validate_name(storage_id, bucket, name)

        if not name.lower().endswith(".parquet"):
            raise ValueError("Statistics are currently supported for Parquet files only")

        metadata = self._parquet_file(storage_id, bucket, name).metadata

        return {
            "format": "parquet",
            "name": name,
            "num_rows": metadata.num_rows,
            "num_columns": metadata.num_columns,
            "num_row_groups": metadata.num_row_groups,
            "serialized_size": metadata.serialized_size,
        }

    def preview(self, storage_id, bucket, name, limit=100):
        name = self._validate_name(storage_id, bucket, name)
        limit = min(max(int(limit), 1), self.max_preview_rows)

        if not name.lower().endswith(".parquet"):
            raise ValueError("Preview is currently supported for Parquet files only")

        parquet = self._parquet_file(storage_id, bucket, name)

        if parquet.metadata.num_row_groups == 0:
            return {
                "format": "parquet",
                "columns": [],
                "rows": [],
                "returned_rows": 0,
                "note": "Parquet file has no row groups.",
            }

        table = parquet.read_row_group(0).slice(0, limit)

        return {
            "format": "parquet",
            "columns": table.column_names,
            "rows": table.to_pylist(),
            "returned_rows": table.num_rows,
            "note": "Preview reads the first Parquet row group only.",
        }

    def test_gcs(self, storage_id, bucket):
        bucket = self._allowed_bucket(storage_id, bucket)
        result = []

        for blob in self._client(storage_id).list_blobs(
            self._bucket(storage_id, bucket)
        ):
            result.append({"name": blob.name, "size": blob.size or 0})
            if len(result) >= 10:
                break

        return {
            "storage_id": storage_id,
            "bucket": bucket,
            "objects_found": len(result),
            "objects": result,
        }
