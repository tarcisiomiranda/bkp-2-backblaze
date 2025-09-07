from typing import Any, Dict, List, Optional
from botocore.exceptions import ClientError
from botocore.client import Config
import boto3
import json
import os


def create_s3_client(cfg: Dict[str, Any]):
    backblaze_cfg = cfg.get("backblaze", {})
    endpoint = os.getenv(
        "BACKBLAZE_ENDPOINT",
        backblaze_cfg.get("endpoint", "s3.us-east-005.backblazeb2.com"),
    )
    region = os.getenv("BACKBLAZE_REGION", backblaze_cfg.get("region", "us-east-005"))
    access_key = os.getenv(
        "BACKBLAZE_ACCESS_KEY_ID", backblaze_cfg.get("access_key_id")
    )
    secret_key = os.getenv(
        "BACKBLAZE_SECRET_ACCESS_KEY", backblaze_cfg.get("secret_access_key")
    )
    bucket_name = os.getenv("BACKBLAZE_BUCKET", backblaze_cfg.get("bucket"))
    if not all([access_key, secret_key]):
        print("Missing Backblaze credentials (env or config)")
        raise SystemExit(1)
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{endpoint}",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
        region_name=region,
    )
    return s3, bucket_name, endpoint


def presign_url(s3: Any, bucket: str, key: str, expiration_seconds: int) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expiration_seconds,
    )


def friendly_public_url(endpoint: str, bucket: str, key: str) -> Optional[str]:
    try:
        cluster_id = endpoint.split(".")[1].split("-")[-1]
        friendly_domain = f"f{cluster_id}.backblazeb2.com"
        return f"https://{friendly_domain}/file/{bucket}/{key}"
    except Exception:
        return None


def upload_file(
    s3: Any, bucket: str, local_file, object_key: str, dry_run: bool = False
) -> None:
    if dry_run:
        print(f"[dry-run] Upload {local_file} -> s3://{bucket}/{object_key}")
        return
    with open(local_file, "rb") as fh:
        s3.put_object(Bucket=bucket, Key=object_key, Body=fh)
    print(
        f"Upload: {getattr(local_file, 'name', str(local_file))} -> s3://{bucket}/{object_key}"
    )


def list_buckets(s3: Any) -> List[str]:
    try:
        resp = s3.list_buckets()
        names = [b.get("Name", "") for b in resp.get("Buckets", [])]
        return [n for n in names if n]
    except Exception as err:
        print(f"Failed to list buckets: {err}")
        return []


def _build_public_read_policy(bucket_name: str) -> Dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicReadGetObject",
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
            }
        ],
    }


def set_bucket_visibility(s3: Any, bucket_name: str, public: bool) -> None:
    try:
        if public:
            policy = _build_public_read_policy(bucket_name)
            s3.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
            print(f"Bucket policy applied for public read: {bucket_name}")
        else:
            try:
                s3.delete_bucket_policy(Bucket=bucket_name)
                print(f"Bucket policy removed (bucket is private): {bucket_name}")
            except Exception:
                print(f"Bucket already private or no policy set: {bucket_name}")
    except Exception as err:
        print(f"Failed to set bucket visibility for '{bucket_name}': {err}")


def ensure_bucket_exists(
    s3: Any, bucket_name: str, region: Optional[str] = None, public: bool = False
) -> bool:
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"Bucket already exists: {bucket_name}")
        return False
    except ClientError as err:
        status_code = int(
            err.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        )
        code_str = (err.response.get("Error", {}) or {}).get("Code", "")
        allowed = status_code in (301, 404, 400) or code_str in (
            "NoSuchBucket",
            "NotFound",
        )
        if not allowed:
            print(
                f"Error checking bucket '{bucket_name}': "
                f'"{code_str or status_code}"'
            )
            return False
    try:
        create_params: Dict[str, Any] = {"Bucket": bucket_name}
        if region:
            create_params["CreateBucketConfiguration"] = {
                "LocationConstraint": region,
            }
        create_params["ACL"] = "public-read" if public else "private"
        s3.create_bucket(**create_params)
        print(f"Bucket created: {bucket_name}")
        try:
            names = [b for b in (list_buckets(s3) or [])]
            if bucket_name not in names:
                print(
                    "Warning: Bucket did not appear in listing immediately. "
                    "Try --list-buckets after a moment."
                )
        except Exception:
            pass
        return True
    except Exception as err:
        print(f"Failed to create bucket '{bucket_name}': {err}")
        return False
