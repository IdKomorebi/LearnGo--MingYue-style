"""理解 KataGo：把引擎输出翻译成“人话”的讲解层。

不依赖 Kivy，可以单独测试；在 KaTrain 里通过 adapters.from_game_node 接入。
"""

from katrain.core.explain.facts import MoveFacts, extract_move_facts
from katrain.core.explain.style_mingyue import render_mingyue

__all__ = ["MoveFacts", "extract_move_facts", "render_mingyue"]
