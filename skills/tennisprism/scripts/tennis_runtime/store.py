"""Small durable local store. Every video/run has its own stable directory."""
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.lock = threading.RLock()
        for name in ("videos", "runs"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def path(self, kind: str, identifier: str) -> Path:
        if kind not in {"videos", "runs"} or not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise KeyError("记录不存在")
        return self.root / kind / identifier

    def create(self, kind: str, record: dict) -> dict:
        with self.lock:
            identifier = uuid.uuid4().hex
            folder = self.path(kind, identifier)
            folder.mkdir()
            value = {**record, "id": identifier, "created_at": now()}
            self._write(folder, value)
            return value

    def _write(self, folder: Path, value: dict):
        # Retain a previous valid record before updating. No user data is deleted.
        serialized = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
        current = folder / "record.json"
        if current.exists():
            raw = current.read_bytes()
            try:
                valid = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                valid = None
            if isinstance(valid, dict) and valid.get("id") == value["id"]:
                (folder / "record.previous.json").write_bytes(raw)
        current.write_text(serialized, encoding="utf-8")

    def get(self, kind: str, identifier: str) -> dict:
        with self.lock:
            folder = self.path(kind, identifier)
            for name in ("record.json", "record.previous.json"):
                path = folder / name
                if path.is_file():
                    try:
                        return json.loads(path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        continue
            raise KeyError("记录不存在或无法读取")

    def update(self, kind: str, identifier: str, **changes) -> dict:
        with self.lock:
            record = {**self.get(kind, identifier), **changes}
            self._write(self.path(kind, identifier), record)
            return record

    def list(self, kind: str) -> list[dict]:
        with self.lock:
            items = []
            for path in (self.root / kind).iterdir():
                if path.is_dir():
                    try:
                        items.append(self.get(kind, path.name))
                    except KeyError:
                        continue
            return sorted(items, key=lambda r: r["created_at"], reverse=True)

    def recover_interrupted(self):
        for kind, states in (("videos", {"preparing", "uploading"}), ("runs", {"queued", "preparing", "analyzing"})):
            for record in self.list(kind):
                if record["status"] in states:
                    self.update(kind, record["id"], status="error", error="上次运行在完成前中断。原始数据已保留，请重新上传或发起新的分析。", message="上次任务已中断")
