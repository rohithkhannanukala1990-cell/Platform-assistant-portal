# ── Stage 1: download pinned static CLI binaries ────────────────────────────
# Kept separate from the runtime image so unzip, curl, and the download
# archives never end up in the final layers.
FROM python:3.12-slim-bookworm AS toolchain

ARG KUBECTL_VERSION=v1.29.9
ARG HELM_VERSION=3.14.4
ARG TERRAFORM_VERSION=1.7.5
ARG AWSCLI_VERSION=2.15.30

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /usr/local/bin/kubectl \
    "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    && chmod +x /usr/local/bin/kubectl

RUN curl -fsSL "https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz" -o /tmp/helm.tar.gz \
    && tar -xzf /tmp/helm.tar.gz -C /tmp \
    && mv /tmp/linux-amd64/helm /usr/local/bin/helm \
    && chmod +x /usr/local/bin/helm \
    && rm -rf /tmp/helm.tar.gz /tmp/linux-amd64

RUN curl -fsSL \
    "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    -o /tmp/terraform.zip \
    && unzip -o /tmp/terraform.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/terraform \
    && rm -f /tmp/terraform.zip

RUN curl -fsSL \
    "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-${AWSCLI_VERSION}.zip" \
    -o /tmp/awscliv2.zip \
    && unzip -o /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli \
    && rm -rf /tmp/awscliv2.zip /tmp/aws

# ── Stage 2: runtime image ──────────────────────────────────────────────────
# Pinned to bookworm rather than the floating `slim` tag (which now resolves
# to trixie/Debian 13) so a rebuild doesn't silently land on a newer, less-
# tested Debian release each time this image is built.
FROM python:3.12-slim-bookworm

# System deps for psycopg2-binary and python3-saml (xmlsec), plus git for the
# in-app terminal. libxml2-dev/libxslt1-dev/zlib1g-dev are needed to build
# lxml from source below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl libxmlsec1-dev libxml2-dev libxslt1-dev zlib1g-dev libffi-dev pkg-config git \
    && rm -rf /var/lib/apt/lists/*

# Terminal CLI tools advertised by the in-app terminal — copied from the
# toolchain stage so the final image stays lean (no unzip/download archives).
COPY --from=toolchain /usr/local/bin/kubectl /usr/local/bin/kubectl
COPY --from=toolchain /usr/local/bin/helm /usr/local/bin/helm
COPY --from=toolchain /usr/local/bin/terraform /usr/local/bin/terraform
# NOTE: aws-cli's real launcher lives under /usr/local/aws-cli/v2/current/dist/
# and locates its bundled libpython via a same-directory (rpath) lookup.
# `COPY --from=` dereferences source symlinks, so copying /usr/local/bin/aws
# directly would flatten it into a standalone file in the wrong directory and
# break that lookup — copy the aws-cli tree only, then recreate the symlinks.
COPY --from=toolchain /usr/local/aws-cli /usr/local/aws-cli
RUN chmod -R a+rX /usr/local/aws-cli \
    && chmod +x /usr/local/bin/kubectl /usr/local/bin/helm /usr/local/bin/terraform \
    && ln -sf /usr/local/aws-cli/v2/current/dist/aws /usr/local/bin/aws \
    && ln -sf /usr/local/aws-cli/v2/current/dist/aws_completer /usr/local/bin/aws_completer

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    # Both lxml and xmlsec ship as prebuilt manylinux wheels, and each wheel
    # independently bundles its own libxml2. Loading two different bundled
    # libxml2s in one process trips xmlsec's own "lxml & xmlsec libxml2
    # library version mismatch" check. Force BOTH to build from source
    # against this container's system libxml2/libxslt (via libxml2-dev/
    # libxslt1-dev/libxmlsec1-dev) so they link the identical library.
    && pip install --no-cache-dir --force-reinstall --no-binary lxml,xmlsec lxml xmlsec

COPY . .

# Symlink lets ``import backend.*`` work in this image (Celery include=backend.tasks).
RUN ln -sfn /app /app/backend \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Use exec form so signals (SIGTERM) are forwarded correctly.
# Do not use --reload here: the compose service is read_only and the
# reloader cannot write watch state, which prevents the process from becoming healthy.
# Run as the backend package so relative imports (from .middleware ...) work.
# The /app/backend symlink above makes ``backend.main`` resolve to this tree.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
