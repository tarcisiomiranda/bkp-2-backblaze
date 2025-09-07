FROM astral/uv:0.8.15-python3.11-bookworm-slim

RUN apt-get update && \
    apt-get install -y binutils lintian rpmlint git curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ARG GITLEAKS_VERSION=8.18.2
RUN curl -sL https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz | tar -xz -C /usr/local/bin gitleaks

WORKDIR /work

ENV HOME=/tmp
ENV UV_CACHE_DIR=/tmp/uv-cache
ENV XDG_CACHE_HOME=/tmp/.cache

RUN mkdir -p /tmp/uv-cache /tmp/.cache /tmp/packages

RUN uv pip install --system pyinstaller semgrep

CMD ["/bin/bash"]
