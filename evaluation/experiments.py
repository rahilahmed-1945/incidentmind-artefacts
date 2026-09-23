"""
IncidentMind evaluation protocol.

Splits are disjoint at the incident level and drawn from independent random
streams.  Hyper-parameters are selected on VALIDATION only; TEST is scored once
per configuration.  The estimator's incident memory contains TRAIN records only,
so no test incident can be retrieved as its own precedent, and counterfactual
ground truth is produced by the frozen environment, never by the estimator.

Run:  python experiments.py
Outputs: results/results.json, results/tables.md, results/fig_*.png
"""
import json
import os
import time

import numpy as np

import metrics as M
from baselines import ALL_BASELINES, Oracle
from environment import (ACTIONS, FAULTS, Realisation, Topology, _layered_topology,
                         build_topologies, generate_corpus, set_spread_form, spec_hash)
from estimator import (IncidentMemory, IncidentMindEstimator, _law, predict_affected,
                       reachable)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
os.makedirs(OUT, exist_ok=True)

N_TRAIN, N_VAL, N_TEST = 1500, 500, 600
SEED_TRAIN, SEED_VAL, SEED_TEST = 101, 202, 303
N_ALT_ACTIONS = 4
# sizes for the heavier sweeps (overridable by the smoke test)
SCALE_CORPUS = (250, 500, 1000, 2000, 4000, 8000)
SCALE_TOPOS = (14, 41, 100, 500, 1000, 2500, 5000)
MISSPEC_N = (800, 250, 250)
MISSPEC_FORMS = ("linear", "quadratic", "exponential", "sqrt")
RESULTS = {}


def set_hp(mem, **kw):
    mem.hp.update(kw)
    mem._sim_cache.clear()
    mem._ctx_cache.clear()


def candidate_grid(entry, rng):
    """Candidate recovery decisions (A, tau) evaluated for one incident."""
    rec = entry["record"]
    fact_a, fact_t = rec["action"], rec["tau"]
    others = [a for a in ACTIONS if a != fact_a]
    alts = [str(a) for a in rng.choice(others, size=N_ALT_ACTIONS - 1, replace=False)]
    taus = [max(0.5, fact_t * 0.25), max(0.5, fact_t * 0.5), fact_t,
            min(30.0, fact_t * 1.75)]
    return [(a, float(t)) for a in [fact_a] + alts for t in taus]


def evaluate(method, data, use_oracle=False, seed=0, limit=None):
    """Score one method over the counterfactual grid of every incident."""
    rng = np.random.default_rng(seed)
    items = data if limit is None else data[:limit]
    yd, pd_, yb, pb, lo, hi, conf = [], [], [], [], [], [], []
    jac, f1s, per_inc = [], [], []
    for i, e in enumerate(items):
        rec, real = e["record"], e["realisation"]
        tv, pv = [], []
        for (a, t) in candidate_grid(e, np.random.default_rng(1000 + i)):
            gt = real.outcome(a, t)
            pr = (method.estimate_with_realisation(real, a, t) if use_oracle
                  else method.estimate(rec["topology"], rec["fault"], rec["origin"], a, t))
            yd.append(gt["duration"]); pd_.append(pr["duration"])
            yb.append(gt["blast"]); pb.append(pr["blast"])
            lo.append(pr["lo"]); hi.append(pr["hi"]); conf.append(pr["confidence"])
            s = M.set_scores(gt["affected"], pr["affected"])
            jac.append(s["jaccard"]); f1s.append(s["f1"])
            tv.append(gt["duration"]); pv.append(pr["duration"])
        r = M.ranking_scores(tv, pv, rng)
        if r:
            per_inc.append(r)
    yd, pd_ = np.array(yd), np.array(pd_)
    yb, pb = np.array(yb), np.array(pb)
    out = {
        "n_pred": int(len(yd)),
        "dur_mae": M.mae(yd, pd_), "dur_rmse": M.rmse(yd, pd_),
        "dur_mape": M.mape(yd, pd_), "dur_smape": M.smape(yd, pd_),
        "blast_mae": M.mae(yb, pb), "blast_rmse": M.rmse(yb, pb),
        "jaccard": float(np.mean(jac)), "set_f1": float(np.mean(f1s)),
        "coverage": M.coverage(yd, lo, hi),
        "top1": float(np.mean([p["top1"] for p in per_inc])),
        "pairwise": float(np.mean([p["pairwise"] for p in per_inc])),
        "kendall": float(np.mean([p["kendall"] for p in per_inc])),
        "regret": float(np.mean([p["regret"] for p in per_inc])),
        "regret_norm": float(np.mean([p["regret_norm"] for p in per_inc])),
    }
    raw = {"abs_err": np.abs(yd - pd_), "abs_err_blast": np.abs(yb - pb),
           "conf": np.array(conf), "y": yd, "p": pd_,
           "regret": np.array([p["regret"] for p in per_inc]),
           "top1": np.array([p["top1"] for p in per_inc])}
    return out, raw


