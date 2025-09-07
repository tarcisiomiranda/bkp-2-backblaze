from typing import Any, Dict, Iterable, List, Optional
from pathlib import Path

from .s3 import upload_file, presign_url, friendly_public_url
from .utils import build_archive_name, run_command_to_file
from .archive import tar_directory, tar_single_file
from .utils import generate_object_key
from .retention import apply_retention


def run_job(
    job: Dict[str, Any],
    defaults: Dict[str, Any],
    s3: Any,
    bucket: Optional[str],
    endpoint: str,
    temp_root: Path,
    dry_run: bool,
) -> None:
    job_name = job.get("name") or job.get("id") or job.get("type")
    if not job_name:
        raise ValueError("Job requires a 'name'.")

    job_type = (job.get("type") or "").lower()
    prefix = job.get("prefix") or defaults.get("prefix") or "backups"
    presign_expiration = int(
        job.get("presign_expiration" or 0) or defaults.get("presign_expiration") or 3600
    )

    retention_cfg = job.get("retention", {})
    max_keep = retention_cfg.get("max_keep") or defaults.get("retention", {}).get(
        "max_keep"
    )
    max_age_days = retention_cfg.get("max_age_days") or defaults.get(
        "retention", {}
    ).get("max_age_days")

    target_bucket = job.get("bucket") or bucket
    if not target_bucket:
        raise ValueError("Job requires 'bucket' (no default bucket defined)")
    archive_name_snake_date = bool(
        job.get(
            "archive_name_snake_date", defaults.get("archive_name_snake_date", False)
        )
    )

    artifacts: List[Path] = []

    try:
        if job_type == "file":
            sources: Iterable[str] = (
                job.get("source")
                if isinstance(job.get("source"), list)
                else [job.get("source")]
            )
            compress = bool(job.get("compress", False))
            for src in sources:
                if not src:
                    continue
                src_path = Path(src)
                if not src_path.exists() or not src_path.is_file():
                    raise FileNotFoundError(f"File not found: {src}")
                if compress:
                    out_name = build_archive_name(
                        (
                            src_path.stem
                            if not job.get("archive_name")
                            else str(job.get("archive_name"))
                        ),
                        archive_name_snake_date,
                    )
                    out = temp_root / out_name
                    artifacts.append(tar_single_file(src_path, out))
                else:
                    artifacts.append(src_path)

        elif job_type == "directory":
            src = job.get("source")
            if not src:
                raise ValueError("'directory' job requires 'source'")
            src_path = Path(src)
            if not src_path.exists() or not src_path.is_dir():
                raise FileNotFoundError(f"Directory not found: {src}")
            exclude_globs = job.get("exclude") or []
            out_name = build_archive_name(
                (
                    src_path.name
                    if not job.get("archive_name")
                    else str(job.get("archive_name"))
                ),
                archive_name_snake_date,
            )
            out = temp_root / out_name
            artifacts.append(tar_directory(src_path, out, exclude_globs))

        elif job_type == "command":
            cmd = job.get("command")
            if not cmd:
                raise ValueError("'command' job requires 'command'")
            out = temp_root / f"{job_name}.out"
            artifacts.append(run_command_to_file(cmd, out))

        elif job_type == "postgres":
            db = job.get("database")
            host = job.get("host", "localhost")
            port = str(job.get("port", 5432))
            user = job.get("user")
            password = job.get("password")
            if not db or not user:
                raise ValueError("'postgres' job requires 'database' and 'user'")
            out = temp_root / f"{job_name}.sql"
            env = {}
            if password:
                env["PGPASSWORD"] = str(password)
            cmd = f"pg_dump -h {host} -p {port} -U {user} {db}"
            artifacts.append(run_command_to_file(cmd, out, env=env))

        elif job_type == "mysql":
            db = job.get("database")
            host = job.get("host", "localhost")
            port = str(job.get("port", 3306))
            user = job.get("user")
            password = job.get("password")
            if not db or not user:
                raise ValueError("'mysql' job requires 'database' and 'user'")
            out = temp_root / f"{job_name}.sql"
            pass_part = f"-p{password}" if password else ""
            cmd = f"mysqldump -h {host} -P {port} -u {user} {pass_part} {db}"
            artifacts.append(run_command_to_file(cmd, out))

        else:
            raise ValueError(f"Unknown job type: {job_type}")

        for artifact in artifacts:
            object_key = generate_object_key(prefix, job_name, artifact)
            upload_file(s3, target_bucket, artifact, object_key, dry_run=dry_run)
            try:
                url = presign_url(s3, target_bucket, object_key, presign_expiration)
                mins = max(1, presign_expiration // 60)
                print(f"Presigned ({mins} min):\n{url}")
            except Exception:
                pass
            pub = friendly_public_url(endpoint, target_bucket, object_key)
            if pub:
                print(f"Public (if bucket is public):\n{pub}")

        apply_retention(
            s3,
            target_bucket,
            f"{prefix}/{job_name}",
            max_keep=max_keep,
            max_age_days=max_age_days,
            dry_run=dry_run,
        )

    finally:
        for artifact in artifacts:
            if artifact.exists() and artifact.parent == temp_root:
                try:
                    artifact.unlink()
                except Exception:
                    pass
