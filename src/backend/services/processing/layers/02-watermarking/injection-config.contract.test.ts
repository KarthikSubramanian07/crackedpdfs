import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import {
  assertResolvedInjectionConfig,
  resolveInjectionConfig,
  type InjectionConfig,
} from "./injection-config";
import { getPythonExecutable } from "./python-utils";

const PYTHON_BIN = getPythonExecutable();
const INJECT_POLICY_SCRIPT = path.join(
  process.cwd(),
  "src",
  "backend",
  "services",
  "processing",
  "layers",
  "02-watermarking",
  "volks-pdf-blocker-ada-layer-1",
  "inject_policy.py"
);

const PYTHON_VALIDATOR = `
import importlib.util
import json
import sys

script_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("inject_policy", script_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

payload = json.loads(sys.stdin.read())
validated = module.validate_resolved_injection_config(payload)
print(json.dumps(validated, sort_keys=True))
`;

function validateWithPython(config: unknown): InjectionConfig {
  const stdout = execFileSync(PYTHON_BIN, ["-c", PYTHON_VALIDATOR, INJECT_POLICY_SCRIPT], {
    input: JSON.stringify(config),
    encoding: "utf-8",
    maxBuffer: 10 * 1024 * 1024,
    stdio: ["pipe", "pipe", "ignore"],
  });
  return JSON.parse(stdout) as InjectionConfig;
}

test("TS resolved injection config satisfies Python validator contract", () => {
  const scenarios: unknown[] = [
    {},
    {
      spatial_regime: "near_margin",
      rendering_regime: "tiny_font",
      structural_regime: "prepend_stream",
      artifact_wrapper: false,
    },
    {
      coordinates: [321.25, 432.5],
      font_size: 0.75,
      render_mode: 3,
      color: [0.1, 0.2, 0.3],
    },
    {
      attack_family: "split_text_objects",
      attack_strength: "strong",
      rendering_regime: "tiny_font",
      structural_regime: "inject_into_existing_stream",
    },
    {
      spatial_regime: "inside_page",
      rendering_regime: "normal_visible",
    },
    {
      spatial_regime: "near_margin",
      rendering_regime: "normal_visible",
    },
  ];

  for (const scenario of scenarios) {
    const resolved = assertResolvedInjectionConfig(resolveInjectionConfig(scenario));
    const validated = validateWithPython(resolved);
    assert.deepEqual(validated, resolved);
  }
});

test("Python validator rejects contract violations", () => {
  const resolved = assertResolvedInjectionConfig(resolveInjectionConfig({}));
  const invalidRenderMode = {
    ...resolved,
    render_mode: 9,
  };
  const invalidArtifactConsistency = {
    ...resolved,
    artifact_wrapper: true,
    artifact_regime: "no_artifact",
  };
  const invalidAttackFamily = {
    ...resolved,
    attack_family: "not_real",
  };

  assert.throws(() => validateWithPython(invalidRenderMode), /render_mode|Command failed/);
  assert.throws(
    () => validateWithPython(invalidArtifactConsistency),
    /artifact_wrapper and artifact_regime are inconsistent|Command failed/
  );
  assert.throws(
    () => validateWithPython(invalidAttackFamily),
    /attack_family|Command failed/
  );
});

test("near_margin_normal_font resolves to a normal-looking visible regime", () => {
  const resolved = assertResolvedInjectionConfig(
    resolveInjectionConfig({
      attack_family: "near_margin_normal_font",
      rendering_regime: "white_text",
      spatial_regime: "inside_page",
      font_size: 4,
    })
  );

  assert.equal(resolved.attack_family, "near_margin_normal_font");
  assert.equal(resolved.spatial_regime, "near_margin");
  assert.equal(resolved.rendering_regime, "normal_visible");
  assert.equal(resolved.render_mode, 0);
  assert.deepEqual(resolved.color, [0, 0, 0]);
  assert.equal(resolved.font_size >= 9, true);
  assert.deepEqual(validateWithPython(resolved), resolved);
});

test("header_footer_like does not keep normal_visible after resolution", () => {
  const resolved = assertResolvedInjectionConfig(
    resolveInjectionConfig({
      attack_family: "header_footer_like",
      rendering_regime: "normal_visible",
    })
  );

  assert.equal(resolved.attack_family, "header_footer_like");
  assert.notEqual(resolved.rendering_regime, "normal_visible");
  assert.deepEqual(validateWithPython(resolved), resolved);
});

test("hard in-page families resolve away from off-page geometry", () => {
  const scenarios = [
    {
      attack_family: "in_page_invisible_text",
      expected_rendering: "invisible_render_mode",
      expected_render_mode: 3,
    },
    {
      attack_family: "in_page_white_text",
      expected_rendering: "white_text",
      expected_render_mode: 0,
    },
    {
      attack_family: "in_page_tiny_text",
      expected_rendering: "tiny_font",
      expected_render_mode: 0,
    },
    {
      attack_family: "in_page_split_text_objects",
      expected_rendering: "invisible_render_mode",
      expected_render_mode: 3,
    },
    {
      attack_family: "layout_mimicry",
      expected_rendering: "white_text",
      expected_render_mode: 0,
    },
    {
      attack_family: "semantic_fragmentation",
      expected_rendering: "invisible_render_mode",
      expected_render_mode: 3,
    },
    {
      attack_family: "existing_stream_patch",
      expected_rendering: "invisible_render_mode",
      expected_render_mode: 3,
    },
    {
      attack_family: "in_page_low_contrast_text",
      expected_rendering: "white_text",
      expected_render_mode: 0,
    },
    {
      attack_family: "steganographic_acrostic",
      expected_rendering: "normal_visible",
      expected_render_mode: 0,
      expected_coordinates: [0.12, 0.78],
    },
    {
      attack_family: "microglyph_steganography",
      expected_rendering: "tiny_font",
      expected_render_mode: 0,
    },
  ];

  for (const scenario of scenarios) {
    const resolved = assertResolvedInjectionConfig(
      resolveInjectionConfig({
        attack_family: scenario.attack_family,
        spatial_regime: "extreme_off_page",
        rendering_regime: "normal_visible",
      })
    );

    assert.equal(resolved.attack_family, scenario.attack_family);
    assert.equal(resolved.spatial_regime, "inside_page");
    assert.equal(resolved.rendering_regime, scenario.expected_rendering);
    assert.equal(resolved.render_mode, scenario.expected_render_mode);
    assert.deepEqual(
      resolved.coordinates,
      "expected_coordinates" in scenario ? scenario.expected_coordinates : [0.5, 0.5]
    );
    assert.deepEqual(validateWithPython(resolved), resolved);
  }
});

test("margin_microtext resolves to near-margin tiny text", () => {
  const resolved = assertResolvedInjectionConfig(
    resolveInjectionConfig({
      attack_family: "margin_microtext",
      spatial_regime: "extreme_off_page",
      rendering_regime: "normal_visible",
      font_size: 12,
    })
  );

  assert.equal(resolved.attack_family, "margin_microtext");
  assert.equal(resolved.spatial_regime, "near_margin");
  assert.equal(resolved.rendering_regime, "tiny_font");
  assert.equal(resolved.render_mode, 0);
  assert.equal(resolved.font_size <= 1.2, true);
  assert.deepEqual(validateWithPython(resolved), resolved);
});
