import os
import argparse
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from dotenv import load_dotenv

from .config import load_config
from .s3 import create_s3_client, presign_url, friendly_public_url, list_buckets, ensure_bucket_exists, set_bucket_visibility
from .jobs import run_job
from .utils import getenv, build_archive_name, generate_task_id
from .locks import get_lock_path, acquire_job_lock, release_job_lock
from .tasks_registry import (
    ensure_tasks_file,
    get_active_jobs_from_registry,
    add_task_to_registry,
    remove_task_from_registry,
)
from .scheduler import schedule_loop


def print_extended_help() -> None:
    help_text = (
        "\n"
        "Backup Orchestrator - Extended Help\n"
        "\n"
        "Commands/Flags:\n"
        "  -c, --config <file>          Path to the TOML config file\n"
        "  -j, --jobs <list>            Comma-separated job names\n"
        "      --dry-run               Simulate (no uploads or deletions)\n"
        "      --list                  List jobs from config and exit\n"
        "      --retention-only        Apply retention policy per job and exit\n"
        "      --list-buckets          List available buckets and exit\n"
        "      --create-bucket         Create a bucket (uses --bucket-name or backblaze.bucket)\n"
        "      --bucket-name <name>    Name of the bucket to create\n"
        "      --public                When creating, set a public-read policy\n"
        "      --help-extended         Show this extended help\n"
        "\n"
        "Supported Job Types (type):\n"
        "  - file        (source: string|list; compress: bool)\n"
        "  - directory   (source: string; exclude: list of globs)\n"
        "  - postgres    (host, port, user, password, database)\n"
        "  - mysql       (host, port, user, password, database)\n"
        "  - command     (command: string)\n"
        "\n"
        "Common Job Fields:\n"
        "  name, type, bucket, prefix, presign_expiration,\n"
        "  retention.max_keep, retention.max_age_days,\n"
        "  archive_name_snake_date (bool), archive_name (string)\n"
        "\n"
        "TOML Configuration:\n"
        "  [backblaze] endpoint, region, access_key_id, secret_access_key, (bucket optional)\n"
        "  [defaults] prefix, presign_expiration\n"
        "  [defaults.retention] max_keep, max_age_days\n"
        "  dot_env = \".env\" | dot_envs = [\"a.env\", \"b.env\"] (optional)\n"
        "\n"
        "ENV_* Placeholders:\n"
        "  Any value 'ENV_NAME' will be replaced by $NAME from the environment (or .env).\n"
        "\n"
        "Examples:\n"
        "  List jobs:              python3 main.py -c config.toml --list\n"
        "  Run all jobs:           python3 main.py -c config.toml\n"
        "  Run specific jobs:      python3 main.py -c config.toml -j site-www,db-main\n"
        "  Simulate run:           python3 main.py -c config.toml --dry-run\n"
        "  Retention only:         python3 main.py -c config.toml --retention-only\n"
        "  List buckets:           python3 main.py -c config.toml --list-buckets\n"
        "  Create private bucket:  python3 main.py -c config.toml --create-bucket --bucket-name my-bucket\n"
        "  Create public bucket:   python3 main.py -c config.toml --create-bucket --bucket-name my-bucket --public\n"
    )
    print(help_text)


