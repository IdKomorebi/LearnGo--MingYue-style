from katrain.core.explain.board import Board, gtp_to_coord, ownership_index
from katrain.core.explain.facts import extract_move_facts, verdict_of
from katrain.core.explain.geometry import describe_point
from katrain.core.explain.style_mingyue import render_mingyue


def test_capture():
    b = Board(19)
    for p, m in [("B", "A2"), ("W", "A1"), ("B", "B1")]:
        cap = b.play(p, gtp_to_coord(m))
    assert cap == [(0, 0)]


def test_ownership_index_top_left_first():
    assert ownership_index(gtp_to_coord("A19")) == 0
    assert ownership_index(gtp_to_coord("T1")) == 360


def test_describe():
    assert describe_point(gtp_to_coord("Q16")) == "右上角星位"
    assert describe_point(gtp_to_coord("C3")) == "左下角三三"
    assert describe_point(gtp_to_coord("K10")) == "中腹"


def test_verdict():
    assert verdict_of(0.1) == "好棋" and verdict_of(7) == "恶手" and verdict_of(20) == "败着"


def _an(score, wr, cands, own=0.0):
    return {
        "rootInfo": {"scoreLead": score, "winrate": wr, "visits": 200},
        "moveInfos": [
            {"move": m, "order": i, "scoreLead": s, "visits": 50, "prior": 0.2, "pv": [m, "D4"]}
            for i, (m, s) in enumerate(cands)
        ],
        "ownership": [own] * 361,
        "policy": [0.01] * 362,
    }


def test_blunder_story():
    moves = [["B", "Q16"], ["W", "D4"], ["B", "A1"]]
    before = _an(1.0, 0.6, [("Q4", 1.0), ("C16", 0.8)])
    after = _an(-9.0, 0.2, [("R4", -9.0)])
    f = extract_move_facts(moves, 2, before, after)
    assert f.points_lost == 10.0 and f.verdict == "恶手" and not f.is_best and f.played_rank is None
    text = render_mingyue(f)
    assert "Q4" in text and "第 3 手" in text
