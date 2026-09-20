# PMTEC Digital Battlefield - Docker Image (P7-v2)
# Multi-stage build: proto generation -> runtime image
# CPU-only (for XPU/GPU acceleration, use a custom base with Intel Arc drivers)
# P7-v2: Adds health check, Prometheus metrics, security, HA support

# ---- Stage 1: Build (generate proto stubs) ----
FROM python:3.11-slim AS builder

# System deps for grpcio build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# P13-3: split sources — torch must come from pytorch.org CPU index
# (PyPI/mirrors ship the CUDA variant = ~3GB nvidia deps); other deps
# go through tsinghua mirror for CN network speed.
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

# CPU-only torch first (satisfies torch>=2.0.0, avoids ~3GB CUDA wheels)
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
    torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt

# Copy proto files and generate gRPC stubs
COPY proto/ ./proto/
RUN mkdir -p ./proto/generated && \
    python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./proto/generated \
    --grpc_python_out=./proto/generated \
    proto/dtb_model.proto && \
    touch ./proto/generated/__init__.py

# ---- Stage 2: Runtime ----
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="PMTEC Digital Battlefield"
LABEL org.opencontainers.image.description="PMTEC DTC2026 - ASDA-cycle digital twin battlefield system"
LABEL org.opencontainers.image.version="P7-v2"
LABEL org.opencontainers.image.authors="PMTEC Team"

# Install runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /pmtec

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

# Install Python dependencies (CPU torch first, see builder stage)
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
    torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt

# Copy generated proto stubs from builder
COPY --from=builder /build/proto/generated/ ./proto/generated/

# Copy application code
COPY config.py ./
COPY services/ ./services/
COPY core/ ./core/
COPY deep_rl/ ./deep_rl/
COPY distributed/ ./distributed/
COPY dt_platform/ ./dt_platform/
COPY learning/ ./learning/
COPY live_data/ ./live_data/
COPY models/ ./models/
COPY persistence/ ./persistence/
COPY realtime/ ./realtime/
COPY security/ ./security/
COPY visualization/ ./visualization/
COPY scripts/ ./scripts/
COPY output/ ./output/
COPY config/ ./config/
# P13: base data (geojson) + pretrained RL models for one-command demo
COPY data/ ./data/

# Create data directories
RUN mkdir -p data/models data/persistence data/logs output

# Environment configuration
ENV PYTHONPATH=/pmtec
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# PMTEC P7-v2 configuration (overridable at runtime via -e flags)
ENV GRPC_HOST=0.0.0.0
ENV GRPC_PORT=50051
ENV PROMETHEUS_ENABLED=1
ENV PROMETHEUS_PORT=9090
ENV PROMETHEUS_METRICS_PATH=/metrics
ENV SECURITY_ENABLED=0
ENV MTLS_ENABLED=0
ENV LIVE_DATA_USE_REAL_API=0
ENV GRPC_HA_ENABLED=0
ENV GRPC_HA_BACKUP_HOSTS=

# Health check (gRPC Health Check Protocol - P7-v2)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "\
import grpc; \
from grpc_health.v1 import health_pb2, health_pb2_grpc; \
ch = grpc.insecure_channel('localhost:50051'); \
stub = health_pb2_grpc.HealthStub(ch); \
r = stub.Check(health_pb2.HealthCheckRequest(service=''), timeout=5); \
exit(0 if r.status == 1 else 1) \
" || exit 1

# Expose ports: gRPC (50051), Prometheus metrics (9090)
EXPOSE 50051 9090

# Entry point: select service via SERVICE env or command arg
# Usage:
#   docker run pmtec-distributed:latest                    # monolithic (all services)
#   docker run -e SERVICE=war_engine pmtec-distributed     # single service
#   docker run -e PROMETHEUS_ENABLED=1 pmtec-distributed    # with metrics
ENTRYPOINT ["python", "-m", "distributed.service_launcher"]
CMD ["--help"]
