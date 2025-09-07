from typing import Any, Dict, List, Optional
from pathlib import Path
import tempfile
import time

from .locks import get_lock_path, acquire_job_lock, release_job_lock
from .utils import generate_task_id, parse_interval_to_seconds
from .tasks_registry import (
    ensure_tasks_file,
    get_active_jobs_from_registry,
    add_task_to_registry,
    remove_task_from_registry,
)
from .jobs import run_job


def schedule_loop(
    args,
    cfg: Dict[str, Any],
    defaults: Dict[str, Any],
    s3: Any,
    bucket_name: Optional[str],
    endpoint: str,
) -> None:
    jobs: List[Dict[str, Any]] = cfg.get("jobs", []) or []
    selected_names: Optional[List[str]] = None
    if getattr(args, "jobs", None):
        selected_names = [n.strip() for n in args.jobs.split(",") if n.strip()]
    if selected_names:
        by_name = {str(j.get("name") or j.get("id")): j for j in jobs}
        jobs = [by_name[n] for n in selected_names if n in by_name]
    schedule_entries: List[Dict[str, Any]] = []
    for job in jobs:
        every_raw = job.get("every")
        interval = parse_interval_to_seconds(every_raw)
        if not interval or interval <= 0:
            continue
        schedule_entries.append({
            "job": job,
            "interval": interval,
            "next_run": time.time(),
        })
    if not schedule_entries:
        print("No jobs with 'every' configured. Exiting schedule mode.")
        return
    lock_root = Path(args.lock_dir)
    tasks_file = Path(args.tasks_file)
    ensure_tasks_file(tasks_file)
    tick = int(args.tick_interval)
    print(f"Scheduler started with {len(schedule_entries)} job(s). Tick={tick}s")
    while True:
        now = time.time()
        next_due = None
        for entry in schedule_entries:
            if entry["next_run"] <= now:
                job = entry["job"]
                job_display = job.get("name") or job.get("id") or job.get("type")
                active_jobs = set(get_active_jobs_from_registry(
                    tasks_file, ttl_seconds=args.lock_ttl)
                )
                if job_display in active_jobs:
                    print(
                        f"Another run is registered for job '{job_display}'. "
                        "Skipping this schedule tick."
                    )
                    entry["next_run"] = now + entry["interval"]
                    continue
                lock_path = get_lock_path(lock_root, job_display)
                if not acquire_job_lock(lock_path, ttl_seconds=args.lock_ttl):
                    print(
                        f"Another run is in progress for job '{job_display}'. "
                        "Skipping this schedule tick."
                    )
                    entry["next_run"] = now + entry["interval"]
                    continue
                task_id = generate_task_id(job_display)
                print(f"task_id={task_id}")
                add_task_to_registry(tasks_file, job_display, task_id)
                try:
                    with tempfile.TemporaryDirectory(prefix="b2-backup-") as tmpdir:
                        temp_root = Path(tmpdir)
                        run_job(
                            job, defaults,
                            s3, bucket_name,
                            endpoint, temp_root,
                            args.dry_run
                        )
                except Exception as err:
                    print(f"Job failed: {err}")
                finally:
                    remove_task_from_registry(tasks_file, task_id)
                    release_job_lock(lock_path)
                entry["next_run"] = time.time() + entry["interval"]
            if next_due is None or entry["next_run"] < next_due:
                next_due = entry["next_run"]
        sleep_for = tick
        if next_due is not None:
            sleep_for = max(1, min(tick, int(next_due - time.time())))
        time.sleep(sleep_for)
