from __future__ import annotations

import os
import uuid
from pathlib import Path

from loguru import logger

from backend.app.core.config import settings


class SecretStore:
    """Simple local file-backed secret store.

    Secrets are stored outside database rows and referenced by ``file:<id>``.
    """

    def __init__(self, root_dir: str) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for_ref(self, secret_ref: str) -> Path | None:
        if not secret_ref.startswith("file:"):
            return None
        token = secret_ref[len("file:") :].strip()
        if not token or "/" in token or "\\" in token or ".." in token:
            return None
        return self.root / f"{token}.secret"

    def set_secret(self, value: str, current_ref: str | None = None) -> str:
        token = ""
        path: Path | None = None
        if current_ref:
            path = self._path_for_ref(current_ref)
            if path is not None:
                token = current_ref[len("file:") :].strip()

        if not token or path is None:
            token = str(uuid.uuid4())
            path = self.root / f"{token}.secret"

        path.write_text(value, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except Exception:
            logger.warning("Failed to chmod secret file {}", path)
        return f"file:{token}"

    def get_secret(self, secret_ref: str | None) -> str | None:
        if not secret_ref:
            return None
        path = self._path_for_ref(secret_ref)
        if path is None or not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            logger.exception("Failed to read secret ref {}", secret_ref)
            return None

    def has_secret(self, secret_ref: str | None) -> bool:
        value = self.get_secret(secret_ref)
        return bool(value and value.strip())

    def delete_secret(self, secret_ref: str | None) -> None:
        if not secret_ref:
            return
        path = self._path_for_ref(secret_ref)
        if path is None or not path.exists():
            return
        try:
            path.unlink()
        except Exception:
            logger.exception("Failed to delete secret ref {}", secret_ref)


_secret_store: SecretStore | None = None


def get_secret_store() -> SecretStore:
    global _secret_store
    if _secret_store is None:
        _secret_store = SecretStore(settings.SECRET_STORE_DIR)
    return _secret_store

