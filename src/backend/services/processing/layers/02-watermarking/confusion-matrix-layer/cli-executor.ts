/**
 * CLI Executor for Rust Confusion Matrix Layer
 * 
 * Executes the Rust binary as a subprocess with full error handling,
 * timeout protection, and progress tracking.
 */

import { spawn } from "child_process";
import * as path from "path";
import * as fs from "fs/promises";
import { getConfusionMatrixBinariesDir, resolveEnvPath } from "../path-utils";

export interface ConfusionMatrixConfig {
  dpi?: number;
  noiseEpsilon?: number;
  jpegQuality?: number;
  weightsPath?: string;
  timeoutMs?: number;
}

export interface ConfusionMatrixResult {
  success: boolean;
  outputPath?: string;
  pageCount?: number;
  error?: string;
  stderr?: string;
  executionTimeMs: number;
}

const DEFAULT_TIMEOUT_MS = 300000; // 5 minutes

/**
 * Execute Rust confusion matrix layer via CLI
 */
export async function executeConfusionMatrixLayer(
  inputPdfPath: string,
  outputDir: string,
  config: ConfusionMatrixConfig = {}
): Promise<ConfusionMatrixResult> {
  const startTime = Date.now();

  try {
    // Validate input file exists
    await fs.access(inputPdfPath);

    // Ensure output directory exists
    await fs.mkdir(outputDir, { recursive: true });

    // Get binary path
    const binaryPath = getBinaryPath();

    // Build arguments
    const args = [inputPdfPath, outputDir];

    // Environment variables for configuration
    const env = {
      ...process.env,
      ...(config.dpi && { NOISE_LAYER_DPI: config.dpi.toString() }),
      ...(config.noiseEpsilon && {
        NOISE_LAYER_EPSILON: config.noiseEpsilon.toString(),
      }),
      ...(config.jpegQuality && {
        NOISE_LAYER_JPEG_QUALITY: config.jpegQuality.toString(),
      }),
      ...(config.weightsPath && {
        NOISE_LAYER_WEIGHTS_PATH: config.weightsPath,
      }),
    };

    const result = await executeBinary(
      binaryPath,
      args,
      env,
      config.timeoutMs || DEFAULT_TIMEOUT_MS
    );

    const executionTimeMs = Date.now() - startTime;

    if (result.exitCode !== 0) {
      return {
        success: false,
        error: `Binary exited with code ${result.exitCode}`,
        stderr: result.stderr,
        executionTimeMs,
      };
    }

    // Parse output to extract result path and page count
    const outputPath = parseOutputPath(result.stdout, outputDir);
    const pageCount = parsePageCount(result.stdout);

    return {
      success: true,
      outputPath,
      pageCount,
      executionTimeMs,
    };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
      executionTimeMs: Date.now() - startTime,
    };
  }
}

/**
 * Get platform-specific binary path
 */
function getBinaryPath(): string {
  const platform = process.platform;
  const binaryName =
    platform === "win32" ? "noise_stuffy_layer.exe" : "noise_stuffy_layer";

  const binaryPath = path.join(getConfusionMatrixBinariesDir(), binaryName);

  // Check if binary exists
  try {
    require("fs").accessSync(binaryPath, require("fs").constants.X_OK);
    return binaryPath;
  } catch {
    throw new Error(
      `Rust binary not found at ${binaryPath}. Run build.sh first.`
    );
  }
}

function getLibrarySearchPaths(): string[] {
  const paths = new Set<string>();
  const binariesDir = getConfusionMatrixBinariesDir();
  paths.add(binariesDir);

  const pdfiumLib = resolveEnvPath("PDFIUM_DYNAMIC_LIB_PATH");
  if (pdfiumLib) {
    paths.add(path.dirname(pdfiumLib));
  }

  const libtorchRoot =
    resolveEnvPath("LIBTORCH") ?? resolveEnvPath("TORCH_HOME");
  if (libtorchRoot) {
    paths.add(path.join(libtorchRoot, "lib"));
    paths.add(path.join(libtorchRoot, "bin"));
  }

  return Array.from(paths).filter(Boolean);
}

