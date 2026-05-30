# Database Layer

Multi-tenant database architecture using **Turso** (distributed SQLite) and **Drizzle ORM**.

## 📊 Schema

### Tables

#### `documents`
Stores all uploaded documents with processing status and metadata.

```typescript
{
  id: number;                    // Auto-increment primary key
  tenantId: string;              // Clerk user ID (multi-tenant isolation)
  filename: string;              // Generated filename
  originalFilename: string;      // User's original filename
  filePath: string;              // Storage path (local or S3 key)
  fileSize: number;              // File size in bytes
  fileType: string;              // MIME type
  status: 'queued' | 'processing' | 'completed' | 'failed';
  uploadedAt: string;            // ISO timestamp
  processedAt?: string;          // ISO timestamp when completed
  processingStartedAt?: string;  // ISO timestamp when started
  errorMessage?: string;         // Error details if failed
  metadata?: Record<string, any>; // Custom metadata (JSON)
}
```

#### `processing_jobs`
Tracks individual processing layer executions for observability.

```typescript
{
  id: number;                    // Auto-increment primary key
  documentId: number;            // References documents.id
  tenantId: string;              // Clerk user ID
  pipelineStage: string;         // Layer name (e.g., "watermarking")
  status: 'pending' | 'running' | 'completed' | 'failed';
  startedAt?: string;            // ISO timestamp
  completedAt?: string;          // ISO timestamp
  errorMessage?: string;         // Error details if failed
  inputData?: Record<string, any>; // Layer input metadata
  outputData?: Record<string, any>; // Layer output metadata
  createdAt: string;             // ISO timestamp
}
```

#### `tenant_metrics`
Aggregated usage statistics per tenant for dashboard display.

```typescript
{
  id: number;                    // Auto-increment primary key
  tenantId: string;              // Clerk user ID (unique)
  totalDocuments: number;        // Total docs uploaded
  documentsProcessed: number;    // Successfully processed
  documentsFailed: number;       // Failed processing
  totalStorageBytes: number;     // Total storage used
  lastUploadAt?: string;         // Last upload timestamp
  createdAt: string;             // ISO timestamp
  updatedAt: string;             // ISO timestamp
}
```

## 🔐 Multi-tenancy

All queries MUST include `tenantId` for data isolation:

```typescript
// ✅ Good - tenant isolated
const docs = await db.select()
  .from(documents)
  .where(eq(documents.tenantId, userId));

// ❌ Bad - exposes all tenants' data
const docs = await db.select()
  .from(documents);
```

## 🔧 Usage Examples

### Insert Document
```typescript
import { db } from '@/backend/db';
import { documents } from '@/backend/db/schema';

const newDoc = await db.insert(documents).values({
  tenantId: userId,
  filename: 'generated-filename.pdf',
  originalFilename: 'resume.pdf',
  filePath: 'uploads/user123/generated-filename.pdf',
  fileSize: 1024000,
  fileType: 'application/pdf',
  status: 'queued',
  uploadedAt: new Date().toISOString(),
}).returning();
```

### Update Document Status
```typescript
import { eq, and } from 'drizzle-orm';

await db.update(documents)
  .set({ 
    status: 'completed',
    processedAt: new Date().toISOString()
  })
  .where(and(
    eq(documents.id, docId),
    eq(documents.tenantId, userId) // Always include tenant check
  ));
```

### Query with Filters
```typescript
const pendingDocs = await db.select()
  .from(documents)
  .where(and(
    eq(documents.tenantId, userId),
    eq(documents.status, 'queued')
  ))
  .orderBy(desc(documents.uploadedAt))
  .limit(10);
```

## 🚀 Migrations

Migrations are managed by Drizzle Kit. Configuration in `drizzle.config.ts`:

```bash
# Generate migration
npx drizzle-kit generate

# Push to database
npx drizzle-kit push
```

## 📈 Performance Tips

1. **Always index `tenantId`** for fast multi-tenant queries
2. **Use `.limit()`** for pagination - never load all records
3. **Batch operations** when possible (use transactions)
4. **JSON metadata** - keep it small, don't store binary data

## 🔗 Connection

Database credentials are stored in `.env`:

```bash
TURSO_CONNECTION_URL=libsql://your-database.turso.io
TURSO_AUTH_TOKEN=your-auth-token
```

Connection is singleton - created once and reused across requests.
