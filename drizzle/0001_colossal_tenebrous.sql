CREATE TABLE `accessibility_requests` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`tenant_id` text NOT NULL,
	`document_id` integer NOT NULL,
	`student_name` text NOT NULL,
	`student_email` text NOT NULL,
	`reason` text NOT NULL,
	`dsp_letter_url` text,
	`status` text DEFAULT 'PENDING' NOT NULL,
	`expiry_duration` text,
	`expiry_date` text,
	`access_url` text,
	`access_sent_at` text,
	`created_at` text NOT NULL,
	`approved_at` text,
	`approved_by` integer,
	FOREIGN KEY (`document_id`) REFERENCES `documents`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
DROP INDEX "tenant_metrics_tenant_id_unique";--> statement-breakpoint
ALTER TABLE `processing_jobs` ALTER COLUMN "status" TO "status" text NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `tenant_metrics_tenant_id_unique` ON `tenant_metrics` (`tenant_id`);