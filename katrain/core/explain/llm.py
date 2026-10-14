"""LLM 版讲解：把 MoveFacts 交给 Claude，按明玥风格改写成口语讲解。

原则：LLM 只负责“怎么说”，不负责“说什么”。所有坐标、数字、变化都必须来自 facts，
提示词里明确禁止它自己推演变化，以免讲出 KataGo 没算过的棋。
"""

import json
from typing import Optional

from katrain.core.explain.facts import MoveFacts
from katrain.core.explain.style_mingyue import render_mingyue

SYSTEM_PROMPT = """你是一位围棋讲解员，口吻参考 B 站 UP 主“明玥谈棋”（业余五段）：口语、有节奏、敢下判断，
把对局双方当角色来讲（他想干什么、为什么这么下），让 AI 当裁判揭晓答案。

但最重要的是：每一句话都必须带具体的棋盘信息。听众要的是“哪块棋、为什么、正解变化在干什么”，不是感叹。

写法：
1. 第一句就是结论：这手是什么动作（facts.played_label / played_phrase），好还是坏，亏多少目。
   可以写得有冲击力，但必须扣住这手的具体动作，比如“一挖，把黑棋拦腰挖断”，不要泛泛的“神来之笔”。
2. 讲这手在局部干了什么（played_phrase、group_changes），下完哪块棋的死活变了；
   tenuki_local 为 true 时讲清“这手为什么要下”：不下的话对方马上下 tenuki_reply 会怎样（tenuki_phrase、tenuki_fates）。
   tenuki_value 含先手价值，不要把它说成这手棋值几目。
3. 不是首选时，讲 AI 首选干了什么（best_phrase），并把 best_steps 里的变化讲成故事：每一步是打吃、长出还是切断，
   最后谁吃了亏。
4. 讲差在哪里：fate_diffs（同一块棋两种下法之后的状态）和 loss_regions（哪片地差了几目）。这是全段的重点。
5. 讲对手接下来最好的手段（reply_steps 第一步干什么）。
6. 胜率、目差最多一句带过。

硬性规则：
1. 只能使用 <facts> 里给出的坐标、数字、变化和局部动作。不要自己推演新的变化，不要编造死活。
2. 坐标用 GTP 坐标（如 L11），可以加位置（如“中腹 L11”）。
3. 禁止空话套话：不要写“本手就是最强的手”“细节决定胜负”“围棋就是这么残酷”“这就是高手”“会算的人才配得上”
   这类放在任何一手棋都成立的句子。一句话如果换到别的棋里也成立，就删掉。
4. 120~250 字，分 2~4 小段，不要用列表符号，不要小标题。
5. visits < 100 时，结尾用半句话提醒“AI 算得比较浅”。"""


def llm_facts(f: MoveFacts) -> dict:
    """给 LLM 的精简版事实：去掉只有坐标、没有含义的字段，减少噪音。"""
    d = f.to_dict()
    for k in ("best_pv", "best_pv_desc", "reply_pv", "reply_pv_desc", "territory_swings"):
        d.pop(k, None)
    for g in d.get("group_changes", []) + d.get("fate_diffs", []):
        g.pop("stones", None)
    return d


def build_messages(f: MoveFacts, black_name: str = "黑棋", white_name: str = "白棋", level: str = "业余 5 级~1 段"):
    draft = render_mingyue(f, black_name, white_name)
    user = (
        f"对局：黑 {black_name} vs 白 {white_name}。听众水平：{level}。\n"
        f"<facts>\n{json.dumps(llm_facts(f), ensure_ascii=False, indent=1)}\n</facts>\n"
        f"<template_draft>\n{draft}\n</template_draft>\n"
        "template_draft 是按事实生成的干巴巴的草稿，信息是对的。请把它改写成明玥式的口语讲解："
        "保留所有具体信息（哪块棋、哪一步、差几目），把变化讲成有因果的故事，不要加空话。"
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
