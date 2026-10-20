"""Measure accuracy on YOUR labelled emails.  CSV columns: subject,body,priority  (priority = Critical/High/Medium/Low)
Run:  python -m gai.evaluate data/my_labelled.csv      (uses Claude too if GAI_LLM=1)"""
import csv, sys
from sklearn.metrics import classification_report, accuracy_score
from . import ai, model as M

def main(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    y = [r["priority"].strip() for r in rows]
    p = [ai.classify(r["subject"], r["body"], model_dir="models")["priority"] for r in rows]
    print("Emails:", len(rows), " Accuracy: %.1f%%" % (100 * accuracy_score(y, p)))
    print(classification_report(y, p, labels=M.PRI, zero_division=0))
    miss = sum(1 for a, b in zip(y, p) if a == "Critical" and b != "Critical")
    print("Critical emails MISSED (not rated Critical):", miss, "of", y.count("Critical"))
if __name__ == "__main__": main(sys.argv[1])
