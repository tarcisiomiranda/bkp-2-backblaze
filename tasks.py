from pathlib import Path
from invoke import task
import botocore
import shutil
import os
import json
from collections import Counter
from dotenv import load_dotenv


load_dotenv()


APP_NAME = "back2blaze"
VERSION = os.getenv("VERSION", "0.1.0")
BUILD_DIR = Path(os.getenv("BUILD_DIR", "dist"))
PREFIX = Path(f"/opt/{APP_NAME}")
BIN_NAME = APP_NAME


def _echo(ctx, cmd: str) -> None:
    ctx.run(cmd, echo=True)


def _analyze_security_reports(reports_dir: Path) -> bool:
    """Analyze security reports and display summary. Returns True if no critical issues found."""
    has_critical_issues = False

    # Analyze Bandit JSON
    bandit_json = reports_dir / "bandit.json"
    if bandit_json.exists():
        print("\n📊 Bandit Security Analysis:")
        try:
            with open(bandit_json, "r", encoding="utf-8") as f:
                bandit_data = json.load(f)

            results = bandit_data.get("results", [])
            if results:
                severities = [r.get("issue_severity", "UNDEFINED") for r in results]
                severity_counts = Counter(severities)
                total = len(results)

                print(f"   🔍 Total findings: {total}")
                for severity in ["HIGH", "MEDIUM", "LOW"]:
                    count = severity_counts.get(severity, 0)
                    if count > 0:
                        emoji = (
                            "🔴"
                            if severity == "HIGH"
                            else "🟡" if severity == "MEDIUM" else "🔵"
                        )
                        print(f"   {emoji} {severity.capitalize()}: {count}")
                        if severity == "HIGH":
                            has_critical_issues = True

                # Show top issues by test_name
                test_counts = Counter([r.get("test_name", "unknown") for r in results])
                if test_counts:
                    print("   📋 Top issues:")
                    for test_name, count in test_counts.most_common(5):
                        print(f"      • {test_name}: {count}")
            else:
                print("   ✅ No security issues found!")

        except Exception as e:
            print(f"   ⚠️ Error analyzing Bandit JSON: {e}")

    # Analyze Gitleaks JSON
    gitleaks_json = reports_dir / "gitleaks.json"
    if gitleaks_json.exists():
        print("\n🔑 Gitleaks Secret Scanning:")
        try:
            with open(gitleaks_json, "r", encoding="utf-8") as f:
                gitleaks_data = json.load(f)

            if isinstance(gitleaks_data, list) and gitleaks_data:
                print(f"   🚨 Found {len(gitleaks_data)} potential secrets!")

                # Group by rule type
                rule_counts = Counter(
                    [item.get("RuleID", "unknown") for item in gitleaks_data]
                )
                for rule_id, count in rule_counts.most_common():
                    print(f"      • {rule_id}: {count}")

                has_critical_issues = True
            else:
                print("   ✅ No secrets detected!")

        except Exception as e:
            print(f"   ⚠️ Error analyzing Gitleaks JSON: {e}")

    print("\n" + "=" * 50)
    if has_critical_issues:
        print("❌ SECURITY SCAN FAILED - Critical issues found!")
        print("🔧 Review the reports in dist/security/ for details")
    else:
        print("✅ SECURITY SCAN PASSED - No critical issues found!")
    print("=" * 50)

    return not has_critical_issues


def _docker_login(ctx) -> bool:
    github_token = os.getenv("GITHUB_TOKEN")
    github_actor = os.getenv("GITHUB_ACTOR")

    if not github_token or not github_actor:
        print("❌ GITHUB_TOKEN or GITHUB_ACTOR not found in .env")
        print("💡 Add the variables to your .env file:")
        print("   GITHUB_TOKEN=ghp_xxxxxxxxxx")
        print("   GITHUB_ACTOR=your_username")
        return False

    try:
        print(f"🔐 Logging in as {github_actor}...")
        ctx.run(
            f'echo "{github_token}" | docker login ghcr.io -u {github_actor} --password-stdin',
            hide="stdout",
        )
        print("✅ Login successful!")
        return True
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return False


@task
def clean(ctx):
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)


