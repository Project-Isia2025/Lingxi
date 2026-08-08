"""视频去重 — 感知哈希 + 关键帧比对。"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


class VideoDeduplicator:
    def __init__(self, threshold: int = 5) -> None:
        self.threshold = threshold

    def is_duplicate(self, video_path: str, reference_videos: list[str]) -> dict:
        target_hashes = self._extract_keyframe_hashes(video_path)
        for ref_path in reference_videos:
            if not Path(ref_path).is_file():
                continue
            ref_hashes = self._extract_keyframe_hashes(ref_path)
            min_distance = self._min_hash_distance(target_hashes, ref_hashes)
            if min_distance < self.threshold:
                return {
                    "is_duplicate": True,
                    "matched_with": ref_path,
                    "distance": min_distance,
                }
        return {"is_duplicate": False}

    def _extract_keyframe_hashes(self, video_path: str) -> list[str]:
        if not Path(video_path).is_file() or Path(video_path).stat().st_size == 0:
            return [hashlib.md5(video_path.encode()).hexdigest()[:16]]

        try:
            import ffmpeg
            import imagehash
            from PIL import Image
        except ImportError:
            return [hashlib.md5(Path(video_path).read_bytes()[:4096]).hexdigest()[:16]]

        frame_dir = Path(f"/tmp/frames_{hash(video_path) & 0xFFFFFFFF}")
        frame_dir.mkdir(parents=True, exist_ok=True)
        try:
            (
                ffmpeg.input(video_path)
                .filter("select", "eq(pict_type,I)")
                .output(str(frame_dir / "frame_%03d.jpg"), vsync="vfr")
                .overwrite_output()
                .run(quiet=True)
            )
            hashes = []
            for frame_file in sorted(frame_dir.iterdir()):
                if frame_file.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    img = Image.open(frame_file)
                    hashes.append(str(imagehash.phash(img)))
            return hashes or [hashlib.md5(video_path.encode()).hexdigest()[:16]]
        except Exception:
            return [hashlib.md5(video_path.encode()).hexdigest()[:16]]
        finally:
            for f in frame_dir.iterdir():
                f.unlink(missing_ok=True)
            frame_dir.rmdir()

    def _min_hash_distance(self, hashes1: list, hashes2: list) -> int:
        try:
            import imagehash
        except ImportError:
            return 999 if hashes1[0] != hashes2[0] else 0

        min_dist = float("inf")
        for h1 in hashes1:
            for h2 in hashes2:
                dist = imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)
                min_dist = min(min_dist, dist)
        return int(min_dist)
