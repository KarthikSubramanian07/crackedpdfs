use std::path::PathBuf;

use anyhow::Result;
use noise_stuffy_layer::{process_pdf, NoiseLayerConfig};

fn main() -> Result<()> {
    let mut args = std::env::args().skip(1);
    let input = args
        .next()
        .expect("usage: noise_stuffy_layer <input.pdf> [output_dir]");

    let output = args
        .next()
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().expect("cwd"));

    let _config = NoiseLayerConfig::default();

    let result = process_pdf(input, &output)?;

    println!(
        "✅ Generated noisy PDF with {} pages at {}",
        result.page_count,
        result.output_pdf.display()
    );

    Ok(())
}
