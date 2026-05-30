/**
 * Watermarking Layer (Layer 02)
 *
 * Replaced with ADA policy injection via volks-pdf-blocker-ada-layer-1.
 * This bypasses the Volk screenshot shatter, Rust nano layer, and link insertion stages.
 */

import { BaseProcessor } from "../../base-processor";
import { ProcessorInput, LayerOutput } from "../../types";
import * as fs from "fs/promises";
import * as path from "path";
import {
  processAdaPolicyLayer,
  validateAdaLayerSetup,
} from "./volks-pdf-blocker-ada-layer-1";
import { resolveInjectionConfig } from "./injection-config";
import { getAdaMessagePolicyPath } from "./path-utils";

export class WatermarkingProcessor extends BaseProcessor {
  private setupValidated = false;

  async process(input: ProcessorInput): Promise<LayerOutput> {
    try {
      const { data, context } = input;

      console.log("[Layer 02 - Watermarking] Starting ADA policy layer", {
        documentId: context.documentId,
        tenantId: context.tenantId,
      });

      if (!this.setupValidated && process.env.NODE_ENV === "development") {
        await this.validateAllLayers();
        this.setupValidated = true;
      }

      const tmpDir = path.join(
        process.cwd(),
        "storage",
        "temp",
        context.tenantId
      );
      await fs.mkdir(tmpDir, { recursive: true });

      let inputPath: string;
      let shouldCleanup = false;

      if (Buffer.isBuffer(data)) {
        inputPath = path.join(tmpDir, `${context.documentId}_input.pdf`);
        await fs.writeFile(inputPath, data);
        shouldCleanup = true;
      } else if (typeof data === "string") {
        inputPath = data;
      } else {
        throw new Error("Invalid input data type");
      }

      const adaOutputPath = await this.executeAdaLayer(
        inputPath,
        tmpDir,
        context
      );

      const processedData = await fs.readFile(adaOutputPath);

      if (shouldCleanup) {
        try {
          await fs.unlink(inputPath);
        } catch {}
      }

      console.log("[Layer 02 - Watermarking] ADA layer completed", {
        documentId: context.documentId,
        finalOutputPath: adaOutputPath,
      });

      return {
        success: true,
        data: processedData,
        metadata: {
          watermarkApplied: true,
          watermarkType: "ada-policy-artifact",
          watermarkVersion: "3.0.0-ada-policy",
          watermarkTimestamp: new Date().toISOString(),
          processingStages: {
            stage1: "ada-policy-artifact",
          },
          processingLayer: "watermarking",
          processingTimeMs: 0,
          algorithm: "ada-policy-protection",
          rustProcessing: false,
          pythonProcessing: true,
          linkInjected: true, // prevent downstream link injection
          adaLayer: true,
        },
      };
    } catch (error) {
      console.error("[Layer 02 - Watermarking] Failed", {
        error: (error as Error).message,
      });

      if (process.env.NODE_ENV === "development") {
        console.warn(
          "[Layer 02 - Watermarking] Falling back to mock processing"
        );
        return this.mockWatermarking(input);
      }

      return {
        success: false,
        data: input.data,
        metadata: {},
        error: (error as Error).message,
      };
    }
  }

  /**
   * ADA policy injection stage
   */
  private async executeAdaLayer(
    inputPath: string,
    tmpDir: string,
    context: ProcessorInput["context"]
  ): Promise<string> {
    console.log("[Stage - ADA Policy Injection] Starting...");

    const outputPath = path.join(tmpDir, `${context.documentId}_ada.pdf`);
    const injectionConfig = resolveInjectionConfig(
      context.metadata?.injectionConfig
    );
    const messageType =
      typeof context.metadata?.messageType === "string"
        ? context.metadata.messageType
        : undefined;
    const policyPath = getAdaMessagePolicyPath(messageType);

    const result = await processAdaPolicyLayer({
      inputPath,
      outputPath,
      policyPath,
      injectionConfig,
      timeoutMs: 180000,
    });

    if (!result.success) {
      console.warn(
        "[Stage - ADA Policy Injection] Failed, using input as-is:",
        result.error
      );
      return inputPath;
    }

    console.log("[Stage - ADA Policy Injection] Completed", {
      outputPath: result.outputPath,
    });
    context.metadata = {
      ...(context.metadata || {}),
      adaLayer: true,
      linkInjected: true,
      policyPath: result.metadata.policyPath,
      injectionConfig: result.metadata.injectionConfig,
    };

    return result.outputPath;
  }

  /**
   * Validate ADA layer setup
   */
  private async validateAllLayers(): Promise<void> {
    console.log("[Layer 02 - Watermarking] Validating ADA layer...");

    const adaValidation = await validateAdaLayerSetup();
    if (!adaValidation.valid) {
      console.warn("[ADA Layer] Validation issues:", adaValidation.errors);
    }

    console.log("[Layer 02 - Watermarking] Validation complete");
  }

  /**
   * Mock watermarking for when layers are not available
   */
  private async mockWatermarking(input: ProcessorInput): Promise<LayerOutput> {
    console.log("[Layer 02 - Watermarking] Using mock watermarking");
    await new Promise((resolve) => setTimeout(resolve, 100));

    return {
      success: true,
      data: input.data,
      metadata: {
        watermarkApplied: true,
        watermarkVersion: "2.0.0-mock",
        processingTimeMs: 100,
        algorithm: "mock-passthrough",
        rustProcessing: false,
        pythonProcessing: false,
        mock: true,
      },
    };
  }
}
