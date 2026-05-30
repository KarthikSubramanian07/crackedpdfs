/**
 * Base Processor Interface
 * 
 * Abstract base class for all processing layers.
 * Each layer must implement the process() method.
 */

import { LayerInput, LayerOutput } from './types';

export abstract class BaseProcessor {
  protected layerName: string;

  constructor(layerName?: string) {
    this.layerName = layerName ?? this.constructor.name;
  }

  /**
   * Process the input data through this layer
   * @param input - Layer input containing context and data
   * @returns LayerOutput with processed data or error
   */
  abstract process(input: LayerInput): Promise<LayerOutput>;

  /**
   * Validate input before processing
   * @param input - Layer input to validate
   * @returns true if valid, throws error if invalid
   */
  protected validateInput(input: LayerInput): boolean {
    if (!input.context) {
      throw new Error(`${this.layerName}: Missing processing context`);
    }
    if (!input.data) {
      throw new Error(`${this.layerName}: Missing input data`);
    }
    return true;
  }

  /**
   * Log processing events (can be extended with proper logging service)
   */
  protected log(level: 'info' | 'warn' | 'error', message: string, meta?: any) {
    const timestamp = new Date().toISOString();
    console[level](`[${timestamp}] [${this.layerName}] ${message}`, meta || '');
  }
}
