
import asyncio
import os
import sys
import pymupdf4llm

async def parse_pdf(file_path):
    print(f"🚀 Testing PDF Parser (Layout-Aware, No OCR) on: {file_path}")
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    try:
        # 1. Convert to Markdown (ignoring images)
        print("   1️⃣ Converting PDF to Markdown...")
        # write_images=False ensures we just get text/tables, no image files extracted
        md_text = pymupdf4llm.to_markdown(file_path, write_images=False)
        print(f"      ✅ Conversion successful. Length: {len(md_text)} chars")
        
        # 2. Preview
        print("\n" + "="*40)
        print("PREVIEW (First 2000 chars):")
        print("="*40)
        print(md_text[:2000])
        print("="*40 + "\n")

        # 3. Check for Tables (Quick heuristic)
        table_count = md_text.count("| --- |")
        print(f"   📊 Found approximately {table_count} tables (based on Markdown separators).")

        # Output result to file for inspection
        output_file = "test_output_no_ocr.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(md_text)
        print(f"\n✅ Done! Result saved to {output_file}")

    except Exception as e:
        print(f"❌ Parsing failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_pdf_parser.py <path_to_pdf>")
        sys.exit(1)
        
    pdf_path = sys.argv[1]
    asyncio.run(parse_pdf(pdf_path))
