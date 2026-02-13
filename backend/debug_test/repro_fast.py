
import pymupdf4llm
import fitz

def create_subset_and_test(pdf_path, start_page, end_page):
    print(f"Creating subset of {pdf_path} (Pages {start_page}-{end_page})...")
    
    # 1. Create a temporary subset PDF to avoid scanning the whole 6000 pages
    doc = fitz.open(pdf_path)
    subset_doc = fitz.open() # New empty PDF
    subset_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
    
    # 2. Test both methods on this subset
    print("\n--- Method 1: String Mode (Raw Text equivalent) ---")
    # Note: to_markdown(doc) is equivalent to loop over pages
    text1 = pymupdf4llm.to_markdown(subset_doc, write_images=False)
    print(text1[:500])
    
    print("\n\n--- Method 2: Batch Mode (page_chunks=True) ---")
    chunks = pymupdf4llm.to_markdown(subset_doc, page_chunks=True, write_images=False)
    text2 = chunks[0]['text'] # First page of subset
    print(text2[:500])
    
    print("\n--- Analysis ---")
    if "**%0A" in text2:
        print("❌ DETECTED: URL Encoded Newlines (%0A) in Method 2!")
    else:
        print("✅ No URL Encoded Newlines in Method 2")
        
    if "Chu<" in text2 or "tm<" in text2:
         print("❌ DETECTED: Font Garbage (Chu<..) in Method 2!")
    else:
         print("✅ No Font Garbage detected in Method 2 (yet)")

if __name__ == "__main__":
    # Use the SUSPECT PDF path: Fusion Compiler PDF
    pdf_path = "C:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data/fusion compiler application options and attributes 24.09.sp3.pdf"
    # Target area (Pages 100-105) where '3dic.common.die_heights' was found
    try:
        create_subset_and_test(pdf_path, 100, 105)
    except Exception as e:
        print(f"Failed: {e}")