# --------------------------------------------------------------------------
def calibrate(mem, est, val, quick=False, stages=("prop", "retr", "cost", "conf", "z")):
    """
    Staged selection on VALIDATION.
      stage 1  propagation parameters (clag_scale, theta) -> blast-radius error
      stage 2  recovery-cost parameters (beta, lam_blend) -> duration error
      stage 3  interval multiplier z -> 80% nominal coverage
    """
    lim = 120 if quick else 200
    trace = []
    best, bs = (mem.hp["clag_scale"], mem.hp["theta"]), np.inf
    for cs in ((0.6, 0.8, 1.0, 1.3, 1.6) if "prop" in stages else ()):
        for th in (0.30, 0.45, 0.60):
            set_hp(mem, clag_scale=cs, theta=th)
            r, _ = evaluate(est, val, seed=5, limit=lim)
            trace.append({"stage": 1, "clag_scale": cs, "theta": th,
                          "blast_mae": r["blast_mae"], "jaccard": r["jaccard"]})
            if r["blast_mae"] < bs:
                bs, best = r["blast_mae"], (cs, th)
    set_hp(mem, clag_scale=best[0], theta=best[1])

    bestr, bsr = (mem.hp["m_relax"], mem.hp["tier_penalty"]), np.inf
    for mr in ((1, 2, 3, 5, 8) if "retr" in stages else ()):
        for tp in (0.05, 0.15, 0.25, 0.5, 1.0):
            set_hp(mem, m_relax=mr, tier_penalty=tp)
            r, _ = evaluate(est, val, seed=5, limit=lim)
            trace.append({"stage": "1b", "m_relax": mr, "tier_penalty": tp,
                          "dur_mae": r["dur_mae"]})
            if r["dur_mae"] < bsr:
                bsr, bestr = r["dur_mae"], (mr, tp)
    set_hp(mem, m_relax=bestr[0], tier_penalty=bestr[1])

    best2, bs2 = (mem.hp["beta"], mem.hp["lam_blend"]), np.inf
    for beta in ((0.3, 0.6, 0.9, 1.3) if "cost" in stages else ()):
        for lam in (0.0, 0.25, 0.5, 0.75, 1.0):
            set_hp(mem, beta=beta, lam_blend=lam)
            r, _ = evaluate(est, val, seed=5, limit=lim)
            trace.append({"stage": 2, "beta": beta, "lam_blend": lam,
                          "dur_mae": r["dur_mae"], "top1": r["top1"]})
            if r["dur_mae"] < bs2:
                bs2, best2 = r["dur_mae"], (beta, lam)
    set_hp(mem, beta=best2[0], lam_blend=best2[1])

    # conflict threshold: smallest separation whose false-flag rate on clean
    # validation data stays at or below the target
    target, chosen = 0.08, mem.hp["conflict_sep"]
    for sep in ((1.6, 2.5, 3.0, 3.5, 4.5, 6.0, 8.0) if "conf" in stages else ()):
        set_hp(mem, conflict_sep=sep)
        nfl = ntot = 0
        for i, e in enumerate(val[:lim]):
            rec = e["record"]
            for (a, t) in candidate_grid(e, np.random.default_rng(1000 + i)):
                nfl += int(est.estimate(rec["topology"], rec["fault"],
                                        rec["origin"], a, t)["conflict"])
                ntot += 1
        rate = nfl / max(1, ntot)
        trace.append({"stage": "2b", "conflict_sep": sep, "flag_rate": rate})
        if rate <= target:
            chosen = sep
            break
    set_hp(mem, conflict_sep=chosen)

    bz, bg = mem.hp["z"], np.inf
    for z in ((0.8, 1.0, 1.28, 1.6, 2.0, 2.5, 3.0, 3.6) if "z" in stages else ()):
        set_hp(mem, z=z)
        r, _ = evaluate(est, val, seed=5, limit=lim)
        trace.append({"stage": 3, "z": z, "coverage": r["coverage"]})
        if abs(r["coverage"] - 0.80) < bg:
            bg, bz = abs(r["coverage"] - 0.80), z
    set_hp(mem, z=bz)
    return {"clag_scale": best[0], "theta": best[1], "m_relax": bestr[0],
            "tier_penalty": bestr[1], "beta": best2[0], "lam_blend": best2[1],
            "conflict_sep": chosen, "z": bz, "val_blast_mae": bs,
            "val_dur_mae": bs2, "trace": trace}


