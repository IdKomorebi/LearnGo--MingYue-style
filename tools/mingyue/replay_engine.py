"""假引擎：按局面手数回放录好的 KataGo 输出，用于在没有 GPU 的环境里跑 KaTrain 界面和截图。

用法：在 KaTrain 配置的 engine/altcommand 里写
  python3 tools/mingyue/replay_engine.py tests/data/g4_katago_analysis.jsonl
"""

import json
import sys

data = {}
for line in open(sys.argv[1], encoding="utf-8"):
    if line.startswith("{"):
        d = json.loads(line)
        data[d["turnNumber"]] = d
sys.stderr.write("replay engine ready\n")
sys.stderr.flush()

for line in sys.stdin:
    query = json.loads(line)
    if query.get("action") == "terminate":
        reply = {"id": query["id"], "action": "terminate", "terminateId": query.get("terminateId")}
        print(json.dumps(reply), flush=True)
        continue
    turn = len(query.get("moves", []))
    src = data.get(turn) or data[min(data, key=lambda t: abs(t - turn))]
    out = {**src, "id": query["id"], "turnNumber": turn, "isDuringSearch": False}
    if turn not in data:  # 不是录好的局面：只留一个候选点，避免讲解层讲出离谱的内容
        out["moveInfos"] = src["moveInfos"][:1]
    print(json.dumps(out), flush=True)
