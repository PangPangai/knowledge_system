
import os
import fitz
import re
import json
from pathlib import Path

def analyze_pdf_health(pdf_path):
    issues = []
    total_pages = 0
    pages_to_check = [0, 50, 100, 200, 500] 
    
    try:
        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}

    sample_text = ""
    for p_num in pages_to_check:
        if p_num >= total_pages: continue
        try:
            page = doc.load_page(p_num)
            text = page.get_text()
            sample_text += text
        except Exception as e:
            pass

    if not sample_text.strip():
        return {"status": "EMPTY", "reason": "No text extracted (Likely scanned image)", "pages": total_pages}

    # Detect known garbage pattern from Identity-H missing map
    # "Chu<" etc. usually shows up as specific nonsense strings or high ratio of non-printable
    if "Chu<" in sample_text or "<untdilbtm" in sample_text:
        return {"status": "GARBLED", "reason": "Confirmed Identity-H mapping failure (Garbage detected)", "pages": total_pages}

    # ASCII density check
    clean_chars = len(re.findall(r'[a-zA-Z0-9\s\.,;:!?\(\)\-\*/%#_\[\]\{\}]', sample_text))
    total_chars = len(sample_text)
    clean_ratio = clean_chars / max(1, total_chars)
    
    if clean_ratio < 0.7:
        return {"status": "GARBLED", "reason": f"Heuristic failure: Low ASCII density ({clean_ratio:.2f})", "pages": total_pages}

    return {"status": "CLEAN", "reason": f"High ASCII density ({clean_ratio:.2f})", "pages": total_pages}

def main():
    base_dir = Path("C:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data")
    pdf_files = list(base_dir.glob("*.pdf"))
    
    report = {}
    for pdf_file in pdf_files:
        print(f"Scanning {pdf_file.name}...")
        report[pdf_file.name] = analyze_pdf_health(pdf_file)
        
    with open("c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/backend/scan_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, ensure_ascii=False)
    
    print("\n✅ Report saved to scan_report.json")

if __name__ == "__main__":
    main()