# --------------------------------------------------------------------------
def make_tables(R):
    L = []
    a = L.append
    s = R["setup"]
    a("# IncidentMind -- measured evaluation results\n")
    a("Environment spec hash `{}`; train/val/test = {}/{}/{} incidents; "
      "{} candidate decisions per test incident.\n".format(
          s["spec_hash"], s["n_train"], s["n_val"], s["n_test"],
          s["candidates_per_incident"]))

    a("\n## Table A. Main comparison (test set)\n")
    a("| Method | Dur MAE (min) | Dur RMSE | MAPE (%) | Blast MAE | Jaccard | "
      "Set F1 | Top-1 (%) | Pairwise (%) | Kendall tau | Regret (min) |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for n, r in R["E1_main"].items():
        a("| {} | {:.2f} | {:.2f} | {:.1f} | {:.2f} | {:.3f} | {:.3f} | {:.1f} | "
          "{:.1f} | {:.3f} | {:.2f} |".format(
              n, r["dur_mae"], r["dur_rmse"], r["dur_mape"], r["blast_mae"],
              r["jaccard"], r["set_f1"], 100 * r["top1"], 100 * r["pairwise"],
              r["kendall"], r["regret"]))

    a("\n## Table B. Significance vs IncidentMind (paired, n={} predictions)\n"
      .format(R["E1_main"]["IncidentMind"]["n_pred"]))
    a("| Baseline | dMAE | 95% CI | Wilcoxon p | Cliff's delta | dRegret |")
    a("|---|---|---|---|---|---|")
    for n, v in R["E2_significance"].items():
        a("| {} | {:+.2f} | [{:+.2f}, {:+.2f}] | {} | {:+.3f} | {:+.2f} |".format(
            n, v["delta_mae"], v["ci_lo"], v["ci_hi"], M.fmt_p(v["wilcoxon_p"]),
            v["cliffs_delta"], v["regret_delta"]))

    a("\n## Table C. Ablation\n")
    a("| Configuration | Dur MAE | Blast MAE | Jaccard | Top-1 (%) | Regret |")
    a("|---|---|---|---|---|---|")
    for n, r in R["E3_ablation"].items():
        a("| {} | {:.2f} | {:.2f} | {:.3f} | {:.1f} | {:.2f} |".format(
            n, r["dur_mae"], r["blast_mae"], r["jaccard"], 100 * r["top1"], r["regret"]))

    a("\n## Table D. Precedent sparsity\n")
    a("| Retrieved precedents | n | Dur MAE | Mean confidence |")
    a("|---|---|---|---|")
    for k, v in R["E5_generalisation"]["by_precedent_count"].items():
        a("| {} | {} | {:.2f} | {:.3f} |".format(k, v["n"], v["mae"], v["mean_conf"]))

    a("\n## Table E. Unseen fault types (leave-one-fault-out)\n")
    a("| Fault held out of memory | n | MAE (seen) | MAE (unseen) | Top-1 seen | Top-1 unseen |")
    a("|---|---|---|---|---|---|")
    for f, v in R["E5_generalisation"]["leave_one_fault_out"].items():
        a("| {} | {} | {:.2f} | {:.2f} | {:.1f} | {:.1f} |".format(
            f, v["n"], v["mae_seen"], v["mae_unseen"], 100 * v["top1_seen"],
            100 * v["top1_unseen"]))

    a("\n## Table F. Contradictory precedent\n")
    a("| Contradiction rate | Dur MAE | Top-1 (%) | Coverage | Conflict flagged | Mean confidence |")
    a("|---|---|---|---|---|---|")
    for v in R["E6_contradiction"]["sweep"]:
        a("| {:.0%} | {:.2f} | {:.1f} | {:.3f} | {:.3f} | {:.3f} |".format(
            v["rate"], v["dur_mae"], 100 * v["top1"], v["coverage"],
            v["conflict_flag_rate"], v["mean_confidence"]))
    a("\nSquared-loss fit at 20% contradiction: MAE {:.2f} (robust loss {:.2f}).\n".format(
        R["E6_contradiction"]["squared_loss_at_20pct"],
        [v for v in R["E6_contradiction"]["sweep"] if v["rate"] == 0.20][0]["dur_mae"]))

    a("\n## Table G. Confidence behaviour by operating regime\n")
    c = R["E7_calibration"]
    a("| Regime | n | Duration MAE | Mean confidence |")
    a("|---|---|---|---|")
    for k, v in c["per_regime"].items():
        a("| {} | {} | {:.2f} | {:.3f} |".format(k, v["n"], v["mae"], v["mean_conf"]))
    a("")
    a("Within the dense-precedent test population rho(confidence, |error|) = {:.3f} "
      "(p {}), and against relative error {:.3f}; the oracle noise floor is {:.2f} min "
      "against IncidentMind's {:.2f} min, so within-regime error is predominantly "
      "irreducible. Pooled across all regimes rho = {:.3f} (p {}), with tercile MAE "
      "{:.2f} / {:.2f} / {:.2f} min from lowest to highest confidence. Empirical "
      "coverage of the nominal 80% interval is {:.3f}.\n".format(
          c["spearman_rho"], M.fmt_p(c["p_value"]), c["spearman_rho_relative"],
          c["oracle_mae"], R["E1_main"]["IncidentMind"]["dur_mae"],
          c["pooled_spearman_rho"], M.fmt_p(c["pooled_p_value"]),
          *c["pooled_tercile_mae"], c["coverage_nominal80"]))

    a("\n## Table H. Robustness to degraded telemetry\n")
    a("| Timestamp jitter (sigma) | Event drop | Dur MAE | Blast MAE | Jaccard | Top-1 (%) |")
    a("|---|---|---|---|---|---|")
    for v in R["E8_noise"]:
        a("| {:.2f} | {:.0%} | {:.2f} | {:.2f} | {:.3f} | {:.1f} |".format(
            v["timestamp_jitter"], v["event_drop"], v["dur_mae"], v["blast_mae"],
            v["jaccard"], 100 * v["top1"]))

    a("\n## Table I. Scalability\n")
    a("| Corpus size | Index build (s) | ms / what-if query |")
    a("|---|---|---|")
    for v in R["E9_scalability"]["corpus"]:
        a("| {} | {:.2f} | {:.2f} |".format(v["n"], v["index_build_s"], v["ms_per_query"]))
    a("\n| Topology size (services) | Edges | ms / propagation traversal |")
    a("|---|---|---|")
    for v in R["E9_scalability"]["topology"]:
        a("| {} | {} | {:.3f} |".format(v["nodes"], v["edges"], v["ms_per_traversal"]))

    a("\n## Table J. Misspecified recovery-cost law\n")
    a("| Generative spread law | IncidentMind MAE | Best baseline MAE | B2 MAE | IM Top-1 (%) |")
    a("|---|---|---|---|---|")
    for v in R["E11_misspecification"]:
        a("| {} | {:.2f} | {:.2f} ({}) | {:.2f} | {:.1f} |".format(
            v["form"], v["im_mae"], v["best_baseline_mae"], v["best_baseline"],
            v["b2_mae"], 100 * v["im_top1"]))

    a("\n## Table K. Seven case-study scenarios (held out, with ground truth)\n")
    a("| # | Scenario | Decision | tau | Pred dur | True dur | Pred blast | True blast | "
      "Jaccard | Conf |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(R["E10_cases"], 1):
        for j, r in enumerate(c["rows"]):
            lbl = "baseline" if j == 0 else "alt " + str(j)
            a("| {} | {} | {} ({}) | {:.0f} | {:.1f} | {:.1f} | {} | {} | {:.2f} | {:.2f} |".format(
                i if j == 0 else "", c["scenario"] if j == 0 else "",
                r["action"], lbl, r["tau"], r["pred_duration"], r["true_duration"],
                r["pred_blast"], r["true_blast"], r["jaccard"], r["confidence"]))
    ok = sum(c["ranking_correct"] for c in R["E10_cases"])
    a("\nCorrect identification of the best of three decisions: {}/{} scenarios.\n"
      .format(ok, len(R["E10_cases"])))

    with open(os.path.join(OUT, "tables.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print("wrote results/tables.md")


def make_figures(R, mem, im, topos, test):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Fig 1: fitted timing-duration law against precedent and ground truth
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    e = test[0]
    rec = e["record"]
    idx, sims, ctier, tier = mem.retrieve(rec["topology"], rec["fault"],
                                          rec["origin"], rec["action"])
    ctx = im._context(rec["topology"], rec["fault"], rec["origin"], rec["action"])
    ts = np.linspace(0.5, 20, 60)
    if idx.size:
        ax[0].scatter(mem.col_tau[idx], mem.col_dur[idx] - mem.col_tau[idx], s=26,
                      alpha=0.7, label="retrieved precedent")
    ax[0].plot(ts, _law(ctx["params"], ts), lw=2, label="fitted law r(tau)")
    ax[0].set_xlabel("intervention timing tau (min)")
    ax[0].set_ylabel("post-action recovery r (min)")
    ax[0].set_title("Timing-duration law (Step 2)")
    ax[0].legend(fontsize=7)

    real = e["realisation"]
    true_d = [real.outcome(rec["action"], t)["duration"] for t in ts]
    pred = [im.estimate(rec["topology"], rec["fault"], rec["origin"], rec["action"], t)
            for t in ts]
    ax[1].plot(ts, true_d, lw=2, label="ground truth")
    ax[1].plot(ts, [p["duration"] for p in pred], lw=2, ls="--", label="IncidentMind")
    ax[1].fill_between(ts, [p["lo"] for p in pred], [p["hi"] for p in pred],
                       alpha=0.18, label="80% interval")
    ax[1].set_xlabel("intervention timing tau (min)")
    ax[1].set_ylabel("incident duration D (min)")
    ax[1].set_title("Predicted vs actual duration")
    ax[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_law.png"), dpi=160)
    plt.close(fig)

    # Fig 2: learning curve + sensitivity to k
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.4))
    lc = R["E4_sensitivity"]["corpus"]
    ax[0].plot([v["n"] for v in lc], [v["dur_mae"] for v in lc], "o-", label="IncidentMind")
    ax[0].plot([v["n"] for v in lc], [v["knn_dur_mae"] for v in lc], "s--",
               label="B5 precedent k-NN")
    ax[0].set_xscale("log"); ax[0].set_xlabel("precedent corpus size")
    ax[0].set_ylabel("duration MAE (min)"); ax[0].set_title("Learning curve")
    ax[0].legend(fontsize=7)

    ks = R["E4_sensitivity"]["k"]
    ax[1].plot([v["k"] for v in ks], [v["dur_mae"] for v in ks], "o-")
    ax[1].set_xlabel("retrieved precedents k"); ax[1].set_ylabel("duration MAE (min)")
    ax[1].set_title("Sensitivity to k")

    sw = R["E6_contradiction"]["sweep"]
    ax[2].plot([v["rate"] for v in sw], [v["dur_mae"] for v in sw], "o-", label="MAE")
    ax2 = ax[2].twinx()
    ax2.plot([v["rate"] for v in sw], [v["mean_confidence"] for v in sw], "s--",
             color="tab:red", label="mean confidence")
    ax[2].set_xlabel("contradictory precedent rate")
    ax[2].set_ylabel("duration MAE (min)")
    ax2.set_ylabel("mean confidence")
    ax[2].set_title("Contradictory precedent")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_sensitivity.png"), dpi=160)
    plt.close(fig)

    # Fig 3: calibration
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    bins = R["E7_calibration"]["bins"]
    ax[0].plot([b["conf"] for b in bins], [b["mae"] for b in bins], "o-")
    ax[0].set_xlabel("confidence score"); ax[0].set_ylabel("duration MAE (min)")
    ax[0].set_title("Confidence vs error")
    names = list(R["E1_main"].keys())
    vals = [R["E1_main"][n]["dur_mae"] for n in names]
    ax[1].barh(range(len(names)), vals)
    ax[1].set_yticks(range(len(names)))
    ax[1].set_yticklabels(names, fontsize=6)
    ax[1].set_xlabel("duration MAE (min)"); ax[1].set_title("Method comparison")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_calibration.png"), dpi=160)
    plt.close(fig)
    print("wrote results/fig_*.png")


# --------------------------------------------------------------------------
def main():
    t_start = time.time()
    set_spread_form("linear")
    print("environment spec hash:", spec_hash())
    topos = build_topologies()

    print("generating corpora ...")
    train = generate_corpus(topos, N_TRAIN, SEED_TRAIN)
    val = generate_corpus(topos, N_VAL, SEED_VAL)
    test = generate_corpus(topos, N_TEST, SEED_TEST)
    train_rec = [e["record"] for e in train]

    mem = IncidentMemory(topos, train_rec)
    im = IncidentMindEstimator(mem)

    print("calibrating on validation ...")
    cal = calibrate(mem, im, val)
    print("  ->", {k: v for k, v in cal.items() if k != "trace"})
    RESULTS["calibration"] = {k: v for k, v in cal.items() if k != "trace"}
    RESULTS["calibration_trace"] = cal["trace"]
    base_hp = dict(mem.hp)
    RESULTS["setup"] = {
        "spec_hash": spec_hash(), "n_train": N_TRAIN, "n_val": N_VAL, "n_test": N_TEST,
        "topologies": {k: {"nodes": len(t.nodes), "edges": len(t.edges)}
                       for k, t in topos.items()},
        "candidates_per_incident": N_ALT_ACTIONS * 4, "hp": dict(base_hp),
    }

    # ---------------- E1 main comparison ----------------
    print("E1 main comparison ...")
    methods = [("IncidentMind", im, False)]
    for cls in ALL_BASELINES:
        b = cls().fit(mem, train_rec)
        methods.append((b.name, b, False))
    methods.append(("Oracle (noise floor)", Oracle().fit(mem, train_rec), True))
    e1, raws = {}, {}
    for name, meth, is_or in methods:
        t0 = time.time()
        r, raw = evaluate(meth, test, use_oracle=is_or, seed=1)
        r["eval_seconds"] = round(time.time() - t0, 2)
        e1[name], raws[name] = r, raw
        print("   {:24s} MAE={:5.2f} blast={:4.2f} J={:.3f} top1={:.3f} regret={:5.2f}"
              .format(name, r["dur_mae"], r["blast_mae"], r["jaccard"], r["top1"],
                      r["regret"]))
    RESULTS["E1_main"] = e1

    # ---------------- E2 significance ----------------
    print("E2 significance ...")
    ref = raws["IncidentMind"]
    e2 = {}
    for name in e1:
        if name == "IncidentMind":
            continue
        a, b = raws[name]["abs_err"], ref["abs_err"]
        bs = M.paired_bootstrap(a, b)
        e2[name] = {"delta_mae": bs["delta"], "ci_lo": bs["ci_lo"], "ci_hi": bs["ci_hi"],
                    "wilcoxon_p": M.wilcoxon(a, b)["p"],
                    "cliffs_delta": M.cliffs_delta(a, b),
                    "regret_delta": float(np.mean(raws[name]["regret"] - ref["regret"]))}
    RESULTS["E2_significance"] = e2

    # ---------------- E3 ablation ----------------
    print("E3 ablations ...")
    e3 = {}
    for label, kw in [
            ("Full mechanism", {}),
            ("without timing-duration law (Step 2)", {"use_law": False}),
            ("without dependency route (Step 3)", {"use_dep": False}),
            ("structural route only", {"lam_blend": 1.0}),
            ("without tiered relaxation (Step 1)", {"use_tiers": False}),
            ("without robust loss", {"robust": False})]:
        set_hp(mem, **base_hp)
        set_hp(mem, **kw)
        r, _ = evaluate(im, test, seed=1)
        e3[label] = {k: r[k] for k in ("dur_mae", "dur_rmse", "blast_mae", "jaccard",
                                       "top1", "regret", "coverage")}
        print("   {:40s} MAE={:5.2f} top1={:.3f}".format(label, r["dur_mae"], r["top1"]))
    set_hp(mem, **base_hp)
    RESULTS["E3_ablation"] = e3

    # ---------------- E4 sensitivity ----------------
    print("E4 sensitivity ...")
    e4 = {"k": [], "m_min": [], "temp": [], "beta": [], "lam_blend": [], "corpus": []}
    for k in (1, 3, 5, 8, 12, 20, 40):
        set_hp(mem, k=k)
        r, _ = evaluate(im, test, seed=1, limit=250)
        e4["k"].append({"k": k, "dur_mae": r["dur_mae"], "top1": r["top1"],
                        "regret": r["regret"]})
    set_hp(mem, **base_hp)
    for t in (0.05, 0.10, 0.18, 0.30, 0.60, 1.20):
        set_hp(mem, temp=t)
        r, _ = evaluate(im, test, seed=1, limit=250)
        e4["temp"].append({"temp": t, "dur_mae": r["dur_mae"], "top1": r["top1"]})
    set_hp(mem, **base_hp)
    for b in (0.3, 0.6, 0.9, 1.3, 1.8):
        set_hp(mem, beta=b)
        r, _ = evaluate(im, test, seed=1, limit=250)
        e4["beta"].append({"beta": b, "dur_mae": r["dur_mae"], "blast_mae": r["blast_mae"]})
    set_hp(mem, **base_hp)
    for lam in (0.0, 0.25, 0.5, 0.75, 1.0):
        set_hp(mem, lam_blend=lam)
        r, _ = evaluate(im, test, seed=1, limit=250)
        e4["lam_blend"].append({"lam": lam, "dur_mae": r["dur_mae"], "top1": r["top1"]})
    set_hp(mem, **base_hp)
    for mm in (2, 3, 5, 8, 12):
        set_hp(mem, m_min=mm)
        r, _ = evaluate(im, test, seed=1, limit=250)
        e4["m_min"].append({"m_min": mm, "dur_mae": r["dur_mae"], "top1": r["top1"]})
    set_hp(mem, **base_hp)
    for n in (50, 100, 250, 500, 1000, 1500):
        sub = train_rec[:n]
        m2 = IncidentMemory(topos, sub, hp=base_hp)
        r, _ = evaluate(IncidentMindEstimator(m2), test, seed=1, limit=250)
        knn = [c for c in ALL_BASELINES if c.__name__ == "PrecedentKNN"][0]().fit(m2, sub)
        rk, _ = evaluate(knn, test, seed=1, limit=250)
        e4["corpus"].append({"n": n, "dur_mae": r["dur_mae"], "top1": r["top1"],
                             "knn_dur_mae": rk["dur_mae"], "coverage": r["coverage"]})
        print("   corpus n={:5d} MAE={:5.2f} (kNN {:5.2f})".format(n, r["dur_mae"],
                                                                   rk["dur_mae"]))
    RESULTS["E4_sensitivity"] = e4

    # ---------------- E5 sparsity + generalisation ----------------
    print("E5 sparse precedent and generalisation ...")
    e5, strat = {}, {}
    regime_raw = {"unseen_fault": [], "unseen_topology": [],
                  "contradictory": []}
    for i, e in enumerate(test):
        rec, real = e["record"], e["realisation"]
        for (a, t) in candidate_grid(e, np.random.default_rng(1000 + i)):
            pr = im.estimate(rec["topology"], rec["fault"], rec["origin"], a, t)
            gt = real.outcome(a, t)
            n = pr["n_precedent"]
            b = ("0" if n == 0 else "1-2" if n <= 2 else "3-4" if n <= 4
                 else "5-8" if n <= 8 else "9+")
            d = strat.setdefault(b, {"e": [], "c": []})
            d["e"].append(abs(gt["duration"] - pr["duration"]))
            d["c"].append(pr["confidence"])
    e5["by_precedent_count"] = {k: {"n": len(v["e"]), "mae": float(np.mean(v["e"])),
                                    "mean_conf": float(np.mean(v["c"]))}
                                for k, v in sorted(strat.items())}

    lofo = {}
    for f in FAULTS:
        held = [e for e in test if e["record"]["fault"] == f]
        if len(held) < 10:
            continue
        sub = [r for r in train_rec if r["fault"] != f]
        m3 = IncidentMemory(topos, sub, hp=base_hp)
        r_h, raw_h = evaluate(IncidentMindEstimator(m3), held, seed=1)
        regime_raw["unseen_fault"].append(raw_h)
        r_f, _ = evaluate(im, held, seed=1)
        lofo[f] = {"n": len(held), "mae_unseen": r_h["dur_mae"], "mae_seen": r_f["dur_mae"],
                   "top1_unseen": r_h["top1"], "top1_seen": r_f["top1"]}
        print("   LOFO {:22s} MAE {:5.2f} -> {:5.2f}".format(f, r_f["dur_mae"],
                                                              r_h["dur_mae"]))
    e5["leave_one_fault_out"] = lofo

    sub = [r for r in train_rec if r["topology"] != "clinical"]
    m4 = IncidentMemory(topos, sub, hp=base_hp)
    i4 = IncidentMindEstimator(m4)
    clin = [e for e in test if e["record"]["topology"] == "clinical"]
    r_un, raw_un = evaluate(i4, clin, seed=1)
    regime_raw["unseen_topology"].append(raw_un)
    r_se, _ = evaluate(im, clin, seed=1)
    b_un = [c for c in ALL_BASELINES if c.__name__ == "ActionMean"][0]().fit(m4, sub)
    r_b, _ = evaluate(b_un, clin, seed=1)
    lam_un = []
    for lam in (0.0, 0.5, 1.0):
        set_hp(m4, lam_blend=lam)
        rr, _ = evaluate(i4, clin, seed=1)
        lam_un.append({"lam": lam, "dur_mae": rr["dur_mae"]})
    set_hp(m4, **base_hp)
    e5["unseen_topology_clinical"] = {
        "n": len(clin), "mae_unseen": r_un["dur_mae"], "mae_seen": r_se["dur_mae"],
        "top1_unseen": r_un["top1"], "top1_seen": r_se["top1"],
        "baseline_mae_unseen": r_b["dur_mae"], "baseline_top1_unseen": r_b["top1"],
        "lam_sweep_unseen": lam_un}
    print("   unseen topology MAE {:5.2f} (in-domain {:5.2f}, B2 {:5.2f})".format(
        r_un["dur_mae"], r_se["dur_mae"], r_b["dur_mae"]))
    RESULTS["E5_generalisation"] = e5

    # ---------------- E6 contradictory precedent ----------------
    print("E6 contradictory precedent ...")
    e6 = []
    for rate in (0.0, 0.05, 0.10, 0.20, 0.30, 0.40):
        rng = np.random.default_rng(77)
        corrupt = []
        for r in train_rec:
            r2 = dict(r)
            if rng.random() < rate:
                r2["duration"] = float(r["duration"] * rng.choice([0.35, 2.6]))
            corrupt.append(r2)
        m5 = IncidentMemory(topos, corrupt, hp=base_hp)
        i5 = IncidentMindEstimator(m5)
        r, raw_c = evaluate(i5, test, seed=1, limit=250)
        if rate >= 0.30:
            regime_raw["contradictory"].append(raw_c)
        nconf, tot, cs = 0, 0, []
        for i, e in enumerate(test[:250]):
            rec = e["record"]
            for (a, t) in candidate_grid(e, np.random.default_rng(1000 + i)):
                pr = i5.estimate(rec["topology"], rec["fault"], rec["origin"], a, t)
                nconf += int(pr["conflict"]); tot += 1; cs.append(pr["confidence"])
        e6.append({"rate": rate, "dur_mae": r["dur_mae"], "top1": r["top1"],
                   "coverage": r["coverage"], "conflict_flag_rate": nconf / max(1, tot),
                   "mean_confidence": float(np.mean(cs))})
        print("   contradiction {:.0%}: MAE={:5.2f} flag={:.3f} conf={:.3f}".format(
            rate, r["dur_mae"], nconf / max(1, tot), float(np.mean(cs))))
    rng = np.random.default_rng(77)
    corrupt = []
    for r in train_rec:
        r2 = dict(r)
        if rng.random() < 0.20:
            r2["duration"] = float(r["duration"] * rng.choice([0.35, 2.6]))
        corrupt.append(r2)
    m6 = IncidentMemory(topos, corrupt, hp=dict(base_hp, robust=False))
    r_sq, _ = evaluate(IncidentMindEstimator(m6), test, seed=1, limit=250)
    RESULTS["E6_contradiction"] = {"sweep": e6, "squared_loss_at_20pct": r_sq["dur_mae"]}

    # ---------------- E7 calibration ----------------
    print("E7 calibration ...")
    diag = M.confidence_diagnostics(ref["conf"], ref["abs_err"])
    rel = ref["abs_err"] / np.maximum(ref["y"], 1e-9)
    diag_rel = M.confidence_diagnostics(ref["conf"], rel)

    # Pooled across operating regimes: dense precedent, unseen fault type,
    # unseen topology, contradictory precedent.  This is the population over
    # which a confidence score must discriminate operationally.
    pool_c, pool_e, per_regime = [list(ref["conf"])], [list(ref["abs_err"])], {}
    per_regime["dense (main test)"] = {
        "mae": float(np.mean(ref["abs_err"])),
        "mean_conf": float(np.mean(ref["conf"])), "n": int(len(ref["conf"]))}
    for label, key in [("unseen fault type", "unseen_fault"),
                       ("unseen topology", "unseen_topology"),
                       ("contradictory precedent", "contradictory")]:
        if not regime_raw[key]:
            continue
        cs = np.concatenate([r["conf"] for r in regime_raw[key]])
        es = np.concatenate([r["abs_err"] for r in regime_raw[key]])
        pool_c.append(list(cs))
        pool_e.append(list(es))
        per_regime[label] = {"mae": float(np.mean(es)),
                             "mean_conf": float(np.mean(cs)), "n": int(cs.size)}
    pc = np.array([v for sub in pool_c for v in sub])
    pe = np.array([v for sub in pool_e for v in sub])
    diag_pool = M.confidence_diagnostics(pc, pe)

    RESULTS["E7_calibration"] = {
        "spearman_rho": diag["spearman_rho"], "p_value": diag["p_value"],
        "tercile_mae": diag["tercile_mae"], "bins": diag["bins"],
        "spearman_rho_relative": diag_rel["spearman_rho"],
        "pooled_spearman_rho": diag_pool["spearman_rho"],
        "pooled_p_value": diag_pool["p_value"],
        "pooled_tercile_mae": diag_pool["tercile_mae"],
        "pooled_bins": diag_pool["bins"],
        "per_regime": per_regime,
        "oracle_mae": e1["Oracle (noise floor)"]["dur_mae"],
        "coverage_nominal80": e1["IncidentMind"]["coverage"],
        "baseline_rho": M.confidence_diagnostics(
            raws["B5 Precedent k-NN"]["conf"], raws["B5 Precedent k-NN"]["abs_err"]
        )["spearman_rho"]}
    print("   within-regime rho={:.3f}  pooled rho={:.3f}  coverage={:.3f}".format(
        diag["spearman_rho"], diag_pool["spearman_rho"],
        e1["IncidentMind"]["coverage"]))
    for k, v in per_regime.items():
        print("      {:26s} n={:5d} MAE={:5.2f} conf={:.3f}".format(
            k, v["n"], v["mae"], v["mean_conf"]))

    # ---------------- E8 telemetry noise ----------------
    print("E8 telemetry noise ...")
    e8 = []
    for jit, drop in [(0.0, 0.0), (0.25, 0.0), (0.5, 0.0), (0.0, 0.1), (0.0, 0.25),
                      (0.5, 0.25)]:
        rng = np.random.default_rng(31)
        noisy = []
        for r in train_rec:
            r2 = dict(r)
            if jit > 0:
                r2["arrivals"] = {s: max(0.0, v * float(np.exp(rng.normal(0, jit))))
                                  for s, v in r["arrivals"].items()}
                r2["tau"] = float(max(0.5, r["tau"] * np.exp(rng.normal(0, jit * 0.5))))
            if drop > 0:
                keep = [s for s in r2["affected"]
                        if rng.random() > drop or s == r["origin"]]
                r2["affected"] = keep
                r2["arrivals"] = {s: v for s, v in r2["arrivals"].items() if s in keep}
                r2["blast"] = max(1, len(keep))
            noisy.append(r2)
        m7 = IncidentMemory(topos, noisy, hp=base_hp)
        r, _ = evaluate(IncidentMindEstimator(m7), test, seed=1, limit=250)
        e8.append({"timestamp_jitter": jit, "event_drop": drop, "dur_mae": r["dur_mae"],
                   "blast_mae": r["blast_mae"], "jaccard": r["jaccard"],
                   "top1": r["top1"]})
        print("   jitter={:.2f} drop={:.2f} MAE={:5.2f} J={:.3f}".format(
            jit, drop, r["dur_mae"], r["jaccard"]))
    RESULTS["E8_noise"] = e8

    # ---------------- E9 scalability ----------------
    print("E9 scalability ...")
    scale = {"corpus": [], "topology": []}
    for n in SCALE_CORPUS:
        rec_big = [e["record"] for e in generate_corpus(topos, n, 909)]
        t0 = time.time()
        mm = IncidentMemory(topos, rec_big, hp=base_hp)
        build_s = time.time() - t0
        ee = IncidentMindEstimator(mm)
        t0, cnt = time.time(), 0
        for i, e in enumerate(test[:60]):
            r0 = e["record"]
            for (a, t) in candidate_grid(e, np.random.default_rng(2000 + i))[:6]:
                ee.estimate(r0["topology"], r0["fault"], r0["origin"], a, t)
                cnt += 1
        ms = (time.time() - t0) * 1000 / cnt
        scale["corpus"].append({"n": n, "index_build_s": round(build_s, 3),
                                "ms_per_query": round(ms, 3)})
        print("   corpus {:5d}: build {:.2f}s  {:.3f} ms/query".format(n, build_s, ms))
    for nn in SCALE_TOPOS:
        nodes, edges = _layered_topology("sc", nn, np.random.default_rng(4242),
                                         width=max(4, nn // 12))
        tp = Topology("sc", nodes, edges, 4242)
        t0, reps = time.time(), 200
        for _ in range(reps):
            visited = predict_affected(mem, tp, nodes[0], 8.0, base_hp["theta"])
        ms = (time.time() - t0) * 1000 / reps
        t0 = time.time()
        for _ in range(reps):
            full = predict_affected(mem, tp, nodes[0], 1e9, 0.0)
        ms_full = (time.time() - t0) * 1000 / reps
        scale["topology"].append({"nodes": nn, "edges": len(edges),
                                  "ms_per_traversal": round(ms, 4),
                                  "nodes_visited": len(visited),
                                  "ms_unbounded": round(ms_full, 4),
                                  "nodes_unbounded": len(full)})
        print("   topology {:5d} nodes: {:.3f} ms/traversal ({} visited); "
              "unbounded {:.3f} ms ({} visited)".format(
                  nn, ms, len(visited), ms_full, len(full)))
    RESULTS["E9_scalability"] = scale

    # ---------------- E10 case studies ----------------
    print("E10 case studies ...")
    CASES = [
        ("Database failure", "db_saturation", "order-db",
         [("pool_restart", 10.0), ("pool_restart", 2.0), ("scale_replicas", 3.0)]),
        ("Service crash", "service_crash", "inventory-service",
         [("pod_restart", 5.0), ("pod_restart", 1.0), ("scale_replicas", 2.0)]),
        ("Network latency", "network_latency", "payment-service",
         [("reroute_traffic", 8.0), ("reroute_traffic", 2.0), ("scale_replicas", 3.0)]),
        ("API timeout cascade", "api_timeout_cascade", "recommendation-service",
         [("circuit_breaker", 6.0), ("circuit_breaker", 1.0), ("rollback_deploy", 3.0)]),
        ("Resource exhaustion", "resource_exhaustion", "search-service",
         [("scale_replicas", 5.0), ("scale_replicas", 1.0), ("rollback_deploy", 4.0)]),
        ("Deployment misconfiguration", "deploy_misconfig", "auth-service",
         [("scale_replicas", 5.0), ("rollback_deploy", 5.0), ("rollback_deploy", 2.0)]),
        ("Cascading dependency failure", "cache_failure", "cache-service",
         [("pod_restart", 9.0), ("pod_restart", 2.0), ("degraded_mode", 3.0)]),
    ]
    topo = topos["ecommerce"]
    cases = []
    for ci, (title, fault, origin, decisions) in enumerate(CASES):
        real = Realisation(topo, fault, origin, 777000 + ci * 37)
        rows = []
        for (a, t) in decisions:
            gt = real.outcome(a, t)
            pr = im.estimate("ecommerce", fault, origin, a, t)
            s = M.set_scores(gt["affected"], pr["affected"])
            rows.append({"action": a, "tau": t,
                         "pred_duration": round(pr["duration"], 1),
                         "true_duration": round(gt["duration"], 1),
                         "pred_blast": pr["blast"], "true_blast": gt["blast"],
                         "jaccard": round(s["jaccard"], 2),
                         "confidence": round(pr["confidence"], 2),
                         "n_precedent": pr["n_precedent"],
                         "pred_services": sorted(pr["affected"]),
                         "true_services": sorted(gt["affected"]),
                         "interval": [round(pr["lo"], 1), round(pr["hi"], 1)]})
        td = [r["true_duration"] for r in rows]
        pdur = [r["pred_duration"] for r in rows]
        cases.append({"scenario": title, "fault": fault, "origin": origin, "rows": rows,
                      "ranking_correct": int(np.argmin(pdur) == np.argmin(td))})
    print("   correct best-of-three: {}/{}".format(
        sum(c["ranking_correct"] for c in cases), len(cases)))
    RESULTS["E10_cases"] = cases

    # ---------------- E11 misspecification ----------------
    print("E11 misspecified recovery-cost law ...")
    e11 = []
    for form in MISSPEC_FORMS:
        set_spread_form(form)
        tr_f = generate_corpus(topos, MISSPEC_N[0], 401)
        va_f = generate_corpus(topos, MISSPEC_N[1], 402)
        te_f = generate_corpus(topos, MISSPEC_N[2], 403)
        rec_f = [e["record"] for e in tr_f]
        mf = IncidentMemory(topos, rec_f, hp=base_hp)
        inf = IncidentMindEstimator(mf)
        calibrate(mf, inf, va_f, quick=True, stages=("cost",))
        r_im, _ = evaluate(inf, te_f, seed=1)
        bl = {}
        for cls in ALL_BASELINES:
            b = cls().fit(mf, rec_f)
            rb, _ = evaluate(b, te_f, seed=1)
            bl[b.name] = rb["dur_mae"]
        bb = min(bl, key=bl.get)
        e11.append({"form": form, "im_mae": r_im["dur_mae"], "im_top1": r_im["top1"],
                    "best_baseline": bb, "best_baseline_mae": bl[bb],
                    "b2_mae": bl["B2 Context-independent"],
                    "all_baselines": bl,
                    "lam_selected": mf.hp["lam_blend"], "beta_selected": mf.hp["beta"]})
        print("   {:12s} IM MAE={:5.2f} top1={:.3f} | best baseline {:5.2f} ({})".format(
            form, r_im["dur_mae"], r_im["top1"], bl[bb], bb))
    set_spread_form("linear")
    RESULTS["E11_misspecification"] = e11

    RESULTS["runtime_seconds"] = round(time.time() - t_start, 1)
    with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(RESULTS, fh, indent=2, default=float)
    make_tables(RESULTS)
    try:
        set_hp(mem, **base_hp)
        make_figures(RESULTS, mem, im, topos, test)
    except Exception as ex:
        print("figure generation failed:", ex)
    print("\ndone in {:.1f}s".format(RESULTS["runtime_seconds"]))
    return RESULTS


if __name__ == "__main__":
    main()
