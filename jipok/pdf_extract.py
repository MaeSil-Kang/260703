"""질문(스케줄) PDF 렌더 + 보조 추출.

스캔 이미지 PDF라 완전 자동 OCR은 불안정 → 페이지를 렌더해 화면에 보여주고
사용자가 편집표에서 검수/수정하는 흐름을 전제로 한다.
"""
import fitz
from PIL import Image


def render_pages(pdf_bytes, dpi=200):
    """PDF 바이트 → PIL 이미지 리스트(페이지별)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    imgs = []
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        imgs.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return imgs


def try_ocr(pdf_bytes, dpi=300):
    """tesseract가 설치돼 있으면 텍스트 1차 추출(보조용). 없으면 ''."""
    try:
        import pytesseract
    except Exception:
        return ""
    text = []
    for img in render_pages(pdf_bytes, dpi):
        try:
            text.append(pytesseract.image_to_string(img, lang="kor+eng"))
        except Exception:
            return ""
    return "\n".join(text)
