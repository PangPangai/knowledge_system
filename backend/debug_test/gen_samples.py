
import pymupdf4llm
import fitz
import os

def extract_and_save(pdf_path, page_num, output_filename):
    print(f"Extracting Page {page_num} from {pdf_path}...")
    try:
        doc = fitz.open(pdf_path)
        # Use simple single-page extraction for clarity
        md_text = pymupdf4llm.to_markdown(doc, pages=[page_num], write_images=False)
        
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(f"# Extracted from: {os.path.basename(pdf_path)} (Page {page_num})\n\n")
            f.write(md_text)
            
        print(f"✅ Saved to: {output_filename}")
    except Exception as e:
        print(f"❌ Error extracting {pdf_path}: {e}")

if __name__ == "__main__":
    base_dir = "C:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/backend/debug_test"
    
    # 1. The GOOD PDF (PrimeTime User Guide)
    pt_pdf = "C:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data/ptug+.pdf"
    extract_and_save(pt_pdf, 100, f"{base_dir}/clean_PT_page100.md")
    
    # 2. The BAD PDF (Fusion Compiler Application Options)
    fc_pdf = "C:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data/fusion compiler application options and attributes 24.09.sp3.pdf"
    # Page 102 confirms the garbage
    extract_and_save(fc_pdf, 102, f"{base_dir}/garbled_FC_page102.md")
