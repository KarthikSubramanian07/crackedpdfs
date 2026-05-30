import type { DatasetGenerationResult } from "./index";

export type DatasetTrackedStatus = "queued" | "running" | "completed" | "failed";

export interface DatasetTrackedRun {
  runId: string;
  tenantId: string;
  datasetName: string;
  status: DatasetTrackedStatus;
  progressPercent: number;
  processedItems: number;
  totalItems: number;
  completedItems: number;
  failedItems: number;
  currentSampleId: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string;
  completedAt: string | null;
  targetSamplesRequested: number;
  manifestPath: string | null;
  manifestUrl: string | null;
  error: string | null;
}

const trackedRuns = new Map<string, DatasetTrackedRun>();
const MAX_TRACKED_RUNS = 500;

function nowIso(): string {
  return new Date().toISOString();
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 100) return 100;
  return Number(value.toFixed(2));
}

function pruneTracker() {
  if (trackedRuns.size <= MAX_TRACKED_RUNS) {
    return;
  }
  const sorted = Array.from(trackedRuns.values()).sort(
    (a, b) => Date.parse(a.updatedAt) - Date.parse(b.updatedAt)
  );
  const removeCount = trackedRuns.size - MAX_TRACKED_RUNS;
  for (let index = 0; index < removeCount; index += 1) {
    trackedRuns.delete(sorted[index].runId);
  }
}

export function startTrackedDatasetRun(input: {
  runId: string;
  tenantId: string;
  datasetName: string;
  targetSamplesRequested: number;
}): DatasetTrackedRun {
  const timestamp = nowIso();
  const next: DatasetTrackedRun = {
    runId: input.runId,
    tenantId: input.tenantId,
    datasetName: input.datasetName,
    status: "running",
    progressPercent: 0,
    processedItems: 0,
    totalItems: input.targetSamplesRequested,
    completedItems: 0,
    failedItems: 0,
    currentSampleId: null,
    createdAt: timestamp,
    updatedAt: timestamp,
    startedAt: timestamp,
    completedAt: null,
    targetSamplesRequested: input.targetSamplesRequested,
    manifestPath: null,
    manifestUrl: null,
    error: null,
  };
  trackedRuns.set(input.runId, next);
  pruneTracker();
  return next;
}

export function updateTrackedDatasetRun(
  runId: string,
  patch: Partial<
    Pick<
      DatasetTrackedRun,
      | "status"
      | "progressPercent"
      | "processedItems"
      | "totalItems"
      | "completedItems"
      | "failedItems"
      | "currentSampleId"
      | "error"
      | "manifestPath"
      | "manifestUrl"
    >
  >
): DatasetTrackedRun | null {
  const current = trackedRuns.get(runId);
  if (!current) {
    return null;
  }

  const next: DatasetTrackedRun = {
    ...current,
    ...patch,
    progressPercent:
      patch.progressPercent !== undefined
        ? clampPercent(patch.progressPercent)
        : current.progressPercent,
    updatedAt: nowIso(),
  };

  if (next.status === "completed" || next.status === "failed") {
    next.completedAt = next.completedAt || nowIso();
  }

  trackedRuns.set(runId, next);
  return next;
}

export function completeTrackedDatasetRun(
  runId: string,
  result: DatasetGenerationResult
): DatasetTrackedRun | null {
  const totalItems = result.totalCompleted + result.totalFailed;
  return updateTrackedDatasetRun(runId, {
    status: "completed",
    progressPercent: 100,
    processedItems: totalItems,
    totalItems: totalItems || result.targetSamplesRequested,
    completedItems: result.totalCompleted,
    failedItems: result.totalFailed,
    currentSampleId: null,
    manifestPath: result.manifestPath,
    manifestUrl: result.manifestUrl,
    error: null,
  });
}

export function failTrackedDatasetRun(
  runId: string,
  error: string
): DatasetTrackedRun | null {
  return updateTrackedDatasetRun(runId, {
    status: "failed",
    currentSampleId: null,
    error,
  });
}

export function getTrackedDatasetRun(
  tenantId: string,
  runId: string
): DatasetTrackedRun | null {
  const run = trackedRuns.get(runId);
  if (!run || run.tenantId !== tenantId) {
    return null;
  }
  return run;
}

export function listTrackedDatasetRuns(tenantId: string): DatasetTrackedRun[] {
  return Array.from(trackedRuns.values())
    .filter((run) => run.tenantId === tenantId)
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
}
