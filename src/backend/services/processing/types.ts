/**
 * Processing Pipeline Types
 * 
 * Core interfaces for the modular document processing system.
 * Designed to integrate with Rust processing core via AWS Lambda/ECS.
 */

export type ProcessingStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface ProcessingContext {
  documentId: number;
  tenantId: string;
  userId: string;
  storageDocumentId?: string;
  filePath: string;
  originalFilename: string;
  fileType: string;
  metadata: Record<string, any>;
}

export interface LayerInput {
  context: ProcessingContext;
  data: Buffer | string;
  previousLayerOutput?: Record<string, any>;
}

// Legacy alias retained for existing layers
export type ProcessorInput = LayerInput;

export interface LayerOutput {
  success: boolean;
  data: Buffer | string;
  metadata: Record<string, any>;
  error?: string;
}

export interface PipelineStage {
  name: string;
  layer: string;
  required: boolean;
  timeout: number; // milliseconds
  retries: number;
}

export interface PipelineConfig {
  stages: PipelineStage[];
  onStageComplete?: (stage: string, output: LayerOutput) => void;
  onStageError?: (stage: string, error: Error) => void;
  onComplete?: (results: Record<string, LayerOutput>) => void;
}

export interface ProcessingJob {
  id: number;
  documentId: number;
  tenantId: string;
  pipelineStage: string;
  status: ProcessingStatus;
  startedAt?: string;
  completedAt?: string;
  errorMessage?: string;
  inputData?: Record<string, any>;
  outputData?: Record<string, any>;
  createdAt: string;
}

export interface AWSProcessingRequest {
  documentId: number;
  tenantId: string;
  s3Key: string;
  stage: string;
  config: Record<string, any>;
}

export interface AWSProcessingResponse {
  success: boolean;
  outputS3Key?: string;
  metadata?: Record<string, any>;
  error?: string;
  processingTimeMs?: number;
}
