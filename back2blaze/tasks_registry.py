from datetime import datetime, timezone
from pathlib import Path
from typing import List
import socket
import os


def ensure_tasks_file(tasks_file: Path) -> None:
    tasks_file.parent.mkdir(parents=True, exist_ok=True)
    if not tasks_file.exists():
        try:
            tasks_file.touch()
        except Exception:
            pass


def get_active_jobs_from_registry(tasks_file: Path, ttl_seconds: int) -> List[str]:
    active_jobs: List[str] = []
    if not tasks_file.exists():
        return active_jobs
    try:
        lines = tasks_file.read_text().splitlines()
    except Exception:
        return active_jobs
    now_ts = datetime.now(timezone.utc).timestamp()
    kept_lines: List[str] = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split("|", 4)
        if len(parts) < 3:
            continue
        try:
            ts = float(parts[0])
        except Exception:
            continue
        job_name = parts[1]
        if now_ts - ts < ttl_seconds:
            active_jobs.append(job_name)
            kept_lines.append(line)
    try:
        if kept_lines != lines:
            tasks_file.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""))
    except Exception:
        pass
    return active_jobs


def add_task_to_registry(tasks_file: Path, job_name: str, task_id: str) -> None:
    ensure_tasks_file(tasks_file)
    entry = (
        f"{datetime.now(timezone.utc).timestamp()}|"
        f"{job_name}|{task_id}|{os.getpid()}|{socket.gethostname()}\n"
    )
    try:
        with tasks_file.open("a") as f:
            f.write(entry)
    except Exception:
        pass


def remove_task_from_registry(tasks_file: Path, task_id: str) -> None:
    if not tasks_file.exists():
        return
    try:
        lines = tasks_file.read_text().splitlines()
        new_lines = []
        for line in lines:
            parts = line.split("|", 4)
            if len(parts) >= 3 and parts[2] == task_id:
                continue
            new_lines.append(line)
        if new_lines != lines:
            tasks_file.write_text("\n".join(new_lines) + ("\n" if new_lines else ""))
    except Exception:
        pass
