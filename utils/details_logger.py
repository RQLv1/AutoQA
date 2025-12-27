from __future__ import annotations

import json
import sys
import time
from io import TextIOBase
from pathlib import Path
from threading import Lock
from typing import Any

from utils.config import DETAILS_PATH


class DetailsLogger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()
        self._data: dict[str, Any] = {"stdout": [], "events": []}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if self._path.exists():
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    stdout = payload.get("stdout")
                    events = payload.get("events")
                    if isinstance(stdout, list):
                        self._data["stdout"] = stdout
                    if isinstance(events, list):
                        self._data["events"] = events
            except Exception:
                pass
        self._loaded = True

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def log_stdout_line(self, line: str) -> None:
        with self._lock:
            self._load()
            self._data["stdout"].append(line)
            self._save()

    def log_event(self, kind: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._load()
            self._data["events"].append(
                {"ts": round(time.time(), 3), "kind": kind, "payload": payload}
            )
            self._save()

    def reset(self) -> None:
        with self._lock:
            self._data = {"stdout": [], "events": []}
            self._loaded = True
            self._save()


class TeeStream(TextIOBase):
    def __init__(self, original: TextIOBase, logger: DetailsLogger, *, is_stderr: bool) -> None:
        self._original = original
        self._logger = logger
        self._is_stderr = is_stderr
        self._buffer = ""

    def write(self, s: str) -> int:
        if not isinstance(s, str):
            s = str(s)
        self._original.write(s)
        self._original.flush()
        self._buffer += s
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if self._is_stderr:
                self._logger.log_event("stderr_line", {"line": line})
            else:
                self._logger.log_stdout_line(line)
        return len(s)

    def flush(self) -> None:
        self._original.flush()

    def close(self) -> None:
        if self._buffer:
            if self._is_stderr:
                self._logger.log_event("stderr_line", {"line": self._buffer})
            else:
                self._logger.log_stdout_line(self._buffer)
            self._buffer = ""
        self._original.flush()


_DETAILS_LOGGER: DetailsLogger | None = None


def get_details_logger() -> DetailsLogger:
    global _DETAILS_LOGGER
    if _DETAILS_LOGGER is None:
        _DETAILS_LOGGER = DetailsLogger(Path(DETAILS_PATH))
    return _DETAILS_LOGGER


def setup_details_logging(*, reset: bool = True) -> DetailsLogger:
    logger = get_details_logger()
    if reset:
        logger.reset()
    if not isinstance(sys.stdout, TeeStream):
        sys.stdout = TeeStream(sys.stdout, logger, is_stderr=False)
    if not isinstance(sys.stderr, TeeStream):
        sys.stderr = TeeStream(sys.stderr, logger, is_stderr=True)
    return logger
