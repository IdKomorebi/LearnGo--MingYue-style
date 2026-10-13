"""从 SGF 主线生成 KataGo analysis 查询，并把着手存成 moves.json。

用法：python mkquery.py game.sgf 74,75,76 60 > query.json
      katago analysis -config cfg -model model < query.json > analysis.jsonl
"""

import json
import sys

from pysgf import GoGame

root = GoGame.parse_file(sys.argv[1])
moves, node = [], root
while node.children:
    node = node.children[0]
    if node.move:
        moves.append([node.move.player, node.move.gtp()])
turns = [int(t) for t in sys.argv[2].split(",")]
json.dump({"moves": moves}, open("moves.json", "w"))
query = {
    "id": "game",
    "moves": moves,
    "rules": "chinese",
    "komi": float(root.get_property("KM", 7.5)),
    "boardXSize": 19,
    "boardYSize": 19,
    "analyzeTurns": turns,
    "maxVisits": int(sys.argv[3]),
    "includeOwnership": True,
    "includePolicy": True,
}
print(json.dumps(query))
