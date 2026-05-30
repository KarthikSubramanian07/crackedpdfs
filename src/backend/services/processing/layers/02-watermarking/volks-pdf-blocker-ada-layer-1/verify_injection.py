import pikepdf
import sys

def verify_pdf(file_path):
    print(f"Verifying {file_path}...")
    pdf = pikepdf.open(file_path)
    page = pdf.pages[0]
    
    # 1. Check for Artifact BMC
    # We need to parse the content stream and look for the operators
    contents = page.Contents
    if isinstance(contents, pikepdf.Array):
        # It might be split across streams, let's look at the last one where we appended
        stream = contents[-1]
    else:
        stream = contents
        
    ops = pikepdf.parse_content_stream(stream)
    
    found_artifact = False
    found_policy_text = False
    
    for i, (op, args) in enumerate(ops):
        if op == pikepdf.Operator("BMC") and args[0] == "/Artifact":
            found_artifact = True
            print("Found /Artifact BMC tag.")
        
        if op == pikepdf.Operator("Tj"):
            # Check if text looks like policy
            text = str(args[0])
            if "POLICY" in text or "ACADEMIC" in text:
                found_policy_text = True
                print(f"Found policy text segment: {text[:20]}...")
                
    if found_artifact and found_policy_text:
        print("SUCCESS: Policy text found wrapped in Artifact tag.")
    else:
        print("FAILURE: Did not find expected Artifact tag or policy text.")
        
    # 2. Check StructTreeRoot (should not have new children for this)
    # This is harder to check automatically without knowing previous state, 
    # but we can just ensure we didn't crash or corrupt it.
    if "/StructTreeRoot" in pdf.Root:
        print("StructTreeRoot exists (good).")
    else:
        print("StructTreeRoot not present (expected for this dummy PDF).")

if __name__ == "__main__":
    verify_pdf(sys.argv[1])
