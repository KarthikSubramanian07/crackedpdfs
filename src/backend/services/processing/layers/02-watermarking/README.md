# Layer 02: Watermarking (ADA Policy Injection)

Layer 02 is now centered on the Python ADA injector in:

- `volks-pdf-blocker-ada-layer-1/inject_policy.py`

The old Rust-placeholder description is obsolete for the current pipeline.

## Current architecture

Primary runtime flow:

1. `WatermarkingProcessor` resolves injection options from request metadata.
2. TS resolves a full injection config via `injection-config.ts`.
3. TS writes resolved config JSON and invokes `inject_policy.py` with:
   - input PDF
   - output PDF
   - selected message archetype text file
   - `--config <resolved-config.json>`
4. Python validates the resolved config contract and executes PDF content-stream injection.
5. Output is returned to the processing pipeline with injection metadata attached.

Key files:

- `index.ts` (layer orchestration)
- `injection-config.ts` (authoritative resolver + assertions)
- `volks-pdf-blocker-ada-layer-1/index.ts` (TS->Python bridge)
- `volks-pdf-blocker-ada-layer-1/inject_policy.py` (executor)
- `volks-pdf-blocker-ada-layer-1/validation_harness.py` (Phase 5 checks)

## Injection config model

Resolved config fields include:

- `spatial_regime`
- `rendering_regime`
- `structural_regime`
- `artifact_wrapper`
- `artifact_regime`
- `coordinates` and `coordinates_mode`
- `font_size`
- `render_mode`
- `color`
- `compatibility_notes`

TS is the single resolver. Python is executor + strict schema/contract validator.

## Regime controls

Spatial:

- `extreme_off_page`
- `negative_off_page`
- `near_margin`
- `inside_page`

Rendering:

- `invisible_render_mode`
- `tiny_font`
- `white_text`
- `normal_visible`

Structural:

- `append_new_stream`
- `prepend_stream`
- `inject_into_existing_stream`

Artifact:

- wrapped (`artifact_wrapper=true`)
- unwrapped (`artifact_wrapper=false`)

## Message archetypes

The ADA layer supports three archetype text inputs:

- `instruction_override`
- `task_hijack`
- `policy_framing`

Dataset mode prepends a per-sample marker line to archetype text for Phase 5 verification.

## Validation harness (Phase 5)

`validation_harness.py` runs three checks:

1. Raw stream extraction check (marker presence/absence expectation).
2. Extractor matrix check (`raw_stream`, `pypdf/PyPDF2`, `pdfplumber`).
3. Renderer visibility check (PyMuPDF render + Tesseract OCR marker visibility path), plus operator inference evidence. If renderer dependencies are unavailable, harness falls back to operator-inference-only verdicts.

Harness output is consumed by `src/backend/services/dataset-mode/validation-harness.ts`.

## Local commands

Type check:

```bash
npx tsc --noEmit
```

Run Python injector directly:

```bash
python src/backend/services/processing/layers/02-watermarking/volks-pdf-blocker-ada-layer-1/inject_policy.py \
  <input.pdf> <output.pdf> <policy.txt> --config <resolved-config.json>
```

Run Phase 5 harness directly:

```bash
python src/backend/services/processing/layers/02-watermarking/volks-pdf-blocker-ada-layer-1/validation_harness.py \
  --input <pdf> --marker "<marker>" --expected-raw true
```

## Test additions

Session 6 tests added for:

- TS/Python config contract parity
- structural placement mode behavior
- dataset compatibility filtering, balancing, reproducibility, and archetype constraints

See:

- `injection-config.contract.test.ts`
- `volks-pdf-blocker-ada-layer-1/test_structural_placement.py`
- `src/backend/services/dataset-mode/index.test.ts`
