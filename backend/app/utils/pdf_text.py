import pdfplumber


def extract_pdf_text_and_tables(file_stream):
    """Returns (full_text, list_of_tables) for a PDF file. Each table is a
    list of rows, each row a list of cell strings (None for empty cells)."""
    full_text_parts = []
    all_tables = []
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text_parts.append(text)
            for table in page.extract_tables():
                all_tables.append(table)
    return "\n".join(full_text_parts), all_tables
