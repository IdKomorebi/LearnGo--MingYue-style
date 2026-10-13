"""战术层：只看棋盘，不看 AI 数字，说清一手棋在局部“干了什么”。

KataGo 只给数字和坐标（胜率、目差、变化图、每个点归谁），不会告诉你“这手是打吃”“这里被切断了”。
讲解要有内容，就得把这些局部动作算出来：提子、打吃、长出、连接、切断、自紧气，以及常见棋形
（挖、扳、靠、长、立、尖、跳、飞、拆）。全部是确定性的计算，不会讲错棋盘上没有的东西。
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from katrain.core.explain.board import Board, Coord, coord_to_gtp, gtp_to_coord
from katrain.core.explain.geometry import CN_NUM, line_of, summarize_region

CN = {"B": "黑", "W": "白"}


def other(player: str) -> str:
    return "W" if player == "B" else "B"


@dataclass
class GroupRef:
    color: str
    stones: List[str]  # GTP 坐标
    anchor: str  # 离讨论点最近的一颗子，用来指代这块棋
    region: str
    libs: int

    @property
    def size(self) -> int:
        return len(self.stones)

    def name(self) -> str:
        """“白L11一子”“黑K11等3子”。"""
        n = self.size
        return f"{CN[self.color]}{self.anchor}" + ("一子" if n == 1 else ("两子" if n == 2 else f"等{n}子"))


def group_ref(board: Board, stones: Iterable[Coord], near: Optional[Coord] = None) -> GroupRef:
    stones = set(stones)
    first = next(iter(stones))
    _, libs = board.group(first) if first in board.stones else (stones, set())
    if near is None:
        c = board.size // 2
        near = (c, c)
    anchor = min(stones, key=lambda s: (abs(s[0] - near[0]) + abs(s[1] - near[1]), s))
    return GroupRef(
        color=board.stones.get(first, "?"),
        stones=sorted(coord_to_gtp(s) for s in stones),
        anchor=coord_to_gtp(anchor),
        region=summarize_region(stones, board.size),
        libs=len(libs),
    )


@dataclass
class MoveTactics:
    player: str
    move: str
    shape: Optional[str] = None  # 棋形词：挖/扳/靠/长/立/爬/尖/跳/小飞/大飞/拆二…
    shape_ref: Optional[str] = None  # 棋形参照的那颗子（扳/靠是对方子，其他是自己的子）
    captured: List[str] = field(default_factory=list)
    atari: List[GroupRef] = field(default_factory=list)  # 被打吃的对方棋块
    pressed: List[GroupRef] = field(default_factory=list)  # 被紧到两气的对方棋块（2 子以上才算）
    rescued: Optional[GroupRef] = None  # 原来被打吃、现在长出来的己方棋块（libs 是长出后的气数）
    rescued_total: int = 0
    connected: Optional[GroupRef] = None  # 把 ≥2 块己方棋连成的整块
    connected_count: int = 0
    cut: List[GroupRef] = field(default_factory=list)  # 被这手分开的对方棋块（≥2 块）
    self_atari: Optional[GroupRef] = None  # 落子后自己只剩一口气
    is_pass: bool = False

    @property
    def is_quiet(self) -> bool:
        return not (self.captured or self.atari or self.rescued or self.connected or self.cut or self.self_atari)

    def label(self) -> str:
        """最主要的一个动作词，用于变化图和标题。"""
        if self.is_pass:
            return "停一手"
        if self.captured:
            return "提"
        if len(self.atari) >= 2:
            return "双打吃"
        if self.atari:
            return "打吃"
        if self.rescued:
            return "长出"
        if self.shape == "挖":
            return "挖"
        if len(self.cut) >= 2:
            return "切断"
        if self.connected:
            return "连接"
        return self.shape or ""

    def shape_phrase(self) -> str:
        """“从K11长”“对白M10扳”“靠住白Q4”。"""
        if not self.shape:
            return ""
        r = self.shape_ref
        if not r:
            return self.shape
        if self.shape == "扳":
            return f"对{CN[other(self.player)]}{r}扳"
        if self.shape == "靠":
            return f"靠住{CN[other(self.player)]}{r}"
        if self.shape.startswith("拆"):
            return f"从{r}{self.shape}"
        return f"从{r}{self.shape}"

    def phrase(self) -> str:
        """一句话说清这手干了什么，没有可说的就返回空串。"""
        if self.is_pass:
            return "停一手"
        opp = CN[other(self.player)]
        parts: List[str] = []
        if self.shape and self.shape != "挖" and not self.rescued and not self.captured:
            parts.append(self.shape_phrase())
        if self.captured:
            parts.append(f"提掉{opp}{len(self.captured)}子（{'、'.join(self.captured[:4])}）")
        atari_anchors = {g.anchor for g in self.atari}
        cut_other = [g for g in self.cut if g.anchor not in atari_anchors]
        if len(self.atari) >= 2:
            parts.append("同时打吃" + "和".join(g.name() for g in self.atari[:2]))
        elif self.atari:
            parts.append(f"打吃{self.atari[0].name()}")
            if cut_other:
                parts.append(f"并把它和{cut_other[0].name()}分开")
        if self.rescued:
            grown = f"，现在{self.rescued_total}子{self.rescued.libs}口气" if self.rescued_total else ""
            parts.append(f"把被打吃的{self.rescued.name()}长出来{grown}")
        if not self.atari and len(cut_other) >= 2:
            a, b = cut_other[0].name(), cut_other[1].name()
            parts.append(f"挖进{a}和{b}中间" if self.shape == "挖" else f"切断{a}和{b}")
        if self.connected and not self.rescued:
            parts.append(f"把{self.connected_count}块{CN[self.player]}棋连成一块（{self.connected.size}子）")
        for g in self.pressed[:1]:
            if not self.atari:
                parts.append(f"把{g.name()}紧到只剩两口气")
        if self.self_atari:
            parts.append(f"但自己这块{self.self_atari.name()}只剩一口气，随时会被提")
        return "，".join(p for p in parts if p)


def _shape(board: Board, player: str, c: Coord) -> Tuple[Optional[str], Optional[Coord]]:
    """落子前的棋盘上，判断这手的棋形名和参照的那颗子。只认几种不容易误判的。"""
    x, y = c
    st = board.stones
    opp = other(player)
    orth = board.neighbours(c)
    own_orth = [n for n in orth if st.get(n) == player]
    opp_orth = [n for n in orth if st.get(n) == opp]
    diag = [(x + dx, y + dy) for dx in (-1, 1) for dy in (-1, 1)]
    own_diag = [d for d in diag if st.get(d) == player]

    # 挖：左右（或上下）都是对方子，自己这边没有子接应
    if not own_orth:
        for a, b in (((x - 1, y), (x + 1, y)), ((x, y - 1), (x, y + 1))):
            if st.get(a) == opp and st.get(b) == opp:
                return "挖", None
    # 扳：斜着有自己的子，且贴着一颗与那颗子相邻的对方子
    if not own_orth and opp_orth:
        for d in own_diag:
            for o in opp_orth:
                if abs(o[0] - d[0]) + abs(o[1] - d[1]) == 1:
                    return "扳", o
    if own_orth:
        n = own_orth[0]
        lc, ln = min(line_of(c, board.size)), min(line_of(n, board.size))
        if lc <= 2 and lc < ln:
            return "立", n
        if lc <= 2 and lc == ln and opp_orth:
            return "爬", n
        return "长", n
    near_own = [(dx, dy) for dx in range(-4, 5) for dy in range(-4, 5) if st.get((x + dx, y + dy)) == player]
    if opp_orth and not own_diag:
        return "靠", opp_orth[0]
    if own_diag:
        return "尖", own_diag[0]
    for dx, dy in near_own:
        ax, ay = abs(dx), abs(dy)
        if (ax, ay) in ((2, 0), (0, 2)) and (x + dx // 2, y + dy // 2) not in st:
            return "跳", (x + dx, y + dy)
    for dx, dy in near_own:
        if sorted((abs(dx), abs(dy))) == [1, 2]:
            return "小飞", (x + dx, y + dy)
    for dx, dy in near_own:
        if sorted((abs(dx), abs(dy))) == [1, 3]:
            return "大飞", (x + dx, y + dy)
    if min(line_of(c, board.size)) <= 4:
        for dx, dy in near_own:
            if (abs(dx), abs(dy)) in ((3, 0), (0, 3), (4, 0), (0, 4)):
                return f"拆{CN_NUM[max(abs(dx), abs(dy)) - 1]}", (x + dx, y + dy)
    return None, None


def analyze_move(board: Board, player: str, c: Optional[Coord]) -> MoveTactics:
    """在 board（落子前）上分析 player 下在 c 的局部动作。会修改 board：调用后 board 是落子后的局面。"""
    t = MoveTactics(player=player, move=coord_to_gtp(c))
    if c is None:
        t.is_pass = True
        return t
    opp = other(player)
    t.shape, ref = _shape(board, player, c)
    t.shape_ref = coord_to_gtp(ref) if ref else None

    own_before: List[Set[Coord]] = []
    opp_before: Dict[frozenset, int] = {}
    for n in board.neighbours(c):
        if n not in board.stones:
            continue
        stones, libs = board.group(n)
        if board.stones[n] == player:
            if not any(n in g for g in own_before):
                own_before.append(stones)
                if len(libs) == 1:
                    t.rescued = group_ref(board, stones, c)  # 先记着，落子后看是否真长出来
        else:
            opp_before[frozenset(stones)] = len(libs)

    captured = board.play(player, c)
    t.captured = sorted(coord_to_gtp(s) for s in captured)

    if c not in board.stones:  # 自杀被提（规则允许时）
        return t
    my_stones, my_libs = board.group(c)
    if t.rescued:
        if len(my_libs) >= 2:
            t.rescued.libs, t.rescued_total = len(my_libs), len(my_stones)
        else:
            t.rescued = None
    if len(own_before) >= 2:
        t.connected = group_ref(board, my_stones, c)
        t.connected_count = len(own_before)
    if len(my_libs) == 1 and not captured:
        t.self_atari = group_ref(board, my_stones, c)

    seen: List[Set[Coord]] = []
    for n in board.neighbours(c):
        if board.stones.get(n) != opp or any(n in g for g in seen):
            continue
        stones, libs = board.group(n)
        seen.append(stones)
        ref = group_ref(board, stones, c)
        before_libs = opp_before.get(frozenset(stones), 99)
        if len(libs) == 1:
            t.atari.append(ref)
        elif len(libs) == 2 and before_libs > 2 and len(stones) >= 2:
            t.pressed.append(ref)
    if len(seen) >= 2 and _separates(board, c, seen):
        t.cut = [group_ref(board, g, c) for g in seen]
    t.atari.sort(key=lambda g: -g.size)
    return t


def _separates(board: Board, c: Coord, groups: List[Set[Coord]]) -> bool:
    """c 旁边的两块对方棋，原本是斜着（断点）或隔着 c 相对（挖/夹）的，落子才算“切断”。"""
    adj = [[n for n in board.neighbours(c) if n in g] for g in groups]
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            for a in adj[i]:
                for b in adj[j]:
                    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
                    if (dx, dy) in ((1, 1), (2, 0), (0, 2)):
                        return True
    return False


def describe_sequence(board: Board, pv: Sequence[str], first_player: str, max_len: int = 5) -> List[Dict]:
    """把一串变化（GTP 坐标）逐手翻成“谁、下哪、干了什么”。不修改传入的 board。"""
    b = board.copy()
    out, p = [], first_player
    for m in pv[:max_len]:
        t = analyze_move(b, p, gtp_to_coord(m, b.size))
        out.append({"player": p, "move": m, "label": t.label(), "phrase": t.phrase()})
        p = other(p)
    return out


def sequence_text(steps: Sequence[Dict]) -> str:
    """“黑L10打吃 → 白L12长出 → 黑M10”。"""
    return " → ".join(f"{CN[s['player']]}{s['move']}{s['label']}" for s in steps)
