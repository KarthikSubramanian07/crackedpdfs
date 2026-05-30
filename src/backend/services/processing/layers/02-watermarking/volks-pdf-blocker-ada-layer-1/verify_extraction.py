import pikepdf

def extract_text_naive(pdf_path):
    print(f"--- Extracting from {pdf_path} ---")
    pdf = pikepdf.open(pdf_path)
    page = pdf.pages[0]
    
    # Naive extraction: just look for Tj in content stream
    # This simulates what a "dumb" LLM scraper might do
    contents = page.Contents.read_bytes()
    print(f"Raw Content Stream snippet: {contents[:200]}...")
    
    if b"OFF-SCREEN" in contents:
        print("SUCCESS: Found 'OFF-SCREEN' in raw stream.")
    elif b"CLIPPED" in contents:
        print("SUCCESS: Found 'CLIPPED' in raw stream.")
    else:
        print("FAILURE: Text not found in stream.")

if __name__ == "__main__":
    extract_text_naive("exp_offscreen.pdf")
    extract_text_naive("exp_clipped.pdf")
