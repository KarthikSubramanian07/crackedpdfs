/**
 * Python PDF Embedding Layer Wrapper
 * Executes the Python script that adds academic integrity warnings
 */

import { execFile } from 'child_process';
import { promisify } from 'util';
import * as fs from 'fs/promises';
import { getVolksLayerScriptPath } from '../path-utils';
import { getPythonExecutable } from '../python-utils';

const execFileAsync = promisify(execFile);

export interface PythonEmbeddingOptions {
  inputPath: string;
  outputPath: string;
  timeoutMs?: number;
}

export interface PythonEmbeddingResult {
  success: boolean;
  outputPath: string;
  metadata: {
    warningsAdded: boolean;
    processingTimeMs: number;
    pythonLayer: string;
  };
  error?: string;
}

/**
 * Process PDF through Python embedding layer
 */
export async function processPythonEmbedding(
  options: PythonEmbeddingOptions
): Promise<PythonEmbeddingResult> {
  const startTime = Date.now();
  const scriptPath = getVolksLayerScriptPath();
  const pythonBin = getPythonExecutable();
  
  try {
    // Verify script exists
    await fs.access(scriptPath);
    
    // Verify input file exists
    await fs.access(options.inputPath);
    
    // Execute Python script
    const { stdout, stderr } = await execFileAsync(
      pythonBin,
      [scriptPath, options.inputPath, options.outputPath],
      {
        timeout: options.timeoutMs || 120000, // 2 minutes default
        maxBuffer: 50 * 1024 * 1024 // 50MB buffer
      }
    );
    
    // Verify output was created
    await fs.access(options.outputPath);
    
    const processingTimeMs = Date.now() - startTime;
    
    console.log('[Volks Screenshot Shatter Layer 1] Success:', {
      inputPath: options.inputPath,
      outputPath: options.outputPath,
      processingTimeMs,
      stdout: stdout.substring(0, 200)
    });
    
    return {
      success: true,
      outputPath: options.outputPath,
      metadata: {
        warningsAdded: true,
        processingTimeMs,
        pythonLayer: 'volks-screenshot-shatter-layer-1'
      }
    };
  } catch (error) {
    const processingTimeMs = Date.now() - startTime;
    const errorMessage = error instanceof Error ? error.message : String(error);
    
    console.error('[Volks Screenshot Shatter Layer 1] Failed:', {
      error: errorMessage,
      inputPath: options.inputPath,
      outputPath: options.outputPath,
      processingTimeMs
    });
    
    return {
      success: false,
      outputPath: options.inputPath, // Return original on failure
      metadata: {
        warningsAdded: false,
        processingTimeMs,
        pythonLayer: 'volks-screenshot-shatter-layer-1'
      },
      error: errorMessage
    };
  }
}

/**
 * Validate Python environment
 */
export async function validatePythonSetup(): Promise<{
  valid: boolean;
  errors: string[];
}> {
  const errors: string[] = [];
  const scriptPath = getVolksLayerScriptPath();
  const pythonBin = getPythonExecutable();
  
  try {
    // Check if script exists
    await fs.access(scriptPath);
  } catch {
    errors.push('Volks Screenshot Shatter Layer 1 script not found');
    return { valid: false, errors };
  }
  
  try {
    // Check Python version
    const { stdout } = await execFileAsync(pythonBin, ['--version']);
    console.log('[Volks Screenshot Shatter Layer 1] Python version:', stdout.trim());
  } catch {
    errors.push('Python 3 not available');
  }
  
  try {
    // Check required packages
    await execFileAsync(pythonBin, [
      '-c',
      'import pdfplumber, PyPDF2, reportlab, docx'
    ]);
  } catch {
    errors.push('Required Python packages not installed (pdfplumber, PyPDF2, reportlab, python-docx)');
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}
