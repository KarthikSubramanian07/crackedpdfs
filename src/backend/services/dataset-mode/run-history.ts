import { storageService } from "@/backend/services/storage";
import type { DatasetRunManifest } from "./index";

const STORAGE_PREFIX =
  (process.env.AWS_S3_PREFIX || "tenants").replace(/\/+$/, "") || "tenants";

function sanitizeSegment(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]/g, "_");
}

function asDatasetRunManifest(raw: string): DatasetRunManifest | null {
  try {
    const parsed = JSON.parse(raw) as DatasetRunManifest;
    if (
      parsed &&
      typeof parsed.run_id === "string" &&
      typeof parsed.dataset_name === "string" &&
      typeof parsed.tenant_id === "string" &&
      typeof parsed.created_at === "string" &&
      Array.isArray(parsed.items)
    ) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

export interface DatasetRunManifestRecord {
  manifestPath: string;
  manifestUrl: string;
  manifest: DatasetRunManifest;
}

export interface DatasetRunProgressSnapshot {
  runId: string;
  datasetName: string;
  status: "queued" | "running" | "completed" | "failed";
  progressPercent: number;
  processedItems: number;
  totalItems: number;
  completedItems: number;
  failedItems: number;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  manifestPath: string | null;
  manifestUrl: string | null;
  error: string | null;
}

export function buildTenantRunsPrefix(tenantId: string): string {
  const tenantSegment = sanitizeSegment(tenantId);
  return [STORAGE_PREFIX, tenantSegment, "users", tenantSegment].join("/");
}

export function buildDatasetRunProgressPath(
  tenantId: string,
  runId: string
): string {
  const tenantSegment = sanitizeSegment(tenantId);
  const runSegment = sanitizeSegment(`dataset-${runId}`);
  return [
    STORAGE_PREFIX,
    tenantSegment,
    "users",
    tenantSegment,
    runSegment,
    "processed",
    "_run-progress.json",
  ].join("/");
}

function isDatasetManifestPath(path: string): boolean {
  return (
    /\/dataset-[^/]+\/processed\/metadata\.json$/i.test(path) ||
    /\/dataset-[^/]+\/metadata\.json$/i.test(path)
  );
}

export async function listDatasetRunManifests(
  tenantId: string
): Promise<DatasetRunManifestRecord[]> {
  const prefix = buildTenantRunsPrefix(tenantId);
  const candidatePaths = (await storageService.list(prefix)).filter(
    isDatasetManifestPath
  );

  const manifests = await Promise.all(
    candidatePaths.map(async (manifestPath) => {
      try {
        const raw = await storageService.download(manifestPath);
        const parsed = asDatasetRunManifest(raw.toString("utf-8"));
        if (!parsed || parsed.tenant_id !== tenantId) {
          return null;
        }

        return {
          manifestPath,
          manifestUrl: storageService.getUrl(manifestPath),
          manifest: parsed,
        } satisfies DatasetRunManifestRecord;
      } catch {
        return null;
      }
    })
  );

  const deduped = new Map<string, DatasetRunManifestRecord>();

  for (const entry of manifests.filter(
    (value): value is DatasetRunManifestRecord => value !== null
  )) {
    const existing = deduped.get(entry.manifest.run_id);
    if (!existing) {
      deduped.set(entry.manifest.run_id, entry);
      continue;
    }

    const entryIsProcessed = /\/processed\/metadata\.json$/i.test(entry.manifestPath);
    const existingIsProcessed = /\/processed\/metadata\.json$/i.test(
      existing.manifestPath
    );

    if (entryIsProcessed && !existingIsProcessed) {
      deduped.set(entry.manifest.run_id, entry);
    }
  }

  return Array.from(deduped.values()).sort(
    (a, b) => Date.parse(b.manifest.created_at) - Date.parse(a.manifest.created_at)
  );
}

export async function getDatasetRunManifestByRunId(
  tenantId: string,
  runId: string
): Promise<DatasetRunManifestRecord | null> {
  const manifests = await listDatasetRunManifests(tenantId);
  return manifests.find((entry) => entry.manifest.run_id === runId) || null;
}

function asRunProgressSnapshot(raw: string): DatasetRunProgressSnapshot | null {
  try {
    const parsed = JSON.parse(raw) as DatasetRunProgressSnapshot;
    if (
      parsed &&
      typeof parsed.runId === "string" &&
      typeof parsed.datasetName === "string" &&
      typeof parsed.status === "string"
    ) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

export async function getDatasetRunProgressSnapshot(
  tenantId: string,
  runId: string
): Promise<DatasetRunProgressSnapshot | null> {
  const progressPath = buildDatasetRunProgressPath(tenantId, runId);
  try {
    const raw = await storageService.download(progressPath);
    const parsed = asRunProgressSnapshot(raw.toString("utf-8"));
    if (!parsed || parsed.runId !== runId) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function isDatasetProgressSnapshotPath(path: string): boolean {
  return /\/dataset-[^/]+\/processed\/_run-progress\.json$/i.test(path);
}

export async function listDatasetRunProgressSnapshots(
  tenantId: string
): Promise<DatasetRunProgressSnapshot[]> {
  const prefix = buildTenantRunsPrefix(tenantId);
  const snapshotPaths = (await storageService.list(prefix)).filter(
    isDatasetProgressSnapshotPath
  );

  const snapshots = await Promise.all(
    snapshotPaths.map(async (snapshotPath) => {
      try {
        const raw = await storageService.download(snapshotPath);
        const parsed = asRunProgressSnapshot(raw.toString("utf-8"));
        return parsed;
      } catch {
        return null;
      }
    })
  );

  return snapshots
    .filter((snapshot): snapshot is DatasetRunProgressSnapshot => snapshot !== null)
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
}
