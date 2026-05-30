# Layer 01: Upload & Validation

**Purpose:** Initial file upload, validation, and storage preparation.

## 🎯 Responsibilities

- Accept file uploads from the dashboard UI
- Validate file type, size, and format
- Store file in local/S3 storage
- Create database record with metadata
- Generate unique document ID
- Update tenant metrics

## 📋 Input

```typescript
{
  context: {
    tenantId: string;
    originalFilename: string;
    fileType: string;
  },
  data: File | Buffer
}
```

## 📤 Output

```typescript
{
  success: boolean;
  data: Buffer; // Original file data
  metadata: {
    documentId: number;
    filePath: string;
    fileSize: number;
    storageType: 'local' | 's3';
    uploadTimestamp: string;
  }
}
```

## 🔌 Integration Point for Dashboard UI

This layer connects directly to the **drag-and-drop upload UI** in `/dashboard/documents`.

### Frontend Upload Flow

```typescript
// In dashboard component
const handleUpload = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await fetch('/api/documents', {
    method: 'POST',
    credentials: 'include', // Clerk session cookie
    body: formData,
  });
  
  const result = await response.json();
  // result.document contains documentId, status, etc.
};
```

### Backend API Route

```typescript
// /api/documents/route.ts calls this layer
import { storageService } from '@/backend/services/storage';

const uploadResult = await storageService.upload(file, tenantId);
// Automatically triggers Layer 01 processing
```

## ✅ Validation Rules

```typescript
const ALLOWED_TYPES = ['application/pdf', 'image/png', 'image/jpeg'];
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

function validateUpload(file: File): void {
  if (!ALLOWED_TYPES.includes(file.type)) {
    throw new Error('Invalid file type');
  }
  if (file.size > MAX_FILE_SIZE) {
    throw new Error('File too large');
  }
}
```

## 🔄 Next Layer

Output from Layer 01 → Input to **Layer 02: Watermarking**

The `documentId` and `filePath` are passed to the watermarking layer for Rust processing.
