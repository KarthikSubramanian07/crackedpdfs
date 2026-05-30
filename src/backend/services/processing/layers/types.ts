/**
 * Shared types for processing layers
 */

export interface LayerContext {
  documentId: string;
  tenantId: string;
  filePath: string;
  fileType?: string;
  originalFilename?: string;
  metadata: Record<string, any>;
}

export interface LayerResult {
  success: boolean;
  context?: LayerContext;
  error?: string;
  layerName: string;
  executionTimeMs: number;
}

export interface ProcessingConfig {
  skipLayers?: string[];
  customConfig?: Record<string, any>;
}
