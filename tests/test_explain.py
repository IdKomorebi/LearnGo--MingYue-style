import json
import os

from katrain.core.base_katrain import KaTrainBase
from katrain.core.explain import extract_move_facts, render_mingyue
from katrain.core.explain.adapters import facts_from_game_node
from katrain.core.explain.service import ExplainService
from katrain.core.game import KaTrainSGF

DATA = os.path.join(os.path.dirname(__file__), "data")


def load_game_with_analysis():
    root = KaTrainSGF.parse_file(os.path.join(DATA, "LS vs AG - G4 - English.sgf"))
    nodes = [root]
    while nodes[-1].children:
        nodes.append(nodes[-1].children[0])
    analyses = {}
    with open(os.path.join(DATA, "g4_katago_analysis.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            analyses[d["turnNumber"]] = d
    for turn, d in analyses.items():
        nodes[turn].set_analysis(d)
    moves = [[m.player, m.gtp()] for n in nodes for m in n.moves]
    return nodes, analyses, moves


def test_adapter_matches_raw_katago():
    nodes, analyses, moves = load_game_with_analysis()
    for turn in sorted(analyses):
        if turn + 1 not in analyses:
            continue
        node = nodes[turn + 1]  # 第 turn+1 手
        via_node = facts_from_game_node(node)
        raw = extract_move_facts(moves, turn, analyses[turn], analyses[turn + 1])
        assert via_node is not None
        assert via_node.move == raw.move == node.move.gtp()
        assert abs(via_node.points_lost - raw.points_lost) < 1e-6
        assert abs(via_node.points_lost - node.points_lost) < 0.06  # 和 KaTrain 自己算的一致
        assert via_node.best_move == raw.best_move


def test_service_renders_in_katrain():
    nodes, analyses, _ = load_game_with_analysis()
    katrain = KaTrainBase(force_package_config=True, debug_level=0)
    service = ExplainService(katrain)
    turn = max(t for t in analyses if t - 1 in analyses)
    text, facts = service.explain(nodes[turn])
    assert f"第 {turn} 手" in text
    assert facts is nodes[turn].explain_facts and facts.move == nodes[turn].move.gtp()
    assert all(len(g.stones) == g.size for g in facts.group_changes)
    assert render_mingyue(facts_from_game_node(nodes[turn]), "AlphaGo", "Lee Sedol") != ""


def test_key_move_gets_deeper_analysis():
    nodes, analyses, _ = load_game_with_analysis()
    katrain = KaTrainBase(force_package_config=True, debug_level=0)
    requested = []

    class FakeEngine:
        def request_analysis(self, node, callback, visits=None, **kwargs):
            requested.append((node.depth, visits))

    katrain.engine = FakeEngine()
    service = ExplainService(katrain)
    _, facts = service.explain(nodes[78])  # 78 手是妙手（AI 第一感很低），只算了 60 步
    assert facts.surprise
    assert sorted(requested) == [(77, 1000), (78, 1000)]
    service.explain(nodes[78])  # 同一节点只加算一次
    assert len(requested) == 2
