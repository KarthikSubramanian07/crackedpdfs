/**
 * Pipeline Orchestrator
 * 
 * Coordinates the execution of processing layers in sequence.
 * Manages job state, error handling, and retries.
 */

import { db } from '@/backend/db';
import { processingJobs } from '@/backend/db/schema';
import { eq } from 'drizzle-orm';
import fs from 'node:fs/promises';
import path from 'node:path';
import { PipelineConfig, ProcessingContext, LayerOutput, PipelineStage } from './types';
import { BaseProcessor } from './base-processor';
import {
  UploadProcessor,
  WatermarkingProcessor,
  EncryptionProcessor,
  VerificationProcessor
} from './layers';

export class PipelineOrchestrator {
  private config: PipelineConfig;
  private processors: Map<string, BaseProcessor>;

  constructor(config: PipelineConfig) {
    this.config = config;
    this.processors = new Map();
    
    // Register default processors
    this.registerDefaultProcessors();
  }

  /**
   * Register default processing layers
   */
  private registerDefaultProcessors() {
    this.registerProcessor('upload', new UploadProcessor());
    this.registerProcessor('watermarking', new WatermarkingProcessor());
    this.registerProcessor('encryption', new EncryptionProcessor());
    this.registerProcessor('verification', new VerificationProcessor());
  }

  /**
   * Register a processor for a specific layer
   */
  registerProcessor(layerName: string, processor: BaseProcessor) {
    this.processors.set(layerName, processor);
    console.log(`[Orchestrator] Registered processor: ${layerName}`);
  }

  /**
   * Execute the full processing pipeline for a document
   */
  async executePipeline(context: ProcessingContext, data: Buffer | string): Promise<Record<string, LayerOutput>> {
    const results: Record<string, LayerOutput> = {};
    let currentData = data;
    let previousOutput: Record<string, any> | undefined;

    for (const stage of this.config.stages) {
      try {
        // Create processing job record
        const job = await this.createJob(context, stage.layer);

        // Execute stage
        const output = await this.executeStage(stage, context, currentData, previousOutput, job.id);

        results[stage.layer] = output;

        if (!output.success) {
          if (stage.required) {
            // Required stage failed - abort pipeline
            await this.updateJobStatus(job.id, 'failed', output.error);
            throw new Error(`Required stage ${stage.layer} failed: ${output.error}`);
          } else {
            // Optional stage failed - continue
            await this.updateJobStatus(job.id, 'failed', output.error);
            this.config.onStageError?.(stage.layer, new Error(output.error || 'Unknown error'));
            continue;
          }
        }

        // Update for next stage
        currentData = output.data;
        previousOutput = output.metadata;

        await this.updateJobStatus(job.id, 'completed', undefined, output.metadata);
        this.config.onStageComplete?.(stage.layer, output);

      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        this.config.onStageError?.(stage.layer, error as Error);
        
        if (stage.required) {
          throw error;
        }
      }
    }

    this.config.onComplete?.(results);
    return results;
  }

  /**
   * Execute a single pipeline stage with retries
   */
  private async executeStage(
    stage: PipelineStage,
    context: ProcessingContext,
    data: Buffer | string,
    previousOutput: Record<string, any> | undefined,
    jobId: number
  ): Promise<LayerOutput> {
    const processor = this.processors.get(stage.layer);
    
    if (!processor) {
      return {
        success: false,
        data,
        metadata: {},
        error: `No processor registered for layer: ${stage.layer}`
      };
    }

    let lastError: Error | undefined;
    
    for (let attempt = 0; attempt <= stage.retries; attempt++) {
      try {
        await this.updateJobStatus(jobId, 'running');
        
        const result = await Promise.race([
          processor.process({ context, data, previousLayerOutput: previousOutput }),
          this.timeout(stage.timeout)
        ]);

        return result;
      } catch (error) {
        lastError = error as Error;
        if (attempt < stage.retries) {
          // Wait before retry (exponential backoff)
          await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
        }
      }
    }

    return {
      success: false,
      data,
      metadata: {},
      error: lastError?.message || 'Stage execution failed'
    };
  }

  /**
   * Create processing job record
   */
  private async createJob(context: ProcessingContext, pipelineStage: string) {
    const jobs = await db.insert(processingJobs).values({
      documentId: context.documentId,
      tenantId: context.tenantId,
      pipelineStage,
      status: 'pending',
      createdAt: new Date().toISOString(),
      inputData: context.metadata
    }).returning();

    return jobs[0];
  }

  /**
   * Update job status in database
   */
  private async updateJobStatus(
    jobId: number,
    status: 'pending' | 'running' | 'completed' | 'failed',
    errorMessage?: string,
    outputData?: Record<string, any>
  ) {
    const updates: any = { status };
    
    if (status === 'running') {
      updates.startedAt = new Date().toISOString();
    } else if (status === 'completed' || status === 'failed') {
      updates.completedAt = new Date().toISOString();
    }
    
    if (errorMessage) {
      updates.errorMessage = errorMessage;
    }
    
    if (outputData) {
      updates.outputData = outputData;
    }

    await db.update(processingJobs)
      .set(updates)
      .where(eq(processingJobs.id, jobId));
  }

