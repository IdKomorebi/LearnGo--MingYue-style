"""KaTrain 里的讲解服务：模板版同步出，LLM 版后台线程生成并缓存在节点上。"""

import threading
from typing import Optional, Tuple

from katrain.core.constants import PRIORITY_EXTRA_ANALYSIS
from katrain.core.explain.adapters import facts_from_game_node
from katrain.core.explain.facts import MoveFacts
from katrain.core.explain.llm import explain_with_claude
from katrain.core.explain.style_mingyue import render_mingyue


class ExplainService:
    def __init__(self, katrain):
        self.katrain = katrain
        self.pending_llm = set()
        self.deepened = set()

    def _names(self, node):
        root = node.root
        return root.get_property("PB", "黑棋"), root.get_property("PW", "白棋")

    def explain(self, node) -> Tuple[str, Optional[MoveFacts]]:
        """返回 (讲解文字, 事实)。没有可讲的内容时返回 ("", None)。事实缓存在 node.explain_facts 供棋盘高亮。"""
        if not self.katrain.config("explain/enabled", True):
            return "", None
        if not (node.move and node.parent and node.analysis_exists and node.parent.analysis_exists):
            return "", None
        facts = facts_from_game_node(node)
        node.explain_facts = facts
        if facts is None:
            return "", None
        self._maybe_deepen(node, facts)
        cached = getattr(node, "explanation_llm", None)
        if cached and getattr(node, "explanation_llm_visits", 0) >= facts.visits:
            return cached, facts
        names = self._names(node)
        key = (id(node), facts.visits)
        if self.katrain.config("explain/llm", False) and node.parent.analysis_complete and key not in self.pending_llm:
            self.pending_llm.add(key)
            threading.Thread(target=self._llm, args=(node, facts, names), daemon=True).start()
        return render_mingyue(facts, *names), facts

    def _maybe_deepen(self, node, facts: MoveFacts):
        """关键手（疑问手及以上或妙手）算得太浅时，自动给落子前后两个局面加算。每个节点只加算一次。"""
        min_visits = self.katrain.config("explain/key_move_visits", 1000)
        engine = getattr(self.katrain, "engine", None)
        is_key = facts.surprise or facts.points_lost >= 3
        if not engine or not is_key or id(node) in self.deepened:
            return
        self.deepened.add(id(node))
        for n in (node.parent, node):
            if n.root_visits < min_visits:
                n.analyze(engine, visits=min_visits, priority=PRIORITY_EXTRA_ANALYSIS, time_limit=False)

    def _llm(self, node, facts, names):
        text = explain_with_claude(facts, *names, model=self.katrain.config("explain/model", "claude-opus-5-5"))
        if text:
            node.explanation_llm = text
            node.explanation_llm_visits = facts.visits
            self.katrain.update_state()
