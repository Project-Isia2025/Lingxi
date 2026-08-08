"""商品图合成：ffmpeg 叠加产品图到成片。"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from services.video_mix import resolve_ffmpeg


def product_compose_enabled() -> bool:
    return os.environ.get("PRODUCT_COMPOSE_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def resolve_product_image(*, extra: dict[str, Any] | None = None, inventory_product: dict[str, Any] | None = None) -> str:
    """解析商品图路径：goal.extra > 库存 SKU > 环境变量 > 默认占位。"""
    import bootstrap

    for src in (
        (extra or {}).get("product_image"),
        (inventory_product or {}).get("image"),
        (inventory_product or {}).get("image_path"),
        os.environ.get("PRODUCT_IMAGE_PATH"),
    ):
        p = Path(str(src or "").strip()).expanduser()
        if p.is_file():
            return str(p.resolve())

    default = bootstrap.project_root() / "data" / "product_images" / "default.png"
    if default.is_file():
        return str(default.resolve())
    return ""


def attach_product_image(
    video_path: Path,
    image_path: str,
    *,
    position: str = "",
) -> dict[str, Any]:
    """在成片右下角叠加商品图。"""
    if not product_compose_enabled():
        return {"ok": False, "reason": "product_compose_disabled"}
    img = Path(image_path).expanduser()
    if not img.is_file():
        return {"ok": False, "error": "product_image_missing", "path": str(img)}
    if not video_path.is_file():
        return {"ok": False, "error": "video_missing", "path": str(video_path)}

    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg_not_found"}

    pos = (position or os.environ.get("PRODUCT_IMAGE_POSITION") or "bottom_right").strip().lower()
    margin = int(os.environ.get("PRODUCT_IMAGE_MARGIN", "40") or 40)
    scale_pct = float(os.environ.get("PRODUCT_IMAGE_SCALE", "0.28") or 0.28)

    if pos == "bottom_left":
        overlay = f"x={margin}:y=H-h-{margin}"
    elif pos == "top_right":
        overlay = f"x=W-w-{margin}:y={margin}"
    else:
        overlay = f"x=W-w-{margin}:y=H-h-{margin}"

    out = video_path.with_name(video_path.stem + "_product.mp4")
    scale = max(0.12, min(0.5, scale_pct))
    filt = f"[1:v]scale=iw*{scale}:-1[img];[0:v][img]overlay={overlay}"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(img),
        "-filter_complex",
        filt,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "copy",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "error": "product_overlay_failed",
            "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")[:300],
        }
    return {
        "ok": True,
        "output_path": str(out.resolve()),
        "product_image": str(img.resolve()),
        "position": pos,
    }