@task(help={"tag": "Tag for the image (default: latest)"})
def build_docker_images(ctx, tag: str = "latest"):
    images = [
        ("Dockerfile", f"back2blaze-build-env:{tag}"),
        ("Dockerfile.deb", f"back2blaze-deb-builder:{tag}"),
        ("Dockerfile.rpm", f"back2blaze-rpm-builder:{tag}"),
    ]

    for dockerfile, image_name in images:
        print(f"Building {image_name}...")
        _echo(ctx, f"docker build -f {dockerfile} -t {image_name} .")


@task(help={"tag": "Tag for the image (default: latest)"})
def build_and_push_images(ctx, tag: str = "latest"):
    registry = "ghcr.io/tarcisiomiranda/bkp-2-backblaze"

    if not _docker_login(ctx):
        return

    images = [
        ("Dockerfile", "build-env"),
        ("Dockerfile.deb", "deb-builder"),
        ("Dockerfile.rpm", "rpm-builder"),
    ]

    for dockerfile, image_name in images:
        local_tag = f"back2blaze-{image_name}:{tag}"
        remote_tag = f"{registry}/{image_name}:{tag}"

        print(f"🔨 Building {local_tag}...")
        _echo(ctx, f"docker build -f {dockerfile} -t {local_tag} -t {remote_tag} .")

        print(f"📤 Pushing {remote_tag}...")
        _echo(ctx, f"docker push {remote_tag}")

    print("✅ All images have been pushed successfully!")


@task(
    help={
        "image": "Image name (build-env, deb-builder, rpm-builder)",
        "tag": "Tag (default: latest)",
    }
)
def build_and_push_single_image(ctx, image: str, tag: str = "latest"):
    registry = "ghcr.io/tarcisiomiranda/bkp-2-backblaze"

    if not _docker_login(ctx):
        return

    image_map = {
        "build-env": "Dockerfile",
        "deb-builder": "Dockerfile.deb",
        "rpm-builder": "Dockerfile.rpm",
    }

    if image not in image_map:
        print(f"❌ Image '{image}' not found. Use: {', '.join(image_map.keys())}")
        return

    dockerfile = image_map[image]
    local_tag = f"back2blaze-{image}:{tag}"
    remote_tag = f"{registry}/{image}:{tag}"

    print(f"🔨 Building {local_tag}...")
    _echo(ctx, f"docker build -f {dockerfile} -t {local_tag} -t {remote_tag} .")

    print(f"📤 Pushing {remote_tag}...")
    _echo(ctx, f"docker push {remote_tag}")

    print(f"✅ Image {remote_tag} pushed successfully!")


@task
def docker_login(ctx):
    _docker_login(ctx)


@task(help={"tag": "Version tag (e.g., v1.0.0)"})
def build_release(ctx, tag: str = None):
    if not tag:
        try:
            last_tag = ctx.run(
                "git tag --sort=-v:refname | head -n1", hide=True
            ).stdout.strip()
            if not last_tag:
                last_tag = "v0.0.0"
            print(f"📋 Last tag: {last_tag}")

            version_parts = last_tag.lstrip("v").split(".")
            if len(version_parts) == 3:
                a, b, c = map(int, version_parts)
                tag = f"v{a}.{b}.{c+1}"
            else:
                tag = "v0.1.0"
        except:
            tag = "v0.1.0"

    print(f"🏗️  Building for release {tag}")

    print("🧹 Cleaning up previous builds...")
    clean(ctx)

    print("🔨 Building binary...")
    build_bin_debian(ctx)

    print("📦 Building .deb package...")
    build_deb(ctx, version=tag.lstrip("v"))

    print("📦 Building .rpm package...")
    build_rpm(ctx, version=tag.lstrip("v"))

    print(f"✅ Full build for {tag} finished!")
    print("📁 Created artifacts:")
    ctx.run("ls -la dist/back2blaze dist/*.deb dist/*.rpm", hide=False)


