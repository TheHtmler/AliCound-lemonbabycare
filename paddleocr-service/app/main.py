import base64
import os
from typing import List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from paddleocr import PaddleOCR
from pydantic import BaseModel

API_KEY = os.environ["OCR_API_KEY"]
LANG = os.environ.get("OCR_LANG", "ch")

app = FastAPI(title="PaddleOCR Service")
ocr_engine: Optional[PaddleOCR] = None


@app.on_event("startup")
def load_model():
    global ocr_engine
    # PP-OCRv5: highest-accuracy model family in PaddleOCR 3.x, CPU inference is fine at low QPS.
    ocr_engine = PaddleOCR(
        lang=LANG,
        ocr_version="PP-OCRv5",
        device="cpu",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
        # PaddlePaddle 3.3.1 + oneDNN 在 PP-OCRv5 上有已知崩溃（PaddleOCR#18119），关闭 mkldnn 规避。
        enable_mkldnn=False,
    )


def check_api_key(x_api_key: str) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")


class OcrLine(BaseModel):
    text: str
    confidence: float
    box: List[List[float]]


class OcrResponse(BaseModel):
    lines: List[OcrLine]


def run_ocr(image_bytes: bytes) -> OcrResponse:
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="unreadable image")

    lines: List[OcrLine] = []
    for res in ocr_engine.predict(image):
        texts = res.get("rec_texts") or []
        scores = res.get("rec_scores") or []
        polys = res.get("rec_polys")
        if polys is None:
            polys = res.get("dt_polys") or []
        for text, score, poly in zip(texts, scores, polys):
            box = poly.tolist() if hasattr(poly, "tolist") else poly
            lines.append(OcrLine(text=str(text), confidence=float(score), box=box))
    return OcrResponse(lines=lines)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ocr/file", response_model=OcrResponse)
def ocr_file(file: UploadFile = File(...), x_api_key: str = Header(...)):
    check_api_key(x_api_key)
    return run_ocr(file.file.read())


class OcrBase64Request(BaseModel):
    image_base64: str


@app.post("/ocr/base64", response_model=OcrResponse)
def ocr_base64(payload: OcrBase64Request, x_api_key: str = Header(...)):
    check_api_key(x_api_key)
    image_bytes = base64.b64decode(payload.image_base64)
    return run_ocr(image_bytes)
