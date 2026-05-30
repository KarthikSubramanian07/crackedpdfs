/**
 * Link Insertion Layer Wrapper
 * Adds accessibility request link to the last page of PDFs
 */

import { execFile } from 'child_process';
import { promisify } from 'util';
import * as fs from 'fs/promises';
import { getLinkInsertionScriptPath } from '../path-utils';
import { getPythonExecutable } from '../python-utils';

const execFileAsync = promisify(execFile);

export interface LinkInsertionOptions {
  inputPath: string;
  outputPath: string;
  accessToken: string;
  baseUrl?: string;
  timeoutMs?: number;
  referencePath?: string;
}

export interface LinkInsertionResult {
  success: boolean;
  outputPath: string;
  metadata: {
    linkAdded: boolean;
    accessibilityUrl: string;
    processingTimeMs: number;
    linkPosition: string;
  };
  error?: string;
}

/**
 * Add accessibility request link to PDF
 */
export async function addAccessibilityLink(
  options: LinkInsertionOptions
): Promise<LinkInsertionResult> {
  const startTime = Date.now();
  const scriptPath = getLinkInsertionScriptPath();
  const baseUrl = options.baseUrl || process.env.NEXT_PUBLIC_APP_URL || 'https://solvance.ai';
  const pythonBin = getPythonExecutable();
  
  try {
    // Verify script exists
    await fs.access(scriptPath);
    
    // Verify input file exists
    await fs.access(options.inputPath);
    
    // Execute Python script
    const args = [
      scriptPath,
      options.inputPath,
      options.outputPath,
      options.accessToken,
      '--base-url',
      baseUrl,
    ];

    if (options.referencePath) {
      args.push('--reference-path', options.referencePath);
    }

    const { stdout, stderr } = await execFileAsync(pythonBin, args, {
      timeout: options.timeoutMs || 30000, // 30 seconds default
      maxBuffer: 10 * 1024 * 1024, // 10MB buffer
    });
    
    // Verify output was created
    await fs.access(options.outputPath);
    
    const processingTimeMs = Date.now() - startTime;
    const accessibilityUrl = `${baseUrl}/accessibility/request?doc=${options.accessToken}`;
    
    console.log('[Link Insertion Layer] Success:', {
      inputPath: options.inputPath,
      outputPath: options.outputPath,
      accessibilityUrl,
      processingTimeMs
    });
    
    return {
      success: true,
      outputPath: options.outputPath,
      metadata: {
        linkAdded: true,
        accessibilityUrl,
        processingTimeMs,
        linkPosition: 'bottom-right'
      }
    };
  } catch (error) {
    const processingTimeMs = Date.now() - startTime;
    const errorMessage = error instanceof Error ? error.message : String(error);
    
    console.error('[Link Insertion Layer] Failed:', {
      error: errorMessage,
      inputPath: options.inputPath,
      outputPath: options.outputPath,
      processingTimeMs
    });
    
    return {
      success: false,
      outputPath: options.inputPath, // Return original on failure
      metadata: {
        linkAdded: false,
        accessibilityUrl: '',
        processingTimeMs,
        linkPosition: 'none'
      },
      error: errorMessage
    };
  }
}

/**
 * Validate link insertion setup
 */
export async function validateLinkInsertionSetup(): Promise<{
  valid: boolean;
  errors: string[];
}> {
  const errors: string[] = [];
  const scriptPath = getLinkInsertionScriptPath();
  const pythonBin = getPythonExecutable();
  
  try {
    // Check if script exists
    await fs.access(scriptPath);
  } catch {
    errors.push('Link insertion script not found');
    return { valid: false, errors };
  }
  
  try {
    // Check Python and required packages
    await execFileAsync(pythonBin, ['-c', 'import PyPDF2, reportlab']);
  } catch {
    errors.push('Required Python packages not installed (PyPDF2, reportlab)');
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}