@task(help={"image": "Docker image to use for linting"})
def lint_packages(
    ctx, image: str = "ghcr.io/tarcisiomiranda/bkp-2-backblaze/build-env:latest"
):
    """Lint .deb and .rpm packages using lintian and rpmlint inside a Docker container."""
    print("🔍 Linting generated packages...")

    deb_files = list(BUILD_DIR.glob("*.deb"))
    rpm_files = list(BUILD_DIR.glob("*.rpm"))

    success = True
    cwd = os.getcwd()

    if deb_files:
        deb_filename = deb_files[0].name
        print(f"🕵️  Running lintian on {deb_filename}...")
        try:
            cmd = f"docker run --rm -v {cwd}:/work -w /work {image} lintian --info --display-info --show-overrides dist/{deb_filename}"
            ctx.run(cmd, pty=True, warn=True)
        except Exception as e:
            print(f"⚠️ Lintian check failed: {e}")
            success = False
    else:
        print("🟡 No .deb package found to lint.")

    if rpm_files:
        rpm_filename = rpm_files[0].name
        print(f"🕵️  Running rpmlint on {rpm_filename}...")
        try:
            cmd = f"docker run --rm -v {cwd}:/work -w /work {image} rpmlint dist/{rpm_filename}"
            ctx.run(cmd, pty=True, warn=True)
        except Exception as e:
            print(f"⚠️ rpmlint check failed: {e}")
            success = False
    else:
        print("🟡 No .rpm package found to lint.")

    if success:
        print("✅ Package linting completed.")
    else:
        print("❌ Package linting finished with warnings or errors.")


@task(help={"image": "Docker image to use for security scans"})
def security_scan(
    ctx, image: str = "ghcr.io/tarcisiomiranda/bkp-2-backblaze/build-env:latest"
):
    """Run security scans (Bandit and Gitleaks) inside a Docker container."""
    print("\n🛡️  Running security scans...")
    cwd = os.getcwd()

    reports_dir = BUILD_DIR / "security"
    reports_dir.mkdir(parents=True, exist_ok=True)

    gitleaks_json = reports_dir / "gitleaks.json"
    gitleaks_sarif = reports_dir / "gitleaks.sarif"

    print("🔎 Running Bandit security analysis...")
    bandit_json_path = reports_dir / "bandit.json"
    bandit_image = "ghcr.io/pycqa/bandit/bandit"
    bandit_config = "bandit.yaml" if Path("bandit.yaml").exists() else ""
    config_arg = f"-c /src/{bandit_config}" if bandit_config else ""

    try:
        # We will fail on HIGH severity issues, but still generate the report.
        # Bandit exits with 1 if issues are found, so we use warn=True and check the report.
        cmd = (
            f"docker run --rm -v '{cwd}:/src' {bandit_image} "
            f"-r {config_arg} -f json -o /src/{bandit_json_path} /src"
        )
        ctx.run(cmd, pty=True, warn=True)

        if bandit_json_path.exists():
            with open(bandit_json_path, "r") as f:
                report = json.load(f)
            high_severity_issues = [
                res
                for res in report.get("results", [])
                if res.get("issue_severity") == "HIGH"
            ]
            if high_severity_issues:
                print("🔴 High severity issues found by Bandit. Failing scan...")
                raise SystemExit("Bandit found high severity issues.")
        else:
            print(f"⚠️ Bandit report not generated at {bandit_json_path}")

    except Exception as e:
        print(f"❌ Bandit scan failed or found issues: {e}")
        raise SystemExit("Bandit scan failed.")

    print("\n🔑 Running gitleaks for secret scanning...")
    try:
        gitleaks_base = "git config --global --add safe.directory /work && gitleaks detect --source ."
        gl_json_cmd = f"docker run --rm -v '{cwd}:/work' -w /work {image} bash -lc '{gitleaks_base} --report-format json --report-path dist/security/gitleaks.json'"
        ctx.run(gl_json_cmd, pty=True, warn=True)
        gl_sarif_cmd = f"docker run --rm -v '{cwd}:/work' -w /work {image} bash -lc '{gitleaks_base} --report-format sarif --report-path dist/security/gitleaks.sarif'"
        ctx.run(gl_sarif_cmd, pty=True, warn=True)
        print(f"📄 Gitleaks reports saved to: {gitleaks_json} and {gitleaks_sarif}")
    except Exception as e:
        print(f"⚠️ Gitleaks scan failed or found issues: {e}")

    # Analyze and display results
    scan_passed = _analyze_security_reports(reports_dir)

    if not scan_passed:
        raise SystemExit("Security scan failed - critical issues found!")

    print("✅ Security scans completed successfully.")


