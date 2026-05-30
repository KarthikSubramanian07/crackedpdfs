CREATE TABLE `documents` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`tenant_id` text NOT NULL,
	`filename` text NOT NULL,
	`original_filename` text NOT NULL,
	`file_path` text NOT NULL,
	`file_size` integer NOT NULL,
	`file_type` text NOT NULL,
	`status` text DEFAULT 'queued' NOT NULL,
	`uploaded_at` text NOT NULL,
	`processed_at` text,
	`processing_started_at` text,
	`error_message` text,
	`metadata` text
);
--> statement-breakpoint
CREATE TABLE `processing_jobs` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`document_id` integer NOT NULL,
	`tenant_id` text NOT NULL,
	`pipeline_stage` text NOT NULL,
	`status` text DEFAULT 'pending' NOT NULL,
	`started_at` text,
	`completed_at` text,
	`error_message` text,
	`input_data` text,
	`output_data` text,
	`created_at` text NOT NULL,
	FOREIGN KEY (`document_id`) REFERENCES `documents`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `tenant_metrics` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`tenant_id` text NOT NULL,
	`total_documents` integer DEFAULT 0 NOT NULL,
	`documents_processed` integer DEFAULT 0 NOT NULL,
	`documents_failed` integer DEFAULT 0 NOT NULL,
	`total_storage_bytes` integer DEFAULT 0 NOT NULL,
	`last_upload_at` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `tenant_metrics_tenant_id_unique` ON `tenant_metrics` (`tenant_id`);