# Confusion Matrix Layer - VGG16 Perceptual Noise Watermarking

High-performance Rust implementation of VGG16-based perceptual noise watermarking for PDF documents. Replicates the `Noise_Stuffy.ipynb` pipeline with production-grade error handling, AWS integration, and multi-tenant support.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Confusion Matrix Layer                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Node.js Orchestrator (index.ts)                                │
│  ├── CLI Executor (cli-executor.ts) ────► Local Development     │
│  └── AWS Handler (aws-lambda-handler.ts) ─► Production          │
│                                                                  │
│  Rust Core (noise_stuffy_layer)                                 │
│  ├── Pdfium Rasterization (200 DPI)                            │
│  ├── VGG16 Feature Extraction (libtorch)                       │
│  ├── Gaussian Noise Injection (ε=0.003)                        │
│  └── PDF Reassembly (pdf-writer)                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Features

- **VGG16-Based Watermarking**: Perceptual noise in feature space
- **High-Performance Rust**: Zero-copy PDF processing with libtorch
- **AWS-Ready**: Automatic Lambda/ECS selection based on file size
- **Multi-Tenant**: S3 path isolation per tenant
- **Configurable**: DPI, epsilon, JPEG quality overrides
- **Error Handling**: Timeout protection, retry logic, detailed logging

## Dependencies

### Rust Dependencies (Cargo.toml)
- `tch` - PyTorch C++ bindings (libtorch)
- `pdfium-render` - PDF rasterization
- `pdf-writer` - PDF generation
- `image` - Image processing
- `reqwest` - VGG16 weight downloads

### System Dependencies
1. **Pdfium** - PDF rendering library
   - Download: https://github.com/bblanchon/pdfium-binaries/releases
   - Place in `binaries/` directory
   - Set `PDFIUM_DYNAMIC_LIB_PATH` if needed

2. **LibTorch** - PyTorch C++ library
   - Auto-downloads via `tch-rs` on first build
   - Set `LIBTORCH` or `TORCH_HOME` for custom installations

3. **VGG16 Weights** - Pretrained model
   - Auto-downloads on first run: `vgg16.ot` (528 MB)
   - Cached in `~/.cache/noise_stuffy_layer/`

## Setup

### 0. Bootstrap native dependencies

The repo no longer checks in libtorch or Pdfium binaries. Before building,
download them into `third_party/` and refresh the Pdfium DLL/SO/DYLIB that lives
next to the Rust binaries:

```bash
bash scripts/setup_third_party.sh
```

```powershell
pwsh -File scripts/setup_third_party.ps1
```

Use the `--force` flag if you need to redownload newer builds. After running the
script, export `LIBTORCH=<repo>/third_party/libtorch` (or set it via `.env`) so
`cargo` and `tch` can resolve the shared libraries.

### 1. Build Rust Binary

```bash
cd rust
chmod +x build.sh
./build.sh
```

This creates:
- `binaries/noise_stuffy_layer` (or `.exe` on Windows)
- `binaries/libnoise_stuffy_layer.so` (shared library)

### 2. Install Pdfium

**Linux:**
```bash
wget https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F6666/pdfium-linux-x64.tgz
tar -xzf pdfium-linux-x64.tgz -C binaries/
mv binaries/lib/libpdfium.so binaries/
```

**macOS:**
```bash
wget https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F6666/pdfium-mac-x64.tgz
tar -xzf pdfium-mac-x64.tgz -C binaries/
mv binaries/lib/libpdfium.dylib binaries/
```

**Windows:**
```powershell
# Download from releases page manually
# Extract pdfium.dll to binaries/
```

### 3. Validate Setup

```typescript
import { validateBinarySetup } from "./confusion-matrix-layer";

const validation = await validateBinarySetup();
if (!validation.valid) {
  console.error(validation.errors);
}
```

## Usage

### Local Development (CLI Mode)

```typescript
import { processConfusionMatrix } from "./confusion-matrix-layer";

const result = await processConfusionMatrix(
  {
    documentId: "doc_123",
    tenantId: "tenant_abc",
    filePath: "/path/to/input.pdf",
    metadata: {},
  },
  {
    mode: "cli",
    dpi: 200,
    noiseEpsilon: 0.003,
    jpegQuality: 95,
    timeoutMs: 300000, // 5 minutes
  }
);

console.log("Watermarked PDF:", result.filePath);
```

### AWS Production (Lambda/ECS)

```typescript
import { handler, selectProcessingService } from "./aws-lambda-handler";

// Automatic service selection
const fileSizeBytes = 50 * 1024 * 1024; // 50MB
const service = selectProcessingService(fileSizeBytes); // "ecs"

// Lambda invocation
const result = await handler({
  tenantId: "tenant_abc",
  documentId: "doc_123",
  inputS3Key: "uploads/tenant_abc/doc_123.pdf",
  inputS3Bucket: "solvance-documents",
  outputS3Bucket: "solvance-protected",
  config: {
    dpi: 200,
    noiseEpsilon: 0.003,
    jpegQuality: 95,
  },
});
```

## Configuration

### NoiseLayerConfig

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dpi` | 200 | Rasterization DPI (higher = better quality, slower) |
| `noiseEpsilon` | 0.003 | Noise magnitude (lower = imperceptible, higher = robust) |
| `jpegQuality` | 95 | JPEG compression quality (1-100) |
| `weightsPath` | Auto | Custom VGG16 weights path (optional) |
| `timeoutMs` | 300000 | Processing timeout (5 minutes) |

### Environment Variables

```bash
# Rust binary configuration
NOISE_LAYER_DPI=200
NOISE_LAYER_EPSILON=0.003
NOISE_LAYER_JPEG_QUALITY=95
NOISE_LAYER_WEIGHTS_PATH=/path/to/vgg16.ot

# System libraries
PDFIUM_DYNAMIC_LIB_PATH=/path/to/libpdfium.so
LIBTORCH=/path/to/libtorch
LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/path/to/libtorch/lib

# AWS configuration
AWS_REGION=us-east-1
AWS_S3_BUCKET=solvance-documents
AWS_S3_BUCKET_PROCESSED=solvance-protected
```

## AWS Deployment

### Lambda Layer (for <10MB PDFs)

```bash
# Create Lambda layer with Rust binary + Pdfium
mkdir -p lambda-layer/bin
cp binaries/noise_stuffy_layer lambda-layer/bin/
cp binaries/libpdfium.so lambda-layer/bin/
cp binaries/libnoise_stuffy_layer.so lambda-layer/bin/

cd lambda-layer
zip -r ../confusion-matrix-layer.zip .
aws lambda publish-layer-version \
  --layer-name confusion-matrix-rust \
  --zip-file fileb://../confusion-matrix-layer.zip
```

### ECS Fargate (for >10MB PDFs)

**Dockerfile:**
```dockerfile
FROM rust:1.75 AS builder
WORKDIR /build
COPY rust/ .
RUN cargo build --release

FROM amazon/aws-lambda-nodejs:20
RUN yum install -y wget tar
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy Rust binary
COPY --from=builder /build/target/release/noise_stuffy_layer /usr/local/bin/

# Install Pdfium
RUN wget https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F6666/pdfium-linux-x64.tgz && \
    tar -xzf pdfium-linux-x64.tgz && \
    mv lib/libpdfium.so /usr/local/lib/ && \
    rm -rf pdfium-linux-x64.tgz lib

# Install LibTorch
RUN wget https://download.pytorch.org/libtorch/cpu/libtorch-cxx11-abi-shared-with-deps-2.1.0%2Bcpu.zip && \
    unzip libtorch-cxx11-abi-shared-with-deps-2.1.0+cpu.zip && \
    mv libtorch /opt/ && \
    rm libtorch-cxx11-abi-shared-with-deps-2.1.0+cpu.zip

ENV LD_LIBRARY_PATH="/usr/local/lib:/opt/libtorch/lib:${LD_LIBRARY_PATH}"

COPY . .
RUN npm install --production

CMD ["aws-lambda-handler.handler"]
```

**Deploy:**
```bash
docker build -t confusion-matrix-ecs .
docker tag confusion-matrix-ecs:latest <ECR_URI>:latest
docker push <ECR_URI>:latest
```

## Performance

| File Size | Pages | Processing Time | Service |
|-----------|-------|-----------------|---------|
| 1 MB | 10 | ~15s | Lambda |
| 5 MB | 50 | ~45s | Lambda |
| 10 MB | 100 | ~90s | Lambda |
| 25 MB | 250 | ~3m | ECS |
| 100 MB | 1000 | ~12m | ECS |

**Optimizations:**
- CUDA acceleration (if GPU available): `Device::cuda_if_available()`
- Batch processing: Process multiple pages in parallel
- Compression: JPEG quality 95 balances size and quality

## Error Handling

```typescript
try {
  const result = await processConfusionMatrix(context, config);
} catch (error) {
  if (error.message.includes("Pdfium library not found")) {
    // Missing Pdfium - install binaries
  } else if (error.message.includes("timed out")) {
    // Processing timeout - increase timeoutMs or use ECS
  } else if (error.message.includes("VGG16 weights")) {
    // Weights download failed - check network/cache dir
  } else {
    // Other error - log and retry
  }
}
```

## Testing

```bash
# Test CLI locally
cd rust
cargo test

# Build and test binary
./build.sh
./binaries/noise_stuffy_layer test.pdf output/

# Test Node.js integration
npm test -- confusion-matrix
```

## Security & Multi-Tenancy

- **Input Validation**: PDF size/page limits enforced
- **Tenant Isolation**: S3 paths prefixed with `tenantId`
- **Timeout Protection**: Prevents resource exhaustion
- **No Persistent State**: Temp files cleaned after processing

## Troubleshooting

**"Pdfium library not found"**
- Download from https://github.com/bblanchon/pdfium-binaries/releases
- Place in `binaries/` directory
- Set `PDFIUM_DYNAMIC_LIB_PATH` environment variable

**"libtorch not found"**
- Install PyTorch C++: https://pytorch.org/get-started/locally/
- Set `LIBTORCH` or `TORCH_HOME` environment variable
- Add to `LD_LIBRARY_PATH` (Linux) or `DYLD_LIBRARY_PATH` (macOS)

**"VGG16 weights download failed"**
- Check network connectivity
- Manually download: https://github.com/LaurentMazare/tch-rs/releases/download/mw/vgg16.ot
- Place in cache dir: `~/.cache/noise_stuffy_layer/vgg16.ot`

**"Processing timeout"**
- Increase `timeoutMs` config
- Use ECS for large files (>10MB)
- Optimize DPI (lower = faster)

## License

Proprietary - Solvance.ai