@task
def security_summary(ctx):
    """Display summary of security scan results from dist/security/"""
    reports_dir = BUILD_DIR / "security"

    if not reports_dir.exists():
        print("❌ No security reports found. Run 'inv security-scan' first.")
        return

    print("📊 Security Scan Summary")
    print("=" * 50)

    scan_passed = _analyze_security_reports(reports_dir)

    if not scan_passed:
        raise SystemExit("Critical security issues found!")


@task
def test_packages(ctx):
    """Test .deb and .rpm packages in clean Docker containers."""
    print("🧪 Testing generated packages in Docker containers...")

    deb_files = list(BUILD_DIR.glob("*.deb"))
    rpm_files = list(BUILD_DIR.glob("*.rpm"))

    success = True

    if deb_files:
        deb_path = deb_files[0]
        deb_filename = deb_path.name
        print(f"📦 Testing Debian package: {deb_filename}")

        test_script = f"""
set -euxo pipefail
apt-get update
apt-get install -y ./{deb_filename}
/opt/back2blaze/bin/back2blaze --help
"""
        container_name = f"test-deb-{os.urandom(4).hex()}"
        try:
            ctx.run(
                f"docker run -d --name {container_name} debian:bookworm-slim sleep 3600",
                hide=True,
            )
            ctx.run(f"docker cp {deb_path} {container_name}:/{deb_filename}")
            ctx.run(f"docker exec {container_name} bash -c '{test_script}'")
            print("✅ Debian package test passed.")
        except Exception as e:
            print(f"❌ Debian package test failed: {e}")
            success = False
        finally:
            ctx.run(f"docker rm -f {container_name}", hide=True)
    else:
        print("🟡 No .deb package found to test.")

    if rpm_files:
        rpm_path = rpm_files[0]
        rpm_filename = rpm_path.name
        print(f"📦 Testing RPM package: {rpm_filename}")

        test_script = f"""
set -euxo pipefail
dnf install -y ./{rpm_filename}
/opt/back2blaze/bin/back2blaze --help
"""
        container_name = f"test-rpm-{os.urandom(4).hex()}"
        try:
            ctx.run(
                f"docker run -d --name {container_name} fedora:latest sleep 3600",
                hide=True,
            )
            ctx.run(f"docker cp {rpm_path} {container_name}:/{rpm_filename}")
            ctx.run(f"docker exec {container_name} bash -c '{test_script}'")
            print("✅ RPM package test passed.")
        except Exception as e:
            print(f"❌ RPM package test failed: {e}")
            success = False
        finally:
            ctx.run(f"docker rm -f {container_name}", hide=True)
    else:
        print("🟡 No .rpm package found to test.")

    if not success:
        raise SystemExit("One or more package tests failed.")
    else:
        print("✅ All package tests passed successfully.")


