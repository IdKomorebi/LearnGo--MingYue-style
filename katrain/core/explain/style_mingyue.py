"""规则模板版讲解。离线、零延迟、不会胡编，也是 LLM 版的草稿和兜底。

v0.3 起的原则：每一句都要带具体的棋盘信息（哪块棋、哪个点、局部发生了什么），
没有内容就不说。固定的标题库和收尾金句已经删掉，明玥式的口吻交给 LLM 版去做。

讲解顺序：
  1. 一句话结论：这手是什么动作，AI 怎么评价，亏多少；
  2. 这手在局部干了什么（打吃/切断/连接/棋形），下完哪块棋的死活变了；
  3. AI 首选干了什么，正解变化每一步的意思；
  4. 差在哪里：两种下法之后，哪块棋的命运不同、哪片地差了几目；
  5. 对手接下来最好的手段；
  6. 形势数字放最后，一行带过。
"""

from typing import List

from katrain.core.explain.facts import MoveFacts
from katrain.core.explain.tactics import sequence_text

COLOR = {"B": "黑", "W": "白"}


def winrate_phrase(wr: float) -> str:
    if wr >= 0.95:
        return "基本胜定"
    if wr >= 0.8:
        return "大优"
    if wr >= 0.62:
        return "明显好下"
    if wr >= 0.55:
        return "稍好"
    if wr > 0.45:
        return "五五开"
    if wr > 0.38:
        return "稍苦"
    if wr > 0.2:
        return "明显落后"
    if wr > 0.05:
        return "大势已去"
    return "几乎没机会"


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _signed(x: float) -> str:
    return f"{x:+.1f}"


def _headline(f: MoveFacts) -> str:
    label = f" {f.played_label}" if f.played_label else ""
    head = f"【第 {f.move_number} 手 {COLOR[f.player]}{f.move}{label}】"
    if f.surprise and f.played_prior is not None:
        return head + f"好棋，而且 AI 的第一感只给它 {_pct(f.played_prior)}，是算出来的一手"
    if f.move == f.best_move:
        return head + "正是 AI 的首选"
    if f.is_best or f.points_lost < 0.5:
        diff = "目数上几乎一样" if f.points_lost < 0.1 else f"只差 {f.points_lost:.1f} 目"
        return head + f"和 AI 首选 {f.best_move} 差不多，{diff}"
    return head + f"{f.verdict}，比 AI 首选 {f.best_move} 亏约 {f.points_lost:.1f} 目"


def render_mingyue(f: MoveFacts, black_name: str = "黑棋", white_name: str = "白棋") -> str:
    name = black_name if f.player == "B" else white_name
    who = COLOR[f.player] if name in ("黑棋", "白棋", "") else f"{name}（{COLOR[f.player]}）"
    opp = "W" if f.player == "B" else "B"
    lines: List[str] = [_headline(f)]

    # 2. 这手干了什么
    what = f.played_phrase or "没有直接接触对方棋子"
    lines.append(f"{who}下在{f.move_desc}{f.move}：{what}。")
    if f.surprise and f.instinct_move and f.instinct_move != f.move:
        alt = f"（{f.instinct_phrase}）" if f.instinct_phrase else ""
        worse = (
            f"，但那样比实战差 {f.instinct_vs_played * -1:.1f} 目"
            if f.instinct_vs_played is not None and f.instinct_vs_played <= -0.5
            else ""
        )
        lines.append(f"AI 的第一感其实是{f.instinct_move}{alt}，概率 {_pct(f.instinct_prior)}{worse}。")
    for g in f.group_changes[:2]:
        if g.before != g.after:
            lines.append(f"下完之后，{g.name}从“{g.before}”变成了“{g.after}”。")

    # 3. AI 首选
    if not f.is_best:
        does = f"：{f.best_phrase}" if f.best_phrase else ""
        lines.append(f"AI 首选是{f.best_desc}{f.best_move}{does}。")
        if len(f.best_steps) >= 2:
            lines.append(f"AI 的变化：{sequence_text(f.best_steps)}。")

    # 4. 差在哪里
    for d in f.fate_diffs:
        if d.actual == d.best:
            change = "安全程度明显不同"
            lines.append(f"差距落在{d.name}：两种下法之后它{change}。")
        else:
            lines.append(f"差距落在{d.name}：按 AI 首选它是“{d.best}”，实战下完是“{d.actual}”。")
    if f.loss_regions and not f.is_best:
        r = f.loss_regions[0]
        if r["points"] > 0:
            lines.append(f"按地盘算，差距主要在{r['region']}，约 {r['points']:.0f} 目。")
    if not f.fate_diffs and not f.loss_regions:
        gains = [s for s in f.territory_swings if abs(s["points"]) >= 3]
        if gains:
            s = gains[0]
            lines.append(
                f"这手下完，{s['region']}一带{COLOR[f.player]}方{'多了' if s['points'] > 0 else '少了'}约 {abs(s['points']):.0f} 目。"
            )

    # 5. 对手接下来
    if f.reply_steps:
        first = f.reply_steps[0]
        does = f"，{first['phrase']}" if first["phrase"] else ""
        lines.append(f"轮到{COLOR[opp]}，AI 认为最好下{first['move']}{does}。")
        if len(f.reply_steps) >= 3:
            lines.append(f"后续大致是：{sequence_text(f.reply_steps[:5])}。")

    # 6. 形势
    lines.append(
        f"形势：{COLOR[f.player]}方胜率 {_pct(f.winrate_before)} → {_pct(f.winrate_after)}（{winrate_phrase(f.winrate_after)}），"
        f"目差 {_signed(f.score_before)} → {_signed(f.score_after)}。"
    )
    if f.visits < 100:
        lines.append(f"（AI 只算了 {f.visits} 步，以上结论偏浅。）")
    return "\n".join(lines)
