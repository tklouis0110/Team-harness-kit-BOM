"""IZ-001 作り直しの入口。cd tasks/IZ-001 してから: python src/run.py [S1 ...]。S1 S2 S3 S4 S5 S6。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import s1_fetch, s2_shape, s3_template, s4_defs, s5_calc, s6_group

STEPS = {"S1": s1_fetch.run, "S2": s2_shape.run, "S3": s3_template.run, "S4": s4_defs.run, "S5": s5_calc.run, "S6": s6_group.run}

if __name__ == "__main__":
    for s in (sys.argv[1:] or list(STEPS)):
        STEPS[s]()
