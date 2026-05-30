# Backend Architecture

This directory contains all backend business logic, separate from the Next.js frontend.

## 📁 Structure

```
backend/
├── db/                    # Database layer (Turso + Drizzle ORM)
│   ├── schema.ts         # Database schema definitions
│   ├── index.ts          # Database connection & client
│   └── migrations/       # Database migrations
│
├── services/             # Business logic services
│   ├── auth/            # Clerk authentication utilities
│   ├── payments/        # Stripe payment integration (future)
│   ├── aws/             # AWS service integrations
│   │   ├── s3.ts       # S3 file storage
│   │   ├── lambda.ts   # Lambda function invocations
│   │   ├── ecs.ts      # ECS task management
│   │   └── sqs.ts      # SQS queue operations
│   ├── storage/         # File storage abstraction layer
│   └── processing/      # Document processing pipeline
│       ├── layers/      # Processing layers (numbered)
│       │   ├── 01-upload/
│       │   ├── 02-watermarking/
│       │   ├── 03-encryption/
│       │   └── 04-verification/
│       ├── orchestrator.ts
│       └── types.ts
│
└── utils/               # Backend utility functions
```

## 🎯 Design Principles

### 1. **Separation of Concerns**
- Frontend (`src/app`, `src/components`) handles UI/UX only
- Backend (`src/backend`) handles all business logic
- API routes (`src/app/api`) are thin wrappers calling backend services

### 2. **Multi-tenant Architecture**
- All database tables include `tenantId` for data isolation
- All services accept `tenantId` as parameter
- Clerk middleware enforces tenant boundaries

### 3. **Modular Processing Pipeline**
- Processing layers are numbered (`01-`, `02-`, etc.) for clear execution order
- Each layer is independent and can be updated without affecting others
- Easy to add new layers by creating new numbered directories

### 4. **AWS-Ready Architecture**
- Storage abstraction allows switching between local/S3
- Processing pipeline ready for Lambda/ECS integration
- SQS queue support for async job processing

## 🔧 How to Extend

### Adding a New Processing Layer

1. Create a new numbered directory in `backend/services/processing/layers/`
   ```
   05-my-new-layer/
   ├── index.ts
   ├── processor.ts
   └── README.md
   ```

2. Implement the `BaseProcessor` interface:
   ```typescript
   import { BaseProcessor, LayerOutput } from '../../types';
   
   export class MyNewLayerProcessor extends BaseProcessor {
     async process(input: ProcessorInput): Promise<LayerOutput> {
       // Your processing logic
     }
   }
   ```

3. Register in the orchestrator:
   ```typescript
   orchestrator.registerProcessor('my-layer', new MyNewLayerProcessor());
   ```

### Adding a New Service

1. Create directory in `backend/services/[service-name]/`
2. Export service functions/classes from `index.ts`
3. Import in API routes: `import { myService } from '@/backend/services/my-service'`

## 📚 Service Documentation

- [Database](./db/README.md) - Schema, migrations, queries
- [Processing Pipeline](./services/processing/README.md) - Document processing layers
- [AWS Integration](./services/aws/README.md) - S3, Lambda, ECS, SQS
- [Authentication](./services/auth/README.md) - Clerk utilities
- [Payments](./services/payments/README.md) - Stripe integration (future)
