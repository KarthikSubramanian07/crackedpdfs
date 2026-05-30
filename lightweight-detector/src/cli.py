from __future__ import annotations

import argparse
import json

from src.data.build_splits import build_grouped_splits
from src.data.validate_dataset import validate_dataset
from src.eval.run import evaluate_from_config
from src.features.build_features import build_features
from src.models.inference import infer_pdf
from src.models.train_hybrid import train_hybrid_from_config
from src.models.train_logreg import train_logreg_from_config
from src.models.train_text import train_text_tfidf_from_config
from src.models.train_xgb import train_xgb_from_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Solvance detector pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_cmd = subparsers.add_parser("validate-dataset")
    validate_cmd.add_argument("--config", default="configs/dataset.yaml")

    features_cmd = subparsers.add_parser("build-features")
    features_cmd.add_argument("--config", default="configs/features.yaml")

    splits_cmd = subparsers.add_parser("build-splits")
    splits_cmd.add_argument("--config", default="configs/dataset.yaml")

    train_cmd = subparsers.add_parser("train")
    train_cmd.add_argument("--model", choices=["logreg", "xgb", "text", "hybrid"], required=True)
    train_cmd.add_argument("--config", required=True)

    evaluate_cmd = subparsers.add_parser("evaluate")
    evaluate_cmd.add_argument("--config", default="configs/eval.yaml")

    infer_cmd = subparsers.add_parser("infer")
    infer_cmd.add_argument("--model", required=True)
    infer_cmd.add_argument("--pdf", required=True)

    run_all_cmd = subparsers.add_parser("run-all")
    run_all_cmd.add_argument("--dataset-config", default="configs/dataset.yaml")
    run_all_cmd.add_argument("--features-config", default="configs/features.yaml")
    run_all_cmd.add_argument("--logreg-config", default="configs/model_logreg.yaml")
    run_all_cmd.add_argument("--xgb-config", default="configs/model_xgb.yaml")
    run_all_cmd.add_argument("--eval-config", default="configs/eval.yaml")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "validate-dataset":
        result = validate_dataset(args.config)
    elif args.command == "build-features":
        result = build_features(args.config)
    elif args.command == "build-splits":
        result = build_grouped_splits(args.config)
    elif args.command == "train":
        if args.model == "logreg":
            _, result = train_logreg_from_config(args.config, persist=True)
        elif args.model == "xgb":
            _, result = train_xgb_from_config(args.config, persist=True)
        elif args.model == "text":
            _, result = train_text_tfidf_from_config(args.config, persist=True)
        else:
            _, result = train_hybrid_from_config(args.config, persist=True)
    elif args.command == "evaluate":
        result = evaluate_from_config(args.config)
    elif args.command == "infer":
        result = infer_pdf(args.model, args.pdf)
    elif args.command == "run-all":
        result = {
            "validate": validate_dataset(args.dataset_config),
            "build_features": build_features(args.features_config),
            "build_splits": build_grouped_splits(args.dataset_config),
            "train_logreg": train_logreg_from_config(args.logreg_config, persist=True)[1],
            "train_xgb": train_xgb_from_config(args.xgb_config, persist=True)[1],
            "evaluate": evaluate_from_config(args.eval_config),
        }
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