function applyLibraryPaths(
  env: NodeJS.ProcessEnv,
  extraPaths: string[]
): NodeJS.ProcessEnv {
  if (extraPaths.length === 0) {
    return env;
  }

  const delimiter = path.delimiter;
  const appendPaths = (existing: string | undefined) => {
    const cleanExisting = existing ?? "";
    const additions = extraPaths.join(delimiter);
    return cleanExisting
      ? `${additions}${delimiter}${cleanExisting}`
      : additions;
  };

  const mergedEnv = { ...env };
  mergedEnv.PATH = appendPaths(env.PATH || process.env.PATH);

  if (process.platform === "darwin") {
    mergedEnv.DYLD_LIBRARY_PATH = appendPaths(
      env.DYLD_LIBRARY_PATH || process.env.DYLD_LIBRARY_PATH
    );
  } else if (process.platform !== "win32") {
    mergedEnv.LD_LIBRARY_PATH = appendPaths(
      env.LD_LIBRARY_PATH || process.env.LD_LIBRARY_PATH
    );
  }

  return mergedEnv;
}

/**
 * Execute binary with timeout protection
 */
function executeBinary(
  binaryPath: string,
  args: string[],
  env: NodeJS.ProcessEnv,
  timeoutMs: number
): Promise<{ exitCode: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const envWithPaths = applyLibraryPaths(env, getLibrarySearchPaths());

    const child = spawn(binaryPath, args, {
      env: envWithPaths,
      stdio: ["ignore", "pipe", "pipe"],
    });

    // Timeout handler
    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      reject(new Error(`Process timed out after ${timeoutMs}ms`));
    }, timeoutMs);

    child.stdout?.on("data", (data) => {
      stdout += data.toString();
    });

    child.stderr?.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });

    child.on("close", (code) => {
      clearTimeout(timeout);
      if (!timedOut) {
        resolve({
          exitCode: code || 0,
          stdout,
          stderr,
        });
      }
    });
  });
}

/**
 * Parse output PDF path from stdout
 */
function parseOutputPath(stdout: string, outputDir: string): string {
  const match = stdout.match(/at (.+\.pdf)/);
  if (match) {
    return match[1];
  }

  // Fallback: construct expected path
  return path.join(outputDir, "novel_noisy_pdfs", "b_perceptual_noisy.pdf");
}

/**
 * Parse page count from stdout
 */
function parsePageCount(stdout: string): number | undefined {
  const match = stdout.match(/(\d+) pages/);
  return match ? parseInt(match[1], 10) : undefined;
}

/**
 * Validate binary and dependencies
 */
export async function validateBinarySetup(): Promise<{
  valid: boolean;
  errors: string[];
}> {
  const errors: string[] = [];

  try {
    // Check binary exists
    getBinaryPath();
  } catch (error) {
    errors.push(
      error instanceof Error ? error.message : "Binary not found"
    );
  }

  // Check Pdfium library
  const platform = process.platform;
  const pdfiumName =
    platform === "win32"
      ? "pdfium.dll"
      : platform === "darwin"
      ? "libpdfium.dylib"
      : "libpdfium.so";

  const pdfiumPath = path.join(getConfusionMatrixBinariesDir(), pdfiumName);

  try {
    await fs.access(pdfiumPath);
  } catch {
    errors.push(
      `Pdfium library not found at ${pdfiumPath}. Download from https://github.com/bblanchon/pdfium-binaries/releases`
    );
  }

  // Check libtorch (tch-rs handles this automatically, but warn if not found)
  if (!process.env.LIBTORCH && !process.env.TORCH_HOME) {
    errors.push(
      "Warning: LIBTORCH or TORCH_HOME not set. Ensure PyTorch C++ libraries are installed."
    );
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
