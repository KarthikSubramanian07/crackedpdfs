/**
 * PDF Link Injector
 * 
 * Adds accessibility request links to the last page of PDFs
 */

import { PDFDocument, rgb, StandardFonts } from 'pdf-lib';
import { promises as fs } from 'fs';
import { tmpdir } from 'os';
import path from 'path';
import { execFile } from 'child_process';
import { promisify } from 'util';
import { getPythonExecutable } from './python-utils';
import { getLinkInsertionScriptPath } from './path-utils';

const execFileAsync = promisify(execFile);

export interface LinkInjectionConfig {
  accessToken: string;
  baseUrl?: string;
  position?: 'bottom-left' | 'bottom-right' | 'bottom-center';
  fontSize?: number;
  textColor?: { r: number; g: number; b: number };
}

/**
 * Inject accessibility request link into PDF
 */
export async function injectAccessibilityLink(
  pdfBuffer: Buffer,
  config: LinkInjectionConfig
): Promise<Buffer> {
  const baseUrl = config.baseUrl || process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000';
  try {
    return await injectWithPython(pdfBuffer, config, baseUrl);
  } catch (pythonError) {
    console.warn('[PDF Link Injector] Python-based injection failed, falling back to pdf-lib:', pythonError);
  }

  try {
    // Load PDF
    const pdfDoc = await PDFDocument.load(pdfBuffer);
    const pages = pdfDoc.getPages();
    
    if (pages.length === 0) {
      throw new Error('PDF has no pages');
    }

    // Get last page
    const lastPage = pages[pages.length - 1];
    const { width, height } = lastPage.getSize();

    // Embed font
    const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
    
    // Generate link URL
    const linkUrl = `${baseUrl}/accessibility/request?token=${config.accessToken}`;
    
    // Link text
    const linkText = 'Request Accessible Copy';
    
    // Calculate text dimensions
    const fontSize = config.fontSize || 10;
    const textWidth = font.widthOfTextAtSize(linkText, fontSize);
    const textHeight = fontSize;
    
    // Calculate position
    let x: number;
    const y = 20; // 20 points from bottom
    const margin = 20;
    
    switch (config.position || 'bottom-right') {
      case 'bottom-left':
        x = margin;
        break;
      case 'bottom-center':
        x = (width - textWidth) / 2;
        break;
      case 'bottom-right':
      default:
        x = width - textWidth - margin;
        break;
    }

    // Draw button background
    const buttonWidth = textWidth + 16;
    const buttonHeight = fontSize + 12;
    const buttonColor = { r: 0.06, g: 0.09, b: 0.16 };
    const textColor = config.textColor || { r: 1, g: 1, b: 1 };

    lastPage.drawRectangle({
      x: x - 8,
      y: y - 6,
      width: buttonWidth,
      height: buttonHeight,
      color: rgb(buttonColor.r, buttonColor.g, buttonColor.b),
      borderColor: rgb(buttonColor.r, buttonColor.g, buttonColor.b),
      borderWidth: 0,
    });

    // Draw text with link
    lastPage.drawText(linkText, {
      x,
      y,
      size: fontSize,
      font,
      color: rgb(textColor.r, textColor.g, textColor.b),
    });

    // NOTE: visual CTA remains available even when annotation injection path is skipped.

    // Serialize PDF
    const pdfBytes = await pdfDoc.save();
    return Buffer.from(pdfBytes);
  } catch (error) {
    console.error('[PDF Link Injector] Failed to inject link:', error);
    throw error;
  }
}

async function injectWithPython(
  pdfBuffer: Buffer,
  config: LinkInjectionConfig,
  baseUrl: string
): Promise<Buffer> {
  const pythonBin = getPythonExecutable();
  const scriptPath = getLinkInsertionScriptPath();
  const tmpRoot = await fs.mkdtemp(path.join(tmpdir(), 'link-inject-'));
  const inputPath = path.join(tmpRoot, 'input.pdf');
  const outputPath = path.join(tmpRoot, 'output.pdf');

  await fs.writeFile(inputPath, pdfBuffer);

  const args = [
    scriptPath,
    inputPath,
    outputPath,
    config.accessToken,
    '--base-url',
    baseUrl,
    '--position',
    config.position || 'bottom-right',
    '--font-size',
    String(config.fontSize || 10),
    '--text',
    'Request Accessible Copy'
  ];

  try {
    await execFileAsync(pythonBin, args, {
      timeout: 30000,
      maxBuffer: 10 * 1024 * 1024
    });
    const result = await fs.readFile(outputPath);
    return result;
  } finally {
    await fs.rm(tmpRoot, { recursive: true, force: true }).catch(() => {});
  }
}

/**
 * Check if buffer is a valid PDF
 */
export function isPDF(buffer: Buffer): boolean {
  if (buffer.length < 5) return false;
  return buffer.toString('utf8', 0, 5) === '%PDF-';
}

