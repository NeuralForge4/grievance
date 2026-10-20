"""Learn from officers: retrain the local model using emails whose priority an officer corrected or confirmed.
Run:  python -m gai.retrain        (personal details are masked before training)"""
import os, sqlite3, pprint
from .app import create_app
from . import model as M, ai

def main():
    app = create_app(seed_demo=False)
    rows = sqlite3.connect(app.config["DB"]).execute("SELECT subject, body, priority, category FROM emails WHERE corrected=1").fetchall()
    extra = [dict(subject=ai.redact(s), body=ai.redact(b), priority=p, category=c) for s, b, p, c in rows]
    print("Officer-verified real emails used:", len(extra))
    pprint.pprint(M.train(app.config["MODEL_DIR"], extra=extra))
if __name__ == "__main__": main()
