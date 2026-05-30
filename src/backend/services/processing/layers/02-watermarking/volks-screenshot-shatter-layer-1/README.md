# Volk's Screenshot Shatter Layer 1

Python-based PDF embedding layer that adds academic integrity protections to documents.

## Features

- **Academic Integrity Warnings**: Embeds contextual warnings between question blocks
- **Confidential Markers**: Adds "(CONFIDENTIAL ACADEMIC MATERIAL)" suffixes to questions
- **Watermarking**: Subtle "CONFIDENTIAL" watermark across all pages
- **Accessibility Link**: Inserts clickable link on last page for accessibility requests

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Command Line

```bash
python3 Volks_Anti_Screenshot_Layer_1.py input.pdf output.pdf --accessibility-link "https://example.com/access/request"
```

### Programmatic (TypeScript)

```typescript
import { processPythonEmbedding } from './index';

const result = await processPythonEmbedding({
  inputPath: '/path/to/input.pdf',
  outputPath: '/path/to/output.pdf',
  timeoutMs: 120000
});
```

## Processing Pipeline Position

This layer runs **after** the Rust CNN confusion matrix layer:

1. **Rust Layer**: Perceptual noise watermarking using VGG16
2. **Python Layer** (this): Academic integrity embedding
3. **Link Insertion Layer**: Accessibility request links

## How It Works

1. **PDF Analysis**: Extracts text layout, fonts, and structure
2. **Question Detection**: Identifies question-like content using NLP patterns
3. **Warning Placement**: Inserts warnings in whitespace near questions
4. **Suffix Addition**: Appends confidential markers inline
5. **Watermark Overlay**: Adds diagonal "CONFIDENTIAL" text
6. **Link Insertion**: Places accessibility request link in bottom corner of last page

## Configuration

The layer automatically:
- Detects appropriate font sizes for warnings (5pt ratio to source)
- Identifies whitespace for non-intrusive placement
- Preserves original document layout
- Handles multi-column layouts
- Skips metadata sections (headers, footers, page numbers)

## Technical Details

**Dependencies:**
- `pdfplumber`: PDF text extraction and layout analysis
- `PyPDF2`: PDF manipulation and merging
- `reportlab`: Canvas drawing for overlays

**Performance:**
- ~3-5 seconds per page for analysis
- ~1-2 seconds per page for overlay generation
- Total: ~5-7 seconds per page

**Output Quality:**
- Maintains original PDF resolution
- Preserves fonts and formatting
- Non-destructive overlay approach
