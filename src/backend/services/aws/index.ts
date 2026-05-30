/**
 * AWS Services Index
 * 
 * Centralized exports for all AWS service integrations.
 */

export { S3Service } from './s3';
export { LambdaService } from './lambda';
export { ECSService } from './ecs';
export { SQSService } from './sqs';

/**
 * AWS Configuration
 */
export const AWS_CONFIG = {
  region: process.env.AWS_REGION || 'us-east-1',
  s3: {
    bucketName: process.env.AWS_S3_BUCKET || 'solvance-documents',
    bucketNameProcessed: process.env.AWS_S3_BUCKET_PROCESSED || 'solvance-protected',
  },
  lambda: {
    functionName: process.env.AWS_LAMBDA_FUNCTION || 'rust-document-processor',
  },
  ecs: {
    cluster: process.env.AWS_ECS_CLUSTER || 'solvance-processing',
    taskDefinition: process.env.AWS_ECS_TASK || 'rust-watermark-task',
  },
  sqs: {
    queueUrl: process.env.AWS_SQS_QUEUE_URL || '',
  }
};

/**
 * Helper to determine which AWS service to use based on job requirements
 */
export function selectProcessingService(fileSizeBytes: number, estimatedDurationMs: number): 'lambda' | 'ecs' {
  // Lambda has 15-minute timeout and 10GB storage limit
  const LAMBDA_TIMEOUT_MS = 15 * 60 * 1000;
  const LAMBDA_STORAGE_LIMIT = 10 * 1024 * 1024 * 1024;

  if (fileSizeBytes > LAMBDA_STORAGE_LIMIT || estimatedDurationMs > LAMBDA_TIMEOUT_MS) {
    return 'ecs';
  }
  
  return 'lambda';
}
