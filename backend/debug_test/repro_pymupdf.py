
import pymupdf4llm
import fitz

def test_pymupdf_encoding(pdf_path, page_num):
    print(f"Testing Page {page_num} of {pdf_path}...")
    doc = fitz.open(pdf_path)
    
    # Method 1: Single Page extraction (Old slow way)
    print("\n--- Method 1: Single Page extract ---")
    md1 = pymupdf4llm.to_markdown(doc, pages=[page_num], write_images=False)
    print(md1[:500])
    
    # Method 2: Batch extract (New fast way)
    print("\n--- Method 2: Batch (page_chunks=True) ---")
    chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, write_images=False)
    md2 = chunks[page_num]['text']
    print(md2[:500])
    
    if md1 == md2:
        print("\n✅ Identical Output")
    else:
        print("\n❌ DIFFERENT Output!")
        # Check for specific artifacts
        if "**%0A" in md2:
            print("   -> Method 2 contains URL encoded newlines!")
        if "Chu<" in md2:
            print("   -> Method 2 contains Font Mapping Garbage!")

if __name__ == "__main__":
    # Use the known PDF path
    pdf_path = "C:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data/ptug+.pdf"
    # Pick a page that likely has text (e.g. 100)
    test_pymupdf_encoding(pdf_path, 100)
