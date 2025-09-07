## Developer Guide

This document covers local builds, packaging, and development using the Invoke task system and Docker. For end-user documentation, see `README.md`.

### 1) Prerequisites

#### Essential Dependencies:
```bash
# Python and Invoke
pip install invoke python-dotenv

# Docker (for containerized builds)
# Install Docker by following the official documentation for your OS
```

#### Pre-commit Hooks (Recommended)
This project uses pre-commit to run automated checks before each commit.

To set it up:
```bash
# Install pre-commit hooks into your .git/hooks directory
pre-commit install
```

After installation, `semgrep` and `gitleaks` will run automatically on every `git commit`.

If you get a `dubious ownership` error from `gitleaks` on commit, run this command once to fix it:
```bash
git config --global --add safe.directory "$(pwd)"
```

#### Initial Setup:
```bash
# Clone the repository
git clone https://github.com/tarcisiomiranda/bkp-2-backblaze.git && \
  cd bkp-2-backblaze

# Install Python dependencies
pip install -r requirements.txt

# Configure GitHub credentials (for pushing images)
cp .env.example .env  # if it exists, or create it manually
```

Edit the `.env` file:
```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxx
GITHUB_ACTOR=your_github_username
GITHUB_REPOSITORY=your_username/bkp-2-backblaze
VERSION=0.1.0
```

### 2) Task System (Invoke)

List all available tasks:
```bash
inv -l
```

Main tasks:
- `build-bin` - Build binary locally
- `build-bin-debian` - Build binary in a Docker container
- `build-deb` - Create .deb package
- `build-rpm` - Create .rpm package
- `build-docker-images` - Build Docker images locally
- `build-and-push-images` - Build and push images to GitHub Registry
- `build-release` - Full build for release (binary + .deb + .rpm)
- `create-release` - Create a GitHub release with artifact uploads
- `release` - Full workflow: build + create release + upload
- `clean` - Clean up build files

### 3) Building the Binary

#### Local Build (requires local PyInstaller):
```bash
inv build-bin
```

#### Docker Container Build (recommended):
```bash
inv build-bin-debian
```

Verify the binary:
```bash
./dist/back2blaze --help-extended
./dist/back2blaze --config config.toml --list
```

### 4) Packaging (.deb/.rpm)

#### Generate Debian/Ubuntu package:
```bash
# First, build the binary
inv build-bin-debian

# Then, create the .deb package
inv build-deb
```

#### Generate RedHat/CentOS/Fedora package:
```bash
# First, build the binary
inv build-bin-debian

# Then, create the .rpm package
inv build-rpm
```

#### Generated artifacts:
- Binary: `dist/back2blaze`
- Debian: `dist/back2blaze_VERSION_amd64.deb`
- RPM: `dist/back2blaze-VERSION-1.x86_64.rpm`

### 5) Docker Image Management

#### Build custom images:
```bash
# Build all images locally
inv build-docker-images

# Build and push to GitHub Container Registry
inv build-and-push-images

# Build and push a specific image
inv build-and-push-single-image --image deb-builder
inv build-and-push-single-image --image rpm-builder
inv build-and-push-single-image --image build-env
```

#### Available images:
- `ghcr.io/tarcisiomiranda/bkp-2-backblaze/build-env:latest` - PyInstaller build environment
- `ghcr.io/tarcisiomiranda/bkp-2-backblaze/deb-builder:latest` - .deb package build environment
- `ghcr.io/tarcisiomiranda/bkp-2-backblaze/rpm-builder:latest` - .rpm package build environment

#### Download images:
```bash
inv pull-images
```

### 6) Development Workflow

#### Local development:
```bash
# Run directly without building
python3 main.py --config config.toml --list
python3 main.py --config config.toml --dry-run
```

#### Full build for distribution:
```bash
# 1. Build the binary
inv build-bin-debian

# 2. Create packages
inv build-deb
inv build-rpm

# 3. Check artifacts
ls -la dist/
```

#### Cleanup:
```bash
inv clean
```

### 7) Installing and Testing Packages

#### Install Debian package:
```bash
sudo dpkg -i dist/back2blaze_*.deb

# Configure
sudo nano /etc/back2blaze/config.toml

# Enable service
sudo systemctl enable --now back2blaze.service
sudo systemctl status back2blaze.service
```

#### Install RPM package:
```bash
sudo rpm -i dist/back2blaze-*.rpm

# Configure and enable just like with Debian
sudo nano /etc/back2blaze/config.toml
sudo systemctl enable --now back2blaze.service
```