@task(help={"tag": "Version tag to create a release for"})
def create_release(ctx, tag: str):
    import requests
    import os
    from pathlib import Path

    binary_path = Path("dist/back2blaze")
    deb_files = list(Path("dist").glob("*.deb"))
    rpm_files = list(Path("dist").glob("*.rpm"))

    if not binary_path.exists():
        print("❌ Binary not found. Run 'inv build-release' first.")
        return

    if not deb_files:
        print("❌ .deb package not found. Run 'inv build-release' first.")
        return

    if not rpm_files:
        print("❌ .rpm package not found. Run 'inv build-release' first.")
        return

    deb_path = deb_files[0]
    rpm_path = rpm_files[0]

    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPOSITORY")

    if not github_token:
        print("❌ GITHUB_TOKEN not found in .env")
        return

    if not github_repo:
        try:
            remote_url = ctx.run("git remote get-url origin", hide=True).stdout.strip()
            if "github.com" in remote_url:
                if remote_url.startswith("git@github.com:"):
                    github_repo = remote_url.replace("git@github.com:", "").replace(
                        ".git", ""
                    )
                elif "github.com/" in remote_url:
                    github_repo = remote_url.split("github.com/")[1].replace(".git", "")
        except:
            pass

    if not github_repo:
        print(
            "❌ GITHUB_REPOSITORY not found. Define it in .env or configure the git remote."
        )
        return

    print(f"🚀 Creating release {tag} for {github_repo}")

    api_url = f"https://api.github.com/repos/{github_repo}/releases"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    release_data = {
        "tag_name": tag,
        "name": f"Release {tag}",
        "draft": False,
        "prerelease": False,
        "body": f"""## Back2Blaze {tag}

### 📦 Available artifacts:
- `back2blaze` - Standalone executable binary
- `{deb_path.name}` - Debian/Ubuntu package
- `{rpm_path.name}` - RedHat/CentOS/Fedora package

### 🚀 Installation:

**Debian/Ubuntu:**
```bash
wget https://github.com/{github_repo}/releases/download/{tag}/{deb_path.name}
sudo dpkg -i {deb_path.name}
```

**RedHat/CentOS/Fedora:**
```bash
wget https://github.com/{github_repo}/releases/download/{tag}/{rpm_path.name}
sudo rpm -i {rpm_path.name}
```

**Standalone binary:**
```bash
wget https://github.com/{github_repo}/releases/download/{tag}/back2blaze
chmod +x back2blaze
./back2blaze --help
```
""",
    }

    print("📝 Creating release...")
    response = requests.post(api_url, headers=headers, json=release_data)

    if response.status_code == 422:
        print("📋 Release already exists, fetching info...")
        response = requests.get(f"{api_url}/tags/{tag}", headers=headers)
    elif response.status_code != 201:
        print(f"❌ Error creating release: {response.status_code}")
        print(response.text)
        return

    if response.status_code not in [200, 201]:
        print(f"❌ Error fetching release info: {response.status_code}")
        print(response.text)
        return

    release_info = response.json()
    release_id = release_info["id"]
    upload_url_template = release_info["upload_url"]

    print(f"✅ Release created/found: ID {release_id}")

    artifacts = [
        (binary_path, "back2blaze", "application/octet-stream"),
        (deb_path, deb_path.name, "application/vnd.debian.binary-package"),
        (rpm_path, rpm_path.name, "application/x-rpm"),
    ]

    for file_path, file_name, content_type in artifacts:
        print(f"📤 Uploading {file_name}...")

        upload_url = upload_url_template.replace("{?name,label}", f"?name={file_name}")

        with open(file_path, "rb") as f:
            upload_headers = {
                "Authorization": f"Bearer {github_token}",
                "Content-Type": content_type,
                "Accept": "application/vnd.github+json",
            }

            upload_response = requests.post(
                upload_url, headers=upload_headers, data=f.read()
            )

            if upload_response.status_code == 201:
                asset_info = upload_response.json()
                print(f"✅ {file_name} uploaded successfully!")
                print(f"   📎 URL: {asset_info['browser_download_url']}")
            else:
                print(f"❌ Error uploading {file_name}: {upload_response.status_code}")
                print(upload_response.text)

    print(f"🎉 Release {tag} created successfully!")
    print(f"🔗 URL: https://github.com/{github_repo}/releases/tag/{tag}")


@task(help={"tag": "Version tag (optional, will be auto-incremented if not provided)"})
def release(ctx, tag: str = None):
    """Full workflow: build + lint + scan + test + create release + upload artifacts"""
    print("🚀 Starting release workflow...")

    build_release(ctx, tag)
    lint_packages(ctx)
    security_scan(ctx)
    test_packages(ctx)

    if not tag:
        try:
            last_tag = ctx.run(
                "git tag --sort=-v:refname | head -n1", hide=True
            ).stdout.strip()
            if not last_tag:
                last_tag = "v0.0.0"
            version_parts = last_tag.lstrip("v").split(".")
            if len(version_parts) == 3:
                a, b, c = map(int, version_parts)
                tag = f"v{a}.{b}.{c+1}"
            else:
                tag = "v0.1.0"
        except:
            tag = "v0.1.0"

    try:
        ctx.run(f"git tag {tag}", hide=True)
        print(f"🏷️  Tag {tag} created")

        ctx.run(f"git push origin {tag}", hide=True)
        print(f"📤 Tag {tag} pushed to repository")
    except:
        print(f"🏷️  Tag {tag} already exists")

    create_release(ctx, tag)


