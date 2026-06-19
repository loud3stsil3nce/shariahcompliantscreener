import io
from unittest.mock import MagicMock
import pytest
from src.data.sec_extractor import SECParser

def test_sec_parser_keywords_filter():
    parser = SECParser()
    
    # Test paragraph selection with whitelist keywords
    sample_text = (
        "This is some generic paragraph that does not contain any keywords.\n"
        "However, our revenue segments show significant growth in beauty products.\n"
        "Another unrelated paragraph here."
    )
    
    filtered = parser.extract_relevant_sections(sample_text, max_chars=300000)
    
    # "revenue" and "product" are in parser.keywords, so the second line (plus surrounding lines) should be selected
    assert "revenue" in filtered
    assert "products" in filtered
    assert "generic paragraph" in filtered  # Preceding line context
    assert "unrelated paragraph" in filtered  # Succeeding line context

def test_pdf_parsing_flow(monkeypatch):
    # Mock pypdf.PdfReader
    mock_reader = MagicMock()
    mock_page_1 = MagicMock()
    mock_page_1.extract_text.return_value = "This is the segment disclosure and revenue details."
    mock_page_2 = MagicMock()
    mock_page_2.extract_text.return_value = "Interest bearing debt is 50 million."
    
    mock_reader.pages = [mock_page_1, mock_page_2]
    
    # When PdfReader is instantiated, return our mock_reader
    monkeypatch.setattr("pypdf.PdfReader", lambda stream: mock_reader)
    
    # Simulate the streamlit extraction logic
    import pypdf
    uploaded_file = io.BytesIO(b"%PDF-1.4 ... mock pdf content ...")
    reader = pypdf.PdfReader(uploaded_file)
    pages_text = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            pages_text.append(t)
    raw_text = "\n".join(pages_text)
    
    assert "segment disclosure" in raw_text
    assert "Interest bearing debt" in raw_text
    
    # Verify SECParser filtering on the extracted text
    parser = SECParser()
    filtered = parser.extract_relevant_sections(raw_text, max_chars=300000)
    assert "segment disclosure" in filtered
    assert "Interest bearing debt" in filtered
