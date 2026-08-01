# CrackedPDFs

## A Controlled Benchmark for Hidden Prompt Injection in PDFs

[![arXiv](https://img.shields.io/badge/arXiv-2607.19396-b31b1b.svg)](https://arxiv.org/abs/2607.19396)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB.svg)](https://www.python.org/downloads/release/python-3137/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[![Paper](https://img.shields.io/badge/Paper-read-b31b1b.svg)](https://arxiv.org/abs/2607.19396)
[![Dataset](https://img.shields.io/badge/Dataset-Hugging_Face-ffd21e.svg)](https://huggingface.co/datasets/volkthienpreecha/crackedpdfs)
[![Code](https://img.shields.io/badge/Code-browse-181717.svg)](https://github.com/volkthienpreecha/crackedpdfs)
[![Results](https://img.shields.io/badge/Results-tables-2563eb.svg)](paper-v1/RESULTS.md)
[![Citation](https://img.shields.io/badge/Citation-BibTeX-8b5cf6.svg)](#citation)

CrackedPDFs is a controlled benchmark for testing hidden prompt injection at the PDF document layer, before a pipeline flattens the file into plain text.

| Corpus | Base documents | Hybrid F1 | Paper-reported paired result |
| ---: | ---: | ---: | ---: |
| **29,322 PDFs** | **4,983** | **0.960** | **95.9%** |

The corpus contains 9,774 injected PDFs and 19,548 benign originals or matched benign confounders. On the 2,919-document held-out test split, the sanitized hybrid detector reached 0.960 F1, 0.998 ROC-AUC, and 0.997 PR-AUC.

The paper describes 95.9% as paired ranking. The frozen evaluation artifact stores 0.958890 as classification accuracy on the balanced injected-versus-matched-confounder set, while its explicit pairwise ranking field is 1.000. The [results provenance note](paper-v1/RESULTS.md#paired-result-provenance) records this distinction so later work does not silently change the metric definition.

Benign source documents were produced with [PDFAutoGen](https://github.com/volkthienpreecha/PDFAutoGen), a deterministic benign-document generator with fourteen templates, seeded layout variation, and structured content banks.

> **Claim boundary:** CrackedPDFs measures controlled, generator-produced PDF attacks. It does not establish robustness to arbitrary real-world documents, OCR-only pipelines, adaptive attackers, unseen parsers, or unseen attack generators.

## What is in this repository

| Path | Purpose |
| --- | --- |
| [`paper-v1/`](paper-v1/) | Paper tables, exact metric artifacts, frozen splits, reproducibility metadata, environment capture, and example triplet metadata. |
| `tools/PDFautogenerator/` | Vendored deterministic benign PDF generator used by this experiment stack. The standalone generator is [PDFAutoGen](https://github.com/volkthienpreecha/PDFAutoGen). |
| `src/backend/services/dataset-mode/` | Paired benchmark construction and validation. |
| `src/backend/services/processing/layers/02-watermarking/` | PDF injection mechanisms and validation helpers. |
| `lightweight-detector/` | Feature extraction, grouped splitting, baselines, learned models, audits, and evaluation. |
| `scripts/run_crackedpdfs_experiment.ps1` | Current end-to-end experiment runner. |

Generated PDFs, local databases, model binaries, and full feature tables remain excluded from Git. They are published in the [Hugging Face dataset](https://huggingface.co/datasets/volkthienpreecha/crackedpdfs); `paper-v1/` is the compact, reviewable paper record.

## Benchmark design

Each benchmark group begins with one benign base document and may contain:

1. a benign original;
2. a matched benign confounder that shares non-label provenance features; and
3. an injected counterpart with machine-visible instructions hidden through PDF structure or rendering.

Splits are grouped by `base_pdf_id`. Related variants cannot cross train, validation, and test boundaries.

| Split | PDFs |
| --- | ---: |
| Train | 23,766 |
| Validation | 2,637 |
| Test | 2,919 |
| **Total** | **29,322** |

The evaluation includes:

- a PDF rule baseline;
- PromptGuard over extracted text;
- structural-only logistic regression and XGBoost;
- a text-only TF-IDF shortcut comparator;
- the primary sanitized text-plus-structure hybrid detector;
- label-shuffle checks;
- shortcut and leakage audits;
- paired benign-confounder controls; and
- held-out attack-family stress tests.

See [`paper-v1/RESULTS.md`](paper-v1/RESULTS.md) for the paper-facing tables and exact artifact keys.

## Linux reproduction

Requirements:

- Python 3.13;
- Node.js 22 and npm;
- GNU Make; and
- Git.

```bash
git clone https://github.com/volkthienpreecha/crackedpdfs.git
cd crackedpdfs
make smoke
```

`make smoke` verifies the May 25 source snapshot, runs the Python generator and TypeScript tests, then generates one benign PDF and one injected counterpart through the real benchmark pipeline.

To regenerate the paper's compact result table from the published frozen features:

```bash
make reproduce-results
```

The second command downloads four hash-pinned artifacts from an immutable [Hugging Face revision](paper-v1/reproducibility/download-manifest.json), verifies every SHA-256 digest, and writes `reproduced-results/hard-setting-summary.csv`. It does not regenerate the 29,322 PDFs.

## Full publication-style run

```powershell
npm run experiment:publication
```

This is an expensive regeneration path. It creates fresh source PDFs and reruns the benchmark. It is not the intended fast path for checking the published numbers.

For paper review, start with:

- [`paper-v1/RESULTS.md`](paper-v1/RESULTS.md);
- [`paper-v1/reproducibility/frozen-splits.json`](paper-v1/reproducibility/frozen-splits.json);
- [`paper-v1/reproducibility/run-manifest.json`](paper-v1/reproducibility/run-manifest.json); and
- [`paper-v1/metrics/metrics.json`](paper-v1/metrics/metrics.json).

## Dataset availability

The complete public dataset is at [Hugging Face](https://huggingface.co/datasets/volkthienpreecha/crackedpdfs). It contains all 29,322 PDFs, row-level metadata, frozen features, labels, paper evaluation splits, metrics, and SHA-256 checksums. The large binaries remain outside Git so the repository stays cloneable.

The release manifest pins the fast reproduction command to dataset revision `02d7e0be03b09d6a29c7e4d388440bc1f5a4907b`. See [`paper-v1/DATASET.md`](paper-v1/DATASET.md) for schema, split semantics, and limitations.

## Citation

If you use the benchmark, code, splits, or paper results, cite:

```bibtex
@misc{thienpreecha2026crackedpdfs,
  title         = {CrackedPDFs: A Controlled Benchmark for Hidden Prompt Injection in PDFs},
  author        = {Thienpreecha, Pukaphol and Subramanian, Karthik},
  year          = {2026},
  eprint        = {2607.19396},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  doi           = {10.48550/arXiv.2607.19396},
  url           = {https://arxiv.org/abs/2607.19396}
}
```

Machine-readable citation metadata is in [`CITATION.cff`](CITATION.cff).

The PDF and TeX source list two authors. At the time this README was written, the arXiv abstract page displayed only Pukaphol Thienpreecha. The citation above follows the paper PDF.

## Contributing and conduct

See [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a change. Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

The repository code and original documentation are available under the [MIT License](LICENSE). Bundled fonts retain their own license files under `tools/PDFautogenerator/assets/fonts/`.
