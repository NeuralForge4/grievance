"""Grievance AI backend: Flask with SQLite for local use and PostgreSQL for hosted deployments."""
import os, json, time, secrets, sqlite3

class HybridRow(dict):
    """Dictionary-style database row that also supports SQLite-style numeric indexes."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

def hybrid_row_factory(cursor):
    names = [col.name for col in cursor.description]
    return lambda values: HybridRow(zip(names, values))

class PostgresDB:
    """Small compatibility wrapper for the SQLite-style calls used by this app."""
    def __init__(self, connection):
        self.connection = connection
    def execute(self, sql, params=()):
        return self.connection.execute(sql.replace("?", "%s"), params)
    def executescript(self, script):
        for statement in script.split(";"):
            if statement.strip():
                self.connection.execute(statement)
    def commit(self):
        self.connection.commit()
    def close(self):
        self.connection.close()
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, jsonify, session, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from . import model as M, ai

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, name TEXT, role TEXT, dept TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS emails(id INTEGER PRIMARY KEY AUTOINCREMENT, gid TEXT UNIQUE, sender TEXT, sender_type TEXT, subject TEXT, body TEXT,
  received_at TEXT, priority TEXT, score INTEGER, category TEXT, dept TEXT, depts TEXT, reasons TEXT, confidence REAL, needs_review INTEGER,
  status TEXT DEFAULT 'open', handled_by TEXT, engine TEXT DEFAULT 'local', corrected INTEGER DEFAULT 0, injection INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS lockouts(email TEXT PRIMARY KEY, fails INTEGER, until REAL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user TEXT, action TEXT, email_id INTEGER, detail TEXT, ip TEXT);
CREATE INDEX IF NOT EXISTS ix_pri ON emails(priority, status);
"""
PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, name TEXT, role TEXT, dept TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS emails(id BIGSERIAL PRIMARY KEY, gid TEXT UNIQUE, sender TEXT, sender_type TEXT, subject TEXT, body TEXT,
  received_at TEXT, priority TEXT, score INTEGER, category TEXT, dept TEXT, depts TEXT, reasons TEXT, confidence DOUBLE PRECISION, needs_review INTEGER,
  status TEXT DEFAULT 'open', handled_by TEXT, engine TEXT DEFAULT 'local', corrected INTEGER DEFAULT 0, injection INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS lockouts(email TEXT PRIMARY KEY, fails INTEGER, until DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS audit(id BIGSERIAL PRIMARY KEY, ts TEXT, "user" TEXT, action TEXT, email_id INTEGER, detail TEXT, ip TEXT);
CREATE INDEX IF NOT EXISTS ix_pri ON emails(priority, status);
"""
DEMO_USERS = [("admin@gov.in", "Admin@123", "Shri A. K. Sharma", "admin", ""),
              ("health@gov.in", "Health@123", "Dr. Neha Singh", "officer", "Health Department"),
              ("pwd@gov.in", "Pwd@123", "Er. R. Yadav", "officer", "Public Works (PWD)")]
DEMO_MAILS = [("Anita Verma <anita@mail.in>", "citizen", "URGENT flood water entering houses", "Flood water has entered homes in Sector 7. 200 families are stranded, elderly and children without food. Send rescue boats immediately!"),
              ("DH Staff <staff@dh.gov.in>", "official", "Oxygen supply low at district hospital", "Oxygen cylinders will last only 6 hours. Several patients on ventilators. Need emergency supply today."),
              ("Sunita Devi <sunita@mail.in>", "citizen", "Widow pension not received", "I am a widow aged 68. My pension has not come for 5 months. I wrote twice before, nobody replied."),
              ("Meena Gupta <meena@mail.in>", "citizen", "Pothole on Station Road", "There is a big pothole near the market on Station Road for 2 weeks. Kindly repair."),
              ("Arjun Nair <arjun@mail.in>", "citizen", "Suggestion for a park", "Thank you for the great work. I suggest adding more benches in the city park."),
              ("Prize Desk <win@promo.biz>", "citizen", "You are a lottery winner", "Click here to claim your free gift. Limited offer, buy now!")]

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")

def create_app(db_path=None, model_dir=None, seed_demo=None):
    app = Flask(__name__, static_folder=None)
    secret = os.environ.get("GAI_SECRET")
    database_url = os.environ.get("DATABASE_URL") if db_path is None else None
    app.config.update(SECRET_KEY=secret or secrets.token_hex(32), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=os.environ.get("GAI_HTTPS") == "1", PERMANENT_SESSION_LIFETIME=8 * 3600,
                      DB=db_path or os.environ.get("GAI_DB", os.path.join(ROOT, "data", "gai.db")),
                      DATABASE_URL=database_url,
                      MODEL_DIR=model_dir or os.environ.get("GAI_MODEL_DIR", os.path.join(ROOT, "models")))
    if not app.config["DATABASE_URL"]:
        os.makedirs(os.path.dirname(app.config["DB"]) or ".", exist_ok=True)

    def db():
        if "db" not in g:
            if app.config["DATABASE_URL"]:
                import psycopg
                g.db = PostgresDB(psycopg.connect(app.config["DATABASE_URL"], row_factory=hybrid_row_factory))
            else:
                g.db = sqlite3.connect(app.config["DB"]); g.db.row_factory = sqlite3.Row
        return g.db
    @app.teardown_appcontext
    def close(_):
        d = g.pop("db", None)
        if d: d.close()

    def audit(action, email_id=None, detail="", user=None):
        db().execute('INSERT INTO audit(ts,"user",action,email_id,detail,ip) VALUES(?,?,?,?,?,?)',
                     (now(), user or session.get("email", "-"), action, email_id, detail, request.remote_addr))
        db().commit()

    def ingest(sender, subject, body, received_at=None, gid=None, sender_type="citizen", allow_llm=True):
        """Analyse one email and store it. Returns id, or None if already stored (dedupe by Message-ID)."""
        if gid and db().execute("SELECT 1 FROM emails WHERE gid=?", (gid,)).fetchone(): return None
        r = ai.classify(subject, body[:6000], sender_type, app.config["MODEL_DIR"], allow_llm=allow_llm)
        sql = "INSERT INTO emails(gid,sender,sender_type,subject,body,received_at,priority,score,category,dept,depts,reasons,confidence,needs_review,engine,injection) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        params = (gid, sender, sender_type, subject, body[:20000], received_at or now(), r["priority"], r["score"], r["category"], r["dept"],
                  json.dumps(r["depts"]), json.dumps(r["reasons"]), r["confidence"], int(r["needs_review"]), r["engine"], int(r["injection"]))
        if app.config["DATABASE_URL"]:
            new_id = db().execute(sql + " RETURNING id", params).fetchone()["id"]
        else:
            new_id = db().execute(sql, params).lastrowid
        db().commit(); return new_id
    app.ingest = ingest

    with app.app_context():
        db().executescript(PG_SCHEMA if app.config["DATABASE_URL"] else SCHEMA)
        if app.config["DATABASE_URL"]:
            have = {x["name"] for x in db().execute("SELECT column_name AS name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'emails'")}
        else:
            have = {x["name"] for x in db().execute("PRAGMA table_info(emails)")}      # upgrade local databases from older versions
        for c, d in (("engine", "TEXT DEFAULT 'local'"), ("corrected", "INTEGER DEFAULT 0"), ("injection", "INTEGER DEFAULT 0")):
            if c not in have: db().execute("ALTER TABLE emails ADD COLUMN %s %s" % (c, d))
        db().commit()
        if seed_demo or (seed_demo is None and os.environ.get("GAI_SEED_DEMO") == "1"):
            for e, pw, n, role, dept in DEMO_USERS:
                db().execute("INSERT INTO users VALUES(?,?,?,?,?) ON CONFLICT(email) DO NOTHING", (e, generate_password_hash(pw), n, role, dept))
            db().commit()
            if not db().execute("SELECT 1 FROM emails").fetchone():
                for s, t, sub, b in DEMO_MAILS: ingest(s, sub, b, sender_type=t, gid="demo-" + sub, allow_llm=False)

    # ---------- security helpers ----------
    @app.after_request
    def headers(r):
        r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                          "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-ancestors 'none'",
                          "Cache-Control": "no-store" if request.path.startswith("/api") else "no-cache"})
        return r
    def need_login(f):
        @wraps(f)
        def w(*a, **k):
            if "email" not in session: return jsonify(error="Please log in."), 401
            if request.method != "GET" and request.headers.get("X-GAI") != "1": return jsonify(error="Missing request header."), 403
            return f(*a, **k)
        return w
    def need_admin(f):
        @wraps(f)
        @need_login
        def w(*a, **k):
            return f(*a, **k) if session.get("role") == "admin" else (jsonify(error="Admins only."), 403)
        return w
    def scope():                                   # SQL fragment limiting rows to what this officer may see
        if session.get("role") == "admin" or not session.get("dept"): return "1=1", []
        return "depts LIKE ?", ['%"' + session["dept"] + '"%']
    def out(r):
        d = dict(r); d["depts"] = json.loads(d["depts"]); d["reasons"] = json.loads(d["reasons"]); d["needs_review"] = bool(d["needs_review"]); d.pop("gid", None); return d

    # ---------- auth ----------
    @app.post("/api/login")
    def login():
        if request.headers.get("X-GAI") != "1": return jsonify(error="Missing request header."), 403
        j = request.get_json(silent=True) or {}; e = str(j.get("email", "")).strip().lower()
        r0 = db().execute("SELECT fails, until FROM lockouts WHERE email=?", (e,)).fetchone(); c, until = (r0["fails"], r0["until"]) if r0 else (0, 0)
        if until > time.time(): return jsonify(error="Too many failed attempts. Try again in a few minutes."), 429
        u = db().execute("SELECT * FROM users WHERE email=?", (e,)).fetchone()
        if not u or not check_password_hash(u["pw_hash"], str(j.get("password", ""))):
            c += 1; db().execute("INSERT INTO lockouts VALUES(?,?,?) ON CONFLICT(email) DO UPDATE SET fails=excluded.fails, until=excluded.until", (e, c, time.time() + 300 if c >= 5 else 0)); db().commit()
            audit("login_failed", detail=e, user=e); return jsonify(error="Wrong email or password."), 401
        db().execute("DELETE FROM lockouts WHERE email=?", (e,)); db().commit(); session.clear(); session.permanent = True
        session.update(email=u["email"], role=u["role"], dept=u["dept"], name=u["name"])
        audit("login"); return jsonify(email=u["email"], name=u["name"], role=u["role"], dept=u["dept"])
    @app.post("/api/logout")
    @need_login
    def logout(): audit("logout"); session.clear(); return jsonify(ok=True)
    @app.get("/api/me")
    @need_login
    def me(): return jsonify({k: session.get(k) for k in ("email", "name", "role", "dept")})

    # ---------- emails ----------
    @app.get("/api/emails")
    @need_login
    def emails():
        w, p = scope(); q = request.args
        for col, key in (("priority", "priority"), ("status", "status"), ("category", "category")):
            if q.get(key): w += f" AND {col}=?"; p.append(q[key])
        if q.get("review") == "1": w += " AND needs_review=1 AND status!='resolved'"
        if q.get("q"): w += " AND (subject LIKE ? OR body LIKE ? OR sender LIKE ?)"; p += ["%" + q["q"] + "%"] * 3
        rows = db().execute(f"SELECT * FROM emails WHERE {w} ORDER BY CASE status WHEN 'resolved' THEN 1 ELSE 0 END, score DESC, received_at DESC LIMIT 500", p).fetchall()
        return jsonify([out(r) for r in rows])
    def get_one(i):
        w, p = scope(); return db().execute(f"SELECT * FROM emails WHERE id=? AND {w}", [i] + p).fetchone()
    @app.get("/api/emails/<int:i>")
    @need_login
    def one(i):
        r = get_one(i)
        if not r: return jsonify(error="Not found."), 404
        audit("view", i); return jsonify(out(r))
    @app.post("/api/emails/<int:i>/status")
    @need_login
    def status(i):
        s = (request.get_json(silent=True) or {}).get("status")
        if s not in ("open", "resolved", "escalated") or not get_one(i): return jsonify(error="Invalid request."), 400
        db().execute("UPDATE emails SET status=?, handled_by=? WHERE id=?", (s, session["email"], i)); db().commit()
        audit("status:" + s, i); return jsonify(out(get_one(i)))
    @app.post("/api/emails/<int:i>/priority")
    @need_login
    def set_priority(i):
        p = (request.get_json(silent=True) or {}).get("priority"); r = get_one(i)
        if p not in M.PRI or not r: return jsonify(error="Invalid request."), 400
        db().execute("UPDATE emails SET priority=?, score=?, needs_review=0, corrected=1 WHERE id=?", (p, {"Critical": 90, "High": 63, "Medium": 38, "Low": 10}[p], i)); db().commit()
        audit("priority:%s->%s" % (r["priority"], p), i); return jsonify(out(get_one(i)))
    @app.post("/api/emails/<int:i>/confirm")
    @need_login
    def confirm(i):
        if not get_one(i): return jsonify(error="Not found."), 404
        db().execute("UPDATE emails SET needs_review=0, corrected=1 WHERE id=?", (i,)); db().commit()
        audit("confirm_ai_priority", i); return jsonify(out(get_one(i)))
    @app.post("/api/analyze")
    @need_login
    def analyze():
        j = request.get_json(silent=True) or {}
        sub, body = str(j.get("subject", "")).strip()[:300], str(j.get("body", "")).strip()
        if not (sub or body): return jsonify(error="Enter a subject or body."), 400
        st = j.get("sender_type") if j.get("sender_type") in ("citizen", "elected", "media", "court", "official") else "citizen"
        i = ingest(str(j.get("sender", "Unknown"))[:200], sub or "(no subject)", body, sender_type=st)
        audit("analyze", i); return jsonify(out(db().execute("SELECT * FROM emails WHERE id=?", (i,)).fetchone()))
    @app.get("/api/stats")
    @need_login
    def stats():
        w, p = scope(); rows = db().execute(f"SELECT priority, COUNT(*) n FROM emails WHERE status!='resolved' AND {w} GROUP BY priority", p).fetchall()
        d = db().execute(f"SELECT dept, COUNT(*) n FROM emails WHERE status!='resolved' AND {w} GROUP BY dept", p).fetchall()
        return jsonify(open_by_priority={r["priority"]: r["n"] for r in rows}, open_by_dept={r["dept"]: r["n"] for r in d}, llm=ai.llm_enabled(),
                       needs_review=db().execute(f"SELECT COUNT(*) FROM emails WHERE needs_review=1 AND status!='resolved' AND {w}", p).fetchone()[0])
    @app.get("/api/audit")
    @need_admin
    def audit_log():
        return jsonify([dict(r) for r in db().execute("SELECT * FROM audit ORDER BY id DESC LIMIT 300")])
    @app.get("/api/metrics")
    @need_login
    def metrics():
        return jsonify(json.load(open(os.path.join(app.config["MODEL_DIR"], "metrics.json"))))
    @app.get("/api/public")
    def public(): return jsonify(demo=os.environ.get("GAI_SEED_DEMO") == "1", llm=ai.llm_enabled())
    @app.get("/static/<path:p>")
    def assets(p): return send_from_directory(os.path.join(ROOT, "static"), p)
    @app.get("/")
    def index(): return send_from_directory(os.path.join(ROOT, "static"), "index.html")
    return app

if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 5055)))
