import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import os from "node:os";
import { eq } from "drizzle-orm";
import { db } from "../src/backend/db";
import {
  documents,
  promptInjectionMessages,
} from "../src/backend/db/schema";
import { storageService } from "../src/backend/services/storage";
import {
  generateDatasetModeRun,
  selectMatchedBenignConfounderFamily,
  type DatasetItemManifest,
} from "../src/backend/services/dataset-mode";
import {
  PROMPT_INJECTION_MESSAGE_TYPES,
  type PromptInjectionMessageType,
} from "../src/lib/prompt-injection-taxonomy";
import {
  RECOMMENDED_PROMPT_INJECTION_MESSAGES,
} from "../src/lib/prompt-injection-message-library";
import {
  PDF_ATTACK_FAMILIES,
  PDF_ATTACK_STRENGTHS,
} from "../src/lib/pdf-benchmark-taxonomy";

const TENANT_ID = "tenant-demo";
const USER_ID = TENANT_ID;
const DATASET_NAME =
  process.env.BENCHMARK_DATASET_NAME?.trim() || "pdf-benchmark-10k-2026-05-20";
const RUN_ID =
  process.env.BENCHMARK_RUN_ID?.trim() || "pdf-benchmark-10k-2026-05-20";
const SOURCE_RUN_ID =
  process.env.BENCHMARK_SOURCE_RUN_ID?.trim() || RUN_ID;
const DATASET_SEED =
  Number.parseInt(process.env.BENCHMARK_SEED ?? "20260520", 10) || 20260520;
const TARGET_SAMPLES = Math.max(
  1,
  Number.parseInt(process.env.BENCHMARK_TARGET_SAMPLES ?? "10000", 10) || 10000
);
const PROCESSING_CONCURRENCY = (() => {
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
})();
const MATCHED_BENIGN_CONFOUNDERS =
  parseBooleanEnv(process.env.BENCHMARK_MATCHED_CONFOUNDERS) ??
  parseBooleanEnv(process.env.BENCHMARK_MATCHED_COUNTERFACTUALS) ??
  true;
const MIN_PAIR_COVERAGE = parseCoverageEnv(
  process.env.BENCHMARK_MIN_PAIR_COVERAGE,
  0.95
);

const SOURCE_ROOT = path.resolve(
  process.env.BENCHMARK_SOURCE_ROOT?.trim() ||
    path.join(process.cwd(), "generated", "benign-usenix-10k")
);
const SOURCE_BASE_DIR = path.join(SOURCE_ROOT, "base");
const SOURCE_MANIFEST_PATH = path.join(SOURCE_ROOT, "manifest.jsonl");

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

const DETECTOR_RAW_DIR = path.resolve("lightweight-detector/data/raw");
const DETECTOR_BENIGN_DIR = path.join(DETECTOR_RAW_DIR, "benign");
const DETECTOR_INJECTED_DIR = path.join(DETECTOR_RAW_DIR, "injected");
const DETECTOR_METADATA_DIR = path.join(DETECTOR_RAW_DIR, "metadata");
const DETECTOR_METADATA_PATH = path.join(DETECTOR_RAW_DIR, "metadata.json");
const DETECTOR_METADATA_JSONL_PATH = path.join(DETECTOR_RAW_DIR, "metadata.jsonl");

