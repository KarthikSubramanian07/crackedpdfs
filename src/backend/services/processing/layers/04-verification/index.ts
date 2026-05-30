/**
 * Verification Layer (Layer 04)
 * 
 * Final processing stage - handles output generation, storage, and verification.
 * Uploads processed documents to S3 (when ready) and updates database.
 * Injects accessibility request links into processed PDFs.
 */

import { BaseProcessor } from '../../base-processor';
import { ProcessorInput, LayerOutput } from '../../types';
import { db } from '@/backend/db';
import { documents } from '@/backend/db/schema';
import { eq } from 'drizzle-orm';
import { storageService } from '@/backend/services/storage';
import { injectAccessibilityLink, isPDF } from '../02-watermarking/pdf-link-injector';

export class VerificationProcessor extends BaseProcessor {
  async process(input: ProcessorInput): Promise<LayerOutput> {
    try {
      const { data, context, previousLayerOutput } = input;
      
      console.log('[Layer 04 - Verification] Starting output processing', { 
        documentId: context.documentId,
        tenantId: context.tenantId
      });

      // Fetch document to get accessToken
      const docRecord = await db.select()
        .from(documents)
        .where(eq(documents.id, context.documentId))
        .limit(1);
      
      if (docRecord.length === 0) {
        throw new Error(`Document ${context.documentId} not found`);
      }

      const accessToken = docRecord[0].accessToken;
      console.log('[Layer 04 - Verification] Document accessToken retrieved');

      // Convert to Buffer if needed
      let processedData = Buffer.isBuffer(data) ? data : Buffer.from(data);

      // Inject accessibility link if it's a PDF (FINAL LAYER - Last step before storage)
      let linkInjected = false;
      if (context.metadata?.linkInjected) {
        linkInjected = true;
        console.log('[Layer 04 - Verification] Skipping pdf-lib injection; link already added in Stage 3.');
      } else if (isPDF(processedData) && accessToken) {
        console.log('[Layer 04 - Verification] Injecting accessibility request link');
        try {
          processedData = await injectAccessibilityLink(processedData, {
            accessToken,
            position: 'bottom-right',
            fontSize: 9,
            textColor: { r: 0.2, g: 0.4, b: 0.8 }
          });
          linkInjected = true;
          console.log('[Layer 04 - Verification] Accessibility link injected successfully');
        } catch (linkError) {
          console.error('[Layer 04 - Verification] Failed to inject link:', linkError);
          // Continue without link injection
        }
      }

      const extension = context.originalFilename?.split('.').pop() || 'bin';
      const storageIdentity = {
        tenantId: context.tenantId,
        userId: context.userId || context.tenantId,
        documentId: context.storageDocumentId || String(context.documentId),
      };

      // Upload processed document to storage
      const file = new File([new Uint8Array(processedData)], `${context.documentId}.${extension}`, { 
        type: context.fileType 
      });
      
      const uploadResult = await storageService.upload(file, {
        ...storageIdentity,
        stage: 'processed',
        filename: `${context.documentId}_${Date.now()}.${extension}`,
      });
      
      console.log('[Layer 04 - Verification] File uploaded to storage', {
        documentId: context.documentId,
        path: uploadResult.path,
        linkInjected
      });

      // Update document record with processed file path
      await db.update(documents)
        .set({
          status: 'completed',
          processedAt: new Date().toISOString(),
          metadata: {
            ...context.metadata,
            outputPath: uploadResult.path,
            storageUrl: uploadResult.url,
            processingChain: previousLayerOutput,
            verifiedAt: new Date().toISOString(),
            accessibilityLinkInjected: linkInjected,
            accessToken
          }
        })
        .where(eq(documents.id, context.documentId));

      console.log('[Layer 04 - Verification] Output processing completed', { 
        documentId: context.documentId,
        outputPath: uploadResult.path
      });

      return {
        success: true,
        data: processedData,
        metadata: {
          outputPath: uploadResult.path,
          storageUrl: uploadResult.url,
          uploadedAt: new Date().toISOString(),
          verified: true,
          processingComplete: true,
          accessibilityLinkInjected: linkInjected,
          accessToken
        }
      };
    } catch (error) {
      console.error('[Layer 04 - Verification] Failed', { error: (error as Error).message });
      return {
        success: false,
        data: input.data,
        metadata: {},
        error: (error as Error).message
      };
    }
  }
}
