"""
Ingestion test: can the FROZEN IncidentMind pipeline consume real telemetry?

Loads the V0 incident records measured on the live cluster, builds an Online
Boutique impact graph, constructs an IncidentMemory and runs the estimator.

The estimator is imported unmodified from evaluation/ at commit 7d0ff7b. No
parameter is changed; configuration C is loaded verbatim from the frozen
dev_interval.json. Nothing here touches the estimator source.

This is a PIPELINE test, not an accuracy result: nine valid incidents is far
below the corpus size at which the estimator produces meaningful predictions,
and any error figures printed are reported only to show the pipeline runs end
to end.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "evaluation"))

from environment import Topology                      # noqa: E402
from estimator import IncidentMemory, IncidentMindEstimator  # noqa: E402

# Online Boutique impact graph: edge (u, v) means "degradation of u can degrade
# v". Derived from the documented call graph of v0.10.6; the frontend is the
# only user-facing sink.
OB_NODES = ["adservice", "cartservice", "checkoutservice", "currencyservice",
            "emailservice", "frontend", "paymentservice", "productcatalogservice",
            "recommendationservice", "redis-cart", "shippingservice"]
OB_EDGES = [
    ("redis-cart", "cartservice"),
    ("cartservice", "frontend"), ("cartservice", "checkoutservice"),
    ("productcatalogservice", "frontend"),
    ("productcatalogservice", "recommendationservice"),
    ("productcatalogservice", "checkoutservice"),
    ("currencyservice", "frontend"), ("currencyservice", "checkoutservice"),
    ("paymentservice", "checkoutservice"),
    ("shippingservice", "frontend"), ("shippingservice", "checkoutservice"),
    ("emailservice", "checkoutservice"),
    ("adservice", "frontend"),
    ("recommendationservice", "frontend"),
    ("checkoutservice", "frontend"),
]

# Incidents whose fault did not actually persist, established by the control
# run: cartservice ignores the PORT environment variable, so a "misconfig"
# there is only a Recreate-induced restart that self-heals.
INVALID = {"i06"}


def to_record(v0):
    """Map a measured V0 incident onto the estimator's record schema."""
    return {
        "id": v0["id"], "topology": "onlineboutique", "fault": v0["fault"],
        "origin": v0["origin"], "action": v0["action"],
        "tau": float(v0["tau_min"]), "duration": float(v0["duration_min"]),
        "blast": int(v0["blast"]), "affected": sorted(v0["affected"]),
        "arrivals": {k: float(v) for k, v in v0["arrivals"].items()},
    }


def main():
    path = os.path.join(ROOT, "realworld", "results", "v0_incidents.jsonl")
    raw = [json.loads(l) for l in open(path) if l.strip()]
    ok = [r for r in raw if r.get("status") == "ok"]
    valid = [r for r in ok if r["id"] not in INVALID]
    print("V0 incidents: %d total, %d completed, %d valid after the control run"
          % (len(raw), len(ok), len(valid)))

    recs = [to_record(r) for r in valid]
    topo = Topology("onlineboutique", OB_NODES, OB_EDGES, seed=1)
    topos = {"onlineboutique": topo}

    hp = json.load(open(os.path.join(ROOT, "evaluation", "results",
                                     "dev_interval.json")))["frozen_hp_C"]
    print("frozen config C:", {k: hp[k] for k in
                               ("novelty_aware", "interval_fix", "scale_prior_df",
                                "lam_blend", "beta", "z")})

    print("\n-- building IncidentMemory from real telemetry --")
    mem = IncidentMemory(topos, recs, hp=hp)
    est = IncidentMindEstimator(mem)
    print("   records indexed      :", mem.n)
    print("   edge delays learned  : %d of %d edges"
          % (sum(1 for e in topo.edges if e in mem.edge_delay), len(topo.edges)))
    print("   global delay (min)   : %.4f" % mem._global_delay)
    print("   per-action lags      :", {k: round(v, 2)
                                        for k, v in mem.clag_action.items()})

    print("\n-- leave-one-out estimates (pipeline check, NOT an accuracy claim) --")
    print("   %-4s %-20s %-16s %6s %8s %8s %6s %6s %5s" % (
        "id", "origin", "action", "tau", "pred", "actual", "predB", "actB", "nov"))
    rows = []
    for i, r in enumerate(recs):
        sub = [x for j, x in enumerate(recs) if j != i]
        m2 = IncidentMemory(topos, sub, hp=hp)
        e2 = IncidentMindEstimator(m2)
        p = e2.estimate("onlineboutique", r["fault"], r["origin"], r["action"],
                        r["tau"])
        rows.append((r, p))
        print("   %-4s %-20s %-16s %6.2f %8.2f %8.2f %6d %6d %5.2f" % (
            r["id"], r["origin"][:20], r["action"][:16], r["tau"],
            p["duration"], r["duration"], p["blast"], r["blast"], p["novelty"]))

    mae = sum(abs(p["duration"] - r["duration"]) for r, p in rows) / len(rows)
    bmae = sum(abs(p["blast"] - r["blast"]) for r, p in rows) / len(rows)
    cov = sum(1 for r, p in rows if p["lo"] <= r["duration"] <= p["hi"]) / len(rows)
    print("\n   duration MAE %.2f min (%.1f s) | blast MAE %.2f | interval coverage %.2f"
          % (mae, mae * 60, bmae, cov))
    print("   (n=%d: far below the corpus size at which the estimator is "
          "meaningful; reported only to demonstrate the pipeline executes)"
          % len(rows))

    out = {"n_total": len(raw), "n_ok": len(ok), "n_valid": len(valid),
           "invalid_ids": sorted(INVALID),
           "pipeline_ran": True, "loo_duration_mae_min": mae,
           "loo_blast_mae": bmae, "loo_interval_coverage": cov,
           "edges_with_learned_delay": sum(1 for e in topo.edges
                                           if e in mem.edge_delay),
           "edges_total": len(topo.edges),
           "rows": [{"id": r["id"], "fault": r["fault"], "origin": r["origin"],
                     "action": r["action"], "tau_min": r["tau"],
                     "pred_duration_min": p["duration"],
                     "actual_duration_min": r["duration"],
                     "pred_blast": p["blast"], "actual_blast": r["blast"],
                     "novelty": p["novelty"], "confidence": p["confidence"],
                     "lo": p["lo"], "hi": p["hi"],
                     "pred_affected": sorted(p["affected"]),
                     "actual_affected": r["affected"]}
                    for r, p in rows]}
    dest = os.path.join(ROOT, "realworld", "results", "v0_ingest.json")
    json.dump(out, open(dest, "w"), indent=2, default=float)
    print("\nwrote", os.path.relpath(dest, ROOT))


if __name__ == "__main__":
    main()
