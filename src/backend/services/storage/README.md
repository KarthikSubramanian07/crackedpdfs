# Storage Service

Unified abstraction for local and AWS S3 storage that enforces the tenant/user/document layout required for production.

## Why it exists

- Every document (raw + processed) lives under `tenants/{tenantId}/users/{userId}/{documentId}` no matter where the code runs.
- `metadata.json` is rewritten at each lifecycle transition (`queued → processing → completed/failed`) so downstream systems can index without touching the database.
- The frontend always hits `/api/files/{key}`; in production the route returns a short‑lived presigned URL so the browser talks directly to S3. Clients never see IAM credentials.

## API surface

```ts
type StorageStage = 'uploads' | 'processed' | 'metadata';

interface StorageIdentity {
  tenantId: string;
  userId: string;
  documentId: string;
}

await storageService.upload(file, { ...identity, stage: 'uploads' });
await storageService.uploadBuffer(buffer, name, mime, { ...identity, stage: 'processed' });
await storageService.writeMetadataFile(identity, metadata);   // writes metadata.json

const buffer = await storageService.download(key);
await storageService.delete(key);

const signed = await storageService.getSignedDownloadUrl(key, 120); // redirects when STORAGE_TYPE=s3
const metadataKey = storageService.getMetadataKey(identity);        // tenants/{tenant}/users/{user}/{doc}/metadata.json
```

`getUrl(key)` always returns `/api/files/{key}` so the UI does not change between environments.

## Configuration

```bash
# Local development (writes to ./storage)
STORAGE_TYPE=local
STORAGE_LOCAL_PATH=./storage

# Production S3
STORAGE_TYPE=s3
AWS_REGION=us-east-1
AWS_S3_BUCKET=solvance-documents
AWS_S3_PREFIX=tenants          # optional, defaults to "tenants"
AWS_S3_KMS_KEY_ID=arn:aws:kms:...   # optional, enables SSE-KMS
STORAGE_SIGNED_URL_TTL=120          # optional download expiry (seconds)
```

AWS credentials (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`) are injected by Railway or the host IAM role—never hard-code them.

## Folder layout (local + S3)

```
solvance-documents/
  tenants/{tenant_id}/
    users/{user_id}/
      {document_id}/
        uploads/{timestamp}_{original}.pdf
        processed/{document_id}_{timestamp}.pdf
        metadata.json
```

Local mode mirrors the exact same structure inside `./storage/`.

## IAM policy (attach to `solvance-backend-role`)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:GetObjectTagging",
        "s3:PutObjectTagging"
      ],
      "Resource": "arn:aws:s3:::solvance-documents/tenants/*/users/*/*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::solvance-documents",
      "Condition": {
        "StringLike": {
          "s3:prefix": "tenants/*/users/*/"
        }
      }
    }
  ]
}
```

- Enable bucket versioning, block public access, and turn on lifecycle rules (e.g., move `uploads/` to Glacier after 30 days, `processed/` to IA after 60 days).
- Use SSE-KMS (`AWS_S3_KMS_KEY_ID`) when you need customer-managed encryption; otherwise AES-256 is used automatically.

## Download flow

1. Client opens `/api/files/{key}`.
2. When `STORAGE_TYPE=s3` the route asks `storageService` for a presigned GET URL (default 120 s TTL) and responds with a 302 redirect.
3. Browser streams the file directly from S3 using that temporary URL.
4. In local mode the route simply streams the bytes from `./storage`.

## Metadata helper

```ts
const identity = { tenantId, userId, documentId };
const uploadResult = await storageService.upload(file, { ...identity, stage: 'uploads' });

await storageService.writeMetadataFile(identity, {
  status: 'queued',
  storageDocumentId: identity.documentId,
  storage: {
    uploadPath: uploadResult.path,
    processedPath: null,
  },
  originalFilename: file.name,
  fileSize: file.size,
  uploadedAt: new Date().toISOString(),
});
```

When processing finishes the verification layer writes an updated metadata blob with `status: 'completed'` and the processed S3 key so analytics/ingestion pipelines have a single source of truth.
