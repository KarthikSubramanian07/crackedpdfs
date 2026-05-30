# Document Processing Pipeline

Modular, layer-by-layer document processing architecture designed for easy extension and maintenance.

## 🏗️ Architecture

The processing pipeline executes layers sequentially. Each layer:
- Receives input from the previous layer
- Performs its specific transformation
- Passes output to the next layer
- Can be updated independently without affecting other layers

## 📁 Layer Structure

```
layers/
├── 01-upload/           # File upload & validation
├── 02-watermarking/     # Rust watermarking (future)
├── 03-encryption/       # Document encryption
└── 04-verification/     # Integrity verification
```

**Why Numbered Folders?**
- Clear execution order at a glance
- Easy to insert new layers between existing ones
- Prevents accidental reordering
- Makes onboarding new developers easier

## 🔧 How Processing Layers Work

### Layer Lifecycle

```
┌─────────────┐
│   Upload    │ Input: File buffer
│  (Layer 01) │ Output: Validated document
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Watermark   │ Input: Document buffer
│  (Layer 02) │ Output: Watermarked buffer
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Encryption  │ Input: Document buffer
│  (Layer 03) │ Output: Encrypted buffer
└──────┬──────┘
       │
       ▼
┌─────────────┐
│Verification │ Input: Encrypted buffer
│  (Layer 04) │ Output: Verified metadata
└─────────────┘
```

### Adding a New Layer

**Example: Adding Layer 05 - Compression**

1. **Create the directory structure:**
   ```bash
   backend/services/processing/layers/05-compression/
   ├── index.ts
   ├── processor.ts
   ├── types.ts
   └── README.md
   ```

2. **Implement the processor** (`processor.ts`):
   ```typescript
   import { BaseProcessor, ProcessorInput, LayerOutput } from '../../types';
   
   export class CompressionProcessor extends BaseProcessor {
     async process(input: ProcessorInput): Promise<LayerOutput> {
       const { data, context, previousLayerOutput } = input;
       
       try {
         // Your compression logic here
         const compressedData = await this.compress(data);
         
         return {
           success: true,
           data: compressedData,
           metadata: {
             originalSize: data.length,
             compressedSize: compressedData.length,
             compressionRatio: compressedData.length / data.length,
           },
         };
       } catch (error) {
         return {
           success: false,
           data,
           metadata: {},
           error: error instanceof Error ? error.message : 'Compression failed',
         };
       }
     }
     
     private async compress(data: Buffer | string): Promise<Buffer> {
       // Compression implementation
     }
   }
   ```

3. **Export from index** (`index.ts`):
   ```typescript
   export { CompressionProcessor } from './processor';
   ```

4. **Register in orchestrator** (`orchestrator.ts`):
   ```typescript
   import { CompressionProcessor } from './layers/05-compression';
   
   // In pipeline config
   stages: [
     // ... existing stages
     {
       layer: 'compression',
       processor: new CompressionProcessor(),
       required: false,
       retries: 2,
       timeout: 30000,
     },
   ]
   ```

## 🎯 Layer Best Practices

### 1. **Independence**
Each layer should be self-contained and not depend on implementation details of other layers.

✅ **Good:**
```typescript
const watermarkData = previousLayerOutput?.watermarkId || generateWatermarkId();
```

❌ **Bad:**
```typescript
// Don't reach into other layer's internal implementation
const watermarkData = previousLayerOutput?.__internal_watermark_state;
```

### 2. **Error Handling**
Always return `LayerOutput` with proper error information:

```typescript
try {
  const result = await processDocument(data);
  return { success: true, data: result, metadata: {} };
} catch (error) {
  return {
    success: false,
    data, // Return original data
    metadata: {},
    error: error.message,
  };
}
```

### 3. **Metadata Propagation**
Pass important information to downstream layers via `metadata`:

```typescript
return {
  success: true,
  data: processedBuffer,
  metadata: {
    processingTime: Date.now() - startTime,
    layerVersion: '2.1.0',
    outputFormat: 'pdf',
    // This will be available in next layer as previousLayerOutput
  },
};
```

### 4. **Idempotency**
Layers should be safe to retry. Same input should produce same output:

```typescript
// Use deterministic IDs based on document content, not random
const watermarkId = crypto.createHash('sha256')
  .update(documentId + tenantId)
  .digest('hex');
```

## 🔗 Connecting to Rust Processing

When you're ready to integrate Rust watermarking:

1. **Keep the layer structure** - Replace the TypeScript implementation in `02-watermarking/`
2. **Use AWS Lambda** - Deploy Rust binary as Lambda function
3. **Update processor** - Call Lambda instead of local processing:

```typescript
// backend/services/processing/layers/02-watermarking/processor.ts
import { LambdaService } from '@/backend/services/aws/lambda';

export class WatermarkingProcessor extends BaseProcessor {
  async process(input: ProcessorInput): Promise<LayerOutput> {
    const { data, context } = input;
    
    // Upload to S3
    const s3Key = await S3Service.upload(`${context.tenantId}/${context.documentId}.pdf`, data);
    
    // Invoke Rust Lambda
    const result = await LambdaService.invokeProcessor({
      documentId: context.documentId,
      tenantId: context.tenantId,
      s3Key,
      operation: 'watermark',
    });
    
    // Download processed file
    const processedData = await S3Service.download(result.outputS3Key);
    
    return {
      success: true,
      data: processedData,
      metadata: result.metadata,
    };
  }
}
```

## 📊 Monitoring & Debugging

Each layer execution is tracked in the `processing_jobs` table:

```sql
SELECT * FROM processing_jobs 
WHERE document_id = 123 
ORDER BY created_at DESC;
```

Fields tracked:
- `pipeline_stage` - Which layer (e.g., "watermarking")
- `status` - pending, running, completed, failed
- `started_at`, `completed_at` - Timing data
- `error_message` - If failed
- `output_data` - Layer metadata

## 🚀 Future Enhancements

Potential layers to add:
- **05-compression** - Reduce file size
- **06-ocr** - Extract text for searchability
- **07-thumbnail** - Generate preview images
- **08-audit-log** - Record access history
- **09-dlp** - Data loss prevention scanning
- **10-adversarial** - Anti-screenshot protections
