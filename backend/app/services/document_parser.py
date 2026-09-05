import io
from pypdf import PdfReader
from docx import Document

def parse_pdf(file_bytes: bytes) -> str:
    """Extract plain text from a PDF file."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = []
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text.append(content)
        return "\n".join(text)
    except Exception as e:
        print(f"[Parser] PDF extraction error: {e}")
        raise ValueError(f"Failed to parse PDF document: {str(e)}")

def parse_docx(file_bytes: bytes) -> str:
    """Extract plain text from a DOCX file."""
    try:
        doc = Document(io.BytesIO(file_bytes))
        text = []
        for paragraph in doc.paragraphs:
            if paragraph.text:
                text.append(paragraph.text)
        return "\n".join(text)
    except Exception as e:
        print(f"[Parser] DOCX extraction error: {e}")
        raise ValueError(f"Failed to parse DOCX document: {str(e)}")

def parse_document(file_bytes: bytes, filename: str) -> str:
    """Detects extension and parses the document into plain text."""
    fn_lower = filename.lower()
    if fn_lower.endswith(".pdf"):
        return parse_pdf(file_bytes)
    elif fn_lower.endswith(".docx"):
        return parse_docx(file_bytes)
    elif fn_lower.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")
    else:
        try:
            return file_bytes.decode("utf-8")
        except Exception:
            raise ValueError(f"Unsupported file format or encoding for file: {filename}")
