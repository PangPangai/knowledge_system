import pymupdf4llm
import pathlib

# Convert specific PDF and check content
pdf_path = r"..\input_data\fcug.pdf"

print("Converting PDF to Markdown...")
md_text = pymupdf4llm.to_markdown(
    pdf_path,
    write_images=False,
    page_chunks=False
)

# Search for RedHawk section
lines = md_text.split('\n')
for i, line in enumerate(lines):
    if 'RedHawk' in line or 'redhawk' in line:
        start = max(0, i-5)
        end = min(len(lines), i+10)
        print(f"\n=== Found at line {i} ===")
        print('\n'.join(lines[start:end]))
        print("=" * 50)
