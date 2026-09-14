# Paper v1 erratum: realized placement and matched-pair signals

| | |
| --- | --- |
| Published | 2026-09-13 |
| Applies to | Paper v1 corpus (Hugging Face revision `245bc98`, Zenodo DOI [`10.5281/zenodo.21735803`](https://doi.org/10.5281/zenodo.21735803)) and its descriptions in [arXiv:2607.19396v1](https://arxiv.org/abs/2607.19396) |
| Does not change | Any PDF, binary label, split, frozen feature, or frozen metric. The paper table still reproduces byte-for-byte with `make reproduce-results`. |
| How it was found | An external team ran an independent hidden-text detector over all 29,322 PDFs and asked why acrostic files labelled `inside_page` carried about 7,000 characters off the page. |
| Evidence | A full audit of all 19,548 injected and confounder PDFs with [`crackedpdfs-audit`](../tools/crackedpdfs-audit/), which reads glyph geometry from the files and never from generator metadata. Tables are in [`errata/2026-09-placement/`](errata/2026-09-placement/). |

## Summary

| # | Finding | Scope |
| --- | --- | --- |
| 1 | `spatial_regime` labels describe the regime the generator requested, not where text landed. No injected PDF labelled `inside_page` has its payload inside the page: 95.1% of those glyphs are below its bottom edge. | All regime-mode samples except `extreme_off_page` |
| 2 | Matched confounders share placement with their injected twins in every pair, but differ in two signals unrelated to the instruction: a bookkeeping marker that only injected PDFs carry, and payload length. | All 9,774 triplets |
| 3 | `in_page_split_text_objects` has no `strong` samples. | 462 samples, one family |

The paper's headline detector is less exposed than these findings might suggest. The hybrid and shortcut-free models drop every spatial-placement feature and the structural size proxies involved (see [What is and is not affected](#what-is-and-is-not-affected)). The benchmark descriptions, per-regime breakdowns, and any evaluation of other detectors on raw PDFs are affected.

## Finding 1: spatial labels are requested regimes, not realized placement

### Root cause

`resolveInjectionConfig` resolved each dataset sample into a config whose `coordinates` were page-relative regime anchors, for example `[0.5, 0.5]` for `inside_page` and `[0.12, 0.78]` for acrostics, tagged `coordinates_mode: "regime"`. The ADA bridge (`processAdaPolicyLayer`) resolved that config a second time. The resolver treated any `coordinates` it received as an explicit override, so the second pass switched the mode to `override`. The Python injector then used the anchors as absolute PDF points. Every regime-mode payload began at roughly (0.5, 0.5) or (0.12, 0.78) points: the bottom-left corner of the page. Its first line straddled the bottom edge and every later line sat below it.

Matched confounders went through the same bridge and received identical geometry.

### Measured effect

Injected PDFs, grouped by label (all 9,774):

| Label | Injected PDFs | Label holds | Glyphs inside page | Clipped by edge | Outside page |
| --- | ---: | ---: | ---: | ---: | ---: |
| `inside_page` | 6,955 | 0 | 0.6% | 4.3% | 95.1% |
| `negative_off_page` | 581 | 0 | 0.0% | 29.6% | 70.4% |
| `near_margin` | 1,689 | 1,689 | 13.9% | 17.6% | 68.5% |
| `extreme_off_page` | 549 | 549 | 0.0% | 0.0% | 100.0% |

A label holds when every added glyph satisfies its contract: fully inside the visible page box for `inside_page`, fully outside for the two off-page labels, and clear of the page inset by 72pt for `near_margin`. `near_margin` labels hold only by accident, because the bottom-left corner happens to lie in the margin band. The requested placements were family-specific positions in the header, footer, or right margin, or just past the right edge.

Source: [`placement-by-spatial-label.csv`](errata/2026-09-placement/placement-by-spatial-label.csv) and, per family, [`placement-audit-summary.csv`](errata/2026-09-placement/placement-audit-summary.csv).

### The steganographic acrostic

Acrostic samples are labelled `inside_page` and `normal_visible`: black 12pt text meant to read as ordinary prose. In the corpus:

| Strength | Injected PDFs | Mean added glyphs | Mean glyphs below page | Glyphs fully inside page (max) | Changed pixels at 72 dpi (median) |
| --- | ---: | ---: | ---: | ---: | ---: |
| weak | 274 | 6,962 | 6,899 | 0 | 2,060 |
| medium | 259 | 9,773 | 9,709 | 0 | 2,058 |
| strong | 259 | 9,844 | 9,780 | 0 | 2,046 |

Between 57 and 69 glyphs of each payload (median 63) touch the page. They are the first line, which is the `[DATASET_SAMPLE_ID=...][MESSAGE_TYPE=...]` bookkeeping marker, clipped along the bottom edge. The acrostic paragraph itself is entirely off the page, which is why a render shows only a thin strip of difference.

![Paper v1 acrostic sample_0009 rendered on an expanded canvas. The document occupies the top of the frame; the entire acrostic paragraph sits below the page boundary.](errata/2026-09-placement/v1-acrostic-off-page.png)

Note also that 80 to 220 one-sentence lines at 12pt cannot fit on a single page from the requested anchor, so the family as specified could not have been fully inside the page even without the resolver bug.

## Finding 2: matched pairs differ in a marker and in length

### Placement is matched

In all 9,774 triplets, the injected PDF and its confounder have the same realized placement class and the same contract verdict. Placement does not separate a pair.

### A bookkeeping marker separates the classes

The generator prepends a validation marker to the injected payload so its checks can find it. The marker never went into confounders, and the two roles use different wrapper tags:

| Token | Injected PDFs (of 9,774) | Confounder PDFs (of 9,774) |
| --- | ---: | ---: |
| `DATASET_SAMPLE_ID` | 9,774 | 0 |
| `MESSAGE_TYPE=` | 9,774 | 0 |
| `SYSTEM_POLICY_DO_NOT_REMOVE` | 8,982 | 0 |
| `DOCUMENT_LAYOUT_NOTE` | 0 | 8,982 |

A substring match on the raw text classifies injected versus confounder perfectly. The paper's hybrid sanitizes these tokens out of its text channel and passed its wrapper-token audit, but a detector evaluated on the raw PDFs gets no such protection. Source: [`lexical-oracle-tokens.csv`](errata/2026-09-placement/lexical-oracle-tokens.csv).

### Payload length orders most pairs

Confounder text was padded up to, but never past, the injected payload's length, and the injected payload also carries the marker line. In 8,849 of the 8,982 non-acrostic pairs the injected PDF has more added glyphs than its confounder, and in none does it have fewer. Acrostics reverse the direction: the confounder is longer in 514 of 792 pairs. Source: [`pair-matching-by-family.csv`](errata/2026-09-placement/pair-matching-by-family.csv).

Ranking each pair by a single frozen length proxy, and calling the larger value injected, reproduces the shape of the paper's held-out paired-ranking results:

| Held-out family | Pairs | Rank by `text_density_per_page` | Paper hybrid paired rank |
| --- | ---: | ---: | ---: |
| Steganographic acrostic | 792 | 0.351 | 0.424 |
| Microglyph steganography | 696 | 1.000 | 1.000 |
| Semantic fragmentation | 639 | 1.000 | 1.000 |
| Layout mimicry | 669 | 0.995 | 1.000 |
| In-page low-contrast text | 682 | 0.985 | 1.000 |
| Margin microtext | 618 | 0.994 | 1.000 |

Values are computed from the hash-pinned `data/features.parquet` over all pairs in each family; ties count as half. All families are in [`length-only-paired-ranker.csv`](errata/2026-09-placement/length-only-paired-ranker.csv).

This does not show that the hybrid ranks by length. The hybrid config drops `text_density_per_page`, `avg_stream_length_bytes`, and the other structural size features. It does show that paired rank accuracy on this corpus cannot distinguish detecting the instruction from detecting the longer payload. Whether length reaches the hybrid through its sanitized text channel has not been tested.

## Finding 3: no strong in-page split samples

At `strong` strength the generator splits the payload into single characters and stacks them one per line. The validation marker then never appears as a contiguous string to the raw-stream or extractor checks, so Phase 5 validation rejects every such sample. Re-running the v1 injector reproduces this: weak and medium samples pass both checks, strong samples fail both. The family has 242 weak and 220 medium samples and no strong samples, while every other family has all three strengths.

## What is and is not affected

| Artifact or claim | Status |
| --- | --- |
| PDF files, binary labels, frozen splits | Unchanged and correct: injected PDFs contain injected text, benign PDFs do not. |
| Headline hybrid metrics (0.960 F1, 0.998 ROC-AUC, 0.997 PR-AUC) | Numbers stand as computed. The hybrid drops the spatial features that would read the misplaced geometry, and pairs are geometry-matched. The text channel's exposure to length is untested (Finding 2). |
| Descriptions of attacks as "in-page", "near margin", or "negative off-page" | Incorrect for this corpus. Read `spatial_regime` as the requested regime. |
| Acrostic described as visible prose on the page | Incorrect. The paragraph is below the page (Finding 1). |
| Per-regime breakdowns grouped by `spatial_regime` (for example `metrics/*_per_regime.csv` in the dataset release) | Groups are by requested regime. Realized placement is `straddles_page_edge` for every label except `extreme_off_page`. |
| Paired ranking accuracy (the frozen 1.000 field and held-out paired ranks) | Numbers stand as computed, but a length proxy alone reaches the same pattern (Finding 2). Treat as an upper bound on instruction-level discrimination. |
| External detectors evaluated on raw v1 PDFs | Exposed to the marker oracle and the length signal. Strip the tokens in the table above before scoring, and report results on both the full pair set and the length-tied pairs. |
| Held-out family results for `in_page_split_text_objects` | Cover weak and medium strengths only (Finding 3). |

## What changed in the generator

These fixes affect newly generated corpora only. The v1 corpus is not modified.

| Change | Effect |
| --- | --- |
| Idempotent config resolution | A resolved config passes through unchanged, and regime anchors are never promoted to overrides. Contract tests resolve all 2,160 regime combinations twice. |
| Measured placement contract | The injector computes every glyph box from standard 14 Helvetica metrics against MediaBox intersected with CropBox, records it as `attack_stats.placement`, and refuses to write a regime-mode PDF whose geometry contradicts its label. In-page payloads are wrapped to fit. `header_footer_like` is labelled `near_margin`. Acrostics use short sentences at 8pt with a fixed sentence count per strength. |
| Matched confounders | Confounders carry the same marker line and exactly the same payload character length as their injected twins. |
| Recorded placement | Dataset manifests and benchmark records include `realized_spatial_class`, glyph counts, and the contract verdict. |
| Independent audit | `crackedpdfs-audit corpus` checks any extracted release against its metadata. |

One design question remains open for the next corpus version. With truthful placement, the acrostic is a visible 8pt paragraph printed over the base document's body text, which a reader would notice immediately. Making it read as innocuous prose needs free-space-aware placement, a dedicated page region, or a change to the family's rendering regime.

![The same benign page regenerated with the fixed generator: every acrostic glyph is inside the page, and the visible paragraph overlaps the document body.](errata/2026-09-placement/fixed-acrostic-in-page.png)

## Reproduce this erratum

```bash
# 1. Fetch the v1 corpus (about 590 MB) and metadata from the dataset release.
hf download volkthienpreecha/crackedpdfs --repo-type dataset \
  --revision 245bc98ec7e838346ee6fd5bdf5fed1b16d2a3e5 --local-dir crackedpdfs-v1
tar -xzf crackedpdfs-v1/pdfs/injected.tar.gz -C crackedpdfs-v1/pdfs
tar -xzf crackedpdfs-v1/pdfs/benign.tar.gz -C crackedpdfs-v1/pdfs

# 2. Audit every injected and confounder PDF against its benign original.
pip install -e "tools/crackedpdfs-audit[parquet]"
crackedpdfs-audit corpus --root crackedpdfs-v1/pdfs \
  --metadata crackedpdfs-v1/data/metadata.parquet --out audit-v1 --render

# 3. Inspect one acrostic.
crackedpdfs-audit file crackedpdfs-v1/pdfs/injected/sample_0009.injected.pdf \
  --reference crackedpdfs-v1/pdfs/benign/sample_0009.benign.pdf --label inside_page
```

The full audit took 12 minutes on an 8-core laptop and reported 0 extraction errors across 19,548 PDFs.
