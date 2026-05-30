# Layer 03: Encryption

**Purpose:** Encrypt watermarked documents for secure storage and distribution.

## 🎯 Responsibilities

- Encrypt document content using industry-standard algorithms
- Generate and manage encryption keys per tenant
- Store encryption metadata for later decryption
- Ensure documents are protected at rest

## 📋 Input

```typescript
{
  context: {
    documentId: number;
    tenantId: string;
  },
  data: Buffer; // Watermarked document
  previousLayerOutput: {
    watermarkId: string;
    signature: string;
  }
}
```

## 📤 Output

```typescript
{
  success: boolean;
  data: Buffer; // Encrypted document
  metadata: {
    encryptionAlgorithm: 'AES-256-GCM';
    keyId: string;
    iv: string; // Initialization vector (base64)
    authTag: string; // Authentication tag (base64)
    encryptedAt: string;
  }
}
```

## 🔐 Encryption Implementation

```typescript
import crypto from 'crypto';

const ALGORITHM = 'aes-256-gcm';
const KEY_LENGTH = 32; // 256 bits

function encryptDocument(data: Buffer, tenantId: string): EncryptionResult {
  // Derive key from tenant ID (or use AWS KMS)
  const key = deriveKeyFromTenant(tenantId);
  
  // Generate random IV
  const iv = crypto.randomBytes(16);
  
  // Create cipher
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  
  // Encrypt data
  const encrypted = Buffer.concat([
    cipher.update(data),
    cipher.final()
  ]);
  
  // Get auth tag
  const authTag = cipher.getAuthTag();
  
  return {
    encryptedData: encrypted,
    iv: iv.toString('base64'),
    authTag: authTag.toString('base64'),
  };
}
```

## 🔑 Key Management

### Current: Tenant-Derived Keys

```typescript
function deriveKeyFromTenant(tenantId: string): Buffer {
  const masterSecret = process.env.MASTER_ENCRYPTION_KEY!;
  return crypto.pbkdf2Sync(
    tenantId,
    masterSecret,
    100000,
    32,
    'sha256'
  );
}
```

### Future: AWS KMS Integration

```typescript
import { KMSClient, EncryptCommand } from '@aws-sdk/client-kms';

async function encryptWithKMS(data: Buffer, tenantId: string): Promise<Buffer> {
  const kms = new KMSClient({ region: 'us-east-1' });
  
  const command = new EncryptCommand({
    KeyId: process.env.KMS_KEY_ID,
    Plaintext: data,
    EncryptionContext: {
      tenantId: tenantId,
    },
  });
  
  const result = await kms.send(command);
  return Buffer.from(result.CiphertextBlob!);
}
```

## 🔓 Decryption (for downloads)

```typescript
function decryptDocument(
  encrypted: Buffer,
  iv: string,
  authTag: string,
  tenantId: string
): Buffer {
  const key = deriveKeyFromTenant(tenantId);
  
  const decipher = crypto.createDecipheriv(
    ALGORITHM,
    key,
    Buffer.from(iv, 'base64')
  );
  
  decipher.setAuthTag(Buffer.from(authTag, 'base64'));
  
  return Buffer.concat([
    decipher.update(encrypted),
    decipher.final()
  ]);
}
```

## 🔄 Next Layer

Output from Layer 03 → Input to **Layer 04: Verification**

The encrypted document is verified for integrity before being marked as "completed".

## ⚡ Performance

- Encryption is CPU-intensive but fast (~100ms for 10MB file)
- Use streams for very large files to avoid memory issues

```typescript
import { createReadStream, createWriteStream } from 'fs';

function encryptLargeFile(inputPath: string, outputPath: string) {
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  
  createReadStream(inputPath)
    .pipe(cipher)
    .pipe(createWriteStream(outputPath));
}
```

## 🛡️ Security Best Practices

1. **Never log encryption keys or IVs**
2. **Use authenticated encryption (GCM mode)** to prevent tampering
3. **Rotate master keys** periodically
4. **Store auth tags** with encrypted data for verification
5. **Use KMS for production** instead of derived keys
