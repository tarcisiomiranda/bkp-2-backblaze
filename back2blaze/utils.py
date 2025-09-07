from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import hashlib
import socket
import uuid
import sys
import os
import re


def getenv(name: str, default: Optional[str] = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        print(f"Missing required environment variable: {name}")
        sys.exit(1)
    return value or ""


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def run_command_to_file(
    command: str, output_file: Path, env: Optional[Dict[str, str]] = None
) -> Path:
    ensure_parent(output_file)
    print(f"$ {command}")

    cmd_list = command.split() if isinstance(command, str) else command
    result = subprocess.run(
        cmd_list,  # nosec B603
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, **(env or {})},
    )
    if result.returncode != 0:
        print(result.stderr.decode("utf-8", errors="ignore"))
        raise RuntimeError(f"Command failed with code {result.returncode}")
    output_file.write_bytes(result.stdout)
    return output_file


def to_snake_lower(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "archive"


def build_archive_name(base: str, add_date: bool = True) -> str:
    base_clean = to_snake_lower(base)
    if add_date:
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"{base_clean}_{date_part}.tar.gz"
    return f"{base_clean}.tar.gz"


def generate_task_id(job_name: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    host = socket.gethostname()
    rand = uuid.uuid4().hex[:8]
    base = f"{job_name}-{host}-{now}-{rand}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def parse_interval_to_seconds(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    try:
        if s.isdigit():
            return int(s)
        if s.endswith("s") and s[:-1].isdigit():
            return int(s[:-1])
        if s.endswith("m") and s[:-1].isdigit():
            return int(s[:-1]) * 60
        if s.endswith("h") and s[:-1].isdigit():
            return int(s[:-1]) * 3600
        if s.endswith("d") and s[:-1].isdigit():
            return int(s[:-1]) * 86400
    except Exception:
        return None
    return None


def generate_object_key(prefix: str, job_name: str, local_file: Path) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix.rstrip('/')}/{job_name}/{timestamp}-{local_file.name}"
