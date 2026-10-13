"""KaTrain 里的讲解服务：模板版同步出，LLM 版后台线程生成并缓存在节点上。"""

import threading

from katrain.core.explain.adapters import facts_from_game_node
from katrain.core.explain.llm import explain_with_claude
from katrain.core.explain.style_mingyue import render_mingyue


class ExplainService:
    def __init__(self, katrain):
        self.katrain = katrain
        self.pending = set()

    def _names(self, node):
        root = node.root
        return root.get_property("PB", "黑棋"), root.get_property("PW", "白棋")

    def explain(self, node) -> str:
        if not self.katrain.config("explain/enabled", True):
            return ""
        if not (node.analysis_complete and node.parent and node.parent.analysis_complete):
            return ""
        cached = getattr(node, "explanation_llm", None)
        if cached:
            return cached
        facts = facts_from_game_node(node)
        if facts is None:
            return ""
        names = self._names(node)
        if self.katrain.config("explain/llm", False) and id(node) not in self.pending:
            self.pending.add(id(node))
            threading.Thread(target=self._llm, args=(node, facts, names), daemon=True).start()
        return render_mingyue(facts, *names)

    def _llm(self, node, facts, names):
        text = explain_with_claude(facts, *names, model=self.katrain.config("explain/model", "claude-opus-5-5"))
        if text:
            node.explanation_llm = text
            self.katrain.update_state()
