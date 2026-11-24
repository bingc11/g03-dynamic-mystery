"""Print three synthetic, reproducible rule traces. Never reads a player's session."""
from dataclasses import asdict
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from npc_actions import CENSOR, MANUSCRIPT, PRINCESS, WITNESS, Investigation

for recipient in (None, WITNESS, PRINCESS):
    game = Investigation()
    if recipient:
        game.apply(0, "show", recipient, MANUSCRIPT)
    reply = game.apply(game.version, "ask", CENSOR, "registry")
    print(json.dumps({"shown_to": recipient, "driver": "offline", "player_reply": reply["reply"],
                      "events": [asdict(e) for e in game.events]}, ensure_ascii=False))
