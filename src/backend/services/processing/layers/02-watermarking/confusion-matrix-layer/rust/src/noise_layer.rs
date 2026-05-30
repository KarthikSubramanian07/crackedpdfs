use std::fs::{self, File};
use std::io::copy;
use std::path::{Path, PathBuf};

use anyhow::{anyhow, bail, Context, Result};
use image::codecs::jpeg::JpegEncoder;
use image::{DynamicImage, ImageBuffer, RgbImage};
use once_cell::sync::Lazy;
use pdf_writer::{Content, Filter, Finish, Name, Pdf, Rect, Ref};
use pdfium_render::prelude::{PdfDocument, Pdfium, PdfRenderConfig};
use reqwest::blocking::Client;
use tch::nn::{self, ModuleT};
use tch::{no_grad, Device, Kind, Tensor};

const DEFAULT_TARGET_DPI: f32 = 200.0;
const DEFAULT_NOISE_EPSILON: f64 = 0.003;
const DEFAULT_JPEG_QUALITY: u8 = 95;
const OUTPUT_SUBDIR: &str = "novel_noisy_pdfs";
const OUTPUT_FILE_NAME: &str = "b_perceptual_noisy.pdf";
const VGG16_WEIGHTS_FILE: &str = "vgg16.ot";
const VGG16_WEIGHTS_URL: &str =
    "https://github.com/LaurentMazare/tch-rs/releases/download/mw/vgg16.ot";

static HTTP_CLIENT: Lazy<Client> = Lazy::new(|| Client::builder().build().expect("client"));

/// Public configuration used when invoking [`process_pdf_with_config`].
#[derive(Clone, Debug)]
pub struct NoiseLayerConfig {
    /// Rasterization DPI to match the notebook.
    pub dpi: f32,
    /// Perturbation epsilon scaling factor for the sampled Gaussian noise.
    pub noise_epsilon: f64,
    /// JPEG quality (1..=100) used when embedding page images back into the PDF.
    pub jpeg_quality: u8,
    /// Optional path to a local `vgg16.ot` weights file. When omitted,
    /// the layer downloads the official pretrained weights into the user cache.
    pub weights_override: Option<PathBuf>,
}

impl Default for NoiseLayerConfig {
    fn default() -> Self {
        Self {
            dpi: DEFAULT_TARGET_DPI,
            noise_epsilon: DEFAULT_NOISE_EPSILON,
            jpeg_quality: DEFAULT_JPEG_QUALITY,
            weights_override: None,
        }
    }
}

/// Struct returned by the layer after successful processing.
#[derive(Debug)]
pub struct LayerOutput {
    pub output_pdf: PathBuf,
    pub page_count: usize,
}

/// Convenience wrapper around [`process_pdf_with_config`] using [`NoiseLayerConfig::default`].
pub fn process_pdf<P: AsRef<Path>, Q: AsRef<Path>>(input_pdf: P, output_dir: Q) -> Result<LayerOutput> {
    process_pdf_with_config(input_pdf, output_dir, &NoiseLayerConfig::default())
}

/// Executes the document noise pipeline, returning the path to the generated PDF
/// along with metadata such as the processed page count.
pub fn process_pdf_with_config<P: AsRef<Path>, Q: AsRef<Path>>(
    input_pdf: P,
    output_dir: Q,
    cfg: &NoiseLayerConfig,
) -> Result<LayerOutput> {
    let input_pdf = input_pdf.as_ref();
    let output_dir = output_dir.as_ref();

    fs::create_dir_all(output_dir)
        .with_context(|| format!("failed to create output directory {}", output_dir.display()))?;

    let pdfium = Pdfium::new(
        Pdfium::bind_to_system_library()
            .context("Pdfium library not found. Ensure pdfium.dll/.so is discoverable via PATH or PDFIUM_DYNAMIC_LIB_PATH")?,
    );

    let document = pdfium
        .load_pdf_from_file(input_pdf, None)
        .with_context(|| format!("unable to open PDF {}", input_pdf.display()))?;

    let mut pages = render_document_pages(&document, cfg.dpi)
        .context("failed to rasterize PDF pages")?;

    let device = Device::cuda_if_available();
    let mut vs = nn::VarStore::new(device);
    let features = build_vgg16_features(&vs.root());

    let weights_path = match &cfg.weights_override {
        Some(path) => path.clone(),
        None => ensure_vgg_weights().context("unable to obtain VGG16 weights")?,
    };

    if !weights_path.exists() {
        bail!(
            "VGG16 weights missing at {}. Provide a valid `vgg16.ot` file.",
            weights_path.display()
        );
    }

    let missing = vs
        .load_partial(&weights_path)
        .with_context(|| format!("failed to load weights from {}", weights_path.display()))?;

    if !missing.is_empty() {
        bail!(
            "Loaded VGG16 weights with missing tensors: {:?}",
            missing
        );
    }

    for page in pages.iter_mut() {
        let noisy_image = apply_perceptual_noise(&features, device, &page.image, cfg.noise_epsilon)
        .context("unable to apply perceptual noise")?;
        page.image = noisy_image;
    }

    let output_root = output_dir.join(OUTPUT_SUBDIR);
    fs::create_dir_all(&output_root)
        .with_context(|| format!("failed to create {}", output_root.display()))?;

    let output_path = output_root.join(OUTPUT_FILE_NAME);

    write_pdf_with_images(&pages, &output_path, cfg.jpeg_quality)
        .with_context(|| format!("failed to write {}", output_path.display()))?;

    Ok(LayerOutput {
        output_pdf: output_path,
        page_count: pages.len(),
    })
}

