import fitz  # PyMuPDF
import sys
import os

def parse_pdf_toc(pdf_path):
    print(f"Reading TOC from PDF: {pdf_path}")
    
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        return

    try:
        doc = fitz.open(pdf_path)
        toc = doc.get_toc() # [[lvl, title, page, ...], ...]
        
        print(f"Found {len(toc)} TOC entries.")
        
        # Print first 50 entries to demonstrate hierarchy
        print("\n--- Document Hierarchy Preview ---")
        for i, entry in enumerate(toc[:50]):
            level, title, page = entry[0], entry[1], entry[2]
            indent = "  " * (level - 1)
            print(f"{indent}[H{level}] {title} (Page {page})")
            
        # Search for our specific target "report_constraint"
        print("\n--- Searching for 'report_constraint' in TOC ---")
        found = False
        for entry in toc:
            level, title, page = entry[0], entry[1], entry[2]
            if "report_constraint" in title:
                indent = "  " * (level - 1)
                print(f"{indent}--> FOUND: [H{level}] '{title}' (Page {page})")
                found = True
        
        if not found:
            print("Warning: 'report_constraint' not found in PDF TOC bookmarks.")
            
    except Exception as e:
        print(f"Error parsing PDF: {e}")

if __name__ == "__main__":
    # Assuming the file is in knowledge_system/input_data/ptug+.pdf
    # I found "input_data\ptug+.pdf" in the search results.
    # Adjust path if needed based on where the user ran the search
    parse_pdf_toc("c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data/ptug+.pdf")
