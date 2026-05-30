# Multi-stage Dockerfile for AWS Lambda/ECS deployment
# Includes Rust binary, Pdfium, and LibTorch dependencies

FROM rust:1.75-slim AS rust-builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    wget \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Copy Rust source
COPY rust/ .

# Build in release mode with optimizations
RUN cargo build --release

# ============================================
# Production Lambda/ECS Image
# ============================================

FROM public.ecr.aws/lambda/nodejs:20

WORKDIR ${LAMBDA_TASK_ROOT}

# Install runtime dependencies
RUN yum update -y && \
    yum install -y wget tar unzip gzip && \
    yum clean all && \
    rm -rf /var/cache/yum

# Copy Rust binary from builder
COPY --from=rust-builder /build/target/release/noise_stuffy_layer /usr/local/bin/
RUN chmod +x /usr/local/bin/noise_stuffy_layer

# Install Pdfium library
RUN wget -q https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F6666/pdfium-linux-x64.tgz && \
    tar -xzf pdfium-linux-x64.tgz && \
    mkdir -p /usr/local/lib && \
    cp lib/libpdfium.so /usr/local/lib/ && \
    rm -rf pdfium-linux-x64.tgz lib include

# Install LibTorch (CPU version for Lambda cost optimization)
RUN wget -q https://download.pytorch.org/libtorch/cpu/libtorch-cxx11-abi-shared-with-deps-2.1.0%2Bcpu.zip && \
    unzip -q libtorch-cxx11-abi-shared-with-deps-2.1.0+cpu.zip && \
    mv libtorch /opt/ && \
    rm libtorch-cxx11-abi-shared-with-deps-2.1.0+cpu.zip

# Download VGG16 weights (528MB - bake into image for Lambda cold start optimization)
RUN mkdir -p /opt/ml/weights && \
    wget -q -O /opt/ml/weights/vgg16.ot \
    https://github.com/LaurentMazare/tch-rs/releases/download/mw/vgg16.ot

# Set library paths
ENV LD_LIBRARY_PATH="/usr/local/lib:/opt/libtorch/lib:${LD_LIBRARY_PATH}"
ENV PDFIUM_DYNAMIC_LIB_PATH="/usr/local/lib/libpdfium.so"
ENV NOISE_LAYER_WEIGHTS_PATH="/opt/ml/weights/vgg16.ot"

# Copy Node.js application
COPY package*.json ./
RUN npm ci --only=production

COPY . .

# Lambda handler
CMD ["aws-lambda-handler.handler"]