type ExistingPromptKey = `${PromptInjectionMessageType}::${string}`;

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
  console.log(`[benchmark] starting ${RUN_ID}`);
  console.log(`[benchmark] processing concurrency ${PROCESSING_CONCURRENCY}`);
  console.log(
    `[benchmark] matched benign confounders ${MATCHED_BENIGN_CONFOUNDERS ? "enabled" : "disabled"}`
  );

  const sourceFiles = await collectSourceFiles();
  console.log(`[benchmark] found ${sourceFiles.length} benign PDFs in ${SOURCE_BASE_DIR}`);

  await ensurePromptLibraryImported(TENANT_ID);
  console.log("[benchmark] prompt library ready");

  const documentIds = await getOrImportSourceDocuments(sourceFiles);
  console.log(`[benchmark] imported ${documentIds.length} source documents`);

  const run = await generateDatasetModeRun({
    tenantId: TENANT_ID,
    documentIds,
    targetSamples: TARGET_SAMPLES,
    datasetName: DATASET_NAME,
    runId: RUN_ID,
    seed: DATASET_SEED,
    freezeVersion: "freeze-2026-05-20",
    processingConcurrency: PROCESSING_CONCURRENCY,
    matchedBenignConfounders: MATCHED_BENIGN_CONFOUNDERS,
    minPairCoverage: MIN_PAIR_COVERAGE,
    policySourceMode: "active_pool",
    splitConfig: {
      train: 0.8,
      validation: 0.1,
      test: 0.1,
      splitSeed: DATASET_SEED,
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
      structural: [
        "append_new_stream",
        "prepend_stream",
        "inject_into_existing_stream",
      ],
      artifactWrapper: [true, false],
      messageType: PROMPT_INJECTION_MESSAGE_TYPES,
      attackFamily: PDF_ATTACK_FAMILIES,
      attackStrength: PDF_ATTACK_STRENGTHS,
    },
    onProgress(progress) {
      if (
        progress.processedItems === 0 ||
        progress.processedItems === progress.totalItems ||
        progress.processedItems % 100 === 0
      ) {
        console.log(
          `[dataset-mode] ${progress.stage} ${progress.processedItems}/${progress.totalItems} completed=${progress.completedItems} failed=${progress.failedItems} ${progress.progressPercent}%`
        );
      }
    },
  });

  console.log(
    `[benchmark] dataset-mode completed completed=${run.totalCompleted} failed=${run.totalFailed}`
  );

  const completedItems = run.items.filter(
    (item) =>
      item.status === "completed" &&
      item.benign_file !== null &&
      item.benign_confounder_file !== null &&
      item.injected_file !== null
  );
  if (completedItems.length === 0) {
    throw new Error(
      "Dataset generation completed without any exportable samples. Inspect metadata.json for failure causes before rerunning."
    );
  }
  if (completedItems.length !== run.items.length) {
    console.warn(
      `[benchmark] exporting completed subset only: ${completedItems.length}/${run.items.length}`
    );
  }
  if (MATCHED_BENIGN_CONFOUNDERS) {
    const coverage = auditMatchedCounterfactualCoverage(completedItems, run.items.length);
    console.log(
      `[benchmark] matched triad coverage ${(coverage.coverage * 100).toFixed(2)}% (${coverage.completeTriads}/${coverage.expectedTriads}); mismatched=${coverage.mismatchedTriads}`
    );
    if (coverage.coverage < MIN_PAIR_COVERAGE) {
      throw new Error(
        `Matched counterfactual pair coverage ${(coverage.coverage * 100).toFixed(2)}% is below required ${(MIN_PAIR_COVERAGE * 100).toFixed(2)}%. Refusing to export non-publication-grade corpus.`
      );
    }
  }

  await exportRunForDetector(completedItems, {
    manifestPath: run.manifestPath,
  });

  console.log(`[benchmark] detector export ready under ${DETECTOR_RAW_DIR}`);
}

async function collectSourceFiles(): Promise<string[]> {
  const manifestExists = await exists(SOURCE_MANIFEST_PATH);
  if (manifestExists) {
    const lines = (await fs.readFile(SOURCE_MANIFEST_PATH, "utf-8"))
      .split(/\r?\n/)
      .filter((line) => line.trim().length > 0);
    const manifestPaths: string[] = [];
    for (const line of lines) {
      const payload = JSON.parse(line) as {
        output_relpath?: string;
        pdf_path?: string;
      };
      if (
        typeof payload.output_relpath === "string" &&
        payload.output_relpath.endsWith(".pdf")
      ) {
        manifestPaths.push(path.join(SOURCE_ROOT, payload.output_relpath));
        continue;
      }
      if (typeof payload.pdf_path === "string" && payload.pdf_path.endsWith(".pdf")) {
        manifestPaths.push(path.resolve(payload.pdf_path));
      }
    }
    if (manifestPaths.length > 0) {
      return manifestPaths.sort((left, right) => left.localeCompare(right));
    }
  }

  const entries = await fs.readdir(SOURCE_BASE_DIR, { withFileTypes: true });
  const pdfs: string[] = [];
  for (const entry of entries) {
    if (entry.isFile() && entry.name.toLowerCase().endsWith(".pdf")) {
      pdfs.push(path.join(SOURCE_BASE_DIR, entry.name));
    }
  }
  return pdfs.sort((left, right) => left.localeCompare(right));
}