struct PageImage {
    image: RgbImage,
    dpi: f32,
}

fn render_document_pages(document: &PdfDocument<'_>, dpi: f32) -> Result<Vec<PageImage>> {
    let mut rendered = Vec::new();

    for page in document.pages().iter() {
        let width_px = points_to_pixels(page.width().value, dpi);
        let height_px = points_to_pixels(page.height().value, dpi);

        let config = PdfRenderConfig::new()
            .set_target_width(width_px)
            .set_target_height(height_px);

        let bitmap = page
            .render_with_config(&config)
            .context("pdfium failed to render page")?;

        let rgb = bitmap.as_image().to_rgb8();

        rendered.push(PageImage { image: rgb, dpi });
    }

    if rendered.is_empty() {
        bail!("PDF contains no pages");
    }

    Ok(rendered)
}

fn apply_perceptual_noise<M>(
    model: &M,
    device: Device,
    image: &RgbImage,
    eps: f64,
) -> Result<RgbImage>
where
    M: ModuleT,
{
    let (width, height) = image.dimensions();
    let input = image_to_tensor(image, device);

    no_grad(|| {
        let _ = model.forward_t(&input, /*train=*/ false);
    });

    let std_scalar = input
        .std(false)
        .double_value(&[])
        .max(f64::EPSILON);

    let noise = Tensor::randn(&input.size(), (Kind::Float, device)) * (eps * std_scalar);
    let perturbed = (input + noise).clamp(0.0, 1.0);

    tensor_to_image(perturbed, width, height)
}

fn write_pdf_with_images(pages: &[PageImage], output_path: &Path, jpeg_quality: u8) -> Result<()> {
    let mut pdf = Pdf::new();

    let catalog_ref = Ref::new(1);
    let page_tree_ref = Ref::new(2);
    let mut next_ref = 3;

    let mut entries = Vec::with_capacity(pages.len());

    for (index, page) in pages.iter().enumerate() {
        let page_ref = Ref::new(next_ref);
        next_ref += 1;
        let image_ref = Ref::new(next_ref);
        next_ref += 1;
        let content_ref = Ref::new(next_ref);
        next_ref += 1;

        let mut jpeg_data = Vec::new();
        {
            let mut encoder =
                JpegEncoder::new_with_quality(&mut jpeg_data, jpeg_quality.clamp(1, 100));
            encoder
                .encode_image(&DynamicImage::ImageRgb8(page.image.clone()))
                .context("JPEG encoding failed")?;
        }

        let (width_px, height_px) = page.image.dimensions();

        entries.push(PageEntry {
            page_ref,
            image_ref,
            content_ref,
            image_name: format!("Im{}", index + 1).into_bytes(),
            width_pt: px_to_points(width_px, page.dpi),
            height_pt: px_to_points(height_px, page.dpi),
            width_px,
            height_px,
            image_data: jpeg_data,
        });
    }

    pdf.catalog(catalog_ref).pages(page_tree_ref);

    let mut pages_dict = pdf.pages(page_tree_ref);
    pages_dict.count(entries.len() as i32);
    pages_dict.kids(entries.iter().map(|entry| entry.page_ref));
    pages_dict.finish();

    for entry in &entries {
        let mut page = pdf.page(entry.page_ref);
        page.media_box(Rect::new(0.0, 0.0, entry.width_pt, entry.height_pt));
        page.parent(page_tree_ref);
        page.contents(entry.content_ref);
        page.resources()
            .x_objects()
            .pair(Name(&entry.image_name), entry.image_ref);
        page.finish();

        let mut image = pdf.image_xobject(entry.image_ref, &entry.image_data);
        image.filter(Filter::DctDecode);
        image.width(entry.width_px as i32);
        image.height(entry.height_px as i32);
        image.color_space().device_rgb();
        image.bits_per_component(8);
        image.finish();

        let mut content = Content::new();
        content.save_state();
        content.transform([entry.width_pt, 0.0, 0.0, entry.height_pt, 0.0, 0.0]);
        content.x_object(Name(&entry.image_name));
        content.restore_state();
        pdf.stream(entry.content_ref, &content.finish());
    }

    fs::write(output_path, pdf.finish()).with_context(|| {
        format!(
            "unable to persist new PDF to {}",
            output_path.display()
        )
    })?;

    Ok(())
}

