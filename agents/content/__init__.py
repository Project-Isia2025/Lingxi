"""内容 Agent — 脚本生成 / 视频混剪 / 去重。"""
from __future__ import annotations

from pathlib import Path

from agents.base import BaseAgent
from agents.content.dedup import VideoDeduplicator
from agents.content.script_generator import ScriptGenerator
from agents.content.video_editor import VideoEditor
from memory.knowledge_base import KnowledgeBase


class ContentAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("content")
        self.script_gen = ScriptGenerator()
        self.editor = VideoEditor()
        self.dedup = VideoDeduplicator()
        self.kb = KnowledgeBase()

    async def execute(self, task: dict) -> dict:
        task_type = task.get("type")

        if task_type == "generate_script":
            result = await self.script_gen.generate(product=task["product"], style=task.get("style", "激情带货"))
            await self.kb.ingest(
                "scripts",
                result["raw_script"],
                {"title": task["product"].get("name"), "platform": task.get("platform", "douyin")},
            )
            return {"script": result}

        if task_type == "produce_video":
            script = task.get("script")
            if not script:
                script_result = await self.script_gen.generate(task["product"])
                script = script_result.get("parsed") or {"raw": script_result.get("raw_script")}

            output_path = task.get("output_path", "data/output/videos/agent_out.mp4")
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            video_path = await self.editor.mix_cut(
                materials=task.get("materials", []),
                script=script if isinstance(script, dict) else {"raw": script},
                output_path=output_path,
            )
            dedup_result = self.dedup.is_duplicate(video_path, task.get("reference_videos", []))
            await self.kb.log_decision(
                agent_name=self.name,
                decision_type="produce_video",
                input_data={"product": task.get("product", {}).get("name")},
                output_data={"video_path": video_path, "dedup": dedup_result},
                confidence=0.2 if dedup_result.get("is_duplicate") else 0.9,
            )
            return {"video_path": video_path, "script": script, "dedup": dedup_result}

        if task_type == "batch_produce":
            results = []
            output_dir = task.get("output_dir", "data/output/videos/batch")
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            for i in range(task.get("count", 5)):
                result = await self.execute(
                    {
                        "type": "produce_video",
                        "product": task["product"],
                        "materials": task["materials"],
                        "output_path": f"{output_dir}/video_{i}.mp4",
                        "reference_videos": task.get("reference_videos", []),
                    }
                )
                results.append(result)
            return {"videos": results, "count": len(results)}

        raise ValueError(f"Unknown task type: {task_type}")


__all__ = ["ContentAgent", "ScriptGenerator", "VideoEditor", "VideoDeduplicator"]
