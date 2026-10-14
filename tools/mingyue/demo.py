"""不启动 KaTrain，直接用录好的 KataGo 输出跑讲解层。

用法（在仓库根目录）：
  python tools/mingyue/demo.py tools/mingyue/g4_moves.json tests/data/g4_katago_analysis.jsonl --from 77 --to 80 --names AlphaGo 李世石
加 --show-prompt 打印 LLM 提示词，加 --llm 调用 Claude（需要 anthropic 包和 API key）。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from katrain.core.explain import extract_move_facts, render_mingyue
from katrain.core.explain.llm import build_messages, explain_with_claude

ap = argparse.ArgumentParser()
ap.add_argument("moves")
ap.add_argument("analysis")
ap.add_argument("--from", dest="start", type=int, default=1)
ap.add_argument("--to", dest="end", type=int, default=10**9)
ap.add_argument("--llm", action="store_true")
ap.add_argument("--show-prompt", action="store_true")
ap.add_argument("--facts", action="store_true")
ap.add_argument("--names", nargs=2, default=["黑棋", "白棋"])
ap.add_argument("--tenuki", help="脱先分析的 jsonl（id 为 tenuki<落子前手数>）")
args = ap.parse_args()

moves = json.load(open(args.moves))["moves"]
by_turn = {}
for line in open(args.analysis, encoding="utf-8"):
    if line.startswith("{"):
        d = json.loads(line)
        if "rootInfo" in d and not d.get("isDuringSearch") and not d.get("id", "").startswith("tenuki"):
            by_turn[d["turnNumber"]] = d

tenuki = {}
if args.tenuki:
    for line in open(args.tenuki, encoding="utf-8"):
        if line.startswith("{"):
            d = json.loads(line)
            if d.get("id", "").startswith("tenuki") and "rootInfo" in d:
                tenuki[int(d["id"][6:])] = d

for n in range(max(args.start, 1), min(args.end, len(moves)) + 1):
    t = n - 1
    if t not in by_turn or t + 1 not in by_turn:
        continue
    f = extract_move_facts(moves, t, by_turn[t], by_turn[t + 1], tenuki=tenuki.get(t))
    print("=" * 60)
    if args.facts:
        print(json.dumps(f.to_dict(), ensure_ascii=False))
    print(render_mingyue(f, *args.names))
    if args.show_prompt:
        system, messages = build_messages(f, *args.names)
        print("--- system ---\n" + system + "\n--- user ---\n" + messages[0]["content"])
    if args.llm:
        print("--- LLM 版 ---\n" + (explain_with_claude(f, *args.names) or "（LLM 调用失败，已回退到模板版）"))
