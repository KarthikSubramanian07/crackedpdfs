import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { PDF_ATTACK_FAMILIES, PDF_ATTACK_STRENGTHS } from "../src/lib/pdf-benchmark-taxonomy";
import type {
  DatasetAttackFamily,
  DatasetBenignConfounderFamily,
  DatasetItemManifest,
} from "../src/backend/services/dataset-mode";

const WATERMARK_LAYER_ROOT = path.resolve(
  "src/backend/services/processing/layers/02-watermarking"
);
process.env.WATERMARK_LAYER_ROOT = WATERMARK_LAYER_ROOT;
process.env.ADA_LAYER_SCRIPT_PATH = path.join(
  WATERMARK_LAYER_ROOT,
  "volks-pdf-blocker-ada-layer-1",
  "inject_policy.py"
);
process.env.ADA_LAYER_POLICY_TEXT_PATH = path.join(
  WATERMARK_LAYER_ROOT,
  "volks-pdf-blocker-ada-layer-1",
  "instruction_override.txt"
);
process.env.PYTHON_BIN = process.env.BENCHMARK_PYTHON_BIN?.trim() || "python";

function resolveBenchmarkConcurrency(): number {
  const requested = Number.parseInt(
    process.env.BENCHMARK_PROCESSING_CONCURRENCY ?? "",
    10
  );
  if (Number.isFinite(requested) && requested > 0) {
    return requested;
  }

  const available =
    typeof os.availableParallelism === "function"
      ? os.availableParallelism()
      : os.cpus().length;
  return Math.max(4, Math.min(12, available));
}

function parseBooleanEnv(value: string | undefined): boolean | null {
  if (value === undefined) return null;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "y", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "n", "off"].includes(normalized)) return false;
  return null;
}

function parseCoverageEnv(value: string | undefined, defaultValue: number): number {
  if (value === undefined || value.trim().length === 0) {
    return defaultValue;
  }
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) {
    throw new Error("BENCHMARK_MIN_PAIR_COVERAGE must be a finite number between 0 and 1.");
  }
  return parsed;
}