@task
def pull_images(ctx):
    registry = "ghcr.io/tarcisiomiranda/bkp-2-backblaze"

    images = ["build-env", "deb-builder", "rpm-builder"]

    for image in images:
        remote_tag = f"{registry}/{image}:latest"
        print(f"📥 Pulling {remote_tag}...")
        _echo(ctx, f"docker pull {remote_tag}")

    print("✅ All images have been downloaded!")


@task(help={"tag": "Tag for the image (default: latest)"})
def build_deb_local(ctx, version: str = VERSION, tag: str = "latest"):
    return build_deb(ctx, version=version, image=f"back2blaze-deb-builder:{tag}")


@task(help={"tag": "Tag for the image (default: latest)"})
def build_rpm_local(ctx, version: str = VERSION, tag: str = "latest"):
    return build_rpm(ctx, version=version, image=f"back2blaze-rpm-builder:{tag}")


@task(
    help={
        "distdir": "Output directory (default: dist)",
    }
)
def build_bin(ctx, distdir: str = "dist"):
    botocore_path = botocore.__path__[0]
    data_path = Path(botocore_path) / "data"
    add_data_arg = f'--add-data "{data_path}{os.pathsep}botocore/data"'
    _echo(
        ctx,
        f"python3 -m PyInstaller -F -n {BIN_NAME} main.py --distpath {distdir} {add_data_arg}",
    )


@task(
    help={
        "image": "Custom Docker image (default: ghcr.io/tarcisiomiranda/bkp-2-backblaze/build-env:latest)",
        "distdir": "Output directory on host (default: dist)",
    }
)
def build_bin_debian(
    ctx,
    image: str = "ghcr.io/tarcisiomiranda/bkp-2-backblaze/build-env:latest",
    distdir: str = "dist",
):
    cwd = os.getcwd()
    uid = os.getuid()
    gid = os.getgid()

    script_content = f"""#!/bin/bash
set -euo pipefail
rm -rf /tmp/uv-cache/* || true
TARGET_DIR=/tmp/packages
mkdir -p $TARGET_DIR
uv pip install --target $TARGET_DIR -r requirements.txt
export PYTHONPATH=$TARGET_DIR
BOTOCORE_PATH=$(python -c 'import botocore; print(botocore.__path__[0])')
python -m PyInstaller -F -n {BIN_NAME} main.py --distpath {distdir} --add-data "$BOTOCORE_PATH/data:botocore/data"
"""

    script_path = Path("build_script.sh")
    script_path.write_text(script_content)
    script_path.chmod(0o755)

    try:
        cmd = f"docker run --rm -v {cwd}:/work -w /work {image} ./build_script.sh"
        _echo(ctx, cmd)
    finally:
        if script_path.exists():
            script_path.unlink()


@task
def prep(ctx):
    pkg_dir = BUILD_DIR / f"{APP_NAME}-pkg"
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)

    (pkg_dir / APP_NAME).mkdir(parents=True, exist_ok=True)
    (pkg_dir / "etc" / APP_NAME).mkdir(parents=True, exist_ok=True)
    (pkg_dir / "lib" / "systemd" / "system").mkdir(parents=True, exist_ok=True)

    binary_path = BUILD_DIR / BIN_NAME
    if binary_path.exists() and binary_path.is_file():
        (pkg_dir / APP_NAME / "bin").mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary_path, pkg_dir / APP_NAME / "bin" / BIN_NAME)
    else:
        shutil.copy2("main.py", pkg_dir / APP_NAME / "main.py")
        if Path("requirements.txt").exists():
            shutil.copy2("requirements.txt", pkg_dir / APP_NAME / "requirements.txt")
        if Path("back2blaze").is_dir():
            shutil.copytree(
                "back2blaze", pkg_dir / APP_NAME / "back2blaze", dirs_exist_ok=True
            )
        if Path("packaging/back2blaze-wrapper.sh").exists():
            shutil.copy2(
                "packaging/back2blaze-wrapper.sh",
                pkg_dir / APP_NAME / "back2blaze-wrapper.sh",
            )
    shutil.copy2(
        "packaging/back2blaze.service",
        pkg_dir / "lib" / "systemd" / "system" / "back2blaze.service",
    )
    if Path("config.toml").exists():
        shutil.copy2("config.toml", pkg_dir / "etc" / APP_NAME / "config.toml")
    if Path("packaging/back2blaze.env").exists():
        shutil.copy2(
            "packaging/back2blaze.env", pkg_dir / "etc" / APP_NAME / ".env"
        )


