/**
 * Processing Layers Index
 * 
 * Centralized exports for all processing layers.
 * Layers execute in numerical order (01 → 02 → 03 → 04).
 */

export { UploadProcessor } from './01-upload';
export { WatermarkingProcessor } from './02-watermarking';
export { EncryptionProcessor } from './03-encryption';
export { VerificationProcessor } from './04-verification';

/**
 * Layer execution order:
 * 
 * 01-upload       → Validates file type, size, format
 * 02-watermarking → Applies Rust adversarial watermarks (AWS Lambda/ECS)
 * 03-encryption   → Cryptographic hashing and signing
 * 04-verification → Uploads to storage and updates database
 */
