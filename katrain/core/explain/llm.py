"""LLM 版讲解：把 MoveFacts 交给 Claude，按明玥风格改写成口语讲解。

原则：LLM 只负责“怎么说”，不负责“说什么”。所有坐标、数字、变化都必须来自 facts，
提示词里明确禁止它自己推演变化，以免讲出 KataGo 没算过的棋。
"""

import json
from typing import Optional

from katrain.core.explain.facts import MoveFacts
from katrain.core.explain.style_mingyue import render_mingyue

SYSTEM_PROMPT = """你是一位围棋讲解员，讲解风格参考 B 站 UP 主“明玥谈棋”（业余五段）：
- 开头一句“标题句”：四字短语、对仗、夸张修辞，像视频标题那样抓人，例如“疯狂弃子，野蛮屠龙！”；
- 把对局双方当角色来讲：他想干什么、为什么这么下、心理上怎么想；
- 让 AI 当“裁判”来揭晓答案，制造反转，但数字要说成人话（“五五开”“差不多一个贴目”“一整块棋”）；
- 讲清楚正解和实战的区别，落到具体棋理（死活、厚薄、先手后手、大小）；
- 结尾一句接地气的金句，可以带点幽默或段位梗（“劫活只能 2 级，净活才是 2 段”这种）；
- 口语化，可以有网络用语，但不低俗、不嘲讽棋手本人。

硬性规则：
1. 只能使用 <facts> 里给出的坐标、胜率、目数、变化（pv）。不要自己推演新的变化，不要编造数字。
2. 坐标同时给出中文位置和 GTP 坐标，例如“右上角星位（Q16）”。
3. facts 里没有的信息（比如棋手当时用时、心理），可以用“可能”“大概”来推测，但要明显是推测。
4. 篇幅 120~250 字，分 3~5 小段，不要用列表符号。
5. 如果 visits 很少（<100），在结尾用一句话提醒“AI 这次算得比较浅，仅供参考”。"""


def build_messages(f: MoveFacts, black_name: str = "黑棋", white_name: str = "白棋", level: str = "业余 5 级~1 段"):
    facts = f.to_dict()
    draft = render_mingyue(f, black_name, white_name)
    user = (
        f"对局：黑 {black_name} vs 白 {white_name}。听众水平：{level}。\n"
        f"<facts>\n{json.dumps(facts, ensure_ascii=False, indent=1)}\n</facts>\n"
        f"<template_draft>\n{draft}\n</template_draft>\n"
        "请在不违反硬性规则的前提下，把这手棋讲得更像明玥：更有故事感、更口语，可以重组 template_draft 的内容。"
    )
    return SYSTEM_PROMPT, [{"role": "user", "content": user}]


def explain_with_claude(
    f: MoveFacts, black_name="黑棋", white_name="白棋", model: str = "claude-opus-5-5", client=None
) -> Optional[str]:
    """需要 `pip install anthropic` 并配置 ANTHROPIC_API_KEY。失败时返回 None，调用方回退到模板。"""
    try:
        import anthropic
    except ImportError:
        return None
    client = client or anthropic.Anthropic()
    system, messages = build_messages(f, black_name, white_name)
    try:
        resp = client.beta.messages.create(
            model=model,
            max_tokens=2000,
            system=system,
            messages=messages,
            output_config={"effort": "low"},  # 讲解是短文本改写，低 effort 足够且更快
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIError:
        return None
    if resp.stop_reason == "refusal":
        return None
    return "".join(b.text for b in resp.content if b.type == "text").strip() or None