@task(
    pre=[prep],
    help={
        "version": "Package version (default: env VERSION or 0.1.0)",
        "image": "Docker image for build (default: ghcr.io/tarcisiomiranda/bkp-2-backblaze/deb-builder:latest)",
    },
)
def build_deb(
    ctx,
    version: str = VERSION,
    image: str = "ghcr.io/tarcisiomiranda/bkp-2-backblaze/deb-builder:latest",
):
    pkg_dir = BUILD_DIR / f"{APP_NAME}-pkg"
    cwd = os.getcwd()

    script_content = f"""#!/bin/bash
set -euo pipefail
cd /work
fpm -s dir -t deb -n {APP_NAME} -v {version} \\
    --after-install packaging/postinstall.sh \\
    --deb-systemd packaging/back2blaze.service \\
    --description 'Backblaze S3 Backup Orchestrator' \\
    --url 'https://github.com/tarcisiomiranda/bkp-2-backblaze' \\
    --license 'MIT' \\
    --depends python3 --depends python3-venv \\
    --config-files /etc/{APP_NAME}/config.toml \\
    --config-files /etc/{APP_NAME}/.env \\
    --package-name-suffix '' \\
    dist/{APP_NAME}-pkg/{APP_NAME}/={PREFIX}/ \\
    dist/{APP_NAME}-pkg/etc/{APP_NAME}/=/etc/{APP_NAME}/ \\
    dist/{APP_NAME}-pkg/lib/systemd/system/back2blaze.service=/lib/systemd/system/back2blaze.service
mv *.deb {BUILD_DIR}/
"""

    script_path = Path("build_deb_script.sh")
    script_path.write_text(script_content)
    script_path.chmod(0o755)

    try:
        cmd = f"docker run --rm -v {cwd}:/work -w /work {image} ./build_deb_script.sh"
        _echo(ctx, cmd)
    finally:
        if script_path.exists():
            script_path.unlink()


@task(
    pre=[prep],
    help={
        "version": "Package version (default: env VERSION or 0.1.0)",
        "image": "Docker image for build (default: ghcr.io/tarcisiomiranda/bkp-2-backblaze/rpm-builder:latest)",
    },
)
def build_rpm(
    ctx,
    version: str = VERSION,
    image: str = "ghcr.io/tarcisiomiranda/bkp-2-backblaze/rpm-builder:latest",
):
    pkg_dir = BUILD_DIR / f"{APP_NAME}-pkg"
    cwd = os.getcwd()

    script_content = f"""#!/bin/bash
set -euo pipefail
cd /work
fpm -s dir -t rpm -n {APP_NAME} -v {version} \\
    --after-install packaging/postinstall.sh \\
    --description 'Backblaze S3 Backup Orchestrator' \\
    --url 'https://github.com/tarcisiomiranda/bkp-2-backblaze' \\
    --license 'MIT' \\
    --depends python3 --depends python3-venv \\
    --config-files /etc/{APP_NAME}/config.toml \\
    --config-files /etc/{APP_NAME}/.env \\
    --package-name-suffix '' \\
    dist/{APP_NAME}-pkg/{APP_NAME}/={PREFIX}/ \\
    dist/{APP_NAME}-pkg/etc/{APP_NAME}/=/etc/{APP_NAME}/ \\
    dist/{APP_NAME}-pkg/lib/systemd/system/back2blaze.service=/usr/lib/systemd/system/back2blaze.service
mv *.rpm {BUILD_DIR}/
"""

    script_path = Path("build_rpm_script.sh")
    script_path.write_text(script_content)
    script_path.chmod(0o755)

    try:
        cmd = f"docker run --rm -v {cwd}:/work -w /work {image} ./build_rpm_script.sh"
        _echo(ctx, cmd)
    finally:
        if script_path.exists():
            script_path.unlink()
