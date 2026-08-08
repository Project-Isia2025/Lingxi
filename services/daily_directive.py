"""策略日指令：库存 + 热点 → 3×15s 切片生产任务。"""
from __future__ import annotations

from datetime import date
from typing import Any


def build_daily_directive(
    *,
    keyword: str,
    perception: dict[str, Any],
    memory: dict[str, Any] | None = None,
    product: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成「今天主推 X，产出 3 条 15 秒切片」结构化指令。"""
    from services.inventory import get_primary_product

    prod = product
    if not prod:
        inv = get_primary_product()
        if not inv.get("ok"):
            prod = {"sku": "DEFAULT", "name": keyword or "主推SKU", "keyword": keyword, "stock": 0}
        else:
            prod = inv["product"]

    name = str(prod.get("name") or keyword)
    stock = int(prod.get("stock") or 0)
    prod_kw = str(prod.get("keyword") or keyword or name)

    hotspots = perception.get("hotspots") or []
    hotlist = perception.get("hotlist") or []
    hot_title = ""
    if hotlist:
        hot_title = str(hotlist[0].get("title") or "")
    elif hotspots:
        hot_title = str(hotspots[0].get("title") or "")
    hot_ref = hot_title or prod_kw

    viral = (memory or {}).get("viral_structure") or []
    hook_hint = ""
    if viral:
        segs = viral[0].get("segments") or []
        if segs:
            hook_hint = str(segs[0].get("hint") or segs[0].get("name") or "")

    instruction = (
        f"今天主推{name}（库存 {stock} 单），结合热点「{hot_ref}」，"
        f"用「痛点+解决方案」结构，产出 3 条 15 秒切片视频。"
    )

    hook_styles = ["痛点反问", "结果先行", "对比冲击"]
    slices: list[dict[str, Any]] = []
    for i, style in enumerate(hook_styles, 1):
        brief = f"15秒切片{i}：{style}开场，聚焦{name}，结构=痛点+解决方案"
        if hook_hint and i == 1:
            brief += f"；参考钩子：{hook_hint[:40]}"
        slices.append({
            "id": f"S{i}",
            "duration_sec": 15,
            "structure": "痛点+解决方案",
            "hook_style": style,
            "product_sku": prod.get("sku"),
            "product_name": name,
            "brief": brief,
        })

    return {
        "ok": True,
        "date": date.today().isoformat(),
        "primary_product": prod,
        "hotspot_ref": hot_ref,
        "instruction": instruction,
        "structure": "痛点+解决方案",
        "slices": slices,
        "slice_count": len(slices),
        "total_duration_sec": sum(s.get("duration_sec", 15) for s in slices),
    }
