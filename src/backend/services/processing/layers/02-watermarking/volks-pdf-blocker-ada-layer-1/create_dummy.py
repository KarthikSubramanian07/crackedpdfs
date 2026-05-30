import pikepdf
from pikepdf import Name, Operator

def create_dummy_pdf(output_path: str):
    pdf = pikepdf.new()
    
    # Create a simple page
    # We need to add some resources and content to make it a valid "page"
    # standard media box for A4 (width, height)
    page_size = (595.28, 841.89)
    
    pdf.add_blank_page(page_size=page_size)
    
    # Add some visible text so it's not empty
    page = pdf.pages[0]
    
    # Add font resource
    font_name = Name("/F1")
    font = pikepdf.Dictionary(
        Type=Name.Font,
        Subtype=Name.Type1,
        BaseFont=Name.Helvetica
    )
    
    font_res = pikepdf.Dictionary()
    font_res[font_name] = font
    
    page.Resources = pikepdf.Dictionary(Font=font_res)
    
    # Draw "Hello World"
    # Use raw bytes to avoid pikepdf.Operator issues
    stream_data = b"""
    BT
    /F1 24 Tf
    100 700 Td
    (Hello World - This is a dummy PDF) Tj
    ET
    """
    
    content_stream = pikepdf.Stream(pdf, stream_data)
    page.Contents = content_stream
    
    pdf.save(output_path)
    print(f"Created dummy PDF at {output_path}")

if __name__ == "__main__":
    create_dummy_pdf("dummy.pdf")