#### Uninstall:
```bash
# Debian/Ubuntu
sudo systemctl disable --now back2blaze.service
sudo dpkg -r back2blaze

# RedHat/CentOS/Fedora
sudo systemctl disable --now back2blaze.service
sudo rpm -e back2blaze
```

### 8) Security Scanning

The project includes automated security scanning with Bandit and Gitleaks:

```bash
# Run security scans
inv security-scan

# View security scan summary
inv security-summary
```

**Bandit Configuration:**
Bandit is configured via `bandit.yaml` to exclude certain tests. It's used by both the `security-scan` task and the pre-commit hook.

**Reports Location:**
Security reports are saved to `dist/security/`:
- `bandit.json` - Code security analysis
- `gitleaks.json` / `gitleaks.sarif` - Secret detection

### 9) Project Structure

```
bkp-2-backblaze/
├── main.py                    # Main entrypoint
├── tasks.py                   # Invoke tasks
├── requirements.txt           # Python dependencies
├── config.toml                # Example configuration
├── .env                       # Environment variables (GITHUB_TOKEN, SEMGREP_APP_TOKEN)
├── back2blaze/                # Modular source code
│   ├── __init__.py
│   ├── cli.py                 # CLI interface
│   ├── config.py              # TOML loading
│   ├── s3.py                  # Backblaze S3 client
│   ├── jobs.py                # Job execution
│   ├── archive.py             # tar.gz compression
│   ├── retention.py           # Retention policies
│   ├── locks.py               # Concurrency control
│   ├── tasks_registry.py      # Active task registry
│   ├── scheduler.py           # Internal scheduler
│   └── utils.py               # Utilities
├── packaging/                 # Packaging files
│   ├── back2blaze.service     # systemd service
│   ├── postinstall.sh         # Post-installation script
│   └── back2blaze-wrapper.sh  # Python/binary wrapper
├── Dockerfile                 # PyInstaller build image
├── Dockerfile.deb             # .deb build image
├── Dockerfile.rpm             # .rpm build image
└── .github/workflows/         # GitHub Actions CI/CD
    └── docker-builders.yml    # Automatic image builds
```

### 9) CI/CD

The project uses GitHub Actions to:
- Automatically build Docker images when Dockerfiles change
- Push to GitHub Container Registry
- Use smart caching for faster builds

Images are updated automatically on push to `main`.

### 10) Troubleshooting

#### Common issues:

**Docker login error:**
```bash
# Check .env variables
cat .env

# Test login manually
inv docker-login
```

**Build fails in container:**
```bash
# Check if Docker is running
docker ps

# Rebuild images
inv build-docker-images
```

**Package won't install:**
```bash
# Check system dependencies
# Debian: python3, python3-venv
# RPM: python3, python3-venv

# Check installation logs
sudo journalctl -u back2blaze.service
```

#### Debug mode:
```bash
# Run with more verbosity
python3 main.py --config config.toml --dry-run

# Check configuration
python3 main.py --config config.toml --list
```

### 11) Releases

#### Create a release locally:
```bash
# Full release (auto-increments version)
inv release

# Release with a specific version
inv release --tag v1.2.3

# Build artifacts only
inv build-release --tag v1.2.3

# Create release only (after build)
inv create-release --tag v1.2.3
```

#### Automatic process (GitHub Actions):
- Push to `main`: Creates a new tag and release automatically
- Push a tag (`v*`): Creates a release for the specific tag
- Manual workflow: Allows creating a release on demand

#### GitHub setup (required for CI/CD):
1. **Environment**: Create a `release` environment in the repository
2. **Secret**: Add `RELEASE_GITHUB_TOKEN` to the `release` environment
   - Value: Personal Access Token with `repo` and `write:packages` permissions
3. **Permissions**: The workflow uses the `release` environment for enhanced security

#### Release artifacts:
- `back2blaze` - Standalone executable binary
- `back2blaze_VERSION_amd64.deb` - Debian/Ubuntu package
- `back2blaze-VERSION-1.x86_64.rpm` - RedHat/CentOS/Fedora package

### 12) Contribution

To contribute:
1. Fork the repository
2. Create a feature branch
3. Make changes
4. Test with `inv build-release`
5. Commit and push
6. Open a Pull Request

The build system ensures that all artifacts are generated consistently in any environment with Docker.
