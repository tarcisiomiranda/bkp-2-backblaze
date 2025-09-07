from datetime import datetime, timezone
from pathlib import Path

import socket
import os
import re


def get_lock_path(lock_dir: Path, job_name: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", job_name)
    return lock_dir / f"backup-lock-{safe}.lock"


def acquire_job_lock(lock_path: Path, ttl_seconds: int) -> bool:
    try:
        if lock_path.exists():
            try:
                data = lock_path.read_text().strip()
                parts = data.split("|", 2)
                ts = float(parts[0]) if parts and parts[0] else 0.0
                if datetime.now(timezone.utc).timestamp() - ts < ttl_seconds:
                    return False
            except Exception:
                pass
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        content = (
                f"{datetime.now(timezone.utc).timestamp()}|"
                f"{os.getpid()}|{socket.gethostname()}\n"
            )
        lock_path.write_text(content)
        return True
    except Exception:
        return False


def release_job_lock(lock_path: Path) -> None:
    try:
        if lock_path.exists():
            lock_path.unlink()
    except Exception:
        pass