def main() -> None:
    dotenv_path = os.getenv("DOTENV_PATH", ".env")
    try:
        load_dotenv(dotenv_path=dotenv_path)
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Backup orchestrator for Backblaze S3")
    parser.add_argument(
        "--config", "-c", help="Path to the TOML configuration file"
    )
    parser.add_argument(
        "--jobs", "-j", help="Comma-separated list of job names to run"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate actions without uploading or deleting",
    )
    parser.add_argument(
        "--list", action="store_true", help="List available jobs from config and exit"
    )
    parser.add_argument(
        "--retention-only",
        action="store_true",
        help="Apply retention policy only, without running backups",
    )
    parser.add_argument(
        "--list-buckets", action="store_true", help="List available buckets and exit"
    )
    parser.add_argument(
        "--create-bucket", action="store_true", help="Create a bucket and exit"
    )
    parser.add_argument(
        "--bucket-name", help="Bucket name to create (used with --create-bucket)"
    )
    parser.add_argument(
        "--help-extended", action="store_true", help="Show extended help and exit"
    )
    parser.add_argument("--public", action="store_true", help="When creating a bucket, apply a public-read policy")
    parser.add_argument("--lock-dir", help="Directory for job locks (default: /tmp)", default="/tmp")
    parser.add_argument("--lock-ttl", type=int, default=6 * 60 * 60, help="Lock TTL seconds to avoid stale concurrent runs (default: 21600)")
    parser.add_argument("--tasks-file", help="Path to tasks registry file (default: /tmp/back2blaze/tasks.txt)", default="/tmp/back2blaze/tasks.txt")
    parser.add_argument("--schedule", action="store_true", help="Run in scheduler mode, using 'every' in jobs")
    parser.add_argument("--tick-interval", type=int, default=10, help="Scheduler loop tick interval in seconds (default: 10)")
    args = parser.parse_args()

    if args.help_extended:
        print_extended_help()
        return

    cfg = load_config(args.config)
    s3, bucket_name, endpoint = create_s3_client(cfg)

    defaults = cfg.get("defaults", {})
    jobs: List[Dict[str, Any]] = cfg.get("jobs", []) or []

    if args.list_buckets:
        names = list_buckets(s3)
        if not names:
            print("No buckets returned or insufficient permissions.")
        else:
            print("Buckets:")
            for n in names:
                print(f"- {n}")
        return

    if args.create_bucket:
        target = args.bucket_name or cfg.get("backblaze", {}).get("bucket")
        if not target:
            print("Please provide --bucket-name or define backblaze.bucket in TOML.")
            return
        region = os.getenv("BACKBLAZE_REGION", cfg.get("backblaze", {}).get("region"))
        created = ensure_bucket_exists(s3, target, region=region, public=args.public)
        if not created and args.public:
            set_bucket_visibility(s3, target, public=True)
        return

    if args.list:
        print("Available jobs:")
        for j in jobs:
            print(f"- {j.get('name') or j.get('id')} ({j.get('type')})")
        return

    if args.schedule:
        schedule_loop(args, cfg, defaults, s3, bucket_name, endpoint)
        return

    selected_jobs: List[Dict[str, Any]]
    if args.jobs:
        selected = [n.strip() for n in args.jobs.split(",") if n.strip()]
        by_name = {str(j.get("name") or j.get("id")): j for j in jobs}
        missing = [n for n in selected if n not in by_name]
        if missing:
            print(f"Jobs not found: {', '.join(missing)}")
            raise SystemExit(1)
        selected_jobs = [by_name[n] for n in selected]
    else:
        selected_jobs = jobs

    if not selected_jobs:
        print(
            "No jobs configured. Define 'jobs' in TOML or use legacy environment variables."
        )
        file_path = getenv("FILE_PATH")
        object_name = getenv(
            "OBJECT_NAME", os.path.basename(file_path) if file_path else ""
        )
        expiration = int(getenv("EXPIRATION", "3600"))
        if not file_path or not Path(file_path).is_file():
            print("Nothing to do.")
            return
        if not bucket_name:
            print(
                "A bucket must be defined (BACKBLAZE_BUCKET) for legacy mode."
            )
            return
        with open(file_path, "rb") as fh:
            if not args.dry_run:
                s3.put_object(Bucket=bucket_name, Key=object_name, Body=fh)
        print(f"Upload: {object_name} -> bucket {bucket_name}")
        try:
            url = presign_url(s3, bucket_name, object_name, expiration)
            print(f"Presigned (≤{max(1, expiration // 60)} min):\n{url}")
        except Exception:
            pass
        pub = friendly_public_url(endpoint, bucket_name, object_name)
        if pub:
            print(f"Public (if bucket is public):\n{pub}")
        return

    with tempfile.TemporaryDirectory(prefix="b2-backup-") as tmpdir:
        temp_root = Path(tmpdir)
        lock_root = Path(args.lock_dir)
        tasks_file = Path(args.tasks_file)
        ensure_tasks_file(tasks_file)
        for job in selected_jobs:
            job_display = job.get("name") or job.get("id") or job.get("type")
            print(
                "\n==> Running job:",
                job_display,
            )
            active_jobs = set(get_active_jobs_from_registry(tasks_file, ttl_seconds=args.lock_ttl))
            if job_display in active_jobs:
                print(f"Another run is registered for job '{job_display}'. Skipping.")
                continue
            if args.retention_only:
                prefix = job.get("prefix") or defaults.get("prefix") or "backups"
                retention_cfg = job.get("retention", {})
                max_keep = retention_cfg.get("max_keep") or defaults.get(
                    "retention", {}
                ).get("max_keep")
                max_age_days = retention_cfg.get("max_age_days") or defaults.get(
                    "retention", {}
                ).get("max_age_days")
                target_bucket = job.get("bucket") or bucket_name
                if not target_bucket:
                    print("Skipping retention: no bucket defined for job.")
                else:
                    from .retention import apply_retention

                    apply_retention(
                        s3,
                        target_bucket,
                        f"{prefix}/{job.get('name')}",
                        max_keep=max_keep,
                        max_age_days=max_age_days,
                        dry_run=args.dry_run,
                    )
                continue
            lock_path = get_lock_path(lock_root, job_display)
            if not acquire_job_lock(lock_path, ttl_seconds=args.lock_ttl):
                print(f"Another run is in progress for job '{job_display}'. Skipping.")
                continue
            task_id = generate_task_id(job_display)
            print(f"task_id={task_id}")
            add_task_to_registry(tasks_file, job_display, task_id)
            try:
                run_job(
                    job, defaults, s3, bucket_name, endpoint, temp_root, args.dry_run
                )
            except Exception as err:
                print(f"Job failed: {err}")
            finally:
                remove_task_from_registry(tasks_file, task_id)
                release_job_lock(lock_path)
