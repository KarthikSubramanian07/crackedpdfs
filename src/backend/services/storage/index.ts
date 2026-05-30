/**
 * File Storage Service
 * 
 * Handles file storage operations with support for local filesystem and S3.
 * Structured to easily swap between local and S3 storage.
 */

import { writeFile, mkdir, unlink, readFile, readdir, copyFile, stat } from 'fs/promises';
import { existsSync } from 'fs';
import path from 'path';
import { randomUUID } from 'crypto';
import {
  S3Client,
  PutObjectCommand,
  GetObjectCommand,
  DeleteObjectCommand,
  ListObjectsV2Command,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import type { Readable } from 'stream';

export type StorageStage = 'uploads' | 'processed' | 'metadata';

export interface StorageContext {
  tenantId: string;
  userId: string;
  documentId: string;
  stage: StorageStage;
  filename?: string;
}

export interface StorageConfig {
  type: 'local' | 's3';
  localBasePath?: string;
  s3Bucket?: string;
  s3Region?: string;
  s3Prefix?: string;
  s3KmsKeyId?: string;
  signedUrlExpirationSeconds?: number;
}

export interface UploadResult {
  path: string;
  url: string;
  size: number;
  bucket?: string;
}

export class FileStorageService {
  private config: StorageConfig;
  private s3Client?: S3Client;
  private readonly verboseLocalLogs: boolean;

  constructor(config: StorageConfig) {
    this.config = config;
    this.verboseLocalLogs = process.env.STORAGE_VERBOSE_LOCAL_LOGS === 'true';
    if (this.config.type === 's3') {
      this.s3Client = new S3Client({
        region: this.config.s3Region,
      });
    }
  }

  isS3(): boolean {
    return this.config.type === 's3';
  }

  isLocal(): boolean {
    return this.config.type === 'local';
  }

  getLocalBasePath(): string | null {
    if (this.config.type !== 'local') {
      return null;
    }
    return this.config.localBasePath || path.join(process.cwd(), 'storage');
  }

  resolveLocalTarget(
    context: StorageContext,
    filename: string
  ): { path: string; fullPath: string; url: string } {
    if (this.config.type !== 'local') {
      throw new Error('Local target resolution is only available for local storage');
    }

    const relativePath = this.buildRelativePath(context, filename);
    const basePath = this.getLocalBasePath();
    if (!basePath) {
      throw new Error('Local storage base path is unavailable');
    }

    return {
      path: relativePath,
      fullPath: path.join(basePath, relativePath),
      url: this.getUrl(relativePath),
    };
  }

  async copyLocalFile(
    sourcePath: string,
    filename: string,
    context: StorageContext
  ): Promise<UploadResult> {
    const target = this.resolveLocalTarget(context, filename);
    const dir = path.dirname(target.fullPath);
    if (!existsSync(dir)) {
      await mkdir(dir, { recursive: true });
    }

    await copyFile(sourcePath, target.fullPath);
    const fileStats = await stat(target.fullPath);

    return {
      path: target.path,
      url: target.url,
      size: fileStats.size,
    };
  }

  /**
   * Upload file/blob to storage
   */
  async upload(file: File, context: StorageContext): Promise<UploadResult> {
    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    const contentType = file.type || 'application/octet-stream';
    const filename = file.name || `${randomUUID()}`;
    return this.uploadBuffer(buffer, filename, contentType, context);
  }

  async uploadBuffer(
    buffer: Buffer,
    filename: string,
    contentType: string,
    context: StorageContext
  ): Promise<UploadResult> {
    if (!context) {
      throw new Error('Storage context is required for uploads');
    }

    if (this.config.type === 'local') {
      return this.uploadLocal(buffer, filename, contentType, context);
    }

    return this.uploadS3(buffer, filename, contentType, context);
  }

  /**
   * Download file from storage
   */
  async download(filePath: string): Promise<Buffer> {
    if (this.config.type === 'local') {
      return this.downloadLocal(filePath);
    } else {
      return this.downloadS3(filePath);
    }
  }

  /**
   * Delete file from storage
   */
  async delete(filePath: string): Promise<void> {
    if (!filePath) return;
    if (this.config.type === 'local') {
      return this.deleteLocal(filePath);
    } else {
      return this.deleteS3(filePath);
    }
  }

  /**
   * List object/file paths under a storage prefix.
   * Returns relative keys (same shape as upload result paths).
   */
  async list(prefix: string): Promise<string[]> {
    if (this.config.type === 'local') {
      return this.listLocal(prefix);
    }
    return this.listS3(prefix);
  }

  /**
   * Generate presigned download URL (S3 only)
   */
  async getSignedDownloadUrl(
    filePath: string,
    expiresInSeconds?: number,
    options?: {
      responseContentDisposition?: string;
      responseContentType?: string;
    }
  ): Promise<string> {
    if (this.config.type !== 's3') {
      return this.getUrl(filePath);
    }

    if (!this.s3Client) {
      throw new Error('S3 client not configured');
    }

    const bucket = this.config.s3Bucket;
    if (!bucket) {
      throw new Error('AWS_S3_BUCKET is not configured');
    }

    const command = new GetObjectCommand({
      Bucket: bucket,
      Key: filePath,
      ...(options?.responseContentDisposition && {
        ResponseContentDisposition: options.responseContentDisposition,
      }),
      ...(options?.responseContentType && {
        ResponseContentType: options.responseContentType,
      }),
    });

    const expiresIn = expiresInSeconds ?? this.config.signedUrlExpirationSeconds ?? 60;
    return getSignedUrl(this.s3Client, command, { expiresIn });
  }

  /**
   * Get internal API URL for accessing files through Next.js route
   */
  getUrl(filePath: string): string {
    return `/api/files/${filePath}`;
  }

  getMetadataKey(identity: { tenantId: string; userId: string; documentId: string }): string {
    return this.buildRelativePath({ ...identity, stage: 'metadata' });
  }

  /**
   * Write metadata.json describing the document (shared between raw + processed).
   */
  async writeMetadataFile(
    baseContext: Omit<StorageContext, 'stage'>,
    metadata: Record<string, any>
  ): Promise<UploadResult> {
    const buffer = Buffer.from(JSON.stringify(metadata, null, 2), 'utf-8');
    const context: StorageContext = { ...baseContext, stage: 'metadata', filename: 'metadata.json' };
    return this.uploadBuffer(buffer, 'metadata.json', 'application/json', context);
  }

  // ==================== LOCAL STORAGE ====================

  private async uploadLocal(
    buffer: Buffer,
    filename: string,
    contentType: string,
    context: StorageContext
  ): Promise<UploadResult> {
    try {
      const basePath = this.config.localBasePath || path.join(process.cwd(), 'storage');
      const relativePath = this.buildRelativePath(context, filename);
      const fullPath = path.join(basePath, relativePath);

      if (this.verboseLocalLogs) {
        console.log('[FileStorage] Upload started (local):', {
          filename,
          size: buffer.length,
          contentType,
          relativePath,
          fullPath
        });
      }

      const dir = path.dirname(fullPath);
      if (!existsSync(dir)) {
        await mkdir(dir, { recursive: true });
      }

      await writeFile(fullPath, buffer);

      const result = {
        path: relativePath,
        url: this.getUrl(relativePath),
        size: buffer.length
      };

      if (this.verboseLocalLogs) {
        console.log('[FileStorage] Upload complete (local):', result);
      }
      return result;
    } catch (error) {
      console.error('[FileStorage] Upload failed (local):', error);
      throw new Error(`Failed to upload file locally: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  private async downloadLocal(filePath: string): Promise<Buffer> {
    const basePath = this.config.localBasePath || path.join(process.cwd(), 'storage');
    const fullPath = path.join(basePath, filePath);

    if (!existsSync(fullPath)) {
      throw new Error(`File not found: ${filePath}`);
    }

    return await readFile(fullPath);
  }

  private async deleteLocal(filePath: string): Promise<void> {
    const basePath = this.config.localBasePath || path.join(process.cwd(), 'storage');
    const fullPath = path.isAbsolute(filePath) ? filePath : path.join(basePath, filePath);

    if (existsSync(fullPath)) {
      await unlink(fullPath);
      console.log('[FileStorage] File deleted (local):', fullPath);
    }
  }

  private async listLocal(prefix: string): Promise<string[]> {
    const basePath = this.config.localBasePath || path.join(process.cwd(), 'storage');
    const normalizedPrefix = prefix
      .replace(/\\/g, '/')
      .replace(/^\/+/, '')
      .replace(/\/+$/, '');
    const absolutePrefixPath = path.join(basePath, ...normalizedPrefix.split('/'));

    if (!existsSync(absolutePrefixPath)) {
      return [];
    }

    const results: string[] = [];
    const walk = async (absoluteDir: string) => {
      const entries = await readdir(absoluteDir, { withFileTypes: true });
      for (const entry of entries) {
        const absolutePath = path.join(absoluteDir, entry.name);
        if (entry.isDirectory()) {
          await walk(absolutePath);
          continue;
        }
        const relativePath = path
          .relative(basePath, absolutePath)
          .split(path.sep)
          .join('/');
        results.push(relativePath);
      }
    };

    await walk(absolutePrefixPath);
    return results.sort((a, b) => a.localeCompare(b));
  }

  // ==================== S3 STORAGE ====================

  private async uploadS3(
    buffer: Buffer,
    filename: string,
    contentType: string,
    context: StorageContext
  ): Promise<UploadResult> {
    if (!this.s3Client) {
      throw new Error('S3 client not configured');
    }

    const bucket = this.config.s3Bucket;
    if (!bucket) {
      throw new Error('AWS_S3_BUCKET is not configured');
    }

    const key = this.buildRelativePath(context, filename);
    const command = new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      Body: buffer,
      ContentType: contentType,
      ServerSideEncryption: this.config.s3KmsKeyId ? 'aws:kms' : 'AES256',
      SSEKMSKeyId: this.config.s3KmsKeyId,
      Tagging: `stage=${context.stage}`,
    });

    await this.s3Client.send(command);

    const result = {
      path: key,
      url: this.getUrl(key),
      size: buffer.length,
      bucket,
    };

    console.log('[FileStorage] Upload complete (s3):', result);
    return result;
  }

  private async downloadS3(filePath: string): Promise<Buffer> {
    if (!this.s3Client) {
      throw new Error('S3 client not configured');
    }

    const bucket = this.config.s3Bucket;
    if (!bucket) {
      throw new Error('AWS_S3_BUCKET is not configured');
    }

    const command = new GetObjectCommand({
      Bucket: bucket,
      Key: filePath,
    });

    const response = await this.s3Client.send(command);
    const body = response.Body;
    if (!body) {
      throw new Error('Empty response from S3');
    }

    const buffer = await this.streamToBuffer(body as Readable);
    return buffer;
  }

  private async deleteS3(filePath: string): Promise<void> {
    if (!this.s3Client) {
      throw new Error('S3 client not configured');
    }

    const bucket = this.config.s3Bucket;
    if (!bucket) {
      throw new Error('AWS_S3_BUCKET is not configured');
    }

    const command = new DeleteObjectCommand({
      Bucket: bucket,
      Key: filePath,
    });

    await this.s3Client.send(command);
    console.log('[FileStorage] File deleted (s3):', filePath);
  }

  private async listS3(prefix: string): Promise<string[]> {
    if (!this.s3Client) {
      throw new Error('S3 client not configured');
    }

    const bucket = this.config.s3Bucket;
    if (!bucket) {
      throw new Error('AWS_S3_BUCKET is not configured');
    }

    const normalizedPrefix = prefix
      .replace(/\\/g, '/')
      .replace(/^\/+/, '')
      .replace(/\/+$/, '');

    let continuationToken: string | undefined;
    const keys: string[] = [];

    do {
      const response = await this.s3Client.send(
        new ListObjectsV2Command({
          Bucket: bucket,
          Prefix: normalizedPrefix.length > 0 ? `${normalizedPrefix}/` : undefined,
          ContinuationToken: continuationToken,
        })
      );

      const contents = response.Contents || [];
      for (const item of contents) {
        if (item.Key) {
          keys.push(item.Key);
        }
      }
      continuationToken = response.IsTruncated
        ? response.NextContinuationToken
        : undefined;
    } while (continuationToken);

    return keys.sort((a, b) => a.localeCompare(b));
  }

  private async streamToBuffer(stream: Readable): Promise<Buffer> {
    const chunks: Buffer[] = [];
    for await (const chunk of stream) {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    }
    return Buffer.concat(chunks);
  }

  private buildRelativePath(context: StorageContext, originalFilename?: string): string {
    const prefix = this.config.s3Prefix?.replace(/\/+$/, '') || 'tenants';
    const sanitizedTenant = this.sanitizeSegment(context.tenantId);
    const sanitizedUser = this.sanitizeSegment(context.userId);
    const sanitizedDocument = this.sanitizeSegment(context.documentId);

    let finalFilename = originalFilename
      ? this.sanitizeSegment(originalFilename)
      : `${Date.now()}_${randomUUID()}`;

    if (context.stage === 'metadata') {
      finalFilename = context.filename || 'metadata.json';
    }

    const segments = [
      prefix,
      sanitizedTenant,
      'users',
      sanitizedUser,
      sanitizedDocument,
      context.stage,
    ];

    if (context.stage === 'metadata') {
      segments.pop(); // remove stage to place metadata at document root
      segments.push('metadata.json');
    } else {
      segments.push(finalFilename);
    }

    return segments.filter(Boolean).join('/');
  }

  private sanitizeSegment(value: string): string {
    return value.replace(/[^a-zA-Z0-9._-]/g, '_');
  }
}

// Default storage service instance
export const storageService = new FileStorageService({
  type: process.env.STORAGE_TYPE === 's3' ? 's3' : 'local',
  localBasePath: process.env.STORAGE_LOCAL_PATH,
  s3Bucket: process.env.AWS_S3_BUCKET,
  s3Region: process.env.AWS_REGION || 'us-east-1',
  s3Prefix: process.env.AWS_S3_PREFIX || 'tenants',
  s3KmsKeyId: process.env.AWS_S3_KMS_KEY_ID,
  signedUrlExpirationSeconds: process.env.STORAGE_SIGNED_URL_TTL
    ? Number(process.env.STORAGE_SIGNED_URL_TTL)
    : 120,
});
