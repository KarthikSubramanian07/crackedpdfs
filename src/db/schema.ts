import { sqliteTable, integer, text } from 'drizzle-orm/sqlite-core';

export const documents = sqliteTable('documents', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  tenantId: text('tenant_id').notNull(),
  filename: text('filename').notNull(),
  originalFilename: text('original_filename').notNull(),
  filePath: text('file_path').notNull(),
  fileSize: integer('file_size').notNull(),
  fileType: text('file_type').notNull(),
  status: text('status').notNull().default('queued'),
  accessToken: text('access_token').notNull().unique(),
  uploadedAt: text('uploaded_at').notNull(),
  processedAt: text('processed_at'),
  processingStartedAt: text('processing_started_at'),
  processingCompletedAt: text('processing_completed_at'),
  errorMessage: text('error_message'),
  metadata: text('metadata', { mode: 'json' }),
  accessibilityRequestLink: text('accessibility_request_link'),
});

export const processingJobs = sqliteTable('processing_jobs', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  documentId: integer('document_id').notNull().references(() => documents.id),
  tenantId: text('tenant_id').notNull(),
  pipelineStage: text('pipeline_stage').notNull(),
  status: text('status').notNull(),
  inputData: text('input_data', { mode: 'json' }),
  outputData: text('output_data', { mode: 'json' }),
  errorMessage: text('error_message'),
  createdAt: text('created_at').notNull(),
  startedAt: text('started_at'),
  completedAt: text('completed_at'),
});

export const tenantMetrics = sqliteTable('tenant_metrics', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  tenantId: text('tenant_id').notNull().unique(),
  totalDocuments: integer('total_documents').notNull().default(0),
  documentsProcessed: integer('documents_processed').notNull().default(0),
  documentsFailed: integer('documents_failed').notNull().default(0),
  totalStorageBytes: integer('total_storage_bytes').notNull().default(0),
  lastUploadAt: text('last_upload_at'),
  createdAt: text('created_at').notNull(),
  updatedAt: text('updated_at').notNull(),
});

export const accessibilityRequests = sqliteTable('accessibility_requests', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  tenantId: text('tenant_id').notNull(),
  documentId: integer('document_id').notNull().references(() => documents.id),
  studentName: text('student_name').notNull(),
  studentEmail: text('student_email').notNull(),
  reason: text('reason').notNull(),
  dspLetterUrl: text('dsp_letter_url'),
  status: text('status').notNull().default('PENDING'),
  expiryDuration: text('expiry_duration'),
  expiryDate: text('expiry_date'),
  accessUrl: text('access_url'),
  accessSentAt: text('access_sent_at'),
  createdAt: text('created_at').notNull(),
  approvedAt: text('approved_at'),
  approvedBy: integer('approved_by'),
});

export const promptInjectionMessages = sqliteTable('prompt_injection_messages', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  tenantId: text('tenant_id').notNull(),
  name: text('name').notNull(),
  messageType: text('message_type').notNull(),
  content: text('content').notNull(),
  isActive: integer('is_active', { mode: 'boolean' }).notNull().default(true),
  createdAt: text('created_at').notNull(),
  updatedAt: text('updated_at').notNull(),
});
