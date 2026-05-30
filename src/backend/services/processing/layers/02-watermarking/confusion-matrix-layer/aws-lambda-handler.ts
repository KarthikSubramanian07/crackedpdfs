/**
 * AWS Lambda Handler for Rust Confusion Matrix Layer
 * 
 * Designed for Lambda/ECS deployment with S3 integration.
 * Handles large PDFs via streaming and automatic service selection.
 */

import { S3Client, GetObjectCommand, PutObjectCommand } from "@aws-sdk/client-s3";
import { Readable } from "stream";
import * as fs from "fs/promises";
import * as path from "path";
import * as os from "os";
import { executeConfusionMatrixLayer, ConfusionMatrixConfig } from "./cli-executor";

interface LambdaEvent {
  tenantId: string;
  documentId: string;
  inputS3Key: string;
  inputS3Bucket: string;
  outputS3Bucket: string;
  config?: ConfusionMatrixConfig;
}

interface LambdaResponse {
  success: boolean;
  outputS3Key?: string;
  pageCount?: number;
  error?: string;
  executionTimeMs: number;
}

const s3Client = new S3Client({ region: process.env.AWS_REGION || "us-east-1" });

/**
 * Lambda handler function
 */
export async function handler(event: LambdaEvent): Promise<LambdaResponse> {
  const startTime = Date.now();
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "confusion-matrix-"));

  try {
    console.log("[Confusion Matrix] Processing started", {
      tenantId: event.tenantId,
      documentId: event.documentId,
      inputKey: event.inputS3Key,
    });

    // Download PDF from S3
    const inputPath = path.join(tmpDir, "input.pdf");
    await downloadFromS3(
      event.inputS3Bucket,
      event.inputS3Key,
      inputPath
    );

    console.log("[Confusion Matrix] Downloaded input PDF", {
      size: (await fs.stat(inputPath)).size,
    });

    // Execute Rust layer
    const result = await executeConfusionMatrixLayer(
      inputPath,
      tmpDir,
      event.config || {}
    );

    if (!result.success) {
      throw new Error(result.error || "Processing failed");
    }

    console.log("[Confusion Matrix] Processing complete", {
      pageCount: result.pageCount,
      executionTimeMs: result.executionTimeMs,
    });

    // Upload result to S3
    const outputS3Key = `processed/${event.tenantId}/${event.documentId}/watermarked.pdf`;
    await uploadToS3(
      event.outputS3Bucket,
      outputS3Key,
      result.outputPath!
    );

    console.log("[Confusion Matrix] Uploaded to S3", { key: outputS3Key });

    // Cleanup
    await fs.rm(tmpDir, { recursive: true, force: true });

    return {
      success: true,
      outputS3Key,
      pageCount: result.pageCount,
      executionTimeMs: Date.now() - startTime,
    };
  } catch (error) {
    console.error("[Confusion Matrix] Error:", error);

    // Cleanup on error
    try {
      await fs.rm(tmpDir, { recursive: true, force: true });
    } catch {}

    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
      executionTimeMs: Date.now() - startTime,
    };
  }
}

/**
 * Download file from S3
 */
async function downloadFromS3(
  bucket: string,
  key: string,
  localPath: string
): Promise<void> {
  const command = new GetObjectCommand({ Bucket: bucket, Key: key });
  const response = await s3Client.send(command);

  if (!response.Body) {
    throw new Error("Empty S3 response body");
  }

  const writeStream = require("fs").createWriteStream(localPath);
  const readStream = response.Body as Readable;

  return new Promise((resolve, reject) => {
    readStream.pipe(writeStream);
    readStream.on("error", reject);
    writeStream.on("error", reject);
    writeStream.on("finish", resolve);
  });
}

/**
 * Upload file to S3
 */
async function uploadToS3(
  bucket: string,
  key: string,
  localPath: string
): Promise<void> {
  const fileContent = await fs.readFile(localPath);

  const command = new PutObjectCommand({
    Bucket: bucket,
    Key: key,
    Body: fileContent,
    ContentType: "application/pdf",
  });

  await s3Client.send(command);
}

/**
 * Determine if Lambda or ECS should be used based on file size
 */
export function selectProcessingService(fileSizeBytes: number): "lambda" | "ecs" {
  const LAMBDA_SIZE_LIMIT = 10 * 1024 * 1024; // 10MB
  return fileSizeBytes > LAMBDA_SIZE_LIMIT ? "ecs" : "lambda";
}
