"""Runs the whole validation in order and times each step. Pure Python; the sweep is most of it.

  python analysis/sentiment_run_all.py            # everything (about 20 minutes, sweep included)
  python analysis/sentiment_run_all.py --no-sweep # reuse the last sweep (about a minute)
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = ["instructor_names", "sentiment_replay", "sentiment_perturb", "sentiment_predict", "sentiment_workload", "sentiment_edge_cases",
         "sentiment_drift", "sentiment_fairness", "sentiment_sweep", "sentiment_decide", "build_sentiment_report"]

if __name__ == "__main__":
    skip = {"sentiment_sweep"} if "--no-sweep" in sys.argv else set()
    t0 = time.time()
    for step in STEPS:
        if step in skip:
            print("-- %s skipped" % step)
            continue
        t1 = time.time()
        r = subprocess.run([sys.executable, os.path.join(HERE, step + ".py")], text=True)
        print("-- %s: %s in %.0fs" % (step, "ok" if r.returncode == 0 else "FAILED (%d)" % r.returncode, time.time() - t1))
        if r.returncode != 0:
            sys.exit(r.returncode)
    r = subprocess.run([sys.executable, "-m", "unittest", "-q", "analysis.test_sentiment_score"], cwd=os.path.dirname(HERE), text=True)
    print("-- unit test: %s | total %.0f min" % ("ok" if r.returncode == 0 else "FAILED", (time.time() - t0) / 60))
