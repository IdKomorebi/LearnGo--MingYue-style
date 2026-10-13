"""把坐标翻译成人话：哪个角、哪条边、几路、什么定式点。"""

from typing import Iterable, Optional, Tuple

from katrain.core.explain.board import Coord

STAR_NAMES = {
    (3, 3): "三三",
    (4, 4): "星位",
    (3, 4): "小目",
    (4, 3): "小目",
    (4, 5): "高目",
    (5, 4): "高目",
    (3, 5): "目外",
    (5, 3): "目外",
    (5, 5): "五五",
}


CN_NUM = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}


def line_of(c: Coord, size: int = 19) -> Tuple[int, int]:
    """返回 (离左右最近边的路数, 离上下最近边的路数)，从 1 开始数。"""
    x, y = c
    return min(x, size - 1 - x) + 1, min(y, size - 1 - y) + 1


def region_of(c: Coord, size: int = 19) -> str:
    x, y = c
    third = size / 3
    h = "左" if x < third else ("右" if x >= size - third else "中")
    v = "下" if y < third else ("上" if y >= size - third else "中")
    if h == "中" and v == "中":
        return "中腹"
    if h == "中":
        return f"{v}边"
    if v == "中":
        return f"{h}边"
    return f"{h}{v}角"


def describe_point(c: Optional[Coord], size: int = 19) -> str:
    if c is None:
        return "停一手"
    lx, ly = line_of(c, size)
    region = region_of(c, size)
    name = STAR_NAMES.get((lx, ly)) if region.endswith("角") else None
    if name:
        return f"{region}{name}"
    low = min(lx, ly)
    if region.endswith("边"):
        return f"{region}{CN_NUM.get(low, low)}路"
    if region == "中腹":
        return "中腹"
    return f"{region}{CN_NUM.get(low, low)}路"


def summarize_region(points: Iterable[Coord], size: int = 19) -> str:
    regions = {}
    for p in points:
        r = region_of(p, size)
        regions[r] = regions.get(r, 0) + 1
    if not regions:
        return ""
    return max(regions, key=regions.get)
