"""
FINAL, ONE-SHOT A/B/C evaluation on a NEW set of untouched seeds.

    A = original audited mechanism            (commit bdb15df configuration)
    B = novelty-aware fallback                (frozen by dev_novelty.py)
    C = novelty-aware + small-sample dispersion fix (frozen by dev_interval.py)

All three configurations are fixed on entry; nothing here selects a parameter.
The evaluation seeds below have never been generated, inspected or used at any
earlier point in this project. Intended to be run exactly once.

Incident memories are built from the training corpus (seed 101) exactly as in
every previous evaluation; only the evaluation data is new.

Run:  python final_abc_eval.py
Writes: results/final_abc_eval.json, results/fig_abc_*.png
"""
import json
import os
import time

import numpy as np
from scipy import stats

import metrics as M
from environment import FAULTS, build_topologies, generate_corpus
from estimator import IncidentMemory, IncidentMindEstimator
import experiments as X

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")

# Seeds never used anywhere else in this project.
NEW_SEEDS = [700101, 700202, 700303, 700404, 700505, 700606]
N_TEST = 600
CONDS = ["seen", "sparse", "unseen_fault", "unseen_topology"]
TAGS = ["A", "B", "C"]


def detailed_eval(mem, data, hp):
    X.set_hp(mem, **hp)
    est = IncidentMindEstimator(mem)
    rng = np.random.default_rng(1)
    yd, pd_, yb, pb, lo, hi = [], [], [], [], [], []
    conf, nov, n1, jac, per = [], [], [], [], []
    for i, e in enumerate(data):
        rec, real = e["record"], e["realisation"]
        tv, pv = [], []
        for (a, t) in X.candidate_grid(e, np.random.default_rng(1000 + i)):
            gt = real.outcome(a, t)
            pr = est.estimate(rec["topology"], rec["fault"], rec["origin"], a, t)
            yd.append(gt["duration"]); pd_.append(pr["duration"])
            yb.append(gt["blast"]); pb.append(pr["blast"])
            lo.append(pr["lo"]); hi.append(pr["hi"])
            conf.append(pr["confidence"]); nov.append(pr["novelty"])
            n1.append(pr["n_tier1"])
            jac.append(M.set_scores(gt["affected"], pr["affected"])["jaccard"])
            tv.append(gt["duration"]); pv.append(pr["duration"])
        r = M.ranking_scores(tv, pv, rng)
        if r:
            per.append(r)
    yd, pd_, yb, pb = map(np.array, (yd, pd_, yb, pb))
    lo, hi = np.array(lo), np.array(hi)
    res = {"dur_mae": M.mae(yd, pd_), "dur_rmse": M.rmse(yd, pd_),
           "dur_mape": M.mape(yd, pd_), "blast_mae": M.mae(yb, pb),
           "jaccard": float(np.mean(jac)), "coverage": M.coverage(yd, lo, hi),
           "top1": float(np.mean([p["top1"] for p in per])),
           "pairwise": float(np.mean([p["pairwise"] for p in per])),
           "regret": float(np.mean([p["regret"] for p in per])),
           "mean_novelty": float(np.mean(nov))}
    raw = {"abs_err": np.abs(yd - pd_), "conf": np.array(conf),
           "n1": np.array(n1), "nov": np.array(nov),
           "hit": ((yd >= lo) & (yd <= hi)).astype(float)}
    return res, raw


