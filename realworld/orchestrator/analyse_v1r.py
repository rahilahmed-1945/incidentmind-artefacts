"""
V1r analysis: the FROZEN IncidentMind (commit 7d0ff7b, configuration C) applied
to real Kubernetes telemetry.

The estimator is imported unmodified from evaluation/ and its hyper-parameters
are loaded verbatim from the frozen dev_interval.json. Nothing here writes to
evaluation/ or alters any estimator behaviour.

CENSORING. Ineffective recovery actions never recover, so those incidents are
right-censored at the 90 s observation window; their recorded duration is a
LOWER BOUND, not a measurement.
  * Corpus: censored records are kept in the incident memory with their
    censored duration. The estimator has no censoring model, so it necessarily
    UNDER-estimates the cost of ineffective actions. This is reported, not
    corrected.
  * Held-out duration error: computed on uncensored incidents only. Censored
    held-out incidents are analysed separately as a directional check (did the
    estimator at least predict a long duration?).
  * Cell-level ranking: uses observed cell means. Censoring only compresses
    ineffective cells downward, so a correct ordering under censoring is a
    conservative result.

NOT CLAIMED: per-incident counterfactual regret. Real incidents provide no
counterfactual for the same latent incident. Ranking is reported strictly as
cell-level expected-outcome ranking.
"""
import json
import math
import os
import statistics as st
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", ".."))
RES = os.path.join(ROOT, "realworld", "results")
sys.path.insert(0, os.path.join(ROOT, "evaluation"))

from environment import Topology                              # noqa: E402
from estimator import IncidentMemory, IncidentMindEstimator   # noqa: E402

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
    ("adservice", "frontend"), ("recommendationservice", "frontend"),
    ("checkoutservice", "frontend"),
]


def to_record(r):
    return {"id": r["id"], "topology": "onlineboutique", "fault": r["fault"],
            "origin": r["origin"], "action": r["action"],
            "tau": float(r["tau_min"]), "duration": float(r["duration_min"]),
            "blast": int(r["blast"]), "affected": sorted(r["affected"]),
            "arrivals": {k: float(v) for k, v in r["arrivals"].items()}}


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / max(1, len(a | b))


