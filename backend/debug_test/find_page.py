
import fitz

def find_text_page(pdf_path, search_text):
    print(f"Searching for '{search_text}' in {pdf_path}...")
    doc = fitz.open(pdf_path)
    
    for page in doc:
        # Search raw text first
        text = page.get_text()
        if search_text in text:
            print(f"✅ FOUND '{search_text}' on Page {page.number}")
            return page.number
            
    print("❌ Text not found.")
    return -1

if __name__ == "__main__":
    pdf_path = "C:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data/fusion compiler application options and attributes 24.09.sp3.pdf"
    # Search for the term seen in user's screenshot
    # Note: If text is garbled, we might NOT find it as plain text.
    # So we search for something simple that MIGHT survive corruption or just search for "Application Options" page
    page_num = find_text_page(pdf_path, "3dic.common.die_heights")
    if page_num == -1:
         # Try simpler search if precise match fails due to minor diffs
         page_num = find_text_page(pdf_path, "Application Options")
