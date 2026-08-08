"""AI 视频生成 provider 基类。"""
from __future__ import annotations

from typing import Any, Protocol


class VideoProvider(Protocol):
    name: str

    def produce(
        self,
        *,
        script: str,
        run_id: str,
        source_video: str = "",
        image_path: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...
