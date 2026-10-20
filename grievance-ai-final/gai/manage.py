"""Real user management (no demo passwords).   python -m gai.manage add-user rao@dept.gov.in "A. Rao" --role officer --dept "Health Department"
Other commands: list-users, reset-password EMAIL"""
import argparse, getpass, sqlite3
from werkzeug.security import generate_password_hash
from .app import create_app

def _pw():
    while True:
        a = getpass.getpass("Password (min 10 chars, letters + digits): ")
        if len(a) >= 10 and any(c.isdigit() for c in a) and any(c.isalpha() for c in a) and a == getpass.getpass("Repeat password: "): return a
        print("Too weak or not matching. Try again.")

def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-user"); a.add_argument("email"); a.add_argument("name"); a.add_argument("--role", default="officer", choices=["admin", "officer"]); a.add_argument("--dept", default="")
    sub.add_parser("list-users"); r = sub.add_parser("reset-password"); r.add_argument("email")
    x = ap.parse_args(); con = sqlite3.connect(create_app(seed_demo=False).config["DB"])
    if x.cmd == "add-user":
        con.execute("INSERT INTO users VALUES(?,?,?,?,?)", (x.email.lower(), generate_password_hash(_pw()), x.name, x.role, x.dept)); print("Created", x.email)
    elif x.cmd == "reset-password":
        con.execute("UPDATE users SET pw_hash=? WHERE email=?", (generate_password_hash(_pw()), x.email.lower())); print("Password updated")
    else:
        for u in con.execute("SELECT email,name,role,dept FROM users"): print(*u, sep=" | ")
    con.commit()
if __name__ == "__main__": main()
