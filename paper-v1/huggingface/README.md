---
pretty_name: CrackedPDFs
license: mit
task_categories:
  - text-classification
  - feature-extraction
language:
  - en
tags:
  - llm-security
  - prompt-injection
  - pdf-security
  - benchmark
size_categories:
  - 10K<n<100K
---

# CrackedPDFs

CrackedPDFs is a paired benchmark for detecting prompt injections embedded in PDF structure. The paper release contains **29,322 PDFs** derived from **4,983 base documents**, organized as 9,774 matched triplets:

- one benign original;
- one benign structural confounder; and
- one injected PDF.

The benign source documents were produced with [PDFAutoGen](https://github.com/volkthienpreecha/crackedpdfs/tree/main/tools/PDFautogenerator). The paired design measures whether a defense detects malicious intent rather than merely reacting to unusual PDF structure.

## Links

- [Paper](https://arxiv.org/abs/2607.19396)
- [Code and frozen paper bundle](https://github.com/volkthienpreecha/crackedpdfs)
- [Paper results](https://github.com/volkthienpreecha/crackedpdfs/tree/main/paper-v1)

## Benchmark tasks

1. **Injected-vs-benign classification:** classify each PDF as benign or injected.
2. **Paired ranking:** rank the injected member above its matched benign original and benign confounder.
3. **Held-out provenance generalization:** train and evaluate with base-document provenance separated across splits.
4. **Shortcut auditing:** compare performance on random negatives against matched structural confounders.
5. **Attack-family holdout:** evaluate generalization across 15 injected attack families.

## Dataset composition

| Role | PDFs |
|---|---:|
| Benign originals | 9,774 |
| Benign structural confounders | 9,774 |
| Injected attacks | 9,774 |
| **Total** | **29,322** |

| Frozen paper evaluation split | Rows |
|---|---:|
| Train | 23,766 |
| Validation | 2,637 |
| Test | 2,919 |

Splits are grouped by `base_pdf_id`; members derived from the same base document do not cross split boundaries.

## Files

```text
data/
  metadata.jsonl          Complete row-level metadata
  metadata.parquet        Columnar metadata
  labels.parquet          Frozen labels and metadata used by the paper run
  features.parquet        54 frozen structural features for all 29,322 PDFs
  splits.json             Frozen group-aware split assignment
pdfs/
  benign.tar.gz           Benign originals and matched confounders
  injected.tar.gz         Injected PDFs
metrics/
  metrics.json            Complete frozen publication metrics
  hard-setting-summary.csv
checksums.sha256           SHA-256 checksums for every published file
```

Extract both PDF archives into a common directory. Their internal paths begin with `benign/` and `injected/`, matching the `file_path` column in the metadata.

## Core schema

| Field | Type | Meaning |
|---|---|---|
| `pdf_id` | string | Unique benchmark PDF identifier |
| `base_pdf_id` | string | Provenance group used to prevent split leakage |
| `sample_id` | string | Matched sample identifier |
| `pair_id` / `triad_id` | string | Matched comparison group |
| `pdf_role` | string | `benign_original`, `benign_confounder`, or `injected_attack` |
| `file_path` | string | Relative path inside the PDF archives |
| `label` | integer | `0` for benign, `1` for injected |
| `dataset_split` | string | Generation-layer assignment retained from the publication table; use `data/splits.json` for the paper evaluation split |
| `attack_family` | string | Injected attack family, or `none` |
| `benign_confounder_family` | string | Matched benign structural transformation |
| `message_type` | string | Prompt-injection objective category |
| `spatial_regime` | string | Placement regime used in the PDF |
| `rendering_regime` | string | Text rendering regime |
| `structural_regime` | string | Content-stream insertion regime |
| `artifact_wrapper` | boolean | Whether marked-content artifact wrapping was used |

The metadata contains additional generation, pairing, physical-regime, and audit fields. `features.parquet` contains `pdf_id` plus the 53 numeric structural measurements defined in the paper snapshot. `data/splits.json` is the authoritative paper evaluation assignment and is grouped by `base_pdf_id`.

## Quick reproduction

```bash
git clone https://github.com/volkthienpreecha/crackedpdfs.git
cd crackedpdfs
make reproduce-results
```

The command downloads and hash-verifies the frozen features, labels, splits, and metrics, then regenerates the paper's hard-setting summary. It does **not** regenerate 29,322 PDFs.

## Limitations and intended use

- The benchmark is English-language and synthetic; it does not establish performance on every real-world document distribution.
- The PDFs cover the attack families and rendering regimes documented in the paper, not every possible PDF parser differential.
- Perfect TF-IDF performance is a shortcut warning, not evidence of universal prompt-injection detection.
- PromptGuard is included as a domain-mismatched text baseline; the results do not imply that PromptGuard is generally broken.
- The files contain adversarial instructions intended for security research. Do not feed them to production agents with tools or sensitive data unless the environment is isolated.
- Do not use the benchmark to claim safety against attacks, models, parsers, or document formats that were not evaluated.

## Citation

```bibtex
@article{thienpreecha2026crackedpdfs,
  title   = {CrackedPDFs: A Controlled Benchmark for Hidden Prompt Injection in PDFs},
  author  = {Thienpreecha, Pukaphol and Subramanian, Karthik},
  journal = {arXiv preprint arXiv:2607.19396},
  year    = {2026},
  url     = {https://arxiv.org/abs/2607.19396}
}
```

## License

The paper-release code and dataset are published under the MIT License. See `LICENSE` in this dataset repository.
