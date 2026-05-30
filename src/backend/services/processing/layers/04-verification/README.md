# Layer 04: Verification

**Purpose:** Final integrity checks and verification before marking documents as processed.

## 🎯 Responsibilities

- Verify encryption was successful
- Validate watermark signature
- Check file integrity (checksums)
- Update document status to "completed"
- Generate verification certificate

## 📋 Input

```typescript
{
  context: {
    documentId: number;
    tenantId: string;
  },
  data: Buffer; // Encrypted document
  previousLayerOutput: {
    watermarkId: string;
    encryptionAlgorithm: string;
    keyId: string;
  }
}
```

## 📤 Output

```typescript
{
  success: boolean;
  data: Buffer; // Same encrypted document
  metadata: {
    verified: boolean;
    checksumSHA256: string;
    verificationCertificate: string;
    finalStatus: 'completed' | 'failed';
    verifiedAt: string;
  }
}
```

## ✅ Verification Steps

```typescript
import crypto from 'crypto';

async function verifyDocument(
  data: Buffer,
  watermarkId: string,
  encryptionKeyId: string
): Promise<VerificationResult> {
  const checks: VerificationCheck[] = [];
  
  // 1. Verify file is not corrupted
  checks.push(verifyFileIntegrity(data));
  
  // 2. Verify encryption succeeded
  checks.push(verifyEncryption(data, encryptionKeyId));
  
  // 3. Verify watermark is present (decrypt temporarily)
  checks.push(await verifyWatermark(data, watermarkId));
  
  // 4. Generate final checksum
  const checksum = crypto.createHash('sha256')
    .update(data)
    .digest('hex');
  
  const allPassed = checks.every(check => check.passed);
  
  return {
    verified: allPassed,
    checksumSHA256: checksum,
    checks,
    verificationCertificate: generateCertificate(checks, checksum),
  };
}
```

## 🏅 Verification Certificate

```typescript
interface VerificationCertificate {
  documentId: number;
  tenantId: string;
  checksumSHA256: string;
  watermarkId: string;
  verifiedAt: string;
  signature: string; // Cryptographic signature
  processingPipeline: {
    upload: { status: 'completed', timestamp: string },
    watermarking: { status: 'completed', timestamp: string },
    encryption: { status: 'completed', timestamp: string },
    verification: { status: 'completed', timestamp: string },
  };
}

function generateCertificate(
  documentId: number,
  tenantId: string,
  metadata: Record<string, any>
): string {
  const cert: VerificationCertificate = {
    documentId,
    tenantId,
    checksumSHA256: metadata.checksum,
    watermarkId: metadata.watermarkId,
    verifiedAt: new Date().toISOString(),
    signature: signCertificate(metadata),
    processingPipeline: metadata.pipeline,
  };
  
  return Buffer.from(JSON.stringify(cert)).toString('base64');
}
```

## 🔍 Integrity Checks

### 1. File Corruption Check

```typescript
function verifyFileIntegrity(data: Buffer): VerificationCheck {
  try {
    // Verify file header and structure
    const isValid = data.length > 0 && validateFileStructure(data);
    return {
      name: 'File Integrity',
      passed: isValid,
      message: isValid ? 'File structure valid' : 'File corrupted',
    };
  } catch (error) {
    return {
      name: 'File Integrity',
      passed: false,
      message: error.message,
    };
  }
}
```

### 2. Encryption Verification

```typescript
function verifyEncryption(data: Buffer, keyId: string): VerificationCheck {
  try {
    // Check encryption markers or attempt decryption
    const hasEncryptionMarkers = checkEncryptionMarkers(data);
    return {
      name: 'Encryption',
      passed: hasEncryptionMarkers,
      message: hasEncryptionMarkers ? 'Document encrypted' : 'Encryption failed',
    };
  } catch (error) {
    return {
      name: 'Encryption',
      passed: false,
      message: error.message,
    };
  }
}
```

### 3. Watermark Verification

```typescript
async function verifyWatermark(
  encryptedData: Buffer,
  watermarkId: string
): Promise<VerificationCheck> {
  try {
    // Decrypt temporarily to check watermark
    const decrypted = await temporaryDecrypt(encryptedData);
    const watermarkExists = await checkWatermarkSignature(decrypted, watermarkId);
    
    return {
      name: 'Watermark',
      passed: watermarkExists,
      message: watermarkExists ? 'Watermark verified' : 'Watermark missing',
    };
  } catch (error) {
    return {
      name: 'Watermark',
      passed: false,
      message: error.message,
    };
  }
}
```

## 📊 Database Update

After successful verification, update the document status:

```typescript
import { db } from '@/backend/db';
import { documents } from '@/backend/db/schema';
import { eq } from 'drizzle-orm';

await db.update(documents)
  .set({
    status: 'completed',
    processedAt: new Date().toISOString(),
    metadata: {
      verificationCertificate: certificate,
      checksumSHA256: checksum,
    },
  })
  .where(eq(documents.id, documentId));
```

## 🔄 What Happens Next?

This is the **final layer** in the processing pipeline. After verification:

1. Document status → `completed`
2. User can download the protected document
3. Verification certificate stored for audit trail
4. Tenant metrics updated (`documentsProcessed++`)

## 🚨 Failure Handling

If verification fails, the document is marked as `failed`:

```typescript
await db.update(documents)
  .set({
    status: 'failed',
    errorMessage: 'Verification failed: ' + error.message,
  })
  .where(eq(documents.id, documentId));
```

The user can retry processing or delete the document.
