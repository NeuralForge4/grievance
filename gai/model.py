import os, json, joblib, numpy as np
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score, f1_score
from sklearn.base import BaseEstimator, TransformerMixin
from . import rules, data

PRI = ["Critical", "High", "Medium", "Low"]
WEIGHT = {"Critical": 90, "High": 63, "Medium": 38, "Low": 10}
DEPT = {c[0]: c[1] for c in rules.CATS}; DEPT["Spam / Irrelevant"] = "Auto-archive"
_cache = {}

CATL = [c[0] for c in rules.CATS] + ["Spam / Irrelevant", "General"]

class RuleFeats(BaseEstimator, TransformerMixin):
    """Turns the transparent rule signals into numeric features so the model can learn how much to trust each one."""
    def fit(self, X, y=None): return self
    def transform(self, X):
        out = []
        for t in X:
            r = rules.analyze(t, ""); low = t.lower()
            v = [0.0] * len(CATL); v[CATL.index(r["category"])] = 1.0
            out.append(v + [r["score"] / 100, float(r["life_risk"]), float(bool(rules._hits(low, rules.URG))),
                            float(bool(rules._hits(low, rules.VUL))), float(bool(rules._hits(low, rules.REP))),
                            float(bool(rules._hits(low, rules.LOW))), float(r["spam"])])
        return np.array(out)
    def get_feature_names_out(self, *a): return np.array(["rule_" + str(i) for i in range(len(CATL) + 7)])

def _pipe():
    feats = FeatureUnion([("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2)),
                          ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)),
                          ("rules", RuleFeats())], transformer_weights={"rules": 4.0})
    return Pipeline([("f", feats), ("lr", LogisticRegression(max_iter=3000, C=8, class_weight="balanced"))])

def _txt(r): return r["subject"] + ". " + r["body"]

def combine(ml_pri, rule, sender):
    """Hybrid decision: ML prediction + safety floors from the rule engine."""
    p = ml_pri
    if rule["spam"]: return "Low"
    if rule["life_risk"] and rules.RANK[p] > rules.RANK["High"]: p = "High"
    if sender == "court" and rules.RANK[p] > 1: p = "High"
    if sender in ("elected", "media") and rules.RANK[p] > 2: p = "Medium"
    return p

def train(model_dir, folds=5, extra=None):
    """Grouped cross-validation: every template is tested exactly once by a model that never saw ANY email of that template."""
    from sklearn.model_selection import GroupKFold
    os.makedirs(model_dir, exist_ok=True)
    rows = data.build() + [dict(e, tid=1000 + k) for k, e in enumerate(extra or []) for _ in range(3)]; X = [_txt(r) for r in rows]; g = [r["tid"] for r in rows]
    yp = np.array([r["priority"] for r in rows]); yc = np.array([r["category"] for r in rows])
    mlp = np.empty(len(rows), dtype=object); cp = np.empty(len(rows), dtype=object)
    for tri, tei in GroupKFold(n_splits=folds).split(X, yp, g):
        xt = [X[i] for i in tri]; xe = [X[i] for i in tei]
        mlp[tei] = _pipe().fit(xt, yp[tri]).predict(xe); cp[tei] = _pipe().fit(xt, yc[tri]).predict(xe)
    ra = [rules.analyze(r["subject"], r["body"]) for r in rows]
    rp = np.array([a["priority"] for a in ra]); hp = np.array([combine(p, a, "citizen") for p, a in zip(mlp, ra)])
    rep = lambda p: classification_report(yp, p, labels=PRI, output_dict=True, zero_division=0)
    summ = lambda p: dict(accuracy=round(accuracy_score(yp, p), 3), macro_f1=round(f1_score(yp, p, average="macro", labels=PRI), 3),
                          critical_recall=round(rep(p)["Critical"]["recall"], 3), critical_precision=round(rep(p)["Critical"]["precision"], 3))
    m = dict(method="%d-fold grouped cross-validation by email template (every test email uses a phrasing the model never saw)" % folds,
             samples=len(rows), templates=len(data.T), real_samples=len(extra or []), rules_only=summ(rp), ml_only=summ(mlp), hybrid=summ(hp),
             category_accuracy=round(accuracy_score(yc, cp), 3),
             per_class_hybrid={k: {a: round(b, 3) for a, b in v.items()} for k, v in rep(hp).items() if k in PRI},
             caveat="Measured on SYNTHETIC emails generated from 50 templates. Real-world accuracy must be measured on real, anonymised grievance emails before deployment.")
    json.dump(m, open(os.path.join(model_dir, "metrics.json"), "w"), indent=2, ensure_ascii=False)
    joblib.dump(dict(pri=_pipe().fit(X, yp), cat=_pipe().fit(X, yc)), os.path.join(model_dir, "model.joblib"))
    _cache.pop(model_dir, None)
    return m

def load(model_dir):
    if model_dir not in _cache:
        f = os.path.join(model_dir, "model.joblib")
        try: _cache[model_dir] = joblib.load(f)
        except Exception: train(model_dir); _cache[model_dir] = joblib.load(f)   # missing or built with another scikit-learn version
    return _cache[model_dir]

def predict(subject, body, sender="citizen", model_dir="models"):
    M = load(model_dir); text = subject + ". " + body
    pp = M["pri"]; pr = pp.predict_proba([text])[0]; cls = list(pp.classes_)
    ml = cls[int(np.argmax(pr))]; conf = float(pr.max())
    cat = M["cat"].predict([text])[0]
    rule = rules.analyze(subject, body, sender)
    final = combine(ml, rule, sender)
    score = int(round(sum(p * WEIGHT[c] for p, c in zip(pr, cls))))
    if final != ml: score = max(score, {"Critical": 75, "High": 50, "Medium": 30, "Low": 0}[final])
    why = []
    try:
        f, lr = pp.named_steps["f"], pp.named_steps["lr"]; x = f.transform([text]); names = f.get_feature_names_out()
        contrib = x.multiply(lr.coef_[cls.index(ml)]).toarray()[0]
        top = [names[i][6:] for i in np.argsort(-contrib)[:15] if names[i].startswith("word__") and contrib[i] > 0][:3]
        if top: why.append("Model key terms: " + ", ".join(top))
    except Exception: pass
    why.append("Model confidence %d%% for %s" % (round(conf * 100), ml))
    if final != ml: why.append("Rule safety net changed priority from %s to %s" % (ml, final))
    why += [r for r in rule["reasons"] if not r.startswith("Matches")]
    if rule["spam"]: cat, why = "Spam / Irrelevant", ["Matches spam patterns"]
    depts = list(dict.fromkeys([DEPT.get(cat, "General Administration")] + rule["depts"]))
    return dict(priority=final, score=min(100, score), category=cat, dept=depts[0], depts=depts, reasons=why,
                confidence=round(conf, 3), needs_review=conf < .55)

if __name__ == "__main__":      # python -m gai.model [model_dir]  (re-import so the pickle references gai.model, not __main__)
    import sys, pprint
    from gai import model as _m
    pprint.pprint(_m.train(sys.argv[1] if len(sys.argv) > 1 else "models"))