async function ensurePromptLibraryImported(tenantId: string): Promise<void> {
  const existing = await db
    .select({
      name: promptInjectionMessages.name,
      messageType: promptInjectionMessages.messageType,
    })
    .from(promptInjectionMessages)
    .where(eq(promptInjectionMessages.tenantId, tenantId));

  const existingKeys = new Set<ExistingPromptKey>();
  for (const row of existing) {
    if (!PROMPT_INJECTION_MESSAGE_TYPES.includes(row.messageType as PromptInjectionMessageType)) {
      continue;
    }
    const key = buildPromptKey(
      row.messageType as PromptInjectionMessageType,
      row.name
    );
    existingKeys.add(key);
  }

  const now = new Date().toISOString();
  const missing = RECOMMENDED_PROMPT_INJECTION_MESSAGES.filter((message) => {
    return !existingKeys.has(buildPromptKey(message.messageType, message.name));
  });

  if (missing.length === 0) {
    return;
  }

  await db.insert(promptInjectionMessages).values(
    missing.map((message) => ({
      tenantId,
      name: message.name,
      messageType: message.messageType,
      content: message.content,
      isActive: true,
      createdAt: now,
      updatedAt: now,
    }))
  );
}

function buildPromptKey(
  messageType: PromptInjectionMessageType,
  name: string
): ExistingPromptKey {
  return `${messageType}::${name.trim().toLowerCase()}`;
}

async function importSourceDocuments(sourceFiles: string[]): Promise<number[]> {
  const documentIds: number[] = [];
  const storageRoot = path.resolve("storage");
  const batchSize = 250;

  for (let offset = 0; offset < sourceFiles.length; offset += batchSize) {
    const batch = sourceFiles.slice(offset, offset + batchSize);
    const pendingInsertValues: Array<typeof documents.$inferInsert> = [];

    for (const filePath of batch) {
      const originalFilename = path.basename(filePath);
      const fileStats = await fs.stat(filePath);
      const storageDocumentId = `dataset-source-${randomUUID()}`;
      const relativeStoragePath = buildStorageUploadPath({
        tenantId: TENANT_ID,
        userId: USER_ID,
        documentId: storageDocumentId,
        filename: originalFilename,
      });
      const absoluteStoragePath = path.join(storageRoot, relativeStoragePath);
      await fs.mkdir(path.dirname(absoluteStoragePath), { recursive: true });
      await fs.copyFile(filePath, absoluteStoragePath);

      const now = new Date().toISOString();
      pendingInsertValues.push({
        tenantId: TENANT_ID,
        filename: originalFilename,
        originalFilename,
        filePath: relativeStoragePath,
        fileSize: Number(fileStats.size),
        fileType: "application/pdf",
        status: "completed",
        accessToken: randomUUID(),
        uploadedAt: now,
        processedAt: now,
        processingCompletedAt: now,
        metadata: {
          uploadPurpose: "dataset_source",
          benchmarkSource: true,
          sourceRunId: SOURCE_RUN_ID,
          datasetRunId: RUN_ID,
          sourcePath: filePath,
          storageDocumentId,
        },
      });
    }

    const insertedRows = await db
      .insert(documents)
      .values(pendingInsertValues)
      .returning({ id: documents.id });

    for (const row of insertedRows) {
      documentIds.push(row.id);
    }

    const processedCount = Math.min(offset + batch.length, sourceFiles.length);
    console.log(`[benchmark] source import ${processedCount}/${sourceFiles.length}`);
  }

  return documentIds;
}

