import { promisify } from "node:util";
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import { getPythonExecutable } from "@/backend/services/processing/layers/02-watermarking/python-utils";
import { getAdaValidationHarnessPath } from "@/backend/services/processing/layers/02-watermarking/path-utils";

const execFileAsync = promisify(execFile);
const HARNESS_VERSION = "phase5-v2";

export interface ValidationHarnessOptions {
  pdfPath: string;
  expectedMarker: string;
  expectedRawExtraction: boolean;
  includeRendererCheck?: boolean;
  timeoutMs?: number;
}

export interface ValidationRawExtractionCheck {
  passed: boolean;
  found_marker: boolean;
  expected_found_marker: boolean;
  matched_marker_count: number;
  snippet: string | null;
}

export interface ValidationRenderVisibilityCheck {
  passed: boolean;
  reason: string;
  mode?: string;
  marker_instances: number;
  inferred_hidden_instances: number;
  inferred_visible_instances: number;
  evidence: Array<{
    page: number;
    x: number | null;
    y: number | null;
    page_width: number;
    page_height: number;
    render_mode: number | null;
    font_size: number | null;
    color: [number, number, number] | null;
    inferred_hidden: boolean;
    hidden_reasons: string[];
  }>;
  renderer_evidence?: {
    ran: boolean;
    engine: string;
    dpi: number;
    pages_scanned: number;
    marker_visible: boolean;
    visible_pages: number[];
    marker_tokens: string[];
    token_threshold: number;
    page_evidence: Array<{
      page: number;
      full_marker_match: boolean;
      matched_tokens: string[];
      ocr_excerpt: string | null;
      ocr_word_count: number;
      ocr_mean_confidence: number | null;
    }>;
    error: string | null;
  };
}

export interface ValidationExtractorOutcome {
  name: string;
  available: boolean;
  ran: boolean;
  found_marker: boolean;
  matched_marker_count: number;
  snippet: string | null;
  extracted_chars: number;
  error: string | null;
  engine?: string;
}

export interface ValidationExtractorMatrixCheck {
  passed: boolean;
  reason: string;
  expected_found_marker: boolean;
  min_extractors_required: number;
  available_extractors: number;
  ran_extractors: number;
  positive_extractors: number;
  negative_extractors: number;
  found_by: string[];
  missed_by: string[];
  extractors: ValidationExtractorOutcome[];
}

export interface ValidationHarnessResult {
  success: boolean;
  harness_version: string;
  pdf_path: string;
  expected_marker: string;
  expected_raw_extraction: boolean;
  raw_extraction_check: ValidationRawExtractionCheck;
  extractor_matrix_check: ValidationExtractorMatrixCheck;
  render_visibility_check: ValidationRenderVisibilityCheck;
  parse_errors: number;
  error?: string;
}

export async function runValidationHarness(
  options: ValidationHarnessOptions
): Promise<ValidationHarnessResult> {
  const scriptPath = getAdaValidationHarnessPath();
  const pythonBin = getPythonExecutable();

  try {
    await fs.access(scriptPath);
  } catch (error) {
    return fallbackFailure(options, `Validation harness script missing: ${scriptPath}`, error);
  }

  try {
    await fs.access(options.pdfPath);
  } catch (error) {
    return fallbackFailure(options, `PDF path is missing: ${options.pdfPath}`, error);
  }

  try {
    const { stdout } = await execFileAsync(
      pythonBin,
      [
        scriptPath,
        "--input",
        options.pdfPath,
        "--marker",
        options.expectedMarker,
        "--expected-raw",
        options.expectedRawExtraction ? "true" : "false",
        ...(options.includeRendererCheck === false ? ["--skip-renderer"] : []),
      ],
      {
        timeout: options.timeoutMs ?? 60000,
        maxBuffer: 20 * 1024 * 1024,
      }
    );

    const parsed = parseHarnessOutput(stdout);
    if (!parsed) {
      return fallbackFailure(
        options,
        "Validation harness returned non-JSON output."
      );
    }

    return {
      ...parsed,
      harness_version: parsed.harness_version || HARNESS_VERSION,
    };
  } catch (error) {
    return fallbackFailure(
      options,
      error instanceof Error ? error.message : "Validation harness execution failed.",
      error
    );
  }
}

function parseHarnessOutput(stdout: string): ValidationHarnessResult | null {
  const trimmed = stdout.trim();
  if (!trimmed) return null;

  try {
    return JSON.parse(trimmed) as ValidationHarnessResult;
  } catch {
    const lines = trimmed.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    for (let i = lines.length - 1; i >= 0; i--) {
      try {
        return JSON.parse(lines[i]) as ValidationHarnessResult;
      } catch {}
    }
    return null;
  }
}

function fallbackFailure(
  options: ValidationHarnessOptions,
  reason: string,
  error?: unknown
): ValidationHarnessResult {
  const message =
    error instanceof Error ? `${reason} (${error.message})` : reason;

  return {
    success: false,
    harness_version: HARNESS_VERSION,
    pdf_path: options.pdfPath,
    expected_marker: options.expectedMarker,
    expected_raw_extraction: options.expectedRawExtraction,
    raw_extraction_check: {
      passed: false,
      found_marker: false,
      expected_found_marker: options.expectedRawExtraction,
      matched_marker_count: 0,
      snippet: null,
    },
    extractor_matrix_check: {
      passed: false,
      reason: "Validation harness unavailable",
      expected_found_marker: options.expectedRawExtraction,
      min_extractors_required: 2,
      available_extractors: 0,
      ran_extractors: 0,
      positive_extractors: 0,
      negative_extractors: 0,
      found_by: [],
      missed_by: [],
      extractors: [],
    },
    render_visibility_check: {
      passed: false,
      reason: "Validation harness unavailable",
      marker_instances: 0,
      inferred_hidden_instances: 0,
      inferred_visible_instances: 0,
      evidence: [],
      renderer_evidence: {
        ran: false,
        engine: "pymupdf+pytesseract",
        dpi: 200,
        pages_scanned: 0,
        marker_visible: false,
        visible_pages: [],
        marker_tokens: [],
        token_threshold: 2,
        page_evidence: [],
        error: "Validation harness unavailable",
      },
    },
    parse_errors: 0,
    error: message,
  };
}
