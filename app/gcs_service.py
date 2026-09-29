import os
from pathlib import Path

import pyarrow.parquet as pq
from pyarrow import fs as pafs
from google.cloud import storage


class GCSService:
    def __init__(self):
        self.bucket_name = os.getenv("GCS_BUCKET_FILTER", "").strip()
        if not self.bucket_name:
            raise RuntimeError("GCS_BUCKET_FILTER is required")

        credentials_file = os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS", ""
        ).strip()

        if credentials_file:
            credentials_path = Path(credentials_file)
            if not credentials_path.exists():
                raise RuntimeError(
                    f"Credentials file not found: {credentials_file}"
                )

            self.client = storage.Client.from_service_account_json(
                credentials_file
            )
        else:
            self.client = storage.Client()

        # Used by PyArrow for remote Parquet access.
        self.arrow_fs = pafs.GcsFileSystem()

        self.root_prefix = os.getenv("GCS_ROOT_PREFIX", "").strip().strip("/")
        if self.root_prefix:
            self.root_prefix += "/"

        self.max_preview_rows = int(
            os.getenv("MAX_PREVIEW_ROWS", "100")
        )
        self.max_search_results = int(
            os.getenv("MAX_SEARCH_RESULTS", "200")
        )

    def _get_bucket(self):
        # Deliberately references the configured bucket directly.
        # No storage.buckets.list permission is required.
        return self.client.bucket(self.bucket_name)

    def _normalize_prefix(self, prefix):
        prefix = (prefix or "").strip().lstrip("/")

        if prefix and not prefix.endswith("/"):
            prefix += "/"

        if self.root_prefix:
            if prefix and not prefix.startswith(self.root_prefix):
                prefix = self.root_prefix + prefix
            elif not prefix:
                prefix = self.root_prefix

        return prefix

    def _validate_name(self, name):
        name = (name or "").strip().lstrip("/")

        if not name:
            raise ValueError("Object name is required")

        if self.root_prefix and not name.startswith(self.root_prefix):
            raise ValueError("Object outside configured root prefix")

        return name

    def _relative_name(self, name, prefix):
        if name.startswith(prefix):
            return name[len(prefix):]
        return name

    def _parent_prefix(self, prefix):
        prefix = (prefix or "").rstrip("/")

        if not prefix:
            return ""

        if self.root_prefix and prefix == self.root_prefix.rstrip("/"):
            return ""

        parent = prefix.rsplit("/", 1)[0] if "/" in prefix else ""

        if parent and not parent.endswith("/"):
            parent += "/"

        if self.root_prefix:
            root = self.root_prefix.rstrip("/")
            if parent and not parent.startswith(root):
                return self.root_prefix
            if parent == root:
                return self.root_prefix

        return parent

    def config(self):
        return {
            "bucket": self.bucket_name,
            "root_prefix": self.root_prefix,
            "max_preview_rows": self.max_preview_rows,
        }

    def list_objects(self, prefix="", sort="name", direction="asc"):
        """
        List the immediate folders and files under prefix.

        Important:
        We intentionally do NOT use delimiter="/".

        Some GCS iterator behaviors around prefixes can make it easy to
        consume the iterator before prefixes are inspected. Instead, we
        retrieve object names and derive the immediate child folders
        ourselves. This also gives the frontend a deterministic tree.
        """
        prefix = self._normalize_prefix(prefix)

        # Materialize the iterator once. This avoids depending on the
        # iterator's internal prefixes state.
        blobs = list(
            self.client.list_blobs(
                self._get_bucket(),
                prefix=prefix,
            )
        )

        folders_map = {}
        objects = []

        for blob in blobs:
            name = blob.name

            # Ignore the synthetic folder marker itself.
            if name == prefix:
                continue

            relative = self._relative_name(name, prefix)

            # A child containing "/" belongs to a subfolder.
            if "/" in relative:
                child_folder = relative.split("/", 1)[0]
                folder_name = f"{prefix}{child_folder}/"

                folders_map[folder_name] = {
                    "name": folder_name.rstrip("/"),
                    "relative_name": child_folder,
                    "is_folder": True,
                    "size": None,
                    "updated": None,
                    "content_type": None,
                    "storage_class": None,
                }
                continue

            objects.append({
                "name": name,
                "relative_name": relative,
                "size": blob.size or 0,
                "updated": (
                    blob.updated.isoformat()
                    if blob.updated
                    else None
                ),
                "content_type": blob.content_type,
                "storage_class": blob.storage_class,
                "is_folder": False,
            })

        folders_data = sorted(
            folders_map.values(),
            key=lambda x: x["relative_name"].lower(),
        )

        key_map = {
            "name": lambda x: x["relative_name"].lower(),
            "size": lambda x: (
                x["size"] if x["size"] is not None else -1
            ),
            "modified": lambda x: x["updated"] or "",
        }

        key = key_map.get(sort, key_map["name"])
        reverse = direction.lower() == "desc"

        items = folders_data + objects
        items.sort(key=key, reverse=reverse)

        return {
            "bucket": self.bucket_name,
            "prefix": prefix,
            "parent_prefix": self._parent_prefix(prefix),
            "folders": folders_data,
            "objects": objects,
            "items": items,
            "count": len(items),
        }

    def search(self, q, prefix=""):
        q = (q or "").strip().lower()
        prefix = self._normalize_prefix(prefix)

        if not q:
            return {
                "query": q,
                "prefix": prefix,
                "results": [],
                "count": 0,
            }

        results = []

        for blob in self.client.list_blobs(
            self._get_bucket(),
            prefix=prefix,
        ):
            if q in blob.name.lower():
                results.append({
                    "name": blob.name,
                    "relative_name": self._relative_name(
                        blob.name, prefix
                    ),
                    "size": blob.size or 0,
                    "updated": (
                        blob.updated.isoformat()
                        if blob.updated
                        else None
                    ),
                    "content_type": blob.content_type,
                    "storage_class": blob.storage_class,
                    "is_folder": False,
                })

            if len(results) >= self.max_search_results:
                break

        return {
            "query": q,
            "prefix": prefix,
            "results": results,
            "count": len(results),
        }

    def object_metadata(self, name):
        name = self._validate_name(name)
        blob = self._get_bucket().blob(name)

        if not blob.exists():
            raise FileNotFoundError(f"Object not found: {name}")

        blob.reload()

        return {
            "name": blob.name,
            "bucket": self.bucket_name,
            "size": blob.size or 0,
            "content_type": blob.content_type,
            "storage_class": blob.storage_class,
            "created": (
                blob.time_created.isoformat()
                if blob.time_created
                else None
            ),
            "updated": (
                blob.updated.isoformat()
                if blob.updated
                else None
            ),
            "etag": blob.etag,
            "md5_hash": blob.md5_hash,
            "crc32c": blob.crc32c,
            "generation": blob.generation,
            "metageneration": blob.metageneration,
        }

    def _parquet_file(self, object_name):
        return pq.ParquetFile(
            f"{self.bucket_name}/{object_name}",
            filesystem=self.arrow_fs,
        )

    def schema(self, name):
        name = self._validate_name(name)

        if not name.lower().endswith(".parquet"):
            raise ValueError("Schema is currently supported for Parquet files only")

        parquet = self._parquet_file(name)

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

    def stats(self, name):
        name = self._validate_name(name)

        if not name.lower().endswith(".parquet"):
            raise ValueError("Statistics are currently supported for Parquet files only")

        parquet = self._parquet_file(name)
        metadata = parquet.metadata

        return {
            "format": "parquet",
            "name": name,
            "num_rows": metadata.num_rows,
            "num_columns": metadata.num_columns,
            "num_row_groups": metadata.num_row_groups,
            "serialized_size": metadata.serialized_size,
        }

    def _preview_parquet(self, name, limit):
        parquet = self._parquet_file(name)

        if parquet.metadata.num_row_groups == 0:
            return {
                "format": "parquet",
                "columns": [],
                "rows": [],
                "returned_rows": 0,
                "note": "Parquet file has no row groups.",
            }

        table = parquet.read_row_group(0)
        table = table.slice(0, limit)

        return {
            "format": "parquet",
            "columns": table.column_names,
            "rows": table.to_pylist(),
            "returned_rows": table.num_rows,
            "note": "Preview reads the first Parquet row group only.",
        }

    def preview(self, name, limit=100):
        name = self._validate_name(name)
        limit = min(
            max(int(limit), 1),
            self.max_preview_rows,
        )

        if name.lower().endswith(".parquet"):
            return self._preview_parquet(name, limit)

        raise ValueError(
            "Preview is currently supported for Parquet files only"
        )
