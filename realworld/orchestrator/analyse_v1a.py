"""Assess the V1a instrument against the success gate. Measurement only."""
import json
import os
import statistics as st
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", ".."))
RES = os.path.join(ROOT, "realworld", "results")


def load(name):
    p = os.path.join(RES, name)
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def main():
    controls = load("v1a_controls.jsonl")
    inc = load("v1a_incidents.jsonl")
    ok = [r for r in inc if r.get("status") == "ok"]

    print("=" * 74)
    print("1. FAULT VALIDITY (no-recovery controls)")
    print("=" * 74)
    persistent, selfheal = [], []
    for c in controls:
        tag = "PERSISTENT" if c.get("persistent") else "SELF-HEALED  <-- INVALID"
        (persistent if c.get("persistent") else selfheal).append(
            (c["fault"], c["origin"]))
        print("   %-20s @ %-24s %s" % (c["fault"], c["origin"], tag))
    print("   validity rate: %d/%d = %.0f%%"
          % (len(persistent), len(controls), 100 * len(persistent) / len(controls)))
    invalid_pairs = set(selfheal)

    print()
    print("=" * 74)
    print("2. PROPAGATION DELAYS  (gate: non-zero and reproducible)")
    print("=" * 74)
    props = []
    for r in ok:
        for svc, ms in (r.get("propagation_ms") or {}).items():
            props.append((r["id"], r["origin"], svc, ms))
    if props:
        vals = [p[3] for p in props]
        print("   observed propagation edges: %d across %d incidents"
              % (len(props), len(ok)))
        print("   delay ms: min %d  p25 %d  median %d  p75 %d  max %d  mean %d"
              % (min(vals), st.quantiles(vals, n=4)[0], st.median(vals),
                 st.quantiles(vals, n=4)[2], max(vals), st.mean(vals)))
        print("   non-zero: %d/%d (%.0f%%)"
              % (sum(1 for v in vals if v > 0), len(vals),
                 100 * sum(1 for v in vals if v > 0) / len(vals)))
        print()
        print("   per observed edge (origin -> dependant):")
        agg = {}
        for _i, o, s, ms in props:
            agg.setdefault((o, s), []).append(ms)
        for (o, s), v in sorted(agg.items(), key=lambda x: -len(x[1])):
            print("      %-24s -> %-24s n=%d  ms=%s"
                  % (o, s, len(v), sorted(v)))
    else:
        print("   NONE OBSERVED")

    print()
    print("=" * 74)
    print("3. AFFECTED-SERVICE SETS  (gate: beyond the origin alone)")
    print("=" * 74)
    blasts = [r["blast"] for r in ok]
    beyond = sum(1 for r in ok if r["blast"] > 1)
    print("   blast radius: min %d  median %.1f  max %d  mean %.2f"
          % (min(blasts), st.median(blasts), max(blasts), st.mean(blasts)))
    print("   incidents with blast > 1: %d/%d (%.0f%%)"
          % (beyond, len(ok), 100 * beyond / len(ok)))
    dist = {}
    for b in blasts:
        dist[b] = dist.get(b, 0) + 1
    print("   distribution:", dict(sorted(dist.items())))

    print()
    print("=" * 74)
    print("4. LEVEL SEPARATION  (gate: dependency-level distinguishable)")
    print("=" * 74)
    only_dep, both = 0, 0
    rows = []
    for r in ok:
        lv = r.get("onset_ms_by_level", {})
        reach = set(lv.get("reachable", {}))
        func = set(lv.get("functional", {}))
        dep = set(lv.get("dependency", {}))
        uv = set(lv.get("uservisible", {}))
        dep_only = dep - reach - func
        if dep_only:
            only_dep += 1
        if dep and (reach or func):
            both += 1
        rows.append((r["id"], sorted(reach), sorted(func), sorted(dep), sorted(uv)))
    print("   incidents where a service failed ONLY at the dependency level: "
          "%d/%d" % (only_dep, len(ok)))
    print("   (these are exactly the failures readiness probing cannot see)")
    print()
    print("   %-5s %-28s %-24s %s" % ("id", "reachable-down", "functional-down",
                                      "dependency-down"))
    for iid, reach, func, dep, _uv in rows:
        print("   %-5s %-28s %-24s %s"
              % (iid, ",".join(s[:12] for s in reach) or "-",
                 ",".join(s[:12] for s in func) or "-",
                 ",".join(s[:12] for s in dep) or "-"))

    print()
    print("=" * 74)
    print("5. DETECTION AND RECOVERY")
    print("=" * 74)
    det = [r["detect_latency_ms"] for r in ok]
    dur = [r["duration_s"] for r in ok]
    cyc = [r["cycle_s"] for r in ok]
    print("   detection latency ms: min %d  median %d  max %d"
          % (min(det), st.median(det), max(det)))
    print("     (V0 at 1 Hz: mean 3780 ms)")
    print("   recovery duration s : min %.1f  median %.1f  max %.1f  sd %.1f"
          % (min(dur), st.median(dur), max(dur), st.pstdev(dur)))
    print("   cycle time s        : mean %.1f  min %.1f  max %.1f"
          % (st.mean(cyc), min(cyc), max(cyc)))
    print("   completed %d/%d, censored %d, reset_ok %d/%d"
          % (len(ok), len(inc), sum(1 for r in inc if r.get("censored")),
             sum(1 for r in ok if r.get("reset_ok")), len(ok)))

    # duration reproducibility within a (fault, action) cell
    cell = {}
    for r in ok:
        cell.setdefault((r["fault"], r["action"]), []).append(r["duration_s"])
    print()
    print("   duration spread within (fault, action) cells:")
    for k, v in sorted(cell.items()):
        if len(v) > 1:
            print("      %-38s n=%d  mean %.1f  sd %.1f"
                  % ("%s/%s" % k, len(v), st.mean(v), st.pstdev(v)))

    print()
    print("=" * 74)
    print("6. GATE ASSESSMENT")
    print("=" * 74)
    g1 = bool(props) and all(p[3] > 0 for p in props)
    g2 = beyond / max(1, len(ok)) >= 0.5
    g3 = only_dep > 0
    g4 = len(ok) == len([r for r in inc if r.get("status") in ("ok", "censored")])
    g5 = len(persistent) / max(1, len(controls)) >= 0.75
    for name, val in [("non-zero reproducible propagation delays", g1),
                      ("affected sets beyond the origin (>=50%)", g2),
                      ("dependency-level degradation distinguishable", g3),
                      ("stable recovery measurement (no censoring/aborts)", g4),
                      ("fault persistence verified (>=75% of pairs)", g5)]:
        print("   [%s] %s" % ("PASS" if val else "FAIL", name))

    out = {
        "controls": {"total": len(controls), "persistent": len(persistent),
                     "self_healed": [list(x) for x in sorted(invalid_pairs)],
                     "validity_rate": len(persistent) / max(1, len(controls))},
        "propagation": {"edges": len(props),
                        "ms": sorted(p[3] for p in props),
                        "median_ms": st.median([p[3] for p in props]) if props else None,
                        "nonzero_frac": (sum(1 for p in props if p[3] > 0)
                                         / len(props)) if props else 0.0,
                        "by_edge": {"%s->%s" % (o, s): v for (o, s), v in
                                    {(o, s): [x[3] for x in props
                                              if x[1] == o and x[2] == s]
                                     for _i, o, s, _m in props}.items()}},
        "blast": {"values": blasts, "mean": st.mean(blasts),
                  "frac_gt1": beyond / max(1, len(ok))},
        "detection_ms": {"median": st.median(det), "min": min(det), "max": max(det)},
        "duration_s": {"median": st.median(dur), "min": min(dur), "max": max(dur)},
        "cycle_s": {"mean": st.mean(cyc)},
        "dependency_only_incidents": only_dep,
        "gate": {"propagation_nonzero": g1, "blast_beyond_origin": g2,
                 "dependency_distinguishable": g3, "stable_recovery": g4,
                 "fault_persistence": g5,
                 "all_pass": all([g1, g2, g3, g4, g5])},
    }
    json.dump(out, open(os.path.join(RES, "v1a_assessment.json"), "w"),
              indent=2, default=float)
    print("\nwrote realworld/results/v1a_assessment.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
