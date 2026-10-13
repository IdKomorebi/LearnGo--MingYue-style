from katrain.core.explain.board import Board, gtp_to_coord, ownership_index
from katrain.core.explain.facts import extract_move_facts
from katrain.core.explain.style_mingyue import render_mingyue
from katrain.core.explain.tactics import analyze_move, describe_sequence, sequence_text


def _board(moves):
    b = Board(19)
    for p, m in moves:
        b.play(p, gtp_to_coord(m))
    return b


def test_atari_and_capture():
    b = _board([("B", "D4"), ("W", "D5"), ("B", "C5"), ("W", "Q16"), ("B", "E5")])
    t = analyze_move(b, "B", gtp_to_coord("D7"))
    assert t.label() != "打吃"  # 不相邻，不算打吃
    b = _board([("B", "D4"), ("W", "D5"), ("B", "C5"), ("W", "Q16"), ("B", "E5")])
    t = analyze_move(b, "B", gtp_to_coord("D6"))
    assert t.captured == ["D5"] and t.label() == "提"
    b = _board([("B", "D4"), ("W", "D5"), ("B", "C5")])
    t = analyze_move(b, "B", gtp_to_coord("E5"))
    assert t.label() == "打吃" and t.atari[0].name() == "白D5一子"


def test_rescue_connect_and_self_atari():
    b = _board([("B", "D4"), ("W", "D5"), ("B", "C5"), ("W", "Q16"), ("B", "E5")])
    t = analyze_move(b, "W", gtp_to_coord("D6"))
    assert t.label() == "长出" and "长出来" in t.phrase()
    b = _board([("B", "C3"), ("B", "E3")])
    t = analyze_move(b, "B", gtp_to_coord("D3"))
    assert t.label() == "连接" and t.connected.size == 3


def test_wedge_and_cut():
    # 黑 K11、M11 中间挖 L11
    b = _board([("B", "K11"), ("B", "M11")])
    t = analyze_move(b, "W", gtp_to_coord("L11"))
    assert t.shape == "挖" and t.label() == "挖" and "挖进" in t.phrase()
    # 斜着的两颗白子之间是断点
    b = _board([("W", "D4"), ("W", "E5"), ("B", "D6")])
    t = analyze_move(b, "B", gtp_to_coord("E4"))
    assert len(t.cut) == 2


def test_sequence_text():
    b = _board([("B", "D4"), ("W", "D5"), ("B", "C5")])
    steps = describe_sequence(b, ["E5", "D6"], "B")
    assert sequence_text(steps) == "黑E5打吃 → 白D6长出"
    assert len(b.stones) == 3  # 不修改传入的棋盘


def _an(score, cands, own_by_move=None, own=None):
    own = own if own is not None else [0.0] * 361
    infos = []
    for i, (m, s, prior) in enumerate(cands):
        d = {"move": m, "order": i, "scoreLead": s, "visits": 50, "prior": prior, "pv": [m]}
        if own_by_move and m in own_by_move:
            d["ownership"] = own_by_move[m]
        infos.append(d)
    return {
        "rootInfo": {"scoreLead": score, "winrate": 0.5 + score / 100, "visits": 500},
        "moveInfos": infos,
        "ownership": own,
        "policy": [0.01] * 362,
    }


def test_where_the_loss_is():
    """首选能吃住白棋，实战让它活了：讲解要指出是哪块棋。"""
    moves = [["W", "D4"], ["W", "D5"], ["B", "C5"], ["B", "C4"], ["B", "D3"], ["B", "E4"], ["B", "Q16"]]
    white = [gtp_to_coord(m) for m in ("D4", "D5")]
    own_best, own_played = [0.0] * 361, [0.0] * 361
    for c in white:
        own_best[ownership_index(c)] = 0.9  # 黑方视角 +：白子被吃
        own_played[ownership_index(c)] = -0.9  # 白活
    before = _an(0.0, [("E5", 5.0, 0.3), ("Q16", -3.0, 0.4)], {"E5": own_best, "Q16": own_played})
    after = _an(-3.0, [("E5", -3.0, 0.5)], own=own_played)
    f = extract_move_facts(moves, 6, before, after)
    assert f.best_move == "E5" and f.best_label == "打吃"
    assert f.fate_diffs and f.fate_diffs[0].color == "W" and f.fate_diffs[0].best == "已死"
    text = render_mingyue(f)
    assert "白D" in text and "已死" in text
    for filler in ("本手", "这就是高手", "围棋就是这么残酷", "细节就是胜负"):
        assert filler not in text
