# 🏗️ Backend Architecture - Solvance

**Clean separation of Frontend, Backend, Authentication (Clerk), Payments (Stripe), and AWS services.**

---

## 📁 Directory Structure

```
src/backend/
├── db/                           # 🗄️ Database Layer
│   ├── schema.ts                # Drizzle ORM schema (multi-tenant)
│   ├── index.ts                 # Database connection (Turso)
│   └── migrations/              # Database migrations
│
├── services/                     # 🔧 Business Logic Services
│   ├── auth/                    # 🔐 Clerk Authentication
│   │   ├── index.ts            # Auth utilities & helpers
│   │   └── README.md           # Clerk integration docs
│   │
│   ├── payments/                # 💳 Stripe Payments
│   │   └── README.md           # Stripe integration guide (future)
│   │
│   ├── aws/                     # ☁️ AWS Services
│   │   ├── s3.ts               # S3 file storage
│   │   ├── lambda.ts           # Lambda function invocations
│   │   ├── ecs.ts              # ECS task management (heavy compute)
│   │   ├── sqs.ts              # SQS queue operations
│   │   ├── index.ts            # AWS config & exports
│   │   └── README.md           # AWS integration guide
│   │
│   ├── storage/                 # 📦 Storage Abstraction
│   │   └── index.ts            # Local/S3 storage service
│   │
│   └── processing/              # ⚙️ Document Processing Pipeline
│       ├── layers/              # Processing layers (numbered)
│       │   ├── 01-upload/      # File validation
│       │   │   └── index.ts
│       │   ├── 02-watermarking/ # Rust watermarking (AWS Lambda/ECS)
│       │   │   └── index.ts
│       │   ├── 03-encryption/   # Cryptographic operations
│       │   │   └── index.ts
│       │   ├── 04-verification/ # Output & storage
│       │   │   └── index.ts
│       │   └── index.ts        # Layer exports
│       │
│       ├── orchestrator.ts      # Pipeline coordinator
│       ├── base-processor.ts    # Base class for processors
│       ├── types.ts             # Type definitions
│       └── README.md            # Processing pipeline docs
│
└── ARCHITECTURE.md               # This file
```

---

## 🎯 Design Principles

### 1. **Clear Separation of Concerns**

**Frontend** (`src/app`, `src/components`)
- UI/UX components
- User interactions
- Client-side state management
- React Server Components for static content

**Backend** (`src/backend`)
- Business logic
- Data processing
- Database operations
- External service integrations (AWS, Stripe, Clerk)

**API Routes** (`src/app/api`)
- Thin wrappers around backend services
- Request validation
- Response formatting
- Error handling

### 2. **Multi-Tenant Architecture**

Every table and service includes `tenantId` for complete data isolation:

```typescript
// All database tables
{
  id: integer,
  tenantId: text,  // ← Multi-tenant isolation
  // ... other fields
}

// All service calls
storageService.upload(file, tenantId);
processingPipeline.execute(context /* includes tenantId */);
```

### 3. **Modular Processing Pipeline**

Processing layers are **numbered** for clear execution order:

```
01-upload       → Validates file type, size, format
02-watermarking → Rust adversarial watermarks (AWS Lambda/ECS)
03-encryption   → Cryptographic hashing and signing
04-verification → Uploads to storage and updates database
```

**Why numbered?**
- ✅ Clear execution order at a glance
- ✅ Easy to insert new layers between existing ones
- ✅ Prevents accidental reordering
- ✅ Makes onboarding new developers easier

### 4. **AWS-Ready Architecture**

All AWS services have placeholder implementations that are ready to activate once credentials are provided:

```typescript
// Storage abstraction switches between local and S3
const storageService = new FileStorageService({
  type: process.env.STORAGE_TYPE === 's3' ? 's3' : 'local',
  // ... AWS config
});

// Processing layer automatically selects Lambda or ECS
const service = selectProcessingService(fileSize, duration);
// Returns: 'lambda' (< 10MB) or 'ecs' (> 10MB or long-running)
```

---

## 🔗 Service Integration Patterns

### Clerk Authentication Flow

```
User Sign-In
    ↓
Clerk Auth (managed service)
    ↓
middleware.ts validates session
    ↓
API route derives tenant from Clerk session (no custom headers)
    ↓
Backend services use tenantId for data isolation
```

**Implementation:**
- Auth utilities: `src/backend/services/auth/`
- Middleware: `middleware.ts` (root)
- Sign-in page: `src/app/login/[[...rest]]/page.tsx`
- Sign-up page: `src/app/signup/[[...rest]]/page.tsx`

### Document Processing Flow

```
Upload UI (Dashboard)
    ↓
POST /api/documents
    ↓
storageService.upload() → Local or S3
    ↓
Processing Pipeline Orchestrator
    ↓
Layer 01: Validation
    ↓
Layer 02: Watermarking (Rust via Lambda/ECS)
    ↓
Layer 03: Encryption & Hashing
    ↓
Layer 04: Verification & Storage
    ↓
Database updated with processed file
```

**Key Files:**
- Upload UI: `src/app/dashboard/documents/page.tsx`
- API Route: `src/app/api/documents/route.ts`
- Processing: `src/backend/services/processing/orchestrator.ts`
- Layers: `src/backend/services/processing/layers/`

