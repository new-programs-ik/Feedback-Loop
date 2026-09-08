"""Runs the whole formula study in order and times each step.

  python analysis/formula/run_all.py             # everything (a few minutes; the loop is most of it)
  python analysis/formula/run_all.py --no-loop   # rebuild the report from the last loop
  python analysis/formula/run_all.py --full-grid # also run the properties on the full 377k-point grid

Steps: features -> inputs_signal -> trust -> cases -> properties -> loop -> report -> unit test.
Outputs under analysis/out/ (gitignored) and the two PDFs at the repo root (gitignored).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STEPS = ["features", "inputs_signal", "trust", "cases", "properties", "loop", "report"]

if __name__ == "__main__":
    skip = {"loop"} if "--no-loop" in sys.argv else set()
    t0 = time.time()
    for step in STEPS:
        if step in skip:
            print("-- %s skipped" % step)
            continue
        t1 = time.time()
        args = [sys.executable, os.path.join(HERE, step + ".py")]
        if step == "properties" and "--full-grid" in sys.argv:
            args.append("--full")
        r = subprocess.run(args, text=True)
        print("-- %s: %s in %.0fs" % (step, "ok" if r.returncode == 0 else "FAILED (%d)" % r.returncode, time.time() - t1))
        if r.returncode != 0:
            sys.exit(r.returncode)
    r = subprocess.run([sys.executable, "-m", "unittest", "-q", "analysis.formula.test_properties"], cwd=ROOT, text=True)
    print("-- unit test: %s | total %.1f min" % ("ok" if r.returncode == 0 else "FAILED", (time.time() - t0) / 60))
