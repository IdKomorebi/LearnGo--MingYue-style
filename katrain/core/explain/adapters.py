"""把 KaTrain 的 GameNode 转成讲解层需要的输入。只在 KaTrain 进程里用。"""

from typing import Dict, Optional

from katrain.core.explain.facts import MoveFacts, extract_move_facts


def node_analysis_to_raw(node) -> Optional[Dict]:
    """GameNode.analysis（root/moves/ownership/policy）→ KataGo 原始格式。"""
    a = node.analysis
    if not a or a.get("root") is None:
        return None
    return {
        "rootInfo": a["root"],
        "moveInfos": [m for m in a["moves"].values() if m.get("order", 999) < 999],
        "ownership": a.get("ownership"),
        "policy": a.get("policy"),
    }


def facts_from_game_node(node) -> Optional[MoveFacts]:
    """讲 node 这一手（node.move），需要 node 和 node.parent 都分析完。"""
    if not node.move or not node.parent:
        return None
    before, after = node_analysis_to_raw(node.parent), node_analysis_to_raw(node)
    if before is None or after is None or not before["moveInfos"]:
        return None
    moves = [[m.player, m.gtp()] for n in node.nodes_from_root for m in n.moves]
    size = node.board_size[0]
    tenuki = getattr(node, "explain_tenuki", None)
    return extract_move_facts(moves, len(moves) - 1, before, after, size=size, tenuki=tenuki)