def main():
    t0 = time.time()
    hp_A = json.load(open(os.path.join(HERE, "hp.json"), encoding="utf-8"))
    hp_A["novelty_aware"] = False
    hp_A["interval_fix"] = False
    hp_B = dict(json.load(open(os.path.join(OUT, "dev_novelty.json"),
                               encoding="utf-8"))["frozen_hp"])
    hp_B["interval_fix"] = False
    devC = json.load(open(os.path.join(OUT, "dev_interval.json"), encoding="utf-8"))
    assert devC["decision"]["accepted"], "dev_interval rejected C"
    hp_C = dict(devC["frozen_hp_C"])
    HP = {"A": hp_A, "B": hp_B, "C": hp_C}

    print("A: novelty_aware={} interval_fix={} z={}".format(
        hp_A["novelty_aware"], hp_A["interval_fix"], hp_A["z"]))
    print("B: novelty_aware={} interval_fix={} z={}".format(
        hp_B["novelty_aware"], hp_B["interval_fix"], hp_B["z"]))
    print("C: novelty_aware={} interval_fix={} scale_prior_df={} z={}".format(
        hp_C["novelty_aware"], hp_C["interval_fix"], hp_C["scale_prior_df"],
        hp_C["z"]))
    print("NEW evaluation seeds:", NEW_SEEDS, "\n")

    topos = build_topologies()
    train = [e["record"] for e in generate_corpus(topos, 1500, X.SEED_TRAIN)]
    print("building memories from train (seed 101) ...")
    mem_full = IncidentMemory(topos, train, hp=dict(hp_A))
    mem_sparse = IncidentMemory(topos, train[:150], hp=dict(hp_A))
    mem_noclin = IncidentMemory(topos, [r for r in train if r["topology"] != "clinical"],
                                hp=dict(hp_A))
    mem_lofo = {f: IncidentMemory(topos, [r for r in train if r["fault"] != f],
                                  hp=dict(hp_A)) for f in FAULTS}

    per = {c: {t: [] for t in TAGS} for c in CONDS}
    raws = {c: {t: [] for t in TAGS} for c in CONDS}

    for seed in NEW_SEEDS:
        fresh = generate_corpus(topos, N_TEST, seed)
        clin = [e for e in fresh if e["record"]["topology"] == "clinical"]
        by_f = {f: [e for e in fresh if e["record"]["fault"] == f] for f in FAULTS}
        for tag in TAGS:
            hp = HP[tag]
            r, w = detailed_eval(mem_full, fresh, hp)
            per["seen"][tag].append(r); raws["seen"][tag].append(w)
            r, w = detailed_eval(mem_sparse, fresh, hp)
            per["sparse"][tag].append(r); raws["sparse"][tag].append(w)
            r, w = detailed_eval(mem_noclin, clin, hp)
            per["unseen_topology"][tag].append(r)
            raws["unseen_topology"][tag].append(w)
            sub, sraw, wts = [], [], []
            for f in FAULTS:
                if len(by_f[f]) < 5:
                    continue
                rr, rw = detailed_eval(mem_lofo[f], by_f[f], hp)
                sub.append(rr); sraw.append(rw); wts.append(len(by_f[f]))
            ww = np.array(wts, float); ww /= ww.sum()
            per["unseen_fault"][tag].append(
                {k: float(np.sum([s[k] * wi for s, wi in zip(sub, ww)])) for k in sub[0]})
            raws["unseen_fault"][tag].append(
                {k: np.concatenate([s[k] for s in sraw]) for k in sraw[0]})
        print("  seed {} done ({:.0f}s)".format(seed, time.time() - t0))

    KEYS = ("dur_mae", "blast_mae", "jaccard", "top1", "regret", "coverage",
            "dur_rmse", "pairwise", "mean_novelty")
    out = {"new_seeds": NEW_SEEDS, "hp": HP, "conditions": {}}
    print("\n{:<16s} {:<11s} {:>9s} {:>9s} {:>9s}   {:<s}".format(
        "condition", "metric", "A", "B", "C", "B-A / C-A"))
    print("-" * 78)
    for c in CONDS:
        entry = {}
        for k in KEYS:
            vals = {t: np.array([r[k] for r in per[c][t]], float) for t in TAGS}
            entry[k] = {t: {"mean": float(vals[t].mean()),
                            "sd": float(vals[t].std(ddof=1)),
                            "values": [float(v) for v in vals[t]]} for t in TAGS}
            for t in ("B", "C"):
                d = vals[t] - vals["A"]
                better = (d < 0) if k in ("dur_mae", "blast_mae", "regret",
                                          "dur_rmse") else (d > 0)
                entry[k][t]["delta_vs_A"] = float(d.mean())
                entry[k][t]["seeds_favouring"] = int(better.sum())
            if k in ("dur_mae", "blast_mae", "top1", "regret", "coverage"):
                print("{:<16s} {:<11s} {:9.4f} {:9.4f} {:9.4f}   {:+.4f} / {:+.4f}".format(
                    c if k == "dur_mae" else "", k, vals["A"].mean(),
                    vals["B"].mean(), vals["C"].mean(),
                    vals["B"].mean() - vals["A"].mean(),
                    vals["C"].mean() - vals["A"].mean()))
        for t in TAGS:
            cc = np.concatenate([r["conf"] for r in raws[c][t]])
            ee = np.concatenate([r["abs_err"] for r in raws[c][t]])
            entry.setdefault("conf_rho", {})[t] = (
                0.0 if np.std(cc) < 1e-12 else float(stats.spearmanr(cc, ee).statistic))
        out["conditions"][c] = entry
        print()

    for t in TAGS:
        cc = np.concatenate([r["conf"] for c in CONDS for r in raws[c][t]])
        ee = np.concatenate([r["abs_err"] for c in CONDS for r in raws[c][t]])
        out.setdefault("pooled_conf_rho", {})[t] = float(
            stats.spearmanr(cc, ee).statistic)
    print("pooled rho(confidence, |error|):  A {:+.4f}  B {:+.4f}  C {:+.4f}".format(
        *[out["pooled_conf_rho"][t] for t in TAGS]))

    # coverage by precedent availability -- the defect C targets
    print("\ncoverage by tier-1 precedent count (pooled over conditions and seeds):")
    print("   {:>6s} {:>9s} {:>9s} {:>9s} {:>9s}".format("bin", "n", "cov A",
                                                         "cov B", "cov C"))
    brk = {}
    for lo_, hi_, lbl in [(0, 0, "0"), (1, 2, "1-2"), (3, 4, "3-4"),
                          (5, 8, "5-8"), (9, 99, "9+")]:
        rec = {}
        for t in TAGS:
            n1 = np.concatenate([r["n1"] for c in CONDS for r in raws[c][t]])
            h = np.concatenate([r["hit"] for c in CONDS for r in raws[c][t]])
            e = np.concatenate([r["abs_err"] for c in CONDS for r in raws[c][t]])
            cf = np.concatenate([r["conf"] for c in CONDS for r in raws[c][t]])
            m = (n1 >= lo_) & (n1 <= hi_)
            rec[t] = {"n": int(m.sum()),
                      "coverage": float(h[m].mean()) if m.any() else None,
                      "mae": float(e[m].mean()) if m.any() else None,
                      "mean_conf": float(cf[m].mean()) if m.any() else None}
        brk[lbl] = rec
        if rec["A"]["n"]:
            print("   {:>6s} {:>9d} {:9.3f} {:9.3f} {:9.3f}".format(
                lbl, rec["A"]["n"], rec["A"]["coverage"], rec["B"]["coverage"],
                rec["C"]["coverage"]))
    out["by_tier1_precedent"] = brk

    # B vs C must be identical on everything except dispersion
    ident = True
    for c in CONDS:
        for k in ("dur_mae", "blast_mae", "top1", "regret", "jaccard"):
            ident &= abs(out["conditions"][c][k]["B"]["mean"]
                         - out["conditions"][c][k]["C"]["mean"]) < 1e-9
    out["B_C_point_estimates_identical"] = bool(ident)
    print("\nB and C identical on MAE / blast / top-1 / regret / Jaccard:", ident)

    out["runtime_seconds"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(OUT, "final_abc_eval.json"), "w"),
              indent=2, default=float)
    print("\nwrote results/final_abc_eval.json ({:.0f}s)".format(out["runtime_seconds"]))
    make_plots(out)
    return out


