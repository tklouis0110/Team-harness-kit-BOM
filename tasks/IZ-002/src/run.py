"""IZ-002 作り直しの入口（引数なし）。out/bom_initial.db を作り直し、表ごとの行数を出す。data/bom.db には触らない。"""
import subprocess, sys, sqlite3
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass
T = Path(__file__).resolve().parent.parent
db = T / "out" / "bom_initial.db"
db.parent.mkdir(exist_ok=True)
db.unlink(missing_ok=True)
r = subprocess.run([sys.executable, str(T / "src" / "build_db.py"), "--src", str(T.parent / "IZ-001" / "out"), "--out", str(db)])
if r.returncode:
    sys.exit(r.returncode)
c = sqlite3.connect(db)
for (t,) in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name").fetchall():
    print(t, c.execute(f"select count(*) from {t}").fetchone()[0])
