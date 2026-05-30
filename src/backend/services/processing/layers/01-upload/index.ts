/**
 * Upload Layer (Layer 01)
 * 
 * Validates document format, size, and structure before processing.
 * First stage in the processing pipeline.
 */

import { BaseProcessor } from '../../base-processor';
import { ProcessorInput, LayerOutput } from '../../types';

export class UploadProcessor extends BaseProcessor {
  private readonly MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB
  private readonly ALLOWED_TYPES = ['application/pdf', 'image/png', 'image/jpeg'];

  async process(input: ProcessorInput): Promise<LayerOutput> {
    try {
      const { data, context } = input;
      
      console.log('[Layer 01 - Upload] Starting validation', { 
        documentId: context.documentId,
        fileType: context.fileType,
        tenantId: context.tenantId
      });

      // Validate file type
      if (!this.ALLOWED_TYPES.includes(context.fileType)) {
        throw new Error(`Unsupported file type: ${context.fileType}. Allowed: ${this.ALLOWED_TYPES.join(', ')}`);
      }

      // Validate file size (if data is Buffer)
      if (Buffer.isBuffer(data)) {
        if (data.length > this.MAX_FILE_SIZE) {
          throw new Error(`File size exceeds maximum: ${data.length} bytes (max: ${this.MAX_FILE_SIZE})`);
        }
      }

      // TODO: Add more validation checks when ready
      // - PDF structure validation
      // - Image format validation
      // - Malware scanning
      // - Content analysis

      console.log('[Layer 01 - Upload] Validation passed', { 
        documentId: context.documentId,
        fileSize: Buffer.isBuffer(data) ? data.length : 'unknown'
      });

      return {
        success: true,
        data: data,
        metadata: {
          validated: true,
          validatedAt: new Date().toISOString(),
          fileType: context.fileType,
          fileSize: Buffer.isBuffer(data) ? data.length : 0,
          checks: ['fileType', 'fileSize']
        }
      };
    } catch (error) {
      console.error('[Layer 01 - Upload] Validation failed', { error: (error as Error).message });
      return {
        success: false,
        data: input.data,
        metadata: {},
        error: (error as Error).message
      };
    }
  }
}
