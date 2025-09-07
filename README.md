## Backblaze S3 Backup Orchestrator

A configurable backup orchestrator for Backblaze B2 S3-compatible storage. It reads a TOML config file defining jobs, bundles artifacts (files, directories, database dumps, or command output), uploads them to Backblaze, and enforces retention policies.

### Key Features
- Multiple job types: file, directory, postgres, mysql, command
- Per-job or default prefixes and buckets
- Optional compression to .tar.gz with snake_case and date suffix
- Presigned URL generation
- Retention policy per job: keep last N and/or delete older than X days
- Environment placeholders in TOML via ENV_* and .env loading
- Utilities: list buckets, create bucket

## Requirements
- Python 3.8+ (Python 3.11+ recommended)
- For Python < 3.11, install `tomli` to parse TOML
- Backblaze B2 account and S3-compatible credentials
- External tools when using DB jobs:
  - Postgres: `pg_dump`
  - MySQL: `mysqldump`

### Python Dependencies
Install with pip:
```bash
pip install boto3 botocore python-dotenv tomli invoke
```
For Python 3.11+, `tomli` is optional.

## Configuration
Create a TOML file, for example `config.toml`:
```toml
[backblaze]
endpoint = "s3.us-east-005.backblazeb2.com"
region = "us-east-005"
access_key_id = "ENV_B2_KEY_ID"
secret_access_key = "ENV_B2_SECRET"

[defaults]
prefix = "backups"
presign_expiration = 3600

[defaults.retention]
max_keep = 7
max_age_days = 30

dot_env = ".env"                  # optional
dot_envs = ["secrets.env"]        # optional

[[jobs]]
name = "site-www"
type = "directory"
source = "/var/www/html"
exclude = ["**/node_modules/**", "**/.git/**"]
bucket = "bucket-website"
archive_name_snake_date = true

[[jobs]]
name = "configs"
type = "file"
source = ["/etc/nginx/nginx.conf", "/etc/cron.d/backup"]
compress = true
archive_name_snake_date = true
archive_name = "server_configs"

[[jobs]]
name = "db-main"
type = "postgres"
host = "127.0.0.1"
port = 5432
user = "postgres"
password = "ENV_DB_PASSWORD"
database = "app_prod"
bucket = "bucket-databases"
```

### Environment placeholders and .env
- Any string exactly equal to `ENV_SOME_NAME` is resolved to the value of environment variable `SOME_NAME`.
- A `.env` in the same directory as the TOML is loaded automatically if present.
- You can also list additional files via `dot_env` or `dot_envs` in the TOML. Paths are resolved relative to the TOML file.
- `.env` loading does not override variables already set in the environment.
- If a placeholder cannot be resolved, a warning is printed and the placeholder remains as-is.

## Usage
All commands run from the project root, using `main.py`.

### List configured jobs
```bash
python3 main.py --config config.toml --list
```

### Run all jobs
```bash
python3 main.py --config config.toml
```

### Run a subset of jobs
```bash
python3 main.py --config config.toml --jobs site-www,db-main
```

### Dry-run (no uploads, no deletions)
```bash
python3 main.py --config config.toml --dry-run
```

### Retention only
```bash
python3 main.py --config config.toml --retention-only
```

### List buckets
```bash
python3 main.py --config config.toml --list-buckets
```

### Create a bucket
```bash
# explicit name
python3 main.py --config config.toml --create-bucket --bucket-name my-new-bucket

# or set backblaze.bucket in TOML and run
python3 main.py --config config.toml --create-bucket

# make it public at creation time
python3 main.py --config config.toml --create-bucket --bucket-name public-bucket --public
```

### Extended help
```bash
python3 main.py --help-extended
```

## Command Reference
- --config/-c: path to the TOML config file
- --jobs/-j: comma-separated list of job names to run
- --dry-run: simulate without uploading or deleting
- --list: list jobs from the config and exit
- --retention-only: apply retention only and exit
- --list-buckets: list buckets for the current credentials
- --create-bucket: create a bucket and exit
- --bucket-name: bucket name to create (used with --create-bucket)
- --public: when creating a bucket, set public read policy
- --help-extended: show extended help and exit

## Job Types
Common fields per job:
- name: unique identifier
- type: one of file, directory, postgres, mysql, command
- bucket: bucket for uploads (required if no default bucket is provided via env)
- prefix: logical prefix under the bucket; defaults to `defaults.prefix`
- presign_expiration: seconds for presigned URL validity
- retention: `{ max_keep, max_age_days }` per job
- archive_name_snake_date: if true, compressed archives are named in snake_case with a date suffix
- archive_name: optional base name override before snake_case/date

#### file
- source: string or list of file paths
- compress: boolean (if true, each file is compressed to tar.gz)

#### directory
- source: directory path
- exclude: list of glob patterns to skip
- Always compressed to a single tar.gz

#### postgres
- host, port, user, password, database
- Uses `pg_dump` and stores SQL output

#### mysql
- host, port, user, password, database
- Uses `mysqldump` and stores SQL output

