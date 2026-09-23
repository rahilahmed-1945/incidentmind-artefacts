"""
FINAL, ONE-SHOT evaluation of the novelty-aware fallback.

Configuration A (frozen original) and configuration B (novelty-aware, frozen by
dev_novelty.py using train+validation only) are evaluated on the FIVE UNTOUCHED
test splits, seeds 50101-50505, across four operating conditions.

Nothing here selects any parameter. Both configurations are fixed on entry and
the script is intended to be run exactly once.

Incident memories are built from the training corpus (seed 101) exactly as in
the reported evaluation; only the evaluation data is fresh.

Run:  python final_novelty_eval.py
Writes: results/final_novelty_eval.json, results/fig_novelty_*.png
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
FRESH_SEEDS = [50101, 50202, 50303, 50404, 50505]
N_TEST = 600
CONDS = ["seen", "sparse", "unseen_fault", "unseen_topology"]


def detailed_eval(mem, data, hp):
    """Evaluate, recording per-prediction novelty alongside the usual metrics."""
    X.set_hp(mem, **hp)
    est = IncidentMindEstimator(mem)
    rng = np.random.default_rng(1)
    yd, pd_, yb, pb, lo, hi = [], [], [], [], [], []
    conf, nov, ntier1, jac, per_inc, inc_nov = [], [], [], [], [], []
    for i, e in enumerate(data):
        rec, real = e["record"], e["realisation"]
        tv, pv, nv = [], [], []
        for (a, t) in X.candidate_grid(e, np.random.default_rng(1000 + i)):
            gt = real.outcome(a, t)
            pr = est.estimate(rec["topology"], rec["fault"], rec["origin"], a, t)
            yd.append(gt["duration"]); pd_.append(pr["duration"])
            yb.append(gt["blast"]); pb.append(pr["blast"])
            lo.append(pr["lo"]); hi.append(pr["hi"])
            conf.append(pr["confidence"]); nov.append(pr["novelty"])
            ntier1.append(pr["n_tier1"])
            jac.append(M.set_scores(gt["affected"], pr["affected"])["jaccard"])
            tv.append(gt["duration"]); pv.append(pr["duration"]); nv.append(pr["novelty"])
        r = M.ranking_scores(tv, pv, rng)
        if r:
            per_inc.append(r)
            inc_nov.append(float(np.mean(nv)))
    yd, pd_ = np.array(yd), np.array(pd_)
    yb, pb = np.array(yb), np.array(pb)
    lo, hi = np.array(lo), np.array(hi)
    res = {"dur_mae": M.mae(yd, pd_), "dur_rmse": M.rmse(yd, pd_),
           "dur_mape": M.mape(yd, pd_), "blast_mae": M.mae(yb, pb),
           "jaccard": float(np.mean(jac)), "coverage": M.coverage(yd, lo, hi),
           "top1": float(np.mean([p["top1"] for p in per_inc])),
           "pairwise": float(np.mean([p["pairwise"] for p in per_inc])),
           "kendall": float(np.mean([p["kendall"] for p in per_inc])),
           "regret": float(np.mean([p["regret"] for p in per_inc])),
           "mean_novelty": float(np.mean(nov))}
    raw = {"abs_err": np.abs(yd - pd_), "abs_err_blast": np.abs(yb - pb),
           "conf": np.array(conf), "nov": np.array(nov),
           "ntier1": np.array(ntier1), "hit": ((yd >= lo) & (yd <= hi)).astype(float),
           "regret": np.array([p["regret"] for p in per_inc]),
           "top1": np.array([p["top1"] for p in per_inc]),
           "inc_nov": np.array(inc_nov)}
    return res, raw


def main():
    t0 = time.time()
    hp_A = json.load(open(os.path.join(HERE, "hp.json"), encoding="utf-8"))
    hp_A["novelty_aware"] = False
    dev = json.load(open(os.path.join(OUT, "dev_novelty.json"), encoding="utf-8"))
    assert dev["decision"]["accepted"], "dev run rejected the mechanism"
    hp_B = dev["frozen_hp"]
    print("A (frozen original)   novelty_aware =", hp_A["novelty_aware"])
    print("B (novelty-aware)     ", {k: hp_B[k] for k in
                                     ("nov_kappa0", "nov_a", "nov_gamma_c", "nov_gamma_i")})
    print("evaluation seeds (untouched):", FRESH_SEEDS, "\n")

    topos = build_topologies()
    train = [e["record"] for e in generate_corpus(topos, 1500, X.SEED_TRAIN)]
    print("building memories from train (seed 101) ...")
    mem_full = IncidentMemory(topos, train, hp=dict(hp_A))
    mem_sparse = IncidentMemory(topos, train[:150], hp=dict(hp_A))
    mem_noclin = IncidentMemory(topos, [r for r in train if r["topology"] != "clinical"],
                                hp=dict(hp_A))
    mem_lofo = {f: IncidentMemory(topos, [r for r in train if r["fault"] != f],
                                  hp=dict(hp_A)) for f in FAULTS}

    per = {c: {"A": [], "B": []} for c in CONDS}
    raws = {c: {"A": [], "B": []} for c in CONDS}

    for seed in FRESH_SEEDS:
        fresh = generate_corpus(topos, N_TEST, seed)
        clin = [e for e in fresh if e["record"]["topology"] == "clinical"]
        by_fault = {f: [e for e in fresh if e["record"]["fault"] == f] for f in FAULTS}
        for tag, hp in (("A", hp_A), ("B", hp_B)):
            r, raw = detailed_eval(mem_full, fresh, hp)
            per["seen"][tag].append(r); raws["seen"][tag].append(raw)

            r, raw = detailed_eval(mem_sparse, fresh, hp)
            per["sparse"][tag].append(r); raws["sparse"][tag].append(raw)

            r, raw = detailed_eval(mem_noclin, clin, hp)
            per["unseen_topology"][tag].append(r)
            raws["unseen_topology"][tag].append(raw)

            sub, subraw, wts = [], [], []
            for f in FAULTS:
                if len(by_fault[f]) < 5:
                    continue
                rr, rw = detailed_eval(mem_lofo[f], by_fault[f], hp)
                sub.append(rr); subraw.append(rw); wts.append(len(by_fault[f]))
            w = np.array(wts, float); w /= w.sum()
            agg = {k: float(np.sum([s[k] * wi for s, wi in zip(sub, w)])) for k in sub[0]}
            per["unseen_fault"][tag].append(agg)
            raws["unseen_fault"][tag].append(
                {k: np.concatenate([s[k] for s in subraw]) for k in subraw[0]})
        print("  seed {} done ({:.0f}s elapsed)".format(seed, time.time() - t0))

    # ---------------- aggregate ----------------
    KEYS = ("dur_mae", "dur_rmse", "dur_mape", "blast_mae", "jaccard", "coverage",
            "top1", "pairwise", "kendall", "regret", "mean_novelty")
    out = {"fresh_seeds": FRESH_SEEDS, "hp_A": hp_A, "hp_B": hp_B, "conditions": {}}
    print("\n{:<16s} {:<12s} {:>9s} {:>9s} {:>9s} {:>8s}".format(
        "condition", "metric", "A", "B", "delta", "p"))
    print("-" * 68)
    for c in CONDS:
        entry = {}
        for k in KEYS:
            a = np.array([r[k] for r in per[c]["A"]], float)
            b = np.array([r[k] for r in per[c]["B"]], float)
            try:
                p = float(stats.wilcoxon(a, b).pvalue) if not np.allclose(a, b) else 1.0
            except Exception:
                p = float("nan")
            entry[k] = {"A_mean": float(a.mean()), "A_sd": float(a.std(ddof=1)),
                        "B_mean": float(b.mean()), "B_sd": float(b.std(ddof=1)),
                        "delta": float(b.mean() - a.mean()), "p_paired": p,
                        "A_values": [float(v) for v in a],
                        "B_values": [float(v) for v in b]}
            if k in ("dur_mae", "blast_mae", "top1", "regret", "coverage"):
                print("{:<16s} {:<12s} {:9.4f} {:9.4f} {:+9.4f} {:>8s}".format(
                    c if k == "dur_mae" else "", k, a.mean(), b.mean(),
                    b.mean() - a.mean(), M.fmt_p(p)))
        # confidence-error relationship, pooled over seeds
        for tag in ("A", "B"):
            cc = np.concatenate([r["conf"] for r in raws[c][tag]])
            ee = np.concatenate([r["abs_err"] for r in raws[c][tag]])
            rho = 0.0 if np.std(cc) < 1e-12 else float(stats.spearmanr(cc, ee).statistic)
            entry.setdefault("conf_rho", {})[tag] = rho
        out["conditions"][c] = entry
        print()

    # pooled-across-conditions confidence diagnostic
    for tag in ("A", "B"):
        cc = np.concatenate([r["conf"] for c in CONDS for r in raws[c][tag]])
        ee = np.concatenate([r["abs_err"] for c in CONDS for r in raws[c][tag]])
        out.setdefault("pooled_conf_rho", {})[tag] = (
            0.0 if np.std(cc) < 1e-12 else float(stats.spearmanr(cc, ee).statistic))
    print("pooled rho(confidence, |error|):  A {:+.4f}   B {:+.4f}".format(
        out["pooled_conf_rho"]["A"], out["pooled_conf_rho"]["B"]))

    # ---------------- breakdown by precedent availability ----------------
    bins = [(0, 0), (1, 2), (3, 4), (5, 8), (9, 99)]
    brk = {}
    for lo_, hi_ in bins:
        lbl = "0" if hi_ == 0 else ("9+" if hi_ == 99 else "%d-%d" % (lo_, hi_))
        rec = {}
        for tag in ("A", "B"):
            e = np.concatenate([r["abs_err"] for c in CONDS for r in raws[c][tag]])
            n1 = np.concatenate([r["ntier1"] for c in CONDS for r in raws[c][tag]])
            h = np.concatenate([r["hit"] for c in CONDS for r in raws[c][tag]])
            cf = np.concatenate([r["conf"] for c in CONDS for r in raws[c][tag]])
            m = (n1 >= lo_) & (n1 <= hi_)
            rec[tag] = {"n": int(m.sum()),
                        "mae": float(e[m].mean()) if m.any() else None,
                        "coverage": float(h[m].mean()) if m.any() else None,
                        "mean_conf": float(cf[m].mean()) if m.any() else None}
        brk[lbl] = rec
    out["by_tier1_precedent"] = brk
    print("\nby tier-1 precedent count (pooled over all conditions and seeds):")
    print("  {:>6s} {:>8s} {:>9s} {:>9s} {:>9s} {:>9s}".format(
        "bin", "n", "MAE A", "MAE B", "cov A", "cov B"))
    for lbl, rec in brk.items():
        if rec["A"]["n"] == 0:
            continue
        print("  {:>6s} {:>8d} {:9.3f} {:9.3f} {:9.3f} {:9.3f}".format(
            lbl, rec["A"]["n"], rec["A"]["mae"], rec["B"]["mae"],
            rec["A"]["coverage"], rec["B"]["coverage"]))

    out["runtime_seconds"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(OUT, "final_novelty_eval.json"), "w"),
              indent=2, default=float)
    print("\nwrote results/final_novelty_eval.json ({:.0f}s)".format(out["runtime_seconds"]))
    make_plots(out, raws)
    return out


def make_plots(out, raws):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(13.5, 3.6))
    labels = [l for l, r in out["by_tier1_precedent"].items() if r["A"]["n"] > 0]
    xa = np.arange(len(labels))
    mae_a = [out["by_tier1_precedent"][l]["A"]["mae"] for l in labels]
    mae_b = [out["by_tier1_precedent"][l]["B"]["mae"] for l in labels]
    ax[0].bar(xa - 0.19, mae_a, 0.38, label="A frozen")
    ax[0].bar(xa + 0.19, mae_b, 0.38, label="B novelty-aware")
    ax[0].set_xticks(xa); ax[0].set_xticklabels(labels)
    ax[0].set_xlabel("tier-1 precedents retrieved"); ax[0].set_ylabel("duration MAE (min)")
    ax[0].set_title("Error by precedent availability"); ax[0].legend(fontsize=7)

    cov_a = [out["by_tier1_precedent"][l]["A"]["coverage"] for l in labels]
    cov_b = [out["by_tier1_precedent"][l]["B"]["coverage"] for l in labels]
    ax[1].bar(xa - 0.19, cov_a, 0.38, label="A frozen")
    ax[1].bar(xa + 0.19, cov_b, 0.38, label="B novelty-aware")
    ax[1].axhline(0.80, ls="--", lw=1, color="k", label="nominal 0.80")
    ax[1].set_xticks(xa); ax[1].set_xticklabels(labels)
    ax[1].set_xlabel("tier-1 precedents retrieved"); ax[1].set_ylabel("interval coverage")
    ax[1].set_title("Coverage by precedent availability"); ax[1].legend(fontsize=7)

    conds = CONDS
    ra = [out["conditions"][c]["regret"]["A_mean"] for c in conds]
    rb = [out["conditions"][c]["regret"]["B_mean"] for c in conds]
    ea = [out["conditions"][c]["regret"]["A_sd"] for c in conds]
    eb = [out["conditions"][c]["regret"]["B_sd"] for c in conds]
    xb = np.arange(len(conds))
    ax[2].bar(xb - 0.19, ra, 0.38, yerr=ea, capsize=3, label="A frozen")
    ax[2].bar(xb + 0.19, rb, 0.38, yerr=eb, capsize=3, label="B novelty-aware")
    ax[2].set_xticks(xb)
    ax[2].set_xticklabels([c.replace("_", "\n") for c in conds], fontsize=7)
    ax[2].set_ylabel("decision regret (min)"); ax[2].set_title("Regret by condition")
    ax[2].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_novelty_summary.png"), dpi=160)
    plt.close(fig)

    # novelty distribution per condition
    fig, ax = plt.subplots(1, 1, figsize=(6.4, 3.4))
    for c in CONDS:
        nv = np.concatenate([r["nov"] for r in raws[c]["B"]])
        ax.hist(nv, bins=30, histtype="step", lw=1.6, density=True,
                label="%s (mean %.2f)" % (c, nv.mean()))
    ax.set_xlabel("novelty score"); ax.set_ylabel("density")
    ax.set_title("Novelty score by operating condition")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_novelty_distribution.png"), dpi=160)
    plt.close(fig)
    print("wrote results/fig_novelty_*.png")


if __name__ == "__main__":
    main()
