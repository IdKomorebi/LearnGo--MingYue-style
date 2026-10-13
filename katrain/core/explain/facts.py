"""事实层：只做确定性的计算，把 KataGo 的数字变成“发生了什么”。

输入统一用 KataGo analysis engine 的原始返回（rootInfo / moveInfos / ownership / policy，
胜率和目差都按黑方视角，即 reportAnalysisWinratesAs=BLACK，KaTrain 默认如此）。
输出 MoveFacts，后面的模板和 LLM 只能用这里面的东西说话，避免“编棋”。
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

from katrain.core.explain.board import Board, coord_to_gtp, gtp_to_coord, ownership_index
from katrain.core.explain.geometry import describe_point, region_of, summarize_region
from katrain.core.explain.tactics import analyze_move, describe_sequence, group_ref

# 和 KaTrain 默认 trainer/eval_thresholds 对齐：[12, 6, 3, 1.5, 0.5, 0]
VERDICTS = [(12, "败着"), (6, "恶手"), (3, "疑问手"), (1.5, "缓手"), (0.5, "小亏"), (-1e9, "好棋")]


def sign(player: str) -> int:
    return 1 if player == "B" else -1


def verdict_of(points_lost: float) -> str:
    for threshold, name in VERDICTS:
        if points_lost >= threshold:
            return name
    return "好棋"


def group_status(s: float) -> str:
    """s：棋块所有子的平均 ownership（从该块自己的颜色看），1=稳活，-1=已死。"""
    if s > 0.7:
        return "安定"
    if s > 0.3:
        return "偏安定"
    if s > -0.3:
        return "未定"
    if s > -0.7:
        return "危险"
    return "已死"


@dataclass
class GroupChange:
    color: str
    region: str
    size: int
    anchor: str
    before: str
    after: str
    delta: float  # 从这块棋自己颜色看，安全度变化（-2..2）
    stones: List[str] = field(default_factory=list)  # GTP 坐标，供棋盘高亮
    name: str = ""  # “白L11一子”


@dataclass
class FateDiff:
    """同一块棋，在“实战”和“AI 首选”两种下法之后的命运对比。"""

    color: str
    name: str
    size: int
    stones: List[str]
    actual: str  # 实战后的状态
    best: str  # 按 AI 首选下之后的状态
    delta: float  # 从这块棋自己颜色看：AI 首选比实战好多少（-2..2）


@dataclass
class MoveFacts:
    move_number: int
    player: str
    move: str
    move_desc: str
    phase: str
    # 以下都从落子方视角
    score_before: float
    score_after: float
    winrate_before: float
    winrate_after: float
    points_lost: float
    winrate_lost: float
    verdict: str
    is_best: bool
    played_rank: Optional[int]  # 在 KataGo 候选里的名次（1 起），None=不在候选里
    played_prior: Optional[float]  # 神经网络第一感（policy）给这手的概率
    best_move: str
    best_desc: str
    best_prior: float
    best_pv: List[str]
    best_pv_desc: List[str]
    near_best_count: int  # 和最佳差 1 目以内的候选数
    surprise: bool  # 好棋但第一感很低：“AI 都没第一时间想到”
    territory_swings: List[Dict] = field(default_factory=list)  # [{region, points}] 落子方视角
    group_changes: List[GroupChange] = field(default_factory=list)
    captured: int = 0
    reply_pv: List[str] = field(default_factory=list)  # 落子后对方最佳应对
    reply_pv_desc: List[str] = field(default_factory=list)
    score_stdev: Optional[float] = None
    visits: int = 0
    # 战术层：局部到底发生了什么（全部由棋盘计算，不依赖 AI）
    played_label: str = ""  # “挖”“打吃”“长”……
    played_phrase: str = ""  # “挖进黑K11一子和黑M11等4子中间”
    best_label: str = ""
    best_phrase: str = ""
    best_steps: List[Dict] = field(default_factory=list)  # [{player, move, label, phrase}]
    reply_steps: List[Dict] = field(default_factory=list)
    # 亏在哪里：实战 vs AI 首选，两种下法之后每块棋的命运、每片区域的归属差
    fate_diffs: List[FateDiff] = field(default_factory=list)
    loss_regions: List[Dict] = field(default_factory=list)  # [{region, points}]，落子方视角，正数=首选更好
    # AI 的“第一感”（policy 最高的候选）：用来讲“直觉 vs 计算”的反转
    instinct_move: str = ""
    instinct_prior: float = 0.0
    instinct_vs_played: Optional[float] = None  # 第一感比实战好多少目（负数=实战更好）
    instinct_phrase: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


def _phase(move_number: int, stones_on_board: int, size: int) -> str:
    if move_number <= size * 2.5 and stones_on_board < size * size * 0.15:
        return "布局"
    if stones_on_board < size * size * 0.55:
        return "中盘"
    return "官子"


def _policy_of(policy: Optional[Sequence[float]], gtp: str, size: int) -> Optional[float]:
    if not policy:
        return None
    c = gtp_to_coord(gtp, size)
    return policy[-1] if c is None else policy[ownership_index(c, size)]


def _pv_desc(pv: Sequence[str], first_player: str, size: int) -> List[str]:
    out, p = [], first_player
    for m in pv:
        out.append(f"{'黑' if p == 'B' else '白'}{describe_point(gtp_to_coord(m, size), size)}({m})")
        p = "W" if p == "B" else "B"
    return out


def _avg_status(stones, color: str, own: Sequence[float], size: int) -> float:
    cs = sign(color)
    return sum(cs * own[ownership_index(s, size)] for s in stones) / len(stones)


def _fate_diffs(board: Board, own_actual, own_best, size: int, limit: int = 2) -> List[FateDiff]:
    """实战局面上的每块棋，比较两种下法之后的 ownership：哪块棋的命运因为没下首选而变了。"""
    out = []
    for color, stones, _ in board.groups():
        sa = _avg_status(stones, color, own_actual, size)
        sb = _avg_status(stones, color, own_best, size)
        d = sb - sa
        if abs(d) < 0.4 or (len(stones) < 2 and abs(d) < 0.8):
            continue
        ref = group_ref(board, stones)
        out.append(
            FateDiff(color, ref.name(), len(stones), ref.stones, group_status(sa), group_status(sb), round(d, 2))
        )
    out.sort(key=lambda f: -abs(f.delta) * f.size)
    return out[:limit]


def _region_diff(own_new, own_old, sg: int, size: int, threshold: float = 1.5, limit: int = 3) -> List[Dict]:
    """两张 ownership 图按区域求差（落子方视角），大约就是各区域的目数变化。"""
    by_region: Dict[str, float] = {}
    for y in range(size):
        for x in range(size):
            i = ownership_index((x, y), size)
            r = region_of((x, y), size)
            by_region[r] = by_region.get(r, 0.0) + sg * (own_new[i] - own_old[i])
    return [
        {"region": r, "points": round(v, 1)}
        for r, v in sorted(by_region.items(), key=lambda kv: -abs(kv[1]))
        if abs(v) >= threshold
    ][:limit]


def extract_move_facts(
    moves: Sequence[Sequence[str]],
    move_index: int,
    before: Dict,
    after: Dict,
    size: int = 19,
    pv_len: int = 6,
) -> MoveFacts:
    """moves：整局 [[player, gtp], ...]；move_index：0 起，表示讲第 move_index+1 手。
    before：落子前局面的分析；after：落子后局面的分析。"""
    player, gtp = moves[move_index]
    sg = sign(player)
    board = Board(size)
    for p, m in moves[:move_index]:
        board.play(p, gtp_to_coord(m, size))
    stones_before = dict(board.stones)
    board_before = board.copy()
    played_t = analyze_move(board, player, gtp_to_coord(gtp, size))
    captured = played_t.captured

    rb, ra = before["rootInfo"], after["rootInfo"]
    score_before, score_after = sg * rb["scoreLead"], sg * ra["scoreLead"]
    wr_before = rb["winrate"] if player == "B" else 1 - rb["winrate"]
    wr_after = ra["winrate"] if player == "B" else 1 - ra["winrate"]
    points_lost = score_before - score_after

    cands = sorted(before.get("moveInfos", []), key=lambda d: d["order"])
    best = cands[0]
    played_rank = next((i + 1 for i, d in enumerate(cands) if d["move"] == gtp), None)
    best_score = sg * best["scoreLead"]
    near_best = sum(1 for d in cands if best_score - sg * d["scoreLead"] <= 1.0 and d["visits"] >= 2)
    played_prior = _policy_of(before.get("policy"), gtp, size)
    is_best = gtp == best["move"] or points_lost <= 0.3

    # 地盘变化：ownership 差（落子方视角），按区域累加
    own_b, own_a = before.get("ownership"), after.get("ownership")
    swings = _region_diff(own_a, own_b, sg, size) if own_b and own_a else []

    # 正解：首选这手在局部干什么，以及它的变化图每一步的意思
    best_t = analyze_move(board_before.copy(), player, gtp_to_coord(best["move"], size))
    best_steps = describe_sequence(board_before, best["pv"][:pv_len], player)

    # 亏在哪里：首选的 ownership vs 实战的 ownership（KaTrain 实时分析里每个候选都带 ownership）
    played_info = next((d for d in cands if d["move"] == gtp), None)
    own_actual = (played_info or {}).get("ownership") or own_a
    own_best = best.get("ownership")
    fate_diffs, loss_regions = [], []
    if own_actual and own_best and best["move"] != gtp:
        fate_diffs = _fate_diffs(board, own_actual, own_best, size)
        loss_regions = _region_diff(own_best, own_actual, sg, size, threshold=1.0, limit=2)

    # 棋块死活变化
    group_changes = []
    if own_b and own_a:
        for color, stones, libs in board.groups():
            old = [s for s in stones if stones_before.get(s) == color]
            if len(stones) < 2 or not old:
                continue
            cs = sign(color)
            s_before = sum(cs * own_b[ownership_index(s, size)] for s in old) / len(old)
            s_after = sum(cs * own_a[ownership_index(s, size)] for s in stones) / len(stones)
            if abs(s_after - s_before) >= 0.5 or (
                group_status(s_before) != group_status(s_after) and abs(s_after - s_before) >= 0.3
            ):
                anchor = coord_to_gtp(min(stones, key=lambda c: abs(c[0] - 9) + abs(c[1] - 9)))
                group_changes.append(
                    GroupChange(
                        color,
                        summarize_region(stones, size),
                        len(stones),
                        anchor,
                        group_status(s_before),
                        group_status(s_after),
                        round(s_after - s_before, 2),
                        sorted(coord_to_gtp(c) for c in stones),
                        group_ref(board, stones).name(),
                    )
                )
        group_changes.sort(key=lambda g: -abs(g.delta) * g.size)
        group_changes = group_changes[:3]

    # 第一感
    instinct = max(cands, key=lambda d: d.get("prior", 0.0))
    instinct_vs_played, instinct_phrase = None, ""
    if instinct["move"] != gtp:
        played_score = sg * played_info["scoreLead"] if played_info else score_after
        if instinct.get("visits", 0) >= 2:
            instinct_vs_played = round(sg * instinct["scoreLead"] - played_score, 1)
        instinct_phrase = analyze_move(board_before.copy(), player, gtp_to_coord(instinct["move"], size)).phrase()

    reply = sorted(after.get("moveInfos", []), key=lambda d: d["order"])
    reply_pv = reply[0]["pv"][:pv_len] if reply else []
    opp = "W" if player == "B" else "B"
    reply_steps = describe_sequence(board, reply_pv, opp)
    return MoveFacts(
        move_number=move_index + 1,
        player=player,
        move=gtp,
        move_desc=describe_point(gtp_to_coord(gtp, size), size),
        phase=_phase(move_index + 1, len(stones_before), size),
        score_before=round(score_before, 1),
        score_after=round(score_after, 1),
        winrate_before=round(wr_before, 3),
        winrate_after=round(wr_after, 3),
        points_lost=round(points_lost, 1),
        winrate_lost=round(wr_before - wr_after, 3),
        verdict=verdict_of(points_lost),
        is_best=is_best,
        played_rank=played_rank,
        played_prior=None if played_prior is None else round(played_prior, 4),
        best_move=best["move"],
        best_desc=describe_point(gtp_to_coord(best["move"], size), size),
        best_prior=round(best.get("prior", 0.0), 4),
        best_pv=best["pv"][:pv_len],
        best_pv_desc=_pv_desc(best["pv"][:pv_len], player, size),
        near_best_count=near_best,
        surprise=bool(is_best and played_prior is not None and played_prior < 0.05),
        territory_swings=swings,
        group_changes=group_changes,
        captured=len(captured),
        reply_pv=reply_pv,
        reply_pv_desc=_pv_desc(reply_pv, opp, size),
        score_stdev=round(ra.get("scoreStdev", 0.0), 1) if "scoreStdev" in ra else None,
        visits=rb.get("visits", 0),
        played_label=played_t.label(),
        played_phrase=played_t.phrase(),
        best_label=best_t.label(),
        best_phrase=best_t.phrase(),
        best_steps=best_steps,
        reply_steps=reply_steps,
        fate_diffs=fate_diffs,
        loss_regions=loss_regions,
        instinct_move=instinct["move"],
        instinct_prior=round(instinct.get("prior", 0.0), 4),
        instinct_vs_played=instinct_vs_played,
        instinct_phrase=instinct_phrase,
    )
