from __future__ import annotations

import importlib
from typing import Any


def dependency_report() -> dict[str, dict[str, Any]]:
    modules = {
        "pikepdf": False,
        "pypdf": False,
        "matplotlib": False,
        "scikit_learn": False,
        "xgboost": False,
    }
    report: dict[str, dict[str, Any]] = {}
    for module_name in modules:
        import_name = module_name
        if module_name == "scikit_learn":
            import_name = "sklearn"
        try:
            module = importlib.import_module(import_name)
            report[module_name] = {
                "available": True,
                "version": getattr(module, "__version__", "unknown"),
            }
        except Exception as exc:
            report[module_name] = {
                "available": False,
                "error": str(exc),
            }
    return report


def assert_training_dependencies() -> None:
    report = dependency_report()
    required = ["pikepdf", "scikit_learn", "matplotlib"]
    missing = [name for name in required if not report[name]["available"]]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required dependencies for detector pipeline: {names}")
