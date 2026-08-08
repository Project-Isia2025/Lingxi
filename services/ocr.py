"""图片 OCR：pytesseract / LLM Vision / 降级兜底。"""
from __future__ import annotations

import base64
import io
import os
import re
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def ocr_enabled() -> bool:
    return os.environ.get("OCR_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _pytesseract_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401

        cmd = (os.environ.get("TESSERACT_CMD") or "").strip()
        if cmd:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = cmd
        return True
    except ImportError:
        return False


def _ocr_with_tesseract(image_bytes: bytes) -> str:
    import pytesseract
    from PIL import Image

    cmd = (os.environ.get("TESSERACT_CMD") or "").strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    img = Image.open(io.BytesIO(image_bytes))
    lang = (os.environ.get("OCR_LANG") or "chi_sim+eng").strip()
    text = pytesseract.image_to_string(img, lang=lang)
    return re.sub(r"\s+", " ", (text or "").strip())


def _ocr_with_llm_vision(image_bytes: bytes) -> str:
    import requests

    base = (os.environ.get("VISION_API_BASE") or os.environ.get("LLM_API_BASE") or "").strip().rstrip("/")
    key = (os.environ.get("VISION_API_KEY") or os.environ.get("LLM_API_KEY") or "").strip()
    model = (os.environ.get("VISION_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini").strip()
    if not base or not key:
        return ""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    resp = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "提取图片中所有可见中文文字，按阅读顺序输出，不要解释。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            "max_tokens": 800,
        },
        timeout=int(os.environ.get("VISION_TIMEOUT_SEC", "60")),
    )
    resp.raise_for_status()
    data = resp.json()
    return str(data["choices"][0]["message"]["content"] or "").strip()


def download_image(url: str, *, timeout: int = 15) -> bytes:
    req = Request(url, headers={"User-Agent": "MatrixAgent/1.0", "Referer": "https://www.xiaohongshu.com/"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def ocr_image_bytes(image_bytes: bytes) -> dict[str, Any]:
    if not ocr_enabled():
        return {"ok": False, "error": "ocr_disabled"}
    if not image_bytes:
        return {"ok": False, "error": "empty_image"}

    if _pytesseract_available():
        try:
            text = _ocr_with_tesseract(image_bytes)
            if text:
                return {"ok": True, "text": text[:2000], "provider": "tesseract"}
        except Exception as exc:
            tess_err = str(exc)
    else:
        tess_err = "pytesseract_not_installed"

    try:
        text = _ocr_with_llm_vision(image_bytes)
        if text:
            return {"ok": True, "text": text[:2000], "provider": "llm_vision"}
    except Exception as exc:
        llm_err = str(exc)
        return {"ok": False, "error": "ocr_failed", "tesseract": tess_err, "llm": llm_err}

    return {"ok": False, "error": "ocr_empty", "tesseract": tess_err}


def ocr_image_url(url: str) -> dict[str, Any]:
    try:
        raw = download_image(url)
    except Exception as exc:
        return {"ok": False, "error": "download_failed", "url": url, "detail": str(exc)}
    out = ocr_image_bytes(raw)
    out["url"] = url
    return out


def ocr_image_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": "file_not_found", "path": str(p)}
    return ocr_image_bytes(p.read_bytes())


def ocr_images(urls: list[str], *, limit: int = 5) -> dict[str, Any]:
    """批量 OCR 并合并文本。"""
    parts: list[str] = []
    details: list[dict[str, Any]] = []
    for url in urls[:limit]:
        if not str(url).startswith("http"):
            continue
        row = ocr_image_url(url)
        details.append(row)
        if row.get("ok") and row.get("text"):
            parts.append(str(row["text"]))
    merged = "\n".join(parts).strip()
    return {
        "ok": bool(merged),
        "merged_text": merged[:4000],
        "image_count": len(details),
        "success_count": sum(1 for d in details if d.get("ok")),
        "details": details,
    }
