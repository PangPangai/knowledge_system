
import fitz
import os
import re

pdf_path = r"C:\Niexingyu\AI\TRAE\backend\笔记\knowledge_system\input_data\fusion compiler application options and attributes 24.09.sp3.pdf"

def diagnose():
    if not os.path.exists(pdf_path):
        print("File not found")
        return
    
    doc = fitz.open(pdf_path)
    # Check page 102 (original report page)
    p = doc[102]
    text = p.get_text()
    print(f"--- PAGE 102 TEXT (Length: {len(text)}) ---")
    print(text[:500])
    
    clean_chars = len(re.findall(r'[a-zA-Z0-9\s\.,;:!?\(\)\-\*/%#_\[\]\{\}]', text))
    total_chars = len(text)
    clean_ratio = clean_chars / max(1, total_chars)
    print(f"\nClean Ratio: {clean_ratio:.2f}")
    
    doc.close()

if __name__ == "__main__":
    diagnose()
