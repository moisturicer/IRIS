import re
import logging
import opendataloader_pdf
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class ExtractionFailedError(Exception):
    pass

class ExtractionStrategy(ABC):
    @abstractmethod
    def extract(self, pdf_bytes: bytes) -> str:
        pass

class PyMuPDFStrategy(ExtractionStrategy):
    """Fallback strategy using PyMuPDF for unstructured text extraction."""
    def extract(self, pdf_bytes: bytes) -> str:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            raw_text = ""
            for page in doc:
                raw_text += page.get_text()
            doc.close()
            return self._clean_text(raw_text)
        except Exception as e:
            logger.error(f"PyMuPDF extraction failed: {e}")
            raise ExtractionFailedError(f"PyMuPDF failed: {e}")

    def _clean_text(self, raw: str) -> str:
        """Clean raw PDF text extracted by PyMuPDF."""
        lines = raw.splitlines()
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if len(stripped) < 4:
                continue
            if re.fullmatch(r"\d+", stripped):
                continue
            cleaned_lines.append(stripped)

        text = " ".join(cleaned_lines)
        text = re.sub(r"[^\w\s.,;:!?()\-\'\"/]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text


class OpenDataLoaderStrategy(ExtractionStrategy):
    """Primary strategy using structure-aware parsing."""
    def extract(self, pdf_bytes: bytes) -> str:
        try:
            # Placeholder implementation assuming a standard API
            return opendataloader_pdf.extract_text(pdf_bytes)
        except Exception as e:
            logger.error(f"OpenDataLoader extraction failed: {e}")
            raise ExtractionFailedError(f"OpenDataLoader failed: {e}")


class TesseractOCRStrategy(ExtractionStrategy):
    """Tertiary fallback strategy for scanned image PDFs (Not yet implemented)."""
    def extract(self, pdf_bytes: bytes) -> str:
        raise NotImplementedError("Tesseract OCR extraction not yet implemented")


class PDFExtractorService:
    """
    Service class implementing the Strategy pattern to manage the three-tier
    extraction pipeline as defined in the SDD.
    """
    def __init__(self):
        # We start with PyMuPDF as the active strategy until OpenDataLoader is ready.
        self.strategies = [
            PyMuPDFStrategy(),
            # OpenDataLoaderStrategy(),
            # TesseractOCRStrategy(),
        ]

    def extract(self, pdf_bytes: bytes) -> str:
        last_error = None
        for strategy in self.strategies:
            try:
                return strategy.extract(pdf_bytes)
            except ExtractionFailedError as e:
                last_error = e
                continue
        
        raise ExtractionFailedError(f"All extraction strategies failed. Last error: {last_error}")
