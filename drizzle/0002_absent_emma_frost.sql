ALTER TABLE `documents` ADD `access_token` text NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `documents_access_token_unique` ON `documents` (`access_token`);