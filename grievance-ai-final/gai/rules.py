"""Transparent keyword rules (English + Hindi). Used as a safety net and as the baseline the ML model is compared with."""
import re
CATS = [
 ("Emergency & Safety", "Disaster Mgmt / Police", 60, ["flood","fire","collapse","accident","injur","death","died","dying","emergency","violence","assault","threat","rape","kidnap","gas leak","landslide","electrocut","stampede","bomb","life at risk","trapped","आग","बाढ़","दुर्घटना","मौत","हिंसा"]),
 ("Health", "Health Department", 45, ["hospital","patient","medicine","doctor","oxygen","dengue","malaria","cholera","outbreak","epidemic","surgery","ambulance","ventilator","dispensary","अस्पताल","बीमारी","दवा"]),
 ("Water & Electricity", "Jal Nigam / Electricity Board", 35, ["no water","water supply","contaminated","drinking water","power cut","blackout","electricity","transformer","outage","sewage","पानी","बिजली"]),
 ("Corruption & Misconduct", "Vigilance Department", 45, ["bribe","corrupt","scam","fraud","embezzle","harass","misuse","kickback","fake bills","रिश्वत","भ्रष्टाचार"]),
 ("Legal / Court / RTI", "Legal Cell", 45, ["court order","high court","supreme court","contempt","rti","legal notice","tribunal","hearing","writ","आदेश","अदालत"]),
 ("Welfare & Pension", "Social Welfare", 30, ["pension","ration","scholarship","subsidy","widow","scheme","stipend","पेंशन","राशन"]),
 ("Roads & Infrastructure", "Public Works (PWD)", 25, ["pothole","road","bridge","streetlight","drain","garbage","waste","encroach","सड़क","कचरा"]),
 ("Education", "Education Department", 25, ["school","teacher","exam","college","student","admission","fees","विद्यालय","शिक्षक"]),
 ("Feedback & Suggestions", "Public Relations", 8, ["suggest","appreciate","thank","feedback","congratulat","invitation","invite","newsletter","धन्यवाद","सुझाव"]),
]
URG = ["urgent","immediately","asap","right now","at once","without delay","tonight","तुरंत","जल्दी"]
VUL = ["elderly","senior citizen","widow","disabled","child","children","pregnant","infant","orphan","वृद्ध","विकलांग","बच्चे","विधवा"]
REP = ["reminder","again","third time","no response","nobody replied","still pending","ignored"]
LOW = ["thank you","thanks","appreciate","invitation","newsletter","unsubscribe","congratulations","suggest","धन्यवाद"]
SPAM = ["lottery","click here","crypto","free gift","loan offer","buy now","limited offer","without prescription"]
SENDER_BONUS = {"elected": (12, "Sender is an elected representative"), "media": (10, "Sender is from media/press"),
                "court": (18, "Sender is a court / legal authority"), "official": (8, "Sender is a government department")}
RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

def _hits(t, arr): return [w for w in arr if w in t]

def analyze(subject, body, sender="citizen"):
    t = (subject + " " + body).lower(); why = []
    if _hits(t, SPAM):
        return dict(score=3, priority="Low", category="Spam / Irrelevant", dept="Auto-archive", depts=["Auto-archive"], reasons=["Matches spam patterns"], spam=True, life_risk=False)
    best, ds, score = None, [], 10
    for name, dept, w, kws in CATS:
        h = _hits(t, kws)
        if h:
            s = w + min(10, (len(h)-1)*4)
            if s >= 30: ds.append(dept)
            if not best or s > best[0]: best = (s, name, dept, h)
    if best:
        score += best[0]; why.append('Category "%s" keywords: %s' % (best[1], ", ".join(best[3][:4])))
    u = _hits(t, URG)
    if u: score += min(18, 8+len(u)*4); why.append("Urgency language: " + ", ".join(u[:3]))
    v = _hits(t, VUL)
    if v: score += 10; why.append("Vulnerable group involved: " + ", ".join(v[:2]))
    if _hits(t, REP): score += 10; why.append("Repeat complaint / no response")
    m = re.search(r"(\d+)\s*(day|week|month)", t)
    if m:
        d = int(m.group(1)) * {"day": 1, "week": 7, "month": 30}[m.group(2)]
        if d >= 4: score += min(12, d//4); why.append("Unresolved for about %d days" % d)
    if sender in SENDER_BONUS: score += SENDER_BONUS[sender][0]; why.append(SENDER_BONUS[sender][1])
    if _hits(t, LOW) and not u: score -= 18; why.append("Low-urgency tone")
    score = max(0, min(100, score))
    pri = "Critical" if score >= 75 else "High" if score >= 50 else "Medium" if score >= 30 else "Low"
    cat = best[1] if best else "General"; dept = best[2] if best else "General Administration"
    return dict(score=score, priority=pri, category=cat, dept=dept, depts=list(dict.fromkeys([dept]+ds)), reasons=why, spam=False, life_risk=cat == "Emergency & Safety")