#### command
- command: shell command to run; stdout is captured and uploaded

### Minimal Examples per Job Type
```toml
[[jobs]]
name = "single-file"
type = "file"
source = "/etc/hosts"
compress = true
bucket = "bucket-backups"
archive_name_snake_date = true

[[jobs]]
name = "site-content"
type = "directory"
source = "/var/www/html"
exclude = ["**/.git/**", "**/node_modules/**"]
bucket = "bucket-website"

[[jobs]]
name = "db-prod"
type = "postgres"
host = "127.0.0.1"
port = 5432
user = "postgres"
password = "ENV_PG_PASS"
database = "app_prod"
bucket = "bucket-databases"

[[jobs]]
name = "mysql-dump"
type = "mysql"
host = "127.0.0.1"
port = 3306
user = "root"
password = "ENV_MYSQL_PASS"
database = "app_prod"
bucket = "bucket-databases"

[[jobs]]
name = "sysinfo"
type = "command"
command = "uname -a && df -h"
bucket = "bucket-logs"
```

## Archive Naming
- If `archive_name_snake_date = true`, compressed archives are named as `<base>_YYYYMMDD.tar.gz` where `<base>` is `archive_name` or the source name converted to snake_case.
- If `archive_name_snake_date = false`, archives are named `<base>.tar.gz`.

## Retention Policy
Applied per `prefix/job_name/` in the bucket after uploads:
- `max_keep`: keep only the most recent N objects under that prefix
- `max_age_days`: delete objects older than X days
Both can be used together. No action if neither is set.

## Buckets
- Buckets can be specified per job. If you do not set a global bucket via environment, each job must define `bucket`.
- Utilities:
  - `--list-buckets` lists available buckets for the current credentials
  - `--create-bucket` creates a bucket by name, with region taken from env or TOML
  - `--public` can be combined with `--create-bucket` to set a public read policy

### Bucket Visibility
- Private (default): only authenticated requests can access objects.
- Public (with `--public`): applies a bucket policy that allows anonymous `GET` to `s3://bucket/key`.
- If your bucket is public, generated public URLs may also work via Backblaze friendly domain format.

## Security Notes
- Avoid committing secrets to the repository. Use `.env` files locally or environment variables.
- Limit IAM credentials to the minimal permissions needed:
  - `s3:ListBuckets` for listing
  - `s3:CreateBucket` for creation
  - `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket`, `s3:GetObject` for backups

## Scheduling
Use your system scheduler, for example cron:
```cron
# Every day at 01:30
30 1 * * * cd /path/to/project && /usr/bin/python3 main.py --config config.toml >> /var/log/b2-backup.log 2>&1
```

### Built-in scheduler
- Add `every` to jobs (e.g., "15m", "1h", 300):
```toml
[[jobs]]
name = "iw4x-docker"
type = "directory"
source = "/srv/iw4x-docker"
exclude = ["**/node_modules/**", "**/.git/**", "**/volumes/**"]
bucket = "iw4x-server"
archive_name_snake_date = true
every = "1h"
```
- Run scheduler:
```bash
python3 main.py --config config.toml --schedule
```

## Development & Building

### Using Invoke Tasks
This project uses [Invoke](https://www.pyinvoke.org/) for task automation. Install it first:
```bash
pip install invoke
```

Available tasks:
```bash
inv -l
```

### Building Binaries
Build locally:
```bash
inv build-bin
```

Build in Docker container (recommended for distribution):
```bash
inv build-bin-debian
```

The Docker build uses a custom image with all dependencies pre-installed for faster builds.

### Packaging (.deb/.rpm)
This repository includes packaging using `fpm`.

Requirements:
- Ruby fpm or Go fpm (ruby gem `fpm` is common on Debian/Ubuntu)

Build packages:
```bash
inv build-deb      # produces dist/back2blaze_VERSION_*.deb
inv build-rpm      # produces dist/back2blaze-VERSION-1.x86_64.rpm
```

What packages do:
- Install app into `/opt/back2blaze` and config into `/etc/back2blaze`
- If compiled binary present, use it at `/opt/back2blaze/bin/back2blaze`
- Otherwise, create a Python venv and install requirements
- Install a systemd unit `back2blaze.service`

Enable service after install:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now back2blaze.service
sudo systemctl status back2blaze.service
```

## Docker Build Environment

This project maintains a custom Docker image with all build dependencies pre-installed:

- **Image**: `ghcr.io/tarcisiomiranda/bkp-2-backblaze/build-env:latest`
- **Base**: `astral/uv:0.8.15-python3.11-bookworm-slim`
- **Includes**: binutils, PyInstaller, optimized build environment

The image is automatically built and pushed to GitHub Container Registry when the Dockerfile changes.

## Troubleshooting
- Missing `pg_dump` or `mysqldump`: install the corresponding database client tools.
- Permission errors on bucket operations: verify credentials and IAM permissions for the region and endpoint.
- Placeholder not resolved: ensure the variable exists in the environment or in loaded `.env` files.