def main():
    rows = [json.loads(l) for l in open(os.path.join(RES, "v1r_incidents.jsonl"))]
    proto = json.load(open(os.path.join(RES, "v1r_protocol.json")))
    alloc = json.load(open(os.path.join(RES, "v1r_allocation.json")))
    hp = json.load(open(os.path.join(ROOT, "evaluation", "results",
                                     "dev_interval.json")))["frozen_hp_C"]

    measured = [r for r in rows if r.get("status") in ("ok", "censored")]
    invalid = [r for r in rows if r.get("status") not in ("ok", "censored")]
    corpus = [r for r in measured if r["phase"] in ("corpus", "stability")]
    held = [r for r in measured if r["phase"] == "heldout"]

    out = {"protocol": {k: proto[k] for k in
                        ("incidentmind_estimator_commit", "censor_window_s",
                         "benchmark", "manifest_sha256", "cluster")},
           "hp_C": hp}

    # ---------------- Table 1: campaign composition ----------------
    t1 = {"attempted": len(rows), "measured": len(measured),
          "invalid": len(invalid),
          "invalid_reasons": {},
          "corpus": len(corpus), "heldout": len(held),
          "censored_total": sum(1 for r in measured if r.get("censored")),
          "censored_corpus": sum(1 for r in corpus if r.get("censored")),
          "censored_heldout": sum(1 for r in held if r.get("censored")),
          # NOTE: a change in container-restart count during an incident is
          # EXPECTED for resource_exhaustion (OOMKill) and for pod_restart
          # recovery. It is reported for transparency but is not by itself
          # evidence of infrastructure failure; the authoritative signals are
          # the stability-gate criteria (net restarts across the batch, clean
          # resets, telemetry continuity).
          "restart_count_changed_during_incident":
              sum(1 for r in measured if r.get("infra_anomaly")),
          "restart_changed_on_fault_inducing_restarts":
              sum(1 for r in measured if r.get("infra_anomaly")
                  and (r["fault"] == "resource_exhaustion"
                       or r["action"] == "pod_restart")),
          "clean_resets": sum(1 for r in measured if r.get("reset_ok")),
          "probe_events_total": sum(r.get("n_probe_events", 0) for r in measured)}
    for r in invalid:
        k = r.get("status", "unknown")
        t1["invalid_reasons"][k] = t1["invalid_reasons"].get(k, 0) + 1
    out["table1_composition"] = t1

    print("=" * 78)
    print("TABLE 1  Campaign composition")
    print("=" * 78)
    for k, v in t1.items():
        print("   %-22s %s" % (k, v))

    # ---------------- Table 2: cell coverage ----------------
    cov = {}
    for r in measured:
        k = "%s|%s|%s" % (r["fault"], r["origin"], r["action"])
        cov[k] = cov.get(k, 0) + 1
    cell_fa = {}
    for r in held:
        k = "%s|%s" % (r["fault"], r["action"])
        cell_fa.setdefault(k, []).append(r)
    out["table2_coverage"] = {"by_fault_service_action": cov,
                              "heldout_by_fault_action":
                                  {k: len(v) for k, v in sorted(cell_fa.items())}}
    print()
    print("=" * 78)
    print("TABLE 2  Held-out (fault x action) cell coverage")
    print("=" * 78)
    for k, v in sorted(cell_fa.items()):
        ncen = sum(1 for r in v if r.get("censored"))
        print("   %-42s n=%d (censored %d)" % (k, len(v), ncen))

    if not held:
        print("\nNo held-out incidents yet; stopping after composition.")
        json.dump(out, open(os.path.join(RES, "v1r_analysis.json"), "w"),
                  indent=2, default=float)
        return 0

    # ---------------- build memory from the frozen corpus ----------------
    topo = Topology("onlineboutique", OB_NODES, OB_EDGES, seed=1)
    topos = {"onlineboutique": topo}
    recs = [to_record(r) for r in corpus]
    mem = IncidentMemory(topos, recs, hp=hp)
    est = IncidentMindEstimator(mem)
    out["memory"] = {"n_records": mem.n,
                     "edges_with_learned_delay":
                         sum(1 for e in topo.edges if e in mem.edge_delay),
                     "edges_total": len(topo.edges),
                     "global_delay_min": mem._global_delay,
                     "clag_action": {k: round(v, 3)
                                     for k, v in mem.clag_action.items()}}
    print()
    print("=" * 78)
    print("Incident memory built from the frozen real-world corpus")
    print("=" * 78)
    for k, v in out["memory"].items():
        print("   %-26s %s" % (k, v))

    # ---------------- predict held-out ----------------
    preds = []
    for r in held:
        p = est.estimate("onlineboutique", r["fault"], r["origin"],
                         r["action"], float(r["tau_min"]))
        preds.append((r, p))

    unc = [(r, p) for r, p in preds if not r.get("censored")]
    cen = [(r, p) for r, p in preds if r.get("censored")]

    # ---------------- Table 3: duration ----------------
    print()
    print("=" * 78)
    print("TABLE 3  Duration prediction (uncensored held-out only)")
    print("=" * 78)
    t3 = {}
    if unc:
        err = [(p["duration"] - r["duration_min"]) * 60.0 for r, p in unc]
        ae = [abs(e) for e in err]
        obs = [r["duration_min"] * 60 for r, _ in unc]
        pr = [p["duration"] * 60 for _, p in unc]
        t3 = {"n": len(unc), "mae_s": st.mean(ae), "median_ae_s": st.median(ae),
              "rmse_s": math.sqrt(st.mean([e * e for e in err])),
              "bias_s": st.mean(err),
              "mape_pct": st.mean([abs(e) / o * 100 for e, o in zip(err, obs)]),
              "observed_range_s": [min(obs), max(obs)],
              "predicted_range_s": [min(pr), max(pr)],
              "error_quartiles_s": st.quantiles(ae, n=4) if len(ae) > 3 else None}
        for k, v in t3.items():
            print("   %-22s %s" % (k, v if not isinstance(v, float) else round(v, 2)))
    else:
        print("   no uncensored held-out incidents")
    t3["censored_directional"] = None
    if cen:
        thr = [(r["tau_min"] + proto["censor_window_s"] / 60.0) for r, _ in cen]
        longer = sum(1 for (r, p), t in zip(cen, thr) if p["duration"] >= t * 0.8)
        t3["censored_directional"] = {
            "n": len(cen), "pred_ge_80pct_of_censor_bound": longer,
            "mean_pred_s": st.mean([p["duration"] * 60 for _, p in cen]),
            "mean_bound_s": st.mean([t * 60 for t in thr])}
        print("   censored held-out: n=%d, mean predicted %.1fs vs censoring "
              "bound %.1fs; %d/%d predicted >=80%% of the bound"
              % (len(cen), t3["censored_directional"]["mean_pred_s"],
                 t3["censored_directional"]["mean_bound_s"], longer, len(cen)))
    out["table3_duration"] = t3

    # ---------------- Table 4: blast / affected set ----------------
    print()
    print("=" * 78)
    print("TABLE 4  Affected-service and blast-radius prediction (all held-out)")
    print("=" * 78)
    bl_err = [abs(p["blast"] - r["blast"]) for r, p in preds]
    jac = [jaccard(r["affected"], p["affected"]) for r, p in preds]
    orig_hit = sum(1 for r, p in preds if r["origin"] in p["affected"])
    inter_true = [(r, p) for r, p in preds if len(r["affected"]) > 1]
    inter_hit = sum(1 for r, p in inter_true
                    if len(set(r["affected"]) & set(p["affected"]) - {r["origin"]}) > 0)
    t4 = {"n": len(preds), "blast_mae": st.mean(bl_err),
          "blast_observed_mean": st.mean([r["blast"] for r, _ in preds]),
          "blast_predicted_mean": st.mean([p["blast"] for _, p in preds]),
          "jaccard_mean": st.mean(jac), "jaccard_median": st.median(jac),
          "origin_detection_rate": orig_hit / len(preds),
          "incidents_with_propagation": len(inter_true),
          "intermediate_service_detection_rate":
              (inter_hit / len(inter_true)) if inter_true else None}
    for k, v in t4.items():
        print("   %-38s %s" % (k, round(v, 3) if isinstance(v, float) else v))
    out["table4_blast"] = t4

    # ---------------- Table 5: propagation ----------------
    print()
    print("=" * 78)
    print("TABLE 5  Propagation-delay reconstruction")
    print("=" * 78)
    obs_edges = {}
    for r in measured:
        for s, ms in (r.get("propagation_edges") or {}).items():
            obs_edges.setdefault((r["origin"], s), []).append(ms)
    learned = {}
    for (u, v), val in mem.edge_delay.items():
        learned[(u, v)] = val * 60000.0     # minutes -> ms
    rows5, abs_err = [], []
    for (o, s), v in sorted(obs_edges.items(), key=lambda x: -len(x[1])):
        lm = learned.get((o, s))
        med = st.median(v)
        rows5.append({"edge": "%s->%s" % (o, s), "n": len(v),
                      "observed_median_ms": med,
                      "learned_ms": lm,
                      "abs_err_ms": abs(lm - med) if lm is not None else None})
        if lm is not None:
            abs_err.append(abs(lm - med))
        print("   %-46s n=%2d  observed %7.0f ms  learned %s"
              % ("%s->%s" % (o, s), len(v), med,
                 "%7.0f ms" % lm if lm is not None else "   n/a"))
    # ordering: does the estimator rank multi-hop arrivals correctly?
    multi = [r for r in measured if len(r.get("propagation_edges") or {}) > 1]
    ordok = 0
    for r in multi:
        pe = r["propagation_edges"]
        obs_order = sorted(pe, key=lambda s: pe[s])
        p = est.estimate("onlineboutique", r["fault"], r["origin"], r["action"],
                         float(r["tau_min"]))
        pred_set = p["affected"]
        if all(s in pred_set for s in obs_order):
            ordok += 1
    t5 = {"edges_observed": len(obs_edges), "rows": rows5,
          "mean_abs_edge_error_ms": st.mean(abs_err) if abs_err else None,
          "multihop_incidents": len(multi),
          "multihop_all_services_predicted": ordok}
    print("   mean |learned - observed| over edges: %s"
          % (round(t5["mean_abs_edge_error_ms"], 1) if abs_err else "n/a"))
    print("   multi-hop incidents: %d; all propagated services predicted in %d"
          % (len(multi), ordok))
    out["table5_propagation"] = t5

    # ---------------- Table 6: uncertainty ----------------
    print()
    print("=" * 78)
    print("TABLE 6  Uncertainty and confidence")
    print("=" * 78)
    t6 = {}
    if unc:
        cov_hit = sum(1 for r, p in unc
                      if p["lo"] <= r["duration_min"] <= p["hi"])
        widths = [(p["hi"] - p["lo"]) * 60 for _, p in unc]
        confs = [p["confidence"] for _, p in unc]
        aes = [abs(p["duration"] - r["duration_min"]) * 60 for r, p in unc]
        rho = None
        if len(unc) > 3 and st.pstdev(confs) > 1e-9:
            from scipy import stats as sstats
            rho = float(sstats.spearmanr(confs, aes).statistic)
        t6 = {"n": len(unc), "interval_coverage": cov_hit / len(unc),
              "nominal": 0.80, "mean_interval_width_s": st.mean(widths),
              "median_interval_width_s": st.median(widths),
              "mean_confidence": st.mean(confs),
              "spearman_conf_vs_abs_error": rho,
              "mean_novelty": st.mean([p["novelty"] for _, p in unc]),
              "mean_n_tier1_precedent": st.mean([p["n_tier1"] for _, p in unc])}
        for k, v in t6.items():
            print("   %-34s %s" % (k, round(v, 3) if isinstance(v, float) else v))
        by = {}
        for r, p in unc:
            b = ("0" if p["n_tier1"] == 0 else "1-2" if p["n_tier1"] <= 2
                 else "3-5" if p["n_tier1"] <= 5 else "6+")
            by.setdefault(b, []).append((r, p))
        print("   by tier-1 precedent count:")
        t6["by_precedent"] = {}
        for b, v in sorted(by.items()):
            mae = st.mean([abs(p["duration"] - r["duration_min"]) * 60
                           for r, p in v])
            c = sum(1 for r, p in v if p["lo"] <= r["duration_min"] <= p["hi"]) / len(v)
            t6["by_precedent"][b] = {"n": len(v), "mae_s": mae, "coverage": c}
            print("      %-5s n=%2d  MAE %6.1f s  coverage %.2f" % (b, len(v), mae, c))
    out["table6_uncertainty"] = t6

    # ---------------- Table 7: cell-level expected-outcome ranking ----------
    print()
    print("=" * 78)
    print("TABLE 7  Cell-level expected-outcome ranking  (NOT counterfactual regret)")
    print("=" * 78)
    by_fault = {}
    for r, p in preds:
        by_fault.setdefault(r["fault"], {}).setdefault(r["action"], []).append((r, p))
    t7 = {"note": "cell means over repeated real incidents; censored cells are "
                  "lower bounds, which only compresses ineffective cells downward",
          "faults": {}}
    correct = total = 0
    for f, acts in sorted(by_fault.items()):
        if len(acts) < 2:
            continue
        obs_mean = {a: st.mean([r["duration_min"] * 60 for r, _ in v])
                    for a, v in acts.items()}
        pred_mean = {a: st.mean([p["duration"] * 60 for _, p in v])
                     for a, v in acts.items()}
        ncen = {a: sum(1 for r, _ in v if r.get("censored")) for a, v in acts.items()}
        best_obs = min(obs_mean, key=obs_mean.get)
        best_pred = min(pred_mean, key=pred_mean.get)
        ok = best_obs == best_pred
        correct += int(ok)
        total += 1
        # pairwise concordance over the cells of this fault
        acts_l = sorted(acts)
        conc = tot = 0
        for i in range(len(acts_l)):
            for j in range(i + 1, len(acts_l)):
                a1, a2 = acts_l[i], acts_l[j]
                tot += 1
                if (obs_mean[a1] < obs_mean[a2]) == (pred_mean[a1] < pred_mean[a2]):
                    conc += 1
        t7["faults"][f] = {"observed_mean_s": obs_mean, "predicted_mean_s": pred_mean,
                           "n_per_cell": {a: len(v) for a, v in acts.items()},
                           "censored_per_cell": ncen,
                           "best_observed": best_obs, "best_predicted": best_pred,
                           "top1_correct": ok,
                           "pairwise_concordance": conc / tot if tot else None}
        print("   %s" % f)
        for a in acts_l:
            print("      %-16s n=%d cens=%d  observed %7.1f s   predicted %7.1f s"
                  % (a, len(acts[a]), ncen[a], obs_mean[a], pred_mean[a]))
        print("      best observed=%s  best predicted=%s  -> %s ; pairwise %.2f"
              % (best_obs, best_pred, "CORRECT" if ok else "WRONG",
                 conc / tot if tot else 0))
    t7["top1_correct"] = correct
    t7["n_faults_ranked"] = total
    print("   top-1 correct in %d/%d fault groups" % (correct, total))
    out["table7_ranking"] = t7

    json.dump(out, open(os.path.join(RES, "v1r_analysis.json"), "w"),
              indent=2, default=float)
    print("\nwrote realworld/results/v1r_analysis.json")
    try:
        make_plots(preds, unc, obs_edges, learned, out)
    except Exception as ex:
        print("plot generation failed:", ex)
    return 0