async function getOrImportSourceDocuments(sourceFiles: string[]): Promise<number[]> {
  const existingRows = await db
    .select({
      id: documents.id,
      metadata: documents.metadata,
    })
    .from(documents)
    .where(eq(documents.tenantId, TENANT_ID));

  const reusedIds: number[] = [];
  for (const row of existingRows) {
    const metadata = row.metadata as Record<string, unknown> | null;
    if (
      metadata &&
      metadata.sourceRunId === SOURCE_RUN_ID &&
      metadata.uploadPurpose === "dataset_source"
    ) {
      reusedIds.push(row.id);
    }
  }

  if (reusedIds.length > 0) {
    reusedIds.sort((left, right) => left - right);
    console.log(`[benchmark] reusing ${reusedIds.length} existing source documents`);
    return reusedIds;
  }

  return importSourceDocuments(sourceFiles);
}

function buildStorageUploadPath(input: {
  tenantId: string;
  userId: string;
  documentId: string;
  filename: string;
}): string {
  const sanitize = (value: string) => value.replace(/[^a-zA-Z0-9._-]/g, "_");
  return [
    "tenants",
    sanitize(input.tenantId),
    "users",
    sanitize(input.userId),
    sanitize(input.documentId),
    "uploads",
    sanitize(input.filename),
  ].join("/");
}

async function exportRunForDetector(
  items: DatasetItemManifest[],
  paths: { manifestPath: string }
): Promise<void> {
  await fs.rm(DETECTOR_RAW_DIR, { recursive: true, force: true });
  await fs.mkdir(DETECTOR_BENIGN_DIR, { recursive: true });
  await fs.mkdir(DETECTOR_INJECTED_DIR, { recursive: true });
  await fs.mkdir(DETECTOR_METADATA_DIR, { recursive: true });

  const manifestBuffer = await storageService.download(paths.manifestPath);
  await fs.writeFile(DETECTOR_METADATA_PATH, manifestBuffer);
  const detectorMetadataRecords = buildDetectorCanonicalMetadata(items);
  await fs.writeFile(
    DETECTOR_METADATA_JSONL_PATH,
    detectorMetadataRecords.map((record) => JSON.stringify(record)).join("\n") + "\n",
    "utf-8"
  );

  for (let index = 0; index < items.length; index++) {
    const item = items[index];
    const benignFile = item.benign_file!;
    const benignConfounderFile = item.benign_confounder_file!;
    const injectedFile = item.injected_file!;

    const benignBuffer = await storageService.download(benignFile.path);
    const benignConfounderBuffer = await storageService.download(benignConfounderFile.path);
    const injectedBuffer = await storageService.download(injectedFile.path);
    const metadataPath = path.join(
      DETECTOR_METADATA_DIR,
      `${item.sample_id}.metadata.json`
    );

    await fs.writeFile(
      path.join(DETECTOR_BENIGN_DIR, benignFile.filename),
      benignBuffer
    );
    await fs.writeFile(
      path.join(DETECTOR_BENIGN_DIR, benignConfounderFile.filename),
      benignConfounderBuffer
    );
    await fs.writeFile(
      path.join(DETECTOR_INJECTED_DIR, injectedFile.filename),
      injectedBuffer
    );
    await fs.writeFile(metadataPath, JSON.stringify(item, null, 2), "utf-8");

    if ((index + 1) % 250 === 0 || index + 1 === items.length) {
      console.log(`[benchmark] detector export ${index + 1}/${items.length}`);
    }
  }
}

