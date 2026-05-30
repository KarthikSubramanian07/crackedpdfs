//! Noise layer library exposing a single entry point to replicate the
//! `Noise_Stuffy.ipynb` document perturbation pipeline in Rust.

pub mod noise_layer;

pub use noise_layer::{
    process_pdf, process_pdf_with_config, LayerOutput, NoiseLayerConfig,
};
