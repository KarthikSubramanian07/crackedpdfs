# Confusion Matrix Layer - Setup Guide

Complete setup guide for the VGG16-based perceptual noise watermarking layer.

## 🎯 Quick Start (5 Minutes)

```bash
cd src/backend/services/processing/layers/02-watermarking/confusion-matrix-layer

# 1. Build Rust binary
cd rust
chmod +x build.sh
./build.sh
cd ..

# 2. Download Pdfium (choose your platform)
# Linux:
wget https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F6666/pdfium-linux-x64.tgz
tar -xzf pdfium-linux-x64.tgz
cp lib/libpdfium.so binaries/
rm -rf lib include pdfium-linux-x64.tgz

# macOS:
wget https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F6666/pdfium-mac-x64.tgz
tar -xzf pdfium-mac-x64.tgz
cp lib/libpdfium.dylib binaries/
rm -rf lib include pdfium-mac-x64.tgz

# Windows: Download manually from releases page, extract pdfium.dll to binaries/

# 3. Validate setup
npm run validate
```

## 📋 Prerequisites

### Required Software

1. **Rust Toolchain** (>= 1.75)
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source $HOME/.cargo/env
   ```

2. **PyTorch C++ (LibTorch)** - Auto-downloads on first build
   - For custom installation:
     ```bash
     # Linux CPU
     wget https://download.pytorch.org/libtorch/cpu/libtorch-cxx11-abi-shared-with-deps-2.1.0%2Bcpu.zip
     unzip libtorch-cxx11-abi-shared-with-deps-2.1.0+cpu.zip
     export LIBTORCH=$(pwd)/libtorch
     export LD_LIBRARY_PATH=$LIBTORCH/lib:$LD_LIBRARY_PATH
     
     # macOS CPU
     wget https://download.pytorch.org/libtorch/cpu/libtorch-macos-2.1.0.zip
     unzip libtorch-macos-2.1.0.zip
     export LIBTORCH=$(pwd)/libtorch
     export DYLD_LIBRARY_PATH=$LIBTORCH/lib:$DYLD_LIBRARY_PATH
     ```

3. **Pdfium Library** - See Quick Start section above

4. **Node.js** (>= 20.0.0) - Already installed

## 🔨 Build Process

### Step 1: Rust Binary

```bash
cd rust
cargo build --release

# Output:
# ✅ target/release/noise_stuffy_layer (or .exe on Windows)
# ✅ target/release/libnoise_stuffy_layer.so (shared library)
```

**Troubleshooting:**
- **"error: linker `cc` not found"**
  ```bash
  # Ubuntu/Debian
  sudo apt install build-essential
  
  # macOS
  xcode-select --install
  
  # Windows
  # Install Visual Studio Build Tools
  ```

- **"tch-rs build failed"**
  ```bash
  # Ensure LibTorch is installed
  export LIBTORCH=/path/to/libtorch
  export LD_LIBRARY_PATH=$LIBTORCH/lib:$LD_LIBRARY_PATH
  cargo clean && cargo build --release
  ```

### Step 2: Pdfium Installation

**Linux (Ubuntu/Debian):**
```bash
cd binaries
wget https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F6666/pdfium-linux-x64.tgz
tar -xzf pdfium-linux-x64.tgz
mv lib/libpdfium.so .
rm -rf lib include pdfium-linux-x64.tgz
chmod +x libpdfium.so
```

**macOS:**
```bash
cd binaries
wget https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F6666/pdfium-mac-x64.tgz
tar -xzf pdfium-mac-x64.tgz
mv lib/libpdfium.dylib .
rm -rf lib include pdfium-mac-x64.tgz
chmod +x libpdfium.dylib
```

**Windows:**
1. Download from: https://github.com/bblanchon/pdfium-binaries/releases
2. Extract `pdfium.dll` to `binaries/` directory
3. Ensure it's in PATH or same directory as executable

### Step 3: Validate Setup

```bash
npm run validate
```

**Expected Output:**
```json
{
  "valid": true,
  "errors": []
}
```

**Common Errors:**
```json
{
  "valid": false,
  "errors": [
    "Rust binary not found at /path/to/binaries/noise_stuffy_layer. Run build.sh first.",
    "Pdfium library not found at /path/to/binaries/libpdfium.so. Download from https://github.com/bblanchon/pdfium-binaries/releases"
  ]
}
```

## 🧪 Testing

### Test Rust Core

```bash
cd rust
cargo test

# Test with sample PDF
cargo run --release -- /path/to/sample.pdf /tmp/output/
```

### Test Node.js Integration

```bash
node -e "
const { executeConfusionMatrixLayer } = require('./cli-executor');
executeConfusionMatrixLayer(
  '/path/to/test.pdf',
  '/tmp/output',
  { dpi: 200, noiseEpsilon: 0.003, jpegQuality: 95 }
).then(result => console.log(result));
"
```

**Expected Output:**
```json
{
  "success": true,
  "outputPath": "/tmp/output/novel_noisy_pdfs/b_perceptual_noisy.pdf",
  "pageCount": 5,
  "executionTimeMs": 15234
}
```

## 🚀 Local Development

### Environment Variables

Create `.env` in project root:
```bash
# Rust configuration
NOISE_LAYER_DPI=200
NOISE_LAYER_EPSILON=0.003
NOISE_LAYER_JPEG_QUALITY=95

# System libraries
PDFIUM_DYNAMIC_LIB_PATH=/path/to/binaries/libpdfium.so
LIBTORCH=/path/to/libtorch
LD_LIBRARY_PATH=$LIBTORCH/lib:/usr/local/lib
```

### Run Processing Pipeline

Upload a PDF through the UI, and the system will:
1. Validate file (Layer 01)
2. **Apply VGG16 watermarking (Layer 02 - Confusion Matrix)** ← Your layer
3. Encrypt/hash (Layer 03)
4. Verify and store (Layer 04)

Watch logs:
```bash
tail -f /tmp/dev-server.out.log | grep "Layer 02"
```

## ☁️ AWS Deployment

### Lambda Deployment (< 10MB PDFs)

```bash
# Build Docker image
docker build -t confusion-matrix-lambda .

# Tag and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
docker tag confusion-matrix-lambda:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/confusion-matrix:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/confusion-matrix:latest

# Create Lambda function
aws lambda create-function \
  --function-name confusion-matrix-watermark \
  --package-type Image \
  --code ImageUri=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/confusion-matrix:latest \
  --role arn:aws:iam::<ACCOUNT_ID>:role/lambda-execution-role \
  --timeout 300 \
  --memory-size 3008
```

### ECS Deployment (> 10MB PDFs)

```bash
# Build and push image
docker build -t confusion-matrix-ecs .
docker tag confusion-matrix-ecs:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/confusion-matrix-ecs:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/confusion-matrix-ecs:latest

# Create ECS task definition (see README.md)
```

### Environment Variables (AWS)

```bash
# Lambda/ECS environment
AWS_REGION=us-east-1
AWS_S3_BUCKET=solvance-documents
AWS_S3_BUCKET_PROCESSED=solvance-protected
NOISE_LAYER_WEIGHTS_PATH=/opt/ml/weights/vgg16.ot
LD_LIBRARY_PATH=/usr/local/lib:/opt/libtorch/lib
```

## 🔍 Verification Checklist

Before considering setup complete, verify:

- [ ] Rust binary builds without errors
- [ ] `binaries/noise_stuffy_layer` exists and is executable
- [ ] Pdfium library in `binaries/` directory
- [ ] `npm run validate` passes
- [ ] Test PDF processes successfully
- [ ] VGG16 weights download automatically on first run
- [ ] Output PDF is visually similar to input (perceptual noise is imperceptible)
- [ ] Processing completes in reasonable time (< 30s for 10-page PDF)

## 📊 Performance Benchmarks

| Configuration | File Size | Pages | Time | Memory |
|--------------|-----------|-------|------|--------|
| DPI 150 | 1 MB | 10 | ~10s | ~1.5 GB |
| DPI 200 | 5 MB | 50 | ~45s | ~2.0 GB |
| DPI 300 | 10 MB | 100 | ~2m | ~3.0 GB |

**Optimization Tips:**
- Lower DPI = Faster processing (trade-off: quality)
- JPEG quality 85-95 balances size and visual quality
- Enable CUDA for 3-5x speedup if GPU available

## 🐛 Troubleshooting

### "Pdfium library not found"
```bash
# Check library exists
ls -la binaries/libpdfium.*

# Set explicit path
export PDFIUM_DYNAMIC_LIB_PATH=$(pwd)/binaries/libpdfium.so
```

### "VGG16 weights download failed"
```bash
# Manual download
mkdir -p ~/.cache/noise_stuffy_layer
wget -O ~/.cache/noise_stuffy_layer/vgg16.ot \
  https://github.com/LaurentMazare/tch-rs/releases/download/mw/vgg16.ot
```

### "libtorch not found"
```bash
# Check installation
echo $LIBTORCH
ls -la $LIBTORCH/lib

# Add to runtime path
export LD_LIBRARY_PATH=$LIBTORCH/lib:$LD_LIBRARY_PATH

# Verify
ldd binaries/noise_stuffy_layer | grep torch
```

### "Processing timeout"
- Increase `timeoutMs` in config (default 5 minutes)
- Switch to ECS for large files
- Lower DPI from 200 to 150

## 📚 Additional Resources

- [Pdfium Binaries](https://github.com/bblanchon/pdfium-binaries/releases)
- [LibTorch Installation](https://pytorch.org/cppdocs/installing.html)
- [tch-rs Documentation](https://github.com/LaurentMazare/tch-rs)
- [VGG16 Paper](https://arxiv.org/abs/1409.1556)

## 🎓 Next Steps

After successful setup:

1. **Test with sample PDFs** - Verify output quality
2. **Tune parameters** - Adjust DPI/epsilon/quality for your use case
3. **AWS integration** - Deploy to Lambda/ECS for production
4. **Monitor performance** - Track processing times and success rates
5. **Scale testing** - Test with 100+ concurrent uploads

## 💡 Tips

- **Development**: Use mock mode when binary unavailable (automatic fallback)
- **Production**: Always use compiled binary for real watermarking
- **AWS**: Lambda for < 10MB, ECS for larger files
- **Security**: Multi-tenant isolation via S3 path prefixes
- **Cost**: Lambda ~$0.0000166667/GB-sec, ECS ~$0.04048/vCPU-hour

---

**Need Help?** Check the main [README.md](./README.md) for detailed API documentation and integration examples.
