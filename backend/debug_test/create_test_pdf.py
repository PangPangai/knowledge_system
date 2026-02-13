import fitz
import os

backend_dir = os.path.dirname(os.path.abspath(__file__))
input_dir = os.path.join(os.path.dirname(backend_dir), "input_data")
pdf_path = os.path.join(input_dir, "ptug+.pdf")
output_path = os.path.join(input_dir, "test_doc.pdf")

if not os.path.exists(pdf_path):
    print(f"Input PDF not found: {pdf_path}")
    exit(1)

try:
    doc = fitz.open(pdf_path)
    # Extract pages 50-60
    selected_pages = [i for i in range(50, 60)]
    # Ensure pages exist
    if len(doc) <= 50:
        selected_pages = [i for i in range(0, min(10, len(doc)))]
        
    test_doc = fitz.open()
    test_doc.insert_pdf(doc, from_page=selected_pages[0], to_page=selected_pages[-1])
    test_doc.save(output_path)
    print(f"Created {output_path} with pages {selected_pages}.")
except Exception as e:
    print(f"Error creating test PDF: {e}")
