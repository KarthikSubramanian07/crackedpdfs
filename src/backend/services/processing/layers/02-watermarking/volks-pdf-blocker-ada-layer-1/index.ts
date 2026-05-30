import { execFile } from "child_process";
import { promisify } from "util";
import * as fs from "fs/promises";
import path from "path";
import {
  getAdaLayerScriptPath,
  getAdaMessagePolicyPath,
  getAdaPolicyTextPath,
} from "../path-utils";
import { getPythonExecutable } from "../python-utils";
import {
  assertResolvedInjectionConfig,
  InjectionConfig,
  resolveInjectionConfig,
} from "../injection-config";
import { PROMPT_INJECTION_MESSAGE_TYPES } from "@/lib/prompt-injection-taxonomy";

const execFileAsync = promisify(execFile);
const VERBOSE_ADA_SUCCESS_LOGS = process.env.ADA_LAYER_VERBOSE_LOGS === "true";

export interface AdaLayerOptions {
  inputPath: string;
  outputPath: string;
  policyPath?: string;
  injectionConfig?: unknown;
  timeoutMs?: number;
}

export interface AdaLayerResult {
  success: boolean;
  outputPath: string;
  metadata: {
    policyInjected: boolean;
    processingTimeMs: number;
    adaLayer: string;
    policyPath?: string;
    injectionConfig: InjectionConfig;
    attackStats: {
      num_chunks: number;
      chunk_strategy: string;
      avg_chunk_len: number;
    };
  };
  error?: string;
}

/**
 * Run the ADA policy injection layer (volks-pdf-blocker-ada-layer-1).
 * The Python script appends an off-screen /Artifact text block to each page.
 */
export async function processAdaPolicyLayer(
  options: AdaLayerOptions
): Promise<AdaLayerResult> {
  const start = Date.now();
  const scriptPath = getAdaLayerScriptPath();
  const pythonBin = getPythonExecutable();
  const policyPath = options.policyPath || getAdaPolicyTextPath();
  const injectionConfig = assertResolvedInjectionConfig(
    resolveInjectionConfig(options.injectionConfig)
  );
  const configFilename = `${path.basename(
    options.outputPath,
    path.extname(options.outputPath)
  )}_injection_config.json`;
  const configPath = path.join(path.dirname(options.outputPath), configFilename);
  const metadataPath = path.join(
    path.dirname(options.outputPath),
    `${path.basename(options.outputPath, path.extname(options.outputPath))}_injection_metadata.json`
  );
  const defaultAttackStats = {
    num_chunks: 0,
    chunk_strategy: "single_line",
    avg_chunk_len: 0,
  };

  try {
    await fs.access(scriptPath);
    await fs.access(options.inputPath);
    await fs.access(policyPath);
    await fs.writeFile(configPath, JSON.stringify(injectionConfig), "utf-8");

    const { stdout } = await execFileAsync(
      pythonBin,
      [
        scriptPath,
        options.inputPath,
        options.outputPath,
        policyPath,
        "--config",
        configPath,
        "--metadata-output",
        metadataPath,
      ],
      {
        timeout: options.timeoutMs ?? 120000,
        maxBuffer: 50 * 1024 * 1024,
      }
    );

    await fs.access(options.outputPath);
    const attackStats = await readAttackStats(metadataPath);

    const processingTimeMs = Date.now() - start;

    if (VERBOSE_ADA_SUCCESS_LOGS) {
      console.log("[ADA Layer] Success:", {
        inputPath: options.inputPath,
        outputPath: options.outputPath,
        policyPath,
        processingTimeMs,
        injectionConfig,
        stdout: stdout?.substring?.(0, 200),
      });
    }

    return {
      success: true,
      outputPath: options.outputPath,
      metadata: {
        policyInjected: true,
        processingTimeMs,
        adaLayer: "volks-pdf-blocker-ada-layer-1",
        policyPath,
        injectionConfig,
        attackStats,
      },
    };
  } catch (error) {
    const processingTimeMs = Date.now() - start;
    const errorMessage = error instanceof Error ? error.message : String(error);

    console.error("[ADA Layer] Failed:", {
      error: errorMessage,
      inputPath: options.inputPath,
      outputPath: options.outputPath,
      policyPath,
      processingTimeMs,
      injectionConfig,
    });

    return {
      success: false,
      outputPath: options.inputPath,
      metadata: {
        policyInjected: false,
        processingTimeMs,
        adaLayer: "volks-pdf-blocker-ada-layer-1",
        policyPath,
        injectionConfig,
        attackStats: defaultAttackStats,
      },
      error: errorMessage,
    };
  } finally {
    await Promise.all([
      fs.unlink(configPath).catch(() => undefined),
      fs.unlink(metadataPath).catch(() => undefined),
    ]);
  }
}

async function readAttackStats(metadataPath: string): Promise<{
  num_chunks: number;
  chunk_strategy: string;
  avg_chunk_len: number;
}> {
  try {
    const raw = await fs.readFile(metadataPath, "utf-8");
    const payload = JSON.parse(raw) as {
      attack_stats?: {
        num_chunks?: number;
        chunk_strategy?: string;
        avg_chunk_len?: number;
      };
      attackStats?: {
        num_chunks?: number;
        chunk_strategy?: string;
        avg_chunk_len?: number;
      };
    };
    const source = payload.attack_stats ?? payload.attackStats;
    return {
      num_chunks:
        typeof source?.num_chunks === "number" && Number.isFinite(source.num_chunks)
          ? source.num_chunks
          : 0,
      chunk_strategy:
        typeof source?.chunk_strategy === "string" && source.chunk_strategy.trim()
          ? source.chunk_strategy
          : "single_line",
      avg_chunk_len:
        typeof source?.avg_chunk_len === "number" && Number.isFinite(source.avg_chunk_len)
          ? source.avg_chunk_len
          : 0,
    };
  } catch {
    return {
      num_chunks: 0,
      chunk_strategy: "single_line",
      avg_chunk_len: 0,
    };
  }
}

/**
 * Validate Python environment and artifacts for ADA layer.
 */
export async function validateAdaLayerSetup(): Promise<{
  valid: boolean;
  errors: string[];
}> {
  const errors: string[] = [];
  const scriptPath = getAdaLayerScriptPath();
  const pythonBin = getPythonExecutable();
  const policyPath = getAdaPolicyTextPath();

  try {
    await fs.access(scriptPath);
  } catch {
    errors.push("ADA layer script not found");
  }

  try {
    await fs.access(policyPath);
  } catch {
    errors.push("ADA layer instruction_override.txt not found");
  }

  for (const messageType of PROMPT_INJECTION_MESSAGE_TYPES) {
    try {
      await fs.access(getAdaMessagePolicyPath(messageType));
    } catch {
      errors.push(`ADA layer policy file missing for ${messageType}`);
    }
  }

  try {
    await execFileAsync(pythonBin, ["-c", "import pikepdf"], {
      timeout: 15000,
    });
  } catch (error) {
    errors.push(
      `Python environment missing pikepdf (${error instanceof Error ? error.message : String(error)})`
    );
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
