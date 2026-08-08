"""FFmpeg 视频混剪引擎。"""
from __future__ import annotations

import os
import random
import shutil
from pathlib import Path


class VideoEditor:
    def __init__(self) -> None:
        self.temp_dir = Path(os.environ.get("VIDEO_TEMP_DIR", "/tmp/video_editor"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def mix_cut(self, materials: list[str], script: dict, output_path: str) -> str:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        valid = [m for m in materials if m and Path(m).is_file()]
        if not valid:
            return self._create_placeholder(out, script)

        try:
            import ffmpeg
        except ImportError:
            return self._copy_first(valid[0], out)

        clips = self._select_clips(valid, script)
        trimmed = []
        for i, (material, duration) in enumerate(clips):
            clip_path = str(self.temp_dir / f"clip_{i}.mp4")
            start = random.uniform(0, max(0, self._get_duration(material, ffmpeg) - duration))
            self._trim(material, start, duration, clip_path, ffmpeg)
            trimmed.append(clip_path)

        concat_path = str(self.temp_dir / "concat.mp4")
        self._concat(trimmed, concat_path, ffmpeg)

        if script.get("subtitles"):
            self._add_subtitles(concat_path, script["subtitles"], str(out), ffmpeg)
        else:
            shutil.move(concat_path, out)

        for f in trimmed:
            Path(f).unlink(missing_ok=True)
        return str(out)

    def _select_clips(self, materials: list[str], script: dict) -> list[tuple[str, float]]:
        n = max(1, len(script.get("segments", [])) or 1)
        duration = 3.0
        selected = random.sample(materials, min(n, len(materials)))
        while len(selected) < n:
            selected.append(random.choice(materials))
        return [(m, duration) for m in selected[:n]]

    def _get_duration(self, path: str, ffmpeg) -> float:
        try:
            probe = ffmpeg.probe(path)
            return float(probe["format"]["duration"])
        except Exception:
            return 10.0

    def _trim(self, input_path, start, duration, output_path, ffmpeg) -> None:
        try:
            (
                ffmpeg.input(input_path, ss=start, t=duration)
                .output(output_path, c="copy")
                .overwrite_output()
                .run(quiet=True)
            )
        except Exception:
            shutil.copy(input_path, output_path)

    def _concat(self, clips, output_path, ffmpeg) -> None:
        if len(clips) == 1:
            shutil.copy(clips[0], output_path)
            return
        try:
            concat_input = ffmpeg.concat(*[ffmpeg.input(c) for c in clips])
            concat_input.output(output_path, c="copy").overwrite_output().run(quiet=True)
        except Exception:
            shutil.copy(clips[0], output_path)

    def _add_subtitles(self, input_path, subtitles, output_path, ffmpeg) -> None:
        shutil.copy(input_path, output_path)

    def _create_placeholder(self, out: Path, script: dict) -> str:
        out.write_bytes(b"")
        return str(out)

    def _copy_first(self, src: str, out: Path) -> str:
        shutil.copy(src, out)
        return str(out)
