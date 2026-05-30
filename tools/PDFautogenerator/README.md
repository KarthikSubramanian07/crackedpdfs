# PDF Autogenerator

Standalone benign one-page PDF generator for research datasets.

## Features

- Six benign document families across fourteen templates
- Portrait-only Letter and A4 output
- Bundled fonts with deterministic sampling
- JSONL manifest with reproducible document metadata
- Resume-safe generation and validation CLI

## Usage

1. Ensure the bundled fonts exist under `assets/fonts/`.
2. Run:

```powershell
python -m pdf_autogenerator.cli generate --config configs/default.yaml
python -m pdf_autogenerator.cli validate --manifest out/manifest.jsonl
```

The generator writes PDFs to `output_root/base/` and a manifest to
`output_root/manifest.jsonl`.
