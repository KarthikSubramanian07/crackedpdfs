import pikepdf
from pikepdf import Name, Operator

def create_experimental_pdfs():
    # 1. Off-Screen Strategy
    pdf_off = pikepdf.new()
    pdf_off.add_blank_page(page_size=(595, 842))
    page_off = pdf_off.pages[0]
    
    font_name = Name("/F1")
    font = pikepdf.Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)
    
    font_res = pikepdf.Dictionary()
    font_res[font_name] = font
    page_off.Resources = pikepdf.Dictionary(Font=font_res)
    
    # Text at 10,000 10,000
    stream_off = b"""
    BT
    /F1 12 Tf
    10000 10000 Td
    (This is OFF-SCREEN text) Tj
    ET
    """
    page_off.Contents = pikepdf.Stream(pdf_off, stream_off)
    pdf_off.save("exp_offscreen.pdf")
    print("Created exp_offscreen.pdf")

    # 2. Clipped Strategy
    pdf_clip = pikepdf.new()
    pdf_clip.add_blank_page(page_size=(595, 842))
    page_clip = pdf_clip.pages[0]
    page_clip.Resources = pikepdf.Dictionary(Font=font_res)
    
    # Text at 100 100, but clipped to 0 0 0 0
    stream_clip = b"""
    q
    0 0 0 0 re W n
    BT
    /F1 12 Tf
    100 100 Td
    (This is CLIPPED text) Tj
    ET
    Q
    """
    page_clip.Contents = pikepdf.Stream(pdf_clip, stream_clip)
    pdf_clip.save("exp_clipped.pdf")
    print("Created exp_clipped.pdf")

if __name__ == "__main__":
    create_experimental_pdfs()