function auditMatchedCounterfactualCoverage(
  completedItems: DatasetItemManifest[],
  expectedTriads: number
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
    const hasCompleteFiles =
      item.benign_file !== null &&
      item.benign_confounder_file !== null &&
      item.injected_file !== null;
    const hasMatchedConfounder = item.benign_confounder_family === expectedConfounder;
    const hasStableTriadId =
      typeof item.pair_id === "string" &&
      item.pair_id.length > 0 &&
      item.triad_id === item.pair_id;

    if (hasCompleteFiles && hasMatchedConfounder && hasStableTriadId) {
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

function buildDetectorCanonicalMetadata(
  items: DatasetItemManifest[]
): Array<Record<string, unknown>> {
  const records: Array<Record<string, unknown>> = [];

  for (const item of items) {
    if (!item.benign_file || !item.benign_confounder_file || !item.injected_file) {
      continue;
    }

    const shared = {
      base_pdf_id: item.base_pdf_id,
      source_type: item.benign_registry.source_type ?? "unknown",
      seed: item.seed,
      freeze_version: RUN_ID,
      split_group: item.split_group,
      dataset_split: item.dataset_split,
      sample_id: item.sample_id,
      pair_id: item.pair_id,
      triad_id: item.triad_id,
      source_document_id: item.source_document_id,
      source_original_filename: item.source_original_filename,
      layout_complexity: item.benign_registry.layout_complexity ?? null,
      font_band: item.benign_registry.font_band ?? null,
      benign_stratum_key: item.benign_stratum_key,
      policy_message_source: item.policy_message_source,
      message_variant_id: item.message_variant_id,
      target_message_type: item.message_type,
      target_attack_family: item.attack_family,
      target_benign_confounder_family: item.benign_confounder_family,
      target_physical_attack_family: item.target_physical_regime.attack_family,
      target_physical_attack_strength: item.target_physical_regime.attack_strength,
      target_physical_spatial_regime: item.target_physical_regime.spatial_regime,
      target_physical_rendering_regime: item.target_physical_regime.rendering_regime,
      target_physical_structural_regime: item.target_physical_regime.structural_regime,
      target_physical_artifact_wrapper: item.target_physical_regime.artifact_wrapper,
      confounder_physical_attack_family:
        item.confounder_physical_regime.attack_family,
      confounder_physical_attack_strength:
        item.confounder_physical_regime.attack_strength,
      confounder_physical_spatial_regime:
        item.confounder_physical_regime.spatial_regime,
      confounder_physical_rendering_regime:
        item.confounder_physical_regime.rendering_regime,
      confounder_physical_structural_regime:
        item.confounder_physical_regime.structural_regime,
      confounder_physical_artifact_wrapper:
        item.confounder_physical_regime.artifact_wrapper,
      attack_strength: item.attack_strength,
      num_chunks: item.num_chunks,
      chunk_strategy: item.chunk_strategy,
      avg_chunk_len: item.avg_chunk_len,
      raw_injected_text: null,
      message_length_chars: null,
    };

    records.push({
      ...shared,
      pdf_id: `${item.sample_id}.benign`,
      pdf_role: "benign_original",
      file_path: `benign/${item.benign_file.filename}`,
      label: 0,
      spatial_regime: "none",
      rendering_regime: "none",
      structural_regime: "none",
      message_type: "none",
      attack_family: "none",
      artifact_wrapper: false,
      benign_confounder_family: "none",
      attack_strength: "none",
      policy_message_source: "none",
      message_variant_id: "none",
      num_chunks: 0,
      chunk_strategy: "none",
      avg_chunk_len: 0,
    });

    records.push({
      ...shared,
      pdf_id: `${item.sample_id}.benign_confounder`,
      pdf_role: "benign_confounder",
      file_path: `benign/${item.benign_confounder_file.filename}`,
      label: 0,
      spatial_regime: "none",
      rendering_regime: "none",
      structural_regime: "none",
      message_type: "none",
      attack_family: "none",
      artifact_wrapper: false,
      benign_confounder_family: item.benign_confounder_family,
      attack_strength: "none",
      policy_message_source: "none",
      message_variant_id: "none",
      num_chunks: 0,
      chunk_strategy: "none",
      avg_chunk_len: 0,
    });

    records.push({
      ...shared,
      pdf_id: `${item.sample_id}.injected`,
      pdf_role: "injected_attack",
      file_path: `injected/${item.injected_file.filename}`,
      label: 1,
      spatial_regime: item.spatial_regime,
      rendering_regime: item.rendering_regime,
      structural_regime: item.structural_regime,
      message_type: item.message_type,
      attack_family: item.attack_family,
      artifact_wrapper: item.artifact_wrapper,
      benign_confounder_family: "none",
    });
  }

  return records;
}

async function exists(targetPath: string): Promise<boolean> {
  try {
    await fs.access(targetPath);
    return true;
  } catch {
    return false;
  }
}

void main().catch((error) => {
  console.error("[benchmark] fatal error", error);
  process.exitCode = 1;
});