def make_plots(out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(14, 3.7))
    labels = [l for l, r in out["by_tier1_precedent"].items() if r["A"]["n"]]
    xa = np.arange(len(labels))
    for i, t in enumerate(TAGS):
        cov = [out["by_tier1_precedent"][l][t]["coverage"] for l in labels]
        ax[0].bar(xa + (i - 1) * 0.27, cov, 0.27, label=t)
    ax[0].axhline(0.80, ls="--", lw=1, color="k")
    ax[0].set_xticks(xa); ax[0].set_xticklabels(labels)
    ax[0].set_xlabel("tier-1 precedents retrieved"); ax[0].set_ylabel("interval coverage")
    ax[0].set_title("Coverage by precedent availability"); ax[0].legend(fontsize=7)

    for i, t in enumerate(TAGS):
        rg = [out["conditions"][c]["regret"][t]["mean"] for c in CONDS]
        sd = [out["conditions"][c]["regret"][t]["sd"] for c in CONDS]
        ax[1].bar(np.arange(len(CONDS)) + (i - 1) * 0.27, rg, 0.27, yerr=sd,
                  capsize=3, label=t)
    ax[1].set_xticks(np.arange(len(CONDS)))
    ax[1].set_xticklabels([c.replace("_", "\n") for c in CONDS], fontsize=7)
    ax[1].set_ylabel("decision regret (min)"); ax[1].set_title("Regret by condition")
    ax[1].legend(fontsize=7)

    for i, t in enumerate(TAGS):
        cv = [out["conditions"][c]["coverage"][t]["mean"] for c in CONDS]
        ax[2].bar(np.arange(len(CONDS)) + (i - 1) * 0.27, cv, 0.27, label=t)
    ax[2].axhline(0.80, ls="--", lw=1, color="k")
    ax[2].set_xticks(np.arange(len(CONDS)))
    ax[2].set_xticklabels([c.replace("_", "\n") for c in CONDS], fontsize=7)
    ax[2].set_ylabel("interval coverage"); ax[2].set_title("Coverage by condition")
    ax[2].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_abc_summary.png"), dpi=160)
    plt.close(fig)
    print("wrote results/fig_abc_summary.png")


if __name__ == "__main__":
    main()
