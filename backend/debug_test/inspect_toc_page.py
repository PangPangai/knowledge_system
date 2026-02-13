import fitz
import os

def inspect_toc(pdf_path, target_page):
    try:
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()
        
        print(f"📖 Inspecting TOC for {os.path.basename(pdf_path)}")
        print(f"Target Page: {target_page}\n")
        
        found = False
        # Find entries around the target page (e.g., +/- 5 pages)
        for entry in toc:
            level, title, page = entry
            # PDF pages are 1-based in TOC usually, fitz uses 1-based for display
            if target_page - 5 <= page <= target_page + 5:
                print(f"L{level}: {title} (Page {page})")
                found = True
                
        if not found:
            print("No TOC entries found in the vicinity of this page.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    pdf_path = r"c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data/fusion compiler tool commands.pdf"
    # User said page 114.
    inspect_toc(pdf_path, 114)