def make_plots(preds, unc, obs_edges, learned, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    ob = [r["duration_min"] * 60 for r, _ in preds]
    pr = [p["duration"] * 60 for _, p in preds]
    cen = [r.get("censored", False) for r, _ in preds]
    ax[0].scatter([o for o, c in zip(ob, cen) if not c],
                  [p for p, c in zip(pr, cen) if not c], s=34, label="uncensored")
    ax[0].scatter([o for o, c in zip(ob, cen) if c],
                  [p for p, c in zip(pr, cen) if c], s=34, marker="x",
                  label="censored (lower bound)")
    lim = max(ob + pr) * 1.05
    ax[0].plot([0, lim], [0, lim], "k--", lw=1)
    ax[0].set_xlabel("observed duration (s)")
    ax[0].set_ylabel("predicted duration (s)")
    ax[0].set_title("Predicted vs observed")
    ax[0].legend(fontsize=7)

    allp = [v for vs in obs_edges.values() for v in vs]
    if allp:
        ax[1].hist(allp, bins=20)
        ax[1].set_xlabel("propagation delay (ms)")
        ax[1].set_ylabel("count")
        ax[1].set_title("Observed propagation delays")

    if unc:
        conf = [p["confidence"] for _, p in unc]
        ae = [abs(p["duration"] - r["duration_min"]) * 60 for r, p in unc]
        ax[2].scatter(conf, ae, s=34)
        ax[2].set_xlabel("confidence")
        ax[2].set_ylabel("absolute error (s)")
        ax[2].set_title("Confidence vs error")
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "fig_v1r_summary.png"), dpi=160)
    plt.close(fig)
    print("wrote realworld/results/fig_v1r_summary.png")


if __name__ == "__main__":
    sys.exit(main())
