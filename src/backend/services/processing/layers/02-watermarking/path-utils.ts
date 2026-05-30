import path from "path";

export const PROJECT_ROOT = process.cwd();
const DEFAULT_WATERMARK_ROOT = path.join(
  PROJECT_ROOT,
  "src",
  "backend",
  "services",
  "processing",
  "layers",
  "02-watermarking"
);

export function resolveEnvPath(key: string): string | undefined {
  const value = process.env[key];
  if (!value) {
    return undefined;
  }

  return path.isAbsolute(value) ? value : path.resolve(PROJECT_ROOT, value);
}

export function getWatermarkLayerRoot(): string {
  return resolveEnvPath("WATERMARK_LAYER_ROOT") ?? DEFAULT_WATERMARK_ROOT;
}

export function resolveWatermarkPath(...segments: string[]): string {
  return path.join(getWatermarkLayerRoot(), ...segments);
}

export function getConfusionMatrixBinariesDir(): string {
  return (
    resolveEnvPath("CONFUSION_MATRIX_BINARIES_DIR") ??
    resolveWatermarkPath("confusion-matrix-layer", "binaries")
  );
}

export function getLinkInsertionScriptPath(): string {
  return (
    resolveEnvPath("LINK_INSERTION_SCRIPT_PATH") ??
    resolveWatermarkPath("link-insertion-layer", "add_accessibility_link.py")
  );
}

export function getVolksLayerScriptPath(): string {
  return (
    resolveEnvPath("VOLKS_LAYER_SCRIPT_PATH") ??
    resolveWatermarkPath(
      "volks-screenshot-shatter-layer-1",
      "Volks_Anti_Screenshot_Layer_1.py"
    )
  );
}

export function getAdaLayerScriptPath(): string {
  return (
    resolveEnvPath("ADA_LAYER_SCRIPT_PATH") ??
    resolveWatermarkPath(
      "volks-pdf-blocker-ada-layer-1",
      "inject_policy.py"
    )
  );
}

export function getAdaPolicyTextPath(): string {
  return (
    resolveEnvPath("ADA_LAYER_POLICY_TEXT_PATH") ??
    resolveWatermarkPath(
      "volks-pdf-blocker-ada-layer-1",
      "instruction_override.txt"
    )
  );
}

export function getAdaValidationHarnessPath(): string {
  return (
    resolveEnvPath("ADA_LAYER_VALIDATION_HARNESS_PATH") ??
    resolveWatermarkPath(
      "volks-pdf-blocker-ada-layer-1",
      "validation_harness.py"
    )
  );
}

export function getAdaMessagePolicyPath(messageType?: string): string {
  const normalized =
    typeof messageType === "string" ? messageType.trim().toLowerCase() : "";

  if (normalized === "task_hijack") {
    return resolveWatermarkPath(
      "volks-pdf-blocker-ada-layer-1",
      "task_hijack.txt"
    );
  }

  if (normalized === "policy_framing") {
    return resolveWatermarkPath(
      "volks-pdf-blocker-ada-layer-1",
      "policy_framing.txt"
    );
  }

  if (normalized === "system_extraction") {
    return resolveWatermarkPath(
      "volks-pdf-blocker-ada-layer-1",
      "system_extraction.txt"
    );
  }

  if (normalized === "refusal_suppression") {
    return resolveWatermarkPath(
      "volks-pdf-blocker-ada-layer-1",
      "refusal_suppression.txt"
    );
  }

  if (normalized === "data_exfiltration") {
    return resolveWatermarkPath(
      "volks-pdf-blocker-ada-layer-1",
      "data_exfiltration.txt"
    );
  }

  if (normalized === "agent_tool_manipulation") {
    return resolveWatermarkPath(
      "volks-pdf-blocker-ada-layer-1",
      "agent_tool_manipulation.txt"
    );
  }

  if (normalized === "summarization_steering") {
    return resolveWatermarkPath(
      "volks-pdf-blocker-ada-layer-1",
      "summarization_steering.txt"
    );
  }

  // Default: instruction_override
  return getAdaPolicyTextPath();
}
