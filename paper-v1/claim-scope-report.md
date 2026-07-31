# Publication Claim Scope

## Approved Primary Claim

On the controlled hard-provenance benchmark, the sanitized hybrid text/structure detector substantially outperforms PromptGuard and structural-only negative controls under paired benign-confounder evaluation, with explicit shortcut audits and label-shuffle sanity checks.

## Disallowed Strong Claims

- Do not claim broad real-world PDF prompt-injection robustness.
- Do not claim reliable generalization across all held-out attack families.
- Do not present text_tfidf as clean positive evidence; treat it as a shortcut-prone comparator.
- Do not present structural-only logreg/xgb as strong detectors; frame them as negative controls.

## Primary Hybrid Result

- F1: 0.960435212660732
- ROC-AUC: 0.9984351382496998
- PR-AUC: 0.9969446987616077
- Paired benign-confounder accuracy: 0.9588900308324769
- Paired benign-confounder support: 1946

## Matched Counterfactual Limitation

Held-out family matched-counterfactual results are reported as stress-test/limitation evidence, not as the main claim.
- steganographic_acrostic: accuracy=0.5, roc_auc=0.4752863228242016, paired_rank_accuracy=0.42424242424242425
- microglyph_steganography: accuracy=0.5, roc_auc=1.0, paired_rank_accuracy=1.0
