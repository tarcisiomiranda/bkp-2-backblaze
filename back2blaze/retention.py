from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional, Tuple


def apply_retention(
    s3: Any,
    bucket: str,
    prefix: str,
    max_keep: Optional[int],
    max_age_days: Optional[int],
    dry_run: bool = False,
) -> None:
    if not max_keep and not max_age_days:
        return

    paginator = s3.get_paginator("list_objects_v2")
    keys: List[Tuple[str, datetime]] = []
    for page in paginator.paginate(
            Bucket=bucket, Prefix=prefix.rstrip("/") + "/"
        ):
        for obj in page.get("Contents", []) or []:
            keys.append((obj["Key"], obj["LastModified"]))

    if not keys:
        return

    keys.sort(key=lambda kv: kv[1], reverse=True)

    to_delete: List[str] = []

    if max_keep and len(keys) > max_keep:
        to_delete.extend([k for k, _ in keys[max_keep:]])

    if max_age_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        to_delete.extend([k for k, lm in keys if lm < cutoff])

    to_delete = sorted(set(to_delete))
    if not to_delete:
        return

    print(
        f"Retention: will delete {len(to_delete)} "
        f"object(s) under prefix '{prefix}'"
    )
    if dry_run:
        for key in to_delete:
            print(f"[dry-run] delete s3://{bucket}/{key}")
        return

    chunk_size = 1000
    for i in range(0, len(to_delete), chunk_size):
        chunk = to_delete[i : i + chunk_size]
        s3.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
        )
    print("Retention applied.")