  /**
   * Timeout helper for stage execution
   */
  private timeout(ms: number): Promise<never> {
    return new Promise((_, reject) => {
      setTimeout(() => reject(new Error(`Stage timeout after ${ms}ms`)), ms);
    });
  }
}

export interface ProcessDocumentOptions {
  tenantId: string;
  userId?: string;
  documentId: number | string;
  inputPath: string;
  outputPath?: string;
  fileType?: string;
  originalFilename?: string;
  metadata?: Record<string, any>;
  confusionMatrix?: Record<string, any>;
  pythonEmbedding?: Record<string, any>;
  storageDocumentId?: string;
}

export interface ProcessDocumentResult {
  success: boolean;
  processingTimeMs?: number;
  metadata?: Record<string, any>;
  error?: string;
}

/**
 * Convenience helper that executes the default pipeline for a single document.
 * This keeps API routes lightweight while ensuring all processing happens
 * through the orchestrator.
 */
export async function processDocument(
  options: ProcessDocumentOptions
): Promise<ProcessDocumentResult> {
  const start = Date.now();

  try {
    const documentId =
      typeof options.documentId === 'string'
        ? parseInt(options.documentId, 10)
        : options.documentId;

    if (Number.isNaN(documentId)) {
      throw new Error('Invalid documentId provided to processDocument');
    }

    const inputBuffer = await fs.readFile(options.inputPath);

    const context: ProcessingContext = {
      documentId,
      tenantId: options.tenantId,
      userId: options.userId || options.tenantId,
      storageDocumentId: options.storageDocumentId || String(documentId),
      filePath: options.inputPath,
      originalFilename:
        options.originalFilename || path.basename(options.inputPath),
      fileType: options.fileType || 'application/pdf',
      metadata: {
        ...(options.metadata || {}),
        ...(options.confusionMatrix && {
          confusionMatrixConfig: options.confusionMatrix,
        }),
        ...(options.pythonEmbedding && {
          pythonEmbeddingConfig: options.pythonEmbedding,
        }),
        requestedOutputPath: options.outputPath,
      },
    };

    const pipeline = createDefaultPipeline();
    const results = await pipeline.executePipeline(context, inputBuffer);
    const verificationOutput = results.verification;
    const completed =
      verificationOutput?.success ??
      Object.values(results).every((stage) => stage.success);

    const serializedResults = sanitizeLayerOutputs(results);

    const finalStageOutput =
      verificationOutput ||
      Object.values(results)[Object.values(results).length - 1];

    if (options.outputPath && finalStageOutput?.data) {
      const buffer = toBuffer(finalStageOutput.data);
      if (buffer) {
        await fs.mkdir(path.dirname(options.outputPath), { recursive: true });
        await fs.writeFile(options.outputPath, buffer);
      }
    }

    return {
      success: completed,
      processingTimeMs: Date.now() - start,
      metadata: {
        ...(verificationOutput?.metadata || {}),
        pipeline: serializedResults,
        outputPath:
          verificationOutput?.metadata?.outputPath || options.outputPath,
      },
    };
  } catch (error) {
    console.error('[Pipeline] processDocument failed', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

function toBuffer(data: LayerOutput['data']): Buffer | undefined {
  if (!data) return undefined;
  if (Buffer.isBuffer(data)) return data;
  if (typeof data === 'string') return Buffer.from(data);
  return undefined;
}

function sanitizeLayerOutputs(
  results: Record<string, LayerOutput>
): Record<string, Pick<LayerOutput, 'success' | 'error' | 'metadata'>> {
  return Object.entries(results).reduce(
    (acc, [stage, output]) => {
      acc[stage] = {
        success: output.success,
        error: output.error,
        metadata: output.metadata,
      };
      return acc;
    },
    {} as Record<string, Pick<LayerOutput, 'success' | 'error' | 'metadata'>>
  );
}

/**
 * Create default pipeline configuration
 */
export function createDefaultPipeline(): PipelineOrchestrator {
  const config: PipelineConfig = {
    stages: [
      {
        name: 'upload',
        layer: 'upload',
        required: true,
        retries: 2,
        timeout: 30000, // 30s
      },
      {
        name: 'watermarking',
        layer: 'watermarking',
        required: true,
        retries: 3,
        timeout: 300000, // 5min for Rust processing
      },
      {
        name: 'encryption',
        layer: 'encryption',
        required: true,
        retries: 2,
        timeout: 30000, // 30s
      },
      {
        name: 'verification',
        layer: 'verification',
        required: true,
        retries: 2,
        timeout: 60000, // 1min for storage upload
      },
    ],
    onStageComplete: (stage, output) => {
      console.log(`[Pipeline] Stage ${stage} completed`, output.metadata);
    },
    onStageError: (stage, error) => {
      console.error(`[Pipeline] Stage ${stage} failed:`, error.message);
    },
    onComplete: (results) => {
      console.log('[Pipeline] All stages completed', Object.keys(results));
    },
  };

  return new PipelineOrchestrator(config);
}
