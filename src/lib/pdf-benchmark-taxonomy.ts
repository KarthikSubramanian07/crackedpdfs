export const PDF_ATTACK_FAMILIES = [
  "plain_single_block",
  "split_text_objects",
  "header_footer_like",
  "near_margin_normal_font",
  "in_page_invisible_text",
  "in_page_white_text",
  "in_page_tiny_text",
  "in_page_split_text_objects",
  "layout_mimicry",
  "semantic_fragmentation",
  "existing_stream_patch",
  "in_page_low_contrast_text",
  "margin_microtext",
  "steganographic_acrostic",
  "microglyph_steganography",
] as const;

export type PdfAttackFamily = (typeof PDF_ATTACK_FAMILIES)[number];

export const PDF_ATTACK_FAMILY_LABELS: Record<PdfAttackFamily, string> = {
  plain_single_block: "Plain Single Block",
  split_text_objects: "Split Text Objects",
  header_footer_like: "Header/Footer Like",
  near_margin_normal_font: "Near Margin Normal Font",
  in_page_invisible_text: "In-Page Invisible Text",
  in_page_white_text: "In-Page White Text",
  in_page_tiny_text: "In-Page Tiny Text",
  in_page_split_text_objects: "In-Page Split Text Objects",
  layout_mimicry: "Layout Mimicry",
  semantic_fragmentation: "Semantic Fragmentation",
  existing_stream_patch: "Existing Stream Patch",
  in_page_low_contrast_text: "In-Page Low Contrast Text",
  margin_microtext: "Margin Microtext",
  steganographic_acrostic: "Steganographic Acrostic",
  microglyph_steganography: "Microglyph Steganography",
};

export const PDF_ATTACK_STRENGTHS = ["weak", "medium", "strong"] as const;

export type PdfAttackStrength = (typeof PDF_ATTACK_STRENGTHS)[number];

export const PDF_ATTACK_STRENGTH_LABELS: Record<PdfAttackStrength, string> = {
  weak: "Weak",
  medium: "Medium",
  strong: "Strong",
};
