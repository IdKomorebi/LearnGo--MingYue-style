"""最小围棋棋盘：落子、提子、找棋块。只为讲解层算“哪块棋”。"""

from typing import Dict, List, Optional, Set, Tuple

COLS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
Coord = Tuple[int, int]  # (x, y)，x 从左到右 0..n-1，y 从下到上 0..n-1（同 KaTrain/pysgf）


def gtp_to_coord(gtp: str, size: int = 19) -> Optional[Coord]:
    if gtp.lower() == "pass":
        return None
    return COLS.index(gtp[0].upper()), int(gtp[1:]) - 1


def coord_to_gtp(c: Optional[Coord]) -> str:
    return "pass" if c is None else f"{COLS[c[0]]}{c[1] + 1}"


def ownership_index(c: Coord, size: int = 19) -> int:
    """KataGo 的 ownership/policy 数组按行优先、从最上面一行开始。"""
    x, y = c
    return (size - 1 - y) * size + x


class Board:
    def __init__(self, size: int = 19):
        self.size = size
        self.stones: Dict[Coord, str] = {}

    def neighbours(self, c: Coord) -> List[Coord]:
        x, y = c
        return [
            (a, b)
            for a, b in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            if 0 <= a < self.size and 0 <= b < self.size
        ]

    def group(self, c: Coord) -> Tuple[Set[Coord], Set[Coord]]:
        color = self.stones[c]
        stones, libs, todo = {c}, set(), [c]
        while todo:
            for n in self.neighbours(todo.pop()):
                if n not in self.stones:
                    libs.add(n)
                elif self.stones[n] == color and n not in stones:
                    stones.add(n)
                    todo.append(n)
        return stones, libs

    def play(self, player: str, c: Optional[Coord]) -> List[Coord]:
        """落子并返回被提掉的子。"""
        if c is None:
            return []
        self.stones[c] = player
        captured = []
        for n in self.neighbours(c):
            if n in self.stones and self.stones[n] != player:
                stones, libs = self.group(n)
                if not libs:
                    captured += stones
                    for s in stones:
                        del self.stones[s]
        stones, libs = self.group(c)
        if not libs:  # 自杀（规则允许时）
            for s in stones:
                del self.stones[s]
        return captured

    def groups(self) -> List[Tuple[str, Set[Coord], Set[Coord]]]:
        seen, out = set(), []
        for c, color in self.stones.items():
            if c not in seen:
                stones, libs = self.group(c)
                seen |= stones
                out.append((color, stones, libs))
        return out
