# -*- coding: utf-8 -*-
"""
Recompute the Layer C "honesty check" quantities that the article quotes but
that `realworld/orchestrator/analyse_v1r.py` does not itself write into
`v1r_analysis.json`:

  * out-of-sample propagation-delay MAE           (article: 181 ms, Table 20)
  * mean cycle time of the campaign               (article: 186 s, Table 18)
  * out-of-combination duration MAE               (article: 17.4 s, Sect. 6.13)
  * the co-failure artefact edge                  (article: cartservice -> adservice, 101.7 s)

Everything is derived from the released raw records
(`realworld/results/v1r_incidents.jsonl`) and, for the out-of-combination subset,
from the frozen estimator run that `analyse_v1r.main()` performs.

Usage:  python verification/recompute_honesty_checks.py

Requires: numpy, scipy (the estimator package).
"""
import json
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RW = os.path.join(ROOT, "realworld", "results")
sys.path.insert(0, os.path.join(ROOT, "realworld", "orchestrator"))
sys.path.insert(0, os.path.join(ROOT, "evaluation"))

rows = [json.loads(l) for l in open(os.path.join(RW, "v1r_incidents.jsonl"), encoding="utf-8")]
measured = [r for r in rows if r.get("status") in ("ok", "censored")]
held = [r for r in measured if r.get("phase") == "heldout"]
corpus = [r for r in measured if r.get("phase") == "corpus"]

print("records: %d measured (%d corpus, %d held-out)" % (len(measured), len(corpus), len(held)))

# ---------------------------------------------------------------- mean cycle time
cyc = [r["cycle_s"] for r in measured if r.get("cycle_s")]
print("\nmean cycle time                : %.1f s   (article: 186 s, Table 18)" % (sum(cyc) / len(cyc)))

# ------------------------------------------- out-of-sample propagation-delay MAE
# Edge delays learned on the corpus phase are compared with the medians observed
# only in the held-out phase. Learned values are read from the analysis file the
# orchestrator script writes; observed medians are recomputed here from the raw
# held-out records.
analysis = json.load(open(os.path.join(RW, "v1r_analysis.json"), encoding="utf-8"))
learned = {row["edge"]: row["learned_ms"] for row in analysis["table5_propagation"]["rows"]}

edges = {}
for r in held:
    for svc, ms in (r.get("propagation_edges") or {}).items():
        edges.setdefault("%s->%s" % (r["origin"], svc), []).append(ms)

errs, detail = [], []
for edge, vals in sorted(edges.items(), key=lambda kv: -len(kv[1])):
    med = st.median(vals)
    lrn = learned.get(edge)
    detail.append((edge, len(vals), med, lrn))
    if lrn is not None and len(vals) >= 4:
        errs.append(abs(med - lrn))

print("\nout-of-sample propagation delay (held-out observed vs corpus-learned):")
for edge, n, med, lrn in detail:
    mark = "  <- used" if (lrn is not None and n >= 4) else "  (n<4 or no learned value: excluded)"
    print("   %-46s n=%2d  observed %8.0f ms  learned %s%s"
          % (edge, n, med, ("%8.0f ms" % lrn) if lrn is not None else "     n/a", mark))
print("   MAE over %d edges            : %.1f ms   (article: 181 ms, Table 20)"
      % (len(errs), sum(errs) / len(errs)))

artefact = [(e, n, m) for e, n, m in ((e, n, m) for e, n, m, _ in detail) if m > 60000]
for e, n, m in artefact:
    print("   co-failure artefact           : %s recorded once at %.1f s (article: 101.7 s)" % (e, m / 1000.0))

# --------------------------------------------------- out-of-combination subset
# Uncensored held-out incidents whose (fault, service, action) combination never
# occurs in the corpus. Predictions come from the frozen estimator, exactly as in
# analyse_v1r.main(); we intercept them rather than re-implementing the pipeline.
captured = {}


def _capture(preds, unc, obs_edges, learned_, out_):
    captured["preds"] = preds


import analyse_v1r as AV  # noqa: E402

AV.make_plots = _capture
AV.main()

seen = {(r["fault"], r["origin"], r["action"]) for r in corpus}
sub = [(r, p) for r, p in captured["preds"]
       if not r.get("censored") and (r["fault"], r["origin"], r["action"]) not in seen]
if sub:
    mae = sum(abs(p["duration"] - r["duration_min"]) * 60 for r, p in sub) / len(sub)
    print("\nout-of-combination subset      : n=%d, MAE %.1f s   (article: n=4, 17.4 s, Sect. 6.13)"
          % (len(sub), mae))
    for r, _ in sub:
        print("   %s  %s / %s / %s" % (r["id"], r["fault"], r["origin"], r["action"]))
else:
    print("\nout-of-combination subset      : empty")