async function main(): Promise<void> {
  const targetSamples = Math.max(
    1,
    Number.parseInt(process.env.BENCHMARK_TARGET_SAMPLES ?? "1000", 10) || 1000
  );
  const processingConcurrency = resolveBenchmarkConcurrency();
  const matchedBenignConfounders =
    parseBooleanEnv(process.env.BENCHMARK_MATCHED_CONFOUNDERS) ??
    parseBooleanEnv(process.env.BENCHMARK_MATCHED_COUNTERFACTUALS) ??
    true;
  const minPairCoverage = parseCoverageEnv(
    process.env.BENCHMARK_MIN_PAIR_COVERAGE,
    0.95
  );
  const seed = Number.parseInt(process.env.BENCHMARK_SEED ?? "20260521", 10) || 20260521;
  const runLabel =
    process.env.BENCHMARK_RUN_LABEL?.trim() || `pdf-benchmark-batch-${targetSamples}`;
  const runId = `${runLabel}-${Date.now()}`;
  const datasetName = `${runLabel}-${Date.now()}`;

  const dbMod = await import("../src/backend/db");
  const schemaMod = await import("../src/backend/db/schema");
  const drizzle = await import("drizzle-orm");
  const datasetMode = await import("../src/backend/services/dataset-mode");
  const db = dbMod.db;
  const schema = schemaMod;

  const rows = await db
    .select({ id: schema.documents.id, metadata: schema.documents.metadata })
    .from(schema.documents)
    .where(drizzle.eq(schema.documents.tenantId, "tenant-demo"));

  const documentIds = rows
    .filter((row) => {
      const metadata = row.metadata as Record<string, unknown> | null;
      return (
        metadata &&
        metadata.uploadPurpose === "dataset_source" &&
        metadata.sourceRunId === "pdf-benchmark-10k-2026-05-20"
      );
    })
    .map((row) => row.id)
    .sort((left, right) => left - right);

  if (documentIds.length === 0) {
    throw new Error("No dataset_source documents found for tenant-demo.");
  }

  console.log(
    `[benchmark] starting runId=${runId} target=${targetSamples} concurrency=${processingConcurrency} sourceDocs=${documentIds.length}`
  );

  const result = await datasetMode.generateDatasetModeRun({
    tenantId: "tenant-demo",
    documentIds,
    targetSamples,
    datasetName,
    runId,
    seed,
    freezeVersion: `freeze-${seed}`,
    processingConcurrency,
    matchedBenignConfounders,
    minPairCoverage,
    policySourceMode: "active_pool",
    splitConfig: {
      train: 0.8,
      validation: 0.1,
      test: 0.1,
      splitSeed: seed,
    },
    regimes: {
      spatial: [
        "extreme_off_page",
        "negative_off_page",
        "near_margin",
        "inside_page",
      ],
      rendering: [
        "invisible_render_mode",
        "tiny_font",
        "white_text",
        "normal_visible",
      ],
      structural: ["append_new_stream", "prepend_stream", "inject_into_existing_stream"],
      artifactWrapper: [true, false],
      messageType: [
        "instruction_override",
        "task_hijack",
        "policy_framing",
        "system_extraction",
        "refusal_suppression",
        "data_exfiltration",
        "agent_tool_manipulation",
        "summarization_steering",
      ],
      attackFamily: PDF_ATTACK_FAMILIES,
      attackStrength: PDF_ATTACK_STRENGTHS,
    },
    async onProgress(update) {
      if (
        update.processedItems === 0 ||
        update.processedItems === update.totalItems ||
        update.processedItems % 25 === 0
      ) {
        console.log(
          `[dataset-mode] ${update.stage} ${update.processedItems}/${update.totalItems} completed=${update.completedItems} failed=${update.failedItems} current=${update.currentSampleId} ${update.progressPercent}%`
        );
      }
    },
  });

  const completedItems = result.items.filter(
    (item) =>
      item.status === "completed" &&
      item.benign_file !== null &&
      item.benign_confounder_file !== null &&
      item.injected_file !== null
  );
  console.log(
    `[benchmark] done runId=${runId} completed=${result.totalCompleted} failed=${result.totalFailed} exportable=${completedItems.length}`
  );
  if (matchedBenignConfounders) {
    const coverage = auditMatchedCounterfactualCoverage(
      completedItems,
      result.items.length,
      datasetMode.selectMatchedBenignConfounderFamily
    );
    console.log(
      `[benchmark] matched triad coverage ${(coverage.coverage * 100).toFixed(2)}% (${coverage.completeTriads}/${coverage.expectedTriads}); mismatched=${coverage.mismatchedTriads}`
    );
    if (coverage.coverage < minPairCoverage) {
      throw new Error(
        `Matched counterfactual pair coverage ${(coverage.coverage * 100).toFixed(2)}% is below required ${(minPairCoverage * 100).toFixed(2)}%.`
      );
    }
  }

  const summaryPath = path.join(
    process.cwd(),
    "storage",
    "temp",
    `${runId}.summary.json`
  );
  await fs.mkdir(path.dirname(summaryPath), { recursive: true });
  await fs.writeFile(
    summaryPath,
    JSON.stringify(
      {
        runId,
        datasetName,
        targetSamples,
        processingConcurrency,
        matchedBenignConfounders,
        totalCompleted: result.totalCompleted,
        totalFailed: result.totalFailed,
        exportableItems: completedItems.length,
        manifestPath: result.manifestPath,
        metadataJsonlPath: result.metadataJsonlPath,
      },
      null,
      2
    ),
    "utf-8"
  );
  console.log(`[benchmark] summary=${summaryPath}`);
}

function auditMatchedCounterfactualCoverage(
  completedItems: DatasetItemManifest[],
  expectedTriads: number,
  selectMatchedBenignConfounderFamily: (
    attackFamily: DatasetAttackFamily
  ) => Exclude<DatasetBenignConfounderFamily, "none">
): {
  expectedTriads: number;
  completeTriads: number;
  mismatchedTriads: number;
  coverage: number;
} {
  let completeTriads = 0;
  let mismatchedTriads = 0;

  for (const item of completedItems) {
    const expectedConfounder = selectMatchedBenignConfounderFamily(item.attack_family);
    const complete =
      item.benign_file !== null &&
      item.benign_confounder_file !== null &&
      item.injected_file !== null &&
      item.benign_confounder_family === expectedConfounder &&
      item.triad_id === item.pair_id;
    if (complete) {
      completeTriads += 1;
    } else {
      mismatchedTriads += 1;
    }
  }

  return {
    expectedTriads,
    completeTriads,
    mismatchedTriads,
    coverage: expectedTriads === 0 ? 0 : completeTriads / expectedTriads,
  };
}

void main().catch((error) => {
  console.error("[benchmark] fatal error", error);
  process.exitCode = 1;
});
