export type BenignSourceType =
  | "born_digital"
  | "scanned"
  | "mixed"
  | "unknown";

export type LayoutComplexity = "low" | "medium" | "high";
export type FontBand = "small" | "medium" | "large" | "unknown";

export interface FontSizeDistribution {
  values: number[];
  count: number;
  median: number | null;
  min: number | null;
  max: number | null;
  bands: Record<Exclude<FontBand, "unknown">, number>;
}

export interface ArtifactPresence {
  present: boolean;
  count: number;
}

export interface BenignRegistrySignals {
  page_count_estimate: number;
  text_operator_count: number;
  text_block_count: number;
  image_object_count: number;
  form_xobject_count: number;
  font_reference_count: number;
}

export interface BenignRegistryProfile {
  source_type: BenignSourceType;
  layout_complexity: LayoutComplexity;
  font_size_distribution: FontSizeDistribution;
  artifact_presence: ArtifactPresence;
  font_band: FontBand;
  stratum_key: string;
  signals: BenignRegistrySignals;
}

const UTF8_DECODER = new TextDecoder("latin1");

export function buildBenignRegistryProfile(pdfBuffer: Buffer): BenignRegistryProfile {
  const raw = UTF8_DECODER.decode(pdfBuffer);

  const textOperatorCount = countMatches(raw, /\b(Tj|TJ|\"|')\b/g);
  const textBlockCount = countMatches(raw, /\bBT\b/g);
  const imageObjectCount = countMatches(raw, /\/Subtype\s*\/Image\b/g);
  const formXObjectCount = countMatches(raw, /\/Subtype\s*\/Form\b/g);
  const fontReferenceCount = countMatches(raw, /\/Font\b/g);
  const pageCountEstimate = Math.max(1, countMatches(raw, /\/Type\s*\/Page\b/g));
  const artifactCount = countMatches(raw, /\/Artifact\s+BMC/g);
  const fontValues = extractFontSizes(raw);

  const sourceType = classifySourceType({
    textOperatorCount,
    textBlockCount,
    imageObjectCount,
  });
  const layoutComplexity = classifyLayoutComplexity({
    pageCountEstimate,
    textOperatorCount,
    textBlockCount,
    imageObjectCount,
    formXObjectCount,
    fontReferenceCount,
  });

  const fontDistribution = summarizeFontSizes(fontValues);
  const fontBand = classifyFontBand(fontDistribution.median);
  const stratumKey = buildStratumKey(sourceType, layoutComplexity, fontBand, artifactCount > 0);

  return {
    source_type: sourceType,
    layout_complexity: layoutComplexity,
    font_size_distribution: fontDistribution,
    artifact_presence: {
      present: artifactCount > 0,
      count: artifactCount,
    },
    font_band: fontBand,
    stratum_key: stratumKey,
    signals: {
      page_count_estimate: pageCountEstimate,
      text_operator_count: textOperatorCount,
      text_block_count: textBlockCount,
      image_object_count: imageObjectCount,
      form_xobject_count: formXObjectCount,
      font_reference_count: fontReferenceCount,
    },
  };
}

function countMatches(input: string, pattern: RegExp): number {
  let count = 0;
  const regex = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`);
  while (regex.exec(input) !== null) {
    count += 1;
  }
  return count;
}

function extractFontSizes(raw: string): number[] {
  const values: number[] = [];
  const regex = /([0-9]+(?:\.[0-9]+)?)\s+Tf\b/g;

  let match: RegExpExecArray | null;
  while ((match = regex.exec(raw)) !== null) {
    const parsed = Number.parseFloat(match[1]);
    if (Number.isFinite(parsed) && parsed > 0 && parsed <= 256) {
      values.push(Number(parsed.toFixed(2)));
    }
  }

  return values;
}

function summarizeFontSizes(values: number[]): FontSizeDistribution {
  if (values.length === 0) {
    return {
      values: [],
      count: 0,
      median: null,
      min: null,
      max: null,
      bands: {
        small: 0,
        medium: 0,
        large: 0,
      },
    };
  }

  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const median =
    sorted.length % 2 === 0
      ? Number(((sorted[mid - 1] + sorted[mid]) / 2).toFixed(2))
      : sorted[mid];

  const bands = sorted.reduce(
    (acc, value) => {
      if (value < 8) {
        acc.small += 1;
      } else if (value <= 14) {
        acc.medium += 1;
      } else {
        acc.large += 1;
      }
      return acc;
    },
    { small: 0, medium: 0, large: 0 }
  );

  return {
    values: sorted,
    count: sorted.length,
    median,
    min: sorted[0],
    max: sorted[sorted.length - 1],
    bands,
  };
}

function classifySourceType(signals: {
  textOperatorCount: number;
  textBlockCount: number;
  imageObjectCount: number;
}): BenignSourceType {
  const textSignal = signals.textOperatorCount + signals.textBlockCount;
  const imageSignal = signals.imageObjectCount;

  if (imageSignal > 0 && textSignal < 15) return "scanned";
  if (imageSignal === 0 && textSignal >= 15) return "born_digital";
  if (imageSignal > 0 && textSignal >= 15) return "mixed";
  return "unknown";
}

function classifyLayoutComplexity(signals: {
  pageCountEstimate: number;
  textOperatorCount: number;
  textBlockCount: number;
  imageObjectCount: number;
  formXObjectCount: number;
  fontReferenceCount: number;
}): LayoutComplexity {
  const score =
    signals.pageCountEstimate * 8 +
    signals.textOperatorCount * 0.3 +
    signals.textBlockCount * 1.2 +
    signals.imageObjectCount * 4 +
    signals.formXObjectCount * 3 +
    signals.fontReferenceCount * 0.5;

  if (score < 50) return "low";
  if (score < 140) return "medium";
  return "high";
}

function classifyFontBand(median: number | null): FontBand {
  if (median === null) return "unknown";
  if (median < 8) return "small";
  if (median <= 14) return "medium";
  return "large";
}

function buildStratumKey(
  sourceType: BenignSourceType,
  layoutComplexity: LayoutComplexity,
  fontBand: FontBand,
  artifactPresent: boolean
): string {
  return `${sourceType}|${layoutComplexity}|${fontBand}|artifact:${artifactPresent ? "1" : "0"}`;
}