fn image_to_tensor(image: &RgbImage, device: Device) -> Tensor {
    let (width, height) = image.dimensions();
    let mut data = Vec::with_capacity((width * height * 3) as usize);

    for pixel in image.pixels() {
        data.push(pixel[0] as f32 / 255.0);
        data.push(pixel[1] as f32 / 255.0);
        data.push(pixel[2] as f32 / 255.0);
    }

    Tensor::from_slice(&data)
        .reshape(&[height as i64, width as i64, 3])
        .permute(&[2, 0, 1])
        .unsqueeze(0)
        .to_device(device)
}

fn tensor_to_image(tensor: Tensor, width: u32, height: u32) -> Result<RgbImage> {
    let cpu_tensor = tensor.to_device(Device::Cpu);
    let tensor = cpu_tensor.squeeze_dim(0).permute(&[1, 2, 0]);
    let tensor = (tensor * 255.0)
        .clamp(0.0, 255.0)
        .to_kind(Kind::Uint8)
        .contiguous();

    let mut bytes = vec![0u8; (width * height * 3) as usize];
    let num_bytes = bytes.len();
    tensor.copy_data(&mut bytes, num_bytes);

    ImageBuffer::from_vec(width, height, bytes).ok_or_else(|| {
        anyhow!(
            "tensor -> image conversion failed for {}x{} buffer",
            width,
            height
        )
    })
}

struct PageEntry {
    page_ref: Ref,
    image_ref: Ref,
    content_ref: Ref,
    image_name: Vec<u8>,
    width_pt: f32,
    height_pt: f32,
    width_px: u32,
    height_px: u32,
    image_data: Vec<u8>,
}

fn points_to_pixels(points: f32, dpi: f32) -> i32 {
    (((points / 72.0) * dpi).round() as i32).max(1)
}

fn px_to_points(px: u32, dpi: f32) -> f32 {
    (px as f32 / dpi) * 72.0
}

fn ensure_vgg_weights() -> Result<PathBuf> {
    let base_dir = dirs::cache_dir()
        .unwrap_or_else(|| std::env::temp_dir())
        .join("noise_stuffy_layer");
    fs::create_dir_all(&base_dir)
        .with_context(|| format!("failed to create cache directory {}", base_dir.display()))?;

    let weights_path = base_dir.join(VGG16_WEIGHTS_FILE);

    if !weights_path.exists() {
        let mut response = HTTP_CLIENT
            .get(VGG16_WEIGHTS_URL)
            .send()
            .context("failed to download VGG16 weights")?;

        if !response.status().is_success() {
            bail!(
                "downloading VGG16 weights failed with HTTP status {}",
                response.status()
            );
        }

        let mut file =
            File::create(&weights_path).context("unable to create weights file")?;

        copy(&mut response, &mut file).context("unable to save VGG16 weights")?;
    }

    Ok(weights_path)
}

fn build_vgg16_features(path: &nn::Path) -> nn::SequentialT {
    let mut seq = nn::seq_t();
    let f = path / "features";

    let mut c_in = 3;
    for channels in vgg16_configuration() {
        for c_out in channels {
            let idx = seq.len();
            let conv_path = &f / idx.to_string();
            seq = seq.add(conv2d(&conv_path, c_in, c_out));
            seq = seq.add_fn(|xs| xs.relu());
            c_in = c_out;
        }
        seq = seq.add_fn(|xs| xs.max_pool2d_default(2));
    }

    seq
}

fn conv2d(path: &nn::Path, c_in: i64, c_out: i64) -> nn::Conv2D {
    let conv_config = nn::ConvConfig {
        stride: 1,
        padding: 1,
        ..Default::default()
    };
    nn::conv2d(path, c_in, c_out, 3, conv_config)
}

fn vgg16_configuration() -> Vec<Vec<i64>> {
    vec![
        vec![64, 64],
        vec![128, 128],
        vec![256, 256, 256],
        vec![512, 512, 512],
        vec![512, 512, 512],
    ]
}