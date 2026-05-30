# Confusion Matrix Layer - Quick Start

## ⚡ 60-Second Setup

```bash
# Navigate to layer directory
cd src/backend/services/processing/layers/02-watermarking/confusion-matrix-layer

# Build Rust binary
cd rust && chmod +x build.sh && ./build.sh && cd ..

# Download Pdfium (Linux example)
wget https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F6666/pdfium-linux-x64.tgz
tar -xzf pdfium-linux-x64.tgz && mv lib/libpdfium.so binaries/ && rm -rf lib include pdfium-linux-x64.tgz

# Validate
npm run validate
```

## 🎯 Expected Result

```json
{
  "valid": true,
  "errors": []
}
```

## 🚀 How It Works

```
📄 PDF Upload → Node.js API → Rust Binary → VGG16 Processing → Watermarked PDF
                    ↓
              [Confusion Matrix Layer]
                    ↓
          • Rasterize PDF (Pdfium)
          • Extract VGG16 features (LibTorch)
          • Apply perceptual noise (ε=0.003)
          • Reassemble PDF (pdf-writer)
```

## 📁 File Structure

```
confusion-matrix-layer/
├── rust/
│   ├── src/
│   │   ├── noise_layer.rs  ← Core VGG16 pipeline
│   │   ├── lib.rs           ← Public API
│   │   └── main.rs          ← CLI wrapper
│   ├── Cargo.toml           ← Rust dependencies
│   └── build.sh             ← Compilation script
├── binaries/
│   ├── noise_stuffy_layer   ← Compiled binary (after build)
│   └── libpdfium.so         ← PDF rendering (download manually)
├── cli-executor.ts          ← Node.js subprocess executor
├── aws-lambda-handler.ts    ← AWS Lambda/ECS handler
├── index.ts                 ← Main integration point
├── Dockerfile               ← AWS deployment
└── README.md                ← Full documentation
```

## 🔧 Configuration

### Default Settings (Production-Ready)
```typescript
{
  dpi: 200,              // Rasterization quality
  noiseEpsilon: 0.003,   // Imperceptible noise level
  jpegQuality: 95,       // High quality output
  timeoutMs: 300000      // 5 minutes
}
```

### Override via Environment
```bash
export NOISE_LAYER_DPI=150           # Faster processing
export NOISE_LAYER_EPSILON=0.005     # More robust watermark
export NOISE_LAYER_JPEG_QUALITY=90   # Smaller file size
```

## 🧪 Testing

```bash
# Test Rust core
cd rust && cargo test

# Test with sample PDF
cargo run --release -- /path/to/test.pdf /tmp/output/

# Expected output:
# ✅ Generated noisy PDF with 5 pages at /tmp/output/novel_noisy_pdfs/b_perceptual_noisy.pdf
```

## 🐛 Common Issues

| Error | Fix |
|-------|-----|
| `Rust binary not found` | Run `./build.sh` in `rust/` directory |
| `Pdfium library not found` | Download from [releases](https://github.com/bblanchon/pdfium-binaries/releases) |
| `libtorch not found` | Auto-downloads on first build, or set `LIBTORCH` env var |
| `Processing timeout` | Increase `timeoutMs` or use ECS for large files |

## 📊 Performance

| File Size | Pages | Processing Time | Service |
|-----------|-------|-----------------|---------|
| 1 MB | 10 | ~15s | Lambda |
| 5 MB | 50 | ~45s | Lambda |
| 25 MB | 250 | ~3m | ECS |
| 100 MB | 1000 | ~12m | ECS |

## 🔍 Verify Integration

```bash
# Upload a PDF through the UI
# Watch logs:
tail -f /tmp/dev-server.out.log | grep "Layer 02"

# Expected logs:
# [Layer 02 - Watermarking] Starting VGG16 confusion matrix watermarking
# [Layer 02 - Watermarking] VGG16 watermarking completed
```

## 🎓 Next Steps

1. ✅ **Setup Complete** - Binary compiled, dependencies installed
2. 📤 **Test Upload** - Upload a PDF through the UI
3. 🔍 **Verify Output** - Check processed file in storage
4. ☁️ **AWS Deploy** - Build Docker image for production
5. 📈 **Monitor** - Track processing times and success rates

## 🆘 Need Help?

- **Setup Issues**: See [SETUP.md](./SETUP.md)
- **API Documentation**: See [README.md](./README.md)
- **AWS Deployment**: See [Dockerfile](./Dockerfile)

## 💡 Pro Tips

- Development fallback: System automatically uses mock processing if binary unavailable
- AWS auto-selection: Lambda for <10MB, ECS for larger files
- Multi-tenant: S3 paths automatically isolated by tenant ID
- VGG16 weights: Auto-download on first run (528 MB, one-time)

---

**Ready to go!** Upload a PDF and watch the VGG16 watermarking in action. 🚀
