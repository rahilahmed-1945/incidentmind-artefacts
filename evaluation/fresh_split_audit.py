"""
Adaptive-overfitting audit.

During development the test split (seed 303) was inspected several times and
three mechanism changes were made in response to what it showed.  That is
adaptive overfitting, and its magnitude cannot be argued away -- it has to be
measured.

This script freezes the final configuration (exactly the hyper-parameters
selected on validation in the reported run) and evaluates it on test splits
drawn from seeds that were NEVER examined at any point during development.
If the reported numbers hold on virgin data, the leakage did not materially
inflate them; if they do not, the reported numbers are optimistic by the
difference.

Usage:  python fresh_split_audit.py
"""
import json
import os

import numpy as np

from baselines import ALL_BASELINES, Oracle
from environment import build_topologies, generate_corpus
from estimator import IncidentMemory, IncidentMindEstimator
import experiments as X

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTED = os.path.join(HERE, "results", "results.json")

# Seeds never used during development. Train stays 101 (the estimator's memory
# must be the same one that was built); only the evaluation data is new.
FRESH_SEEDS = [50101, 50202, 50303, 50404, 50505]
KEYS = ("dur_mae", "dur_rmse", "dur_mape", "blast_mae", "jaccard",
        "top1", "pairwise", "regret", "coverage")


def main():
    rep = json.load(open(REPORTED, encoding="utf-8"))
    hp = dict(rep["setup"]["hp"])          # the frozen, validation-selected config
    topos = build_topologies()
    train_rec = [e["record"] for e in generate_corpus(topos, rep["setup"]["n_train"],
                                                      X.SEED_TRAIN)]
    mem = IncidentMemory(topos, train_rec, hp=hp)
    im = IncidentMindEstimator(mem)

    methods = [("IncidentMind", im, False)]
    for cls in ALL_BASELINES:
        b = cls().fit(mem, train_rec)
        methods.append((b.name, b, False))
    methods.append(("Oracle (noise floor)", Oracle().fit(mem, train_rec), True))

    print("frozen config:", {k: hp[k] for k in
                             ("k", "temp", "m_relax", "tier_penalty", "beta",
                              "lam_blend", "theta", "clag_scale", "conflict_sep", "z")})
    print("reported test seed: {} (inspected during development)".format(X.SEED_TEST))
    print("fresh seeds: {} (never inspected)\n".format(FRESH_SEEDS))

    per_method = {}
    for seed in FRESH_SEEDS:
        fresh = generate_corpus(topos, rep["setup"]["n_test"], seed)
        for name, meth, is_or in methods:
            r, _ = X.evaluate(meth, fresh, use_oracle=is_or, seed=1)
            per_method.setdefault(name, []).append(r)
        im_r = per_method["IncidentMind"][-1]
        print("  seed {:6d}: IM MAE={:.3f} top1={:.3f} regret={:.3f} J={:.3f}".format(
            seed, im_r["dur_mae"], im_r["top1"], im_r["regret"], im_r["jaccard"]))

    out = {"fresh_seeds": FRESH_SEEDS, "frozen_hp": hp, "methods": {}}
    print("\n{:<24s} {:>10s} {:>10s} {:>8s} {:>10s}".format(
        "metric / method", "reported", "fresh mean", "sd", "delta"))
    print("-" * 66)
    for name, runs in per_method.items():
        rep_r = rep["E1_main"][name]
        entry = {}
        for k in KEYS:
            vals = np.array([r[k] for r in runs], dtype=float)
            entry[k] = {"reported": rep_r[k], "fresh_mean": float(vals.mean()),
                        "fresh_sd": float(vals.std(ddof=1)),
                        "delta": float(vals.mean() - rep_r[k]),
                        "fresh_values": [float(v) for v in vals]}
        out["methods"][name] = entry
        if name in ("IncidentMind", "B6 Gradient boosting", "Oracle (noise floor)"):
            for k in ("dur_mae", "top1", "regret"):
                e = entry[k]
                print("{:<24s} {:10.3f} {:10.3f} {:8.3f} {:+10.3f}".format(
                    (name + " / " + k)[:24], e["reported"], e["fresh_mean"],
                    e["fresh_sd"], e["delta"]))

    # headline verdict
    im_mae = out["methods"]["IncidentMind"]["dur_mae"]
    gb_mae = out["methods"]["B6 Gradient boosting"]["dur_mae"]
    im_reg = out["methods"]["IncidentMind"]["regret"]
    gb_reg = out["methods"]["B6 Gradient boosting"]["regret"]
    out["verdict"] = {
        "im_mae_inflation": im_mae["delta"],
        "im_mae_inflation_sd_units": (im_mae["delta"] / im_mae["fresh_sd"]
                                      if im_mae["fresh_sd"] > 0 else 0.0),
        "beats_gb_on_mae_fresh": bool(im_mae["fresh_mean"] < gb_mae["fresh_mean"]),
        "beats_gb_on_regret_fresh": bool(im_reg["fresh_mean"] < gb_reg["fresh_mean"]),
    }
    print("\nverdict:", json.dumps(out["verdict"], indent=2))
    with open(os.path.join(HERE, "results", "fresh_split_audit.json"), "w",
              encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=float)
    print("\nwrote results/fresh_split_audit.json")


if __name__ == "__main__":
    main()
