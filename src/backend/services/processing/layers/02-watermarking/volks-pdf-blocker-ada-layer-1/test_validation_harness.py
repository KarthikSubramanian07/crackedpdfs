import importlib.util
from pathlib import Path
import unittest


def load_validation_harness_module():
    module_path = Path(__file__).with_name("validation_harness.py")
    spec = importlib.util.spec_from_file_location("validation_harness", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HARNESS = load_validation_harness_module()


class RenderVisibilityDecisionTests(unittest.TestCase):
    def test_renderer_unavailable_falls_back_to_operator_inference(self):
        passed, reason, mode = HARNESS._evaluate_render_visibility(
            expected_raw=True,
            found_marker=True,
            all_instances=[{"inferred_hidden": True}],
            renderer_evidence={"ran": False, "marker_visible": False},
        )

        self.assertTrue(passed)
        self.assertEqual(reason, "operator_inference_passed_renderer_unavailable")
        self.assertEqual(mode, "operator_inference_only")

    def test_renderer_unavailable_with_visible_operator_evidence_fails(self):
        passed, reason, mode = HARNESS._evaluate_render_visibility(
            expected_raw=True,
            found_marker=True,
            all_instances=[{"inferred_hidden": False}],
            renderer_evidence={"ran": False, "marker_visible": False},
        )

        self.assertFalse(passed)
        self.assertEqual(reason, "marker_instances_may_be_visible")
        self.assertEqual(mode, "operator_inference_only")

    def test_renderer_unavailable_with_missing_marker_instances_fails(self):
        passed, reason, mode = HARNESS._evaluate_render_visibility(
            expected_raw=True,
            found_marker=True,
            all_instances=[],
            renderer_evidence={"ran": False, "marker_visible": False},
        )

        self.assertFalse(passed)
        self.assertEqual(reason, "marker_text_not_detected_in_parsed_operations")
        self.assertEqual(mode, "operator_inference_only")

    def test_renderer_detected_visibility_still_fails(self):
        passed, reason, mode = HARNESS._evaluate_render_visibility(
            expected_raw=True,
            found_marker=True,
            all_instances=[{"inferred_hidden": True}],
            renderer_evidence={"ran": True, "marker_visible": True},
        )

        self.assertFalse(passed)
        self.assertEqual(reason, "renderer_detected_visible_marker")
        self.assertEqual(mode, "renderer+operator_inference")


if __name__ == "__main__":
    unittest.main()
