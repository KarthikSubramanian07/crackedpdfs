/**
 * Confusion Matrix Layer - Main Integration Point
 * 
 * Orchestrates Rust VGG16-based perceptual noise watermarking.
 * Supports local CLI execution and AWS Lambda/ECS deployment.
 */

import * as path from "path";
import { executeConfusionMatrixLayer, validateBinarySetup } from "./cli-executor";
import type { ConfusionMatrixConfig } from "./cli-executor";
import { LayerContext } from "../../types";

export interface ConfusionMatrixLayerConfig extends ConfusionMatrixConfig {
  mode?: "cli" | "lambda" | "ecs";
}

/**
 * Process document with confusion matrix watermarking
 */
export async function processConfusionMatrix(
  context: LayerContext,
  config: ConfusionMatrixLayerConfig = {}
): Promise<LayerContext> {
  console.log("[Layer 02 - Confusion Matrix] Starting", {
    documentId: context.documentId,
    tenantId: context.tenantId,
    mode: config.mode || "cli",
  });

  const initialMode = config.mode || (process.env.AWS_LAMBDA_FUNCTION_NAME ? "lambda" : "cli");
  let mode: "cli" | "lambda" | "ecs" = initialMode;
  let lambdaHandlerModule: { handler: Function } | null = null;

  try {
    // Validate setup (dev mode only)
    if (mode === "cli" && process.env.NODE_ENV === "development") {
      const validation = await validateBinarySetup();
      if (!validation.valid) {
        throw new Error(
          `Rust binary setup invalid:\n${validation.errors.join("\n")}`
        );
      }
    }

    let outputPath: string;
    let pageCount: number | undefined;

    if (mode === "lambda" || mode === "ecs") {
      if (!lambdaHandlerModule) {
        try {
          lambdaHandlerModule = await import("./aws-lambda-handler");
        } catch (awsImportError) {
          console.warn(
            "[Layer 02 - Confusion Matrix] AWS handler unavailable, falling back to CLI mode.",
            awsImportError
          );
          mode = "cli";
        }
      }
    }

    if (mode === "lambda" || mode === "ecs") {
      const { handler } = lambdaHandlerModule as { handler: Function };
      const result = await handler({
        tenantId: context.tenantId,
        documentId: context.documentId,
        inputS3Key: context.filePath, // Assumes S3 key in AWS mode
        inputS3Bucket: process.env.AWS_S3_BUCKET || "solvance-documents",
        outputS3Bucket: process.env.AWS_S3_BUCKET_PROCESSED || "solvance-protected",
        config,
      });

      if (!result.success) {
        throw new Error(result.error || "AWS processing failed");
      }

      outputPath = result.outputS3Key!;
      pageCount = result.pageCount;
    } else {
      // Local mode: Execute binary directly
      const outputDir = path.dirname(context.filePath);

      const result = await executeConfusionMatrixLayer(
        context.filePath,
        outputDir,
        {
          dpi: config.dpi || 200,
          noiseEpsilon: config.noiseEpsilon || 0.003,
          jpegQuality: config.jpegQuality || 95,
          weightsPath: config.weightsPath,
          timeoutMs: config.timeoutMs || 300000,
        }
      );

      if (!result.success) {
        throw new Error(result.error || "Processing failed");
      }

      outputPath = result.outputPath!;
      pageCount = result.pageCount;
    }

    console.log("[Layer 02 - Confusion Matrix] Complete", {
      outputPath,
      pageCount,
    });

    return {
      ...context,
      filePath: outputPath,
      metadata: {
        ...context.metadata,
        watermarkType: "confusion_matrix_vgg16",
        watermarkTimestamp: new Date().toISOString(),
        pageCount,
        processingLayer: "02-watermarking-confusion-matrix",
      },
    };
  } catch (error) {
    console.error("[Layer 02 - Confusion Matrix] Error:", error);
    throw error;
  }
}

export { validateBinarySetup, executeConfusionMatrixLayer } from "./cli-executor";
export type { ConfusionMatrixConfig } from "./cli-executor";
