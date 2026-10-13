"""规则模板版“明玥式”讲解。离线、零延迟、不会胡编，作为 LLM 版的兜底和草稿。

风格要素（来自明玥谈棋公开视频标题和简介的归纳，见方案文档）：
  1. 先抛一个有冲击力的“标题句”，四字短语、对仗、夸张修辞；
  2. 把棋手当角色讲：他想干什么、为什么这么下；
  3. 用 AI 当“裁判”揭晓答案，数字口语化，制造反转；
  4. 摆出正解变化，讲清楚差在哪；
  5. 用一句接地气的金句/段位梗收尾。
"""

import random
from typing import List

from katrain.core.explain.facts import MoveFacts

COLOR = {"B": "黑", "W": "白"}

TITLES = {
    "surprise": ["冷门妙手，AI 都没想到！", "神来之笔，第一感根本看不见！", "一手挖穿，石破天惊！"],
    "good": ["稳如老狗，本手本手！", "滴水不漏，AI 点头。", "这手棋，挑不出毛病。"],
    "small": ["不是最佳，但也不算错。", "差之毫厘，还在可控范围。"],
    "slack": ["有点缓了！", "温吞水一手，机会悄悄溜走。"],
    "doubt": ["这手有问题！", "疑问手出现，局面开始松动。"],
    "bad": ["恶手！形势急转直下！", "一步踏空，满盘皆惊！"],
    "blunder": ["败着！AI 看了都得吐血！", "一手崩盘，大龙说没就没！", "史诗级翻车现场！"],
}
VERDICT_KEY = {"好棋": "good", "小亏": "small", "缓手": "slack", "疑问手": "doubt", "恶手": "bad", "败着": "blunder"}

CLOSERS = {
    "surprise": ["这种棋，第一感是看不到的，得算。会算的人，才配得上这一手。", "看懂这手棋，你的棋力就上了一个台阶。"],
    "good": ["本手，就是最强的手。", "朴素，但是正确，这就是高手。"],
    "small": ["这点差别，业余比赛里根本不算事，但高手对局里，细节就是胜负。"],
    "slack": ["缓一手，对手就多一口气。下棋，最怕温吞。"],
    "doubt": ["这里多想十秒，局面就完全不一样。"],
    "bad": ["形势判断错了，后面怎么算都是白算。"],
    "blunder": ["一着不慎，满盘皆输，围棋就是这么残酷。"],
}


def winrate_phrase(wr: float) -> str:
    if wr >= 0.95:
        return "基本锁定胜局"
    if wr >= 0.8:
        return "大优"
    if wr >= 0.62:
        return "明显好下"
    if wr >= 0.55:
        return "稍好"
    if wr > 0.45:
        return "五五开，难解难分"
    if wr > 0.38:
        return "稍苦"
    if wr > 0.2:
        return "明显落后"
    if wr > 0.05:
        return "大势已去"
    return "几乎没机会了"


def points_phrase(p: float) -> str:
    p = abs(p)
    if p < 1:
        return "不到一目"
    if p < 3:
        return f"{p:.0f} 目左右的小账"
    if p < 8:
        return f"{p:.0f} 目，差不多一个贴目"
    if p < 15:
        return f"{p:.0f} 目，相当于一个大场"
    return f"{p:.0f} 目，等于一整块棋"


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_mingyue(f: MoveFacts, black_name: str = "黑棋", white_name: str = "白棋") -> str:
    rng = random.Random(f.move_number)  # 同一手每次讲法一样，方便测试
    who = black_name if f.player == "B" else white_name
    key = "surprise" if f.surprise else VERDICT_KEY[f.verdict]
    if key == "good" and not f.is_best:
        key = "small"  # 目数没亏多少，但不是 AI 的选择，标题别夸
    lines: List[str] = [f"【第 {f.move_number} 手】{rng.choice(TITLES[key])}"]

    # 1. 角色视角：他下了哪儿
    lines.append(
        f"{who}（{COLOR[f.player]}）这手下在{f.move_desc}（{f.move}）。"
        + (f"一口气提掉 {f.captured} 子！" if f.captured else "")
    )

    # 2. AI 当裁判
    swing = f.winrate_after - f.winrate_before
    lines.append(
        f"AI 怎么看？落子前{COLOR[f.player]}方胜率 {_pct(f.winrate_before)}（{winrate_phrase(f.winrate_before)}），"
        f"下完 {_pct(f.winrate_after)}（{winrate_phrase(f.winrate_after)}）"
        + ("。" if abs(swing) < 0.03 else f"，一手棋{'涨' if swing > 0 else '掉'}了 {abs(swing) * 100:.0f} 个百分点！")
    )
    if f.points_lost >= 0.5:
        lines.append(f"按目数算，这手亏了 {points_phrase(f.points_lost)}。")

    if f.surprise and f.played_prior is not None:
        lines.append(f"最妙的是：AI 的第一感只给这手 {_pct(f.played_prior)} 的概率，是靠算出来的，不是看出来的。")

    # 3. 正解与区别
    if not f.is_best:
        rank = f"AI 候选里排第 {f.played_rank}" if f.played_rank else "AI 候选里根本没有这手"
        lines.append(
            f"{rank}。AI 想下的是{f.best_desc}（{f.best_move}），后续大致是：{' → '.join(f.best_pv_desc[:5])}。"
        )
    elif f.visits < 200:
        pass  # 算得太浅，“唯一的一手 / 哪里都行”这种判断不可靠，干脆不说
    elif f.near_best_count >= 4 and not f.surprise:
        lines.append(f"这里其实有 {f.near_best_count} 个点价值差不多，属于“哪里都行”的局面，选这手没毛病。")
    elif f.near_best_count <= 1 and f.is_best:
        lines.append("而且这几乎是唯一的一手，别的下法都要明显吃亏。")

    # 4. 棋理：哪块棋、哪片地变了
    for g in f.group_changes[:2]:
        side = "自己" if g.color == f.player else "对方"
        lines.append(
            f"关键在{g.region}那块{COLOR[g.color]}棋（{side}的，{g.size} 子）：从“{g.before}”变成了“{g.after}”。"
        )
    gains = [s for s in f.territory_swings if abs(s["points"]) >= 3]
    if gains and not f.group_changes:
        s = gains[0]
        lines.append(
            f"地盘上，{s['region']}一带{'多出' if s['points'] > 0 else '丢掉'}了大约 {abs(s['points']):.0f} 目。"
        )

    if f.reply_pv_desc and not f.is_best:
        lines.append(f"对手的最佳应对：{' → '.join(f.reply_pv_desc[:4])}。")

    # 5. 收尾金句
    lines.append(rng.choice(CLOSERS[key]))
    if f.visits < 100:
        lines.append(f"（AI 这次只算了 {f.visits} 步，判断比较浅，仅供参考。）")
    return "\n".join(lines)