### AWS Integration (Ready for Activation)

```
Document Upload
    ↓
Upload to S3 (raw bucket)
    ↓
Determine: Lambda vs ECS?
    ├─ Lambda: Files < 10MB, < 15min processing
    └─ ECS: Files > 10MB, long-running jobs
    ↓
Rust Processor Executes
    ↓
Result uploaded to S3 (processed bucket)
    ↓
Database updated with processed file URL
```

**AWS Credentials Needed:**
```bash
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
AWS_S3_BUCKET=solvance-documents-raw
AWS_S3_BUCKET_PROCESSED=solvance-documents-protected
AWS_LAMBDA_FUNCTION=rust-document-processor
AWS_ECS_CLUSTER=solvance-processing
AWS_ECS_TASK=rust-watermark-task
```

---

## 🚀 Adding New Features

### Adding a New Processing Layer

**Example: Adding Layer 05 - Compression**

1. **Create directory:**
   ```
   src/backend/services/processing/layers/05-compression/
   └── index.ts
   ```

2. **Implement processor:**
   ```typescript
   import { BaseProcessor } from '../../base-processor';
   import { ProcessorInput, LayerOutput } from '../../types';
   
   export class CompressionProcessor extends BaseProcessor {
     async process(input: ProcessorInput): Promise<LayerOutput> {
       const { data, context } = input;
       
       // Your compression logic
       const compressed = await this.compress(data);
       
       return {
         success: true,
         data: compressed,
         metadata: {
           originalSize: data.length,
           compressedSize: compressed.length,
         },
       };
     }
   }
   ```

3. **Export from layers/index.ts:**
   ```typescript
   export { CompressionProcessor } from './05-compression';
   ```

4. **Register in orchestrator.ts:**
   ```typescript
   this.registerProcessor('compression', new CompressionProcessor());
   
   // Add to pipeline config
   stages: [
     // ... existing stages
     {
       layer: 'compression',
       required: false,
       retries: 2,
       timeout: 30000,
     },
   ]
   ```

### Adding a New Backend Service

1. **Create service directory:**
   ```
   src/backend/services/my-service/
   ├── index.ts
   └── README.md
   ```

2. **Implement service:**
   ```typescript
   export class MyService {
     async doSomething(tenantId: string) {
       // Your logic
     }
   }
   
   export const myService = new MyService();
   ```

3. **Use in API route:**
```typescript
import { myService } from '@/backend/services/my-service';
import { requireTenantContext } from '@/backend/services/auth';

export async function POST(request: NextRequest) {
  const tenantId = await requireTenantContext(request.headers);
  const result = await myService.doSomething(tenantId);
  return NextResponse.json({ success: true, data: result });
}
```

---

## 📊 Monitoring & Debugging

### Database Tables for Tracking

**Documents Table** (`documents`)
- Status: queued → processing → completed/failed
- Upload timestamp, processed timestamp
- File paths, sizes, types

**Processing Jobs Table** (`processing_jobs`)
- Each layer execution creates a job record
- Tracks: pipeline_stage, status, started_at, completed_at
- Error messages for failed jobs

**Tenant Metrics Table** (`tenant_metrics`)
- Total documents, processed, failed
- Storage used
- Last upload timestamp

### Logging

All processing layers log to console:
```
[Layer 01 - Upload] Starting validation
[Layer 02 - Watermarking] Starting watermarking
[Layer 03 - Encryption] Starting cryptographic processing
[Layer 04 - Verification] Starting output processing
[Pipeline] All stages completed
```

---

## 🔐 Security Considerations

### Multi-Tenant Data Isolation
- Every query includes `WHERE tenantId = ?`
- No cross-tenant data leakage
- Enforced by Clerk middleware

### File Storage Security
- Local: Files stored in `storage/uploads/{tenantId}/`
- S3: Server-side encryption (AES-256)
- Presigned URLs for temporary access

### API Security
- All routes protected by Clerk auth
- Tenant ID extracted from JWT token
- Rate limiting (future)

---

## 📚 Related Documentation

- [Processing Pipeline README](./services/processing/README.md)
- [AWS Integration Guide](./services/aws/README.md)
- [Clerk Auth Setup](./services/auth/README.md)
- [Database Schema](./db/schema.ts)

---

## 🛠️ Development Workflow

### Running Locally
```bash
# Install dependencies
bun install

# Run dev server
bun dev

# Database migrations
bun run db:push
```

### Testing Document Processing
```bash
# Upload a test document
curl -X POST http://localhost:3000/api/documents \
  -H "Authorization: Bearer <CLERK_SESSION_JWT>" \
  -F "file=@test.pdf"

# Check processing status
curl http://localhost:3000/api/documents \
  -H "Authorization: Bearer <CLERK_SESSION_JWT>"
```

### Activating AWS Integration
1. Add AWS credentials to `.env`
2. Set `STORAGE_TYPE=s3` in `.env`
3. Deploy Rust Lambda function
4. Update layer implementations to use AWS services

---

**Last Updated:** November 2025  
**Architecture Version:** 1.0
