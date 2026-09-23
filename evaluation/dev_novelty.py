"""
Development of the novelty-aware fallback -- TRAIN + VALIDATION ONLY.

DATA DISCIPLINE
    Uses seed 101 (train) to build incident memories and seed 202 (validation)
    to evaluate.  It never touches seed 303 (the development-contaminated test
    split) nor seeds 50101-50505 (the untouched final evaluation).

PRE-REGISTERED SELECTION RULE  (fixed before any result was inspected)
    Stage 1 -- (nov_kappa0, nov_a):
        minimise  mean over the four dev conditions of  MAE_B / MAE_A
        subject to  MAE_B(seen) <= 1.02 * MAE_A(seen).
        If no grid point satisfies the constraint, the mechanism is REJECTED
        and the frozen system is kept unchanged.
    Stage 2 -- nov_gamma_i:
        minimise mean over conditions of |coverage - 0.80|.
    Stage 3 -- nov_gamma_c:
        maximise the magnitude of the negative Spearman correlation between
        confidence and |error|, pooled over the four conditions.
    Ties are broken toward the smaller parameter value (weaker intervention).

Run:  python dev_novelty.py
Writes: results/dev_novelty.json
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
SEEN_N = 250

KAPPA0_GRID = [1.0, 2.0, 4.0, 8.0, 16.0]
A_GRID = [0.5, 1.0, 2.0]
GAMMA_I_GRID = [0.0, 0.25, 0.5, 1.0]
GAMMA_C_GRID = [0.0, 0.2, 0.4, 0.6]


def build_conditions(topos, base_hp):
    """Four development conditions, all from train (101) + validation (202)."""
    train = [e["record"] for e in generate_corpus(topos, 1500, X.SEED_TRAIN)]
    val = generate_corpus(topos, 500, X.SEED_VAL)
    conds = {}

    conds["seen"] = {"mem": IncidentMemory(topos, train, hp=dict(base_hp)),
                     "data": val[:SEEN_N]}
    conds["sparse"] = {"mem": IncidentMemory(topos, train[:150], hp=dict(base_hp)),
                       "data": val[:SEEN_N]}

    lofo = []
    for f in FAULTS:
        held = [e for e in val if e["record"]["fault"] == f]
        if len(held) < 10:
            continue
        sub = [r for r in train if r["fault"] != f]
        lofo.append((IncidentMemory(topos, sub, hp=dict(base_hp)), held, f))
    conds["unseen_fault"] = {"parts": lofo}

    clin = [e for e in val if e["record"]["topology"] == "clinical"]
    sub = [r for r in train if r["topology"] != "clinical"]
    conds["unseen_topology"] = {"mem": IncidentMemory(topos, sub, hp=dict(base_hp)),
                                "data": clin}
    return conds, train, val


def eval_condition(cond, hp, name):
    """Evaluate one condition under hyper-parameters hp; returns metrics + raw."""
    if name == "unseen_fault":
        agg, raws = [], []
        for mem, held, _f in cond["parts"]:
            X.set_hp(mem, **hp)
            r, raw = X.evaluate(IncidentMindEstimator(mem), held, seed=1)
            agg.append((r, len(held)))
            raws.append(raw)
        w = np.array([n for _r, n in agg], dtype=float)
        w = w / w.sum()
        out = {}
        for k in ("dur_mae", "blast_mae", "jaccard", "top1", "regret", "coverage",
                  "dur_rmse", "pairwise"):
            out[k] = float(np.sum([r[k] * wi for (r, _n), wi in zip(agg, w)]))
        raw = {kk: np.concatenate([r[kk] for r in raws])
               for kk in ("abs_err", "conf", "y", "p", "abs_err_blast")}
        return out, raw
    mem = cond["mem"]
    X.set_hp(mem, **hp)
    return X.evaluate(IncidentMindEstimator(mem), cond["data"], seed=1)


def eval_all(conds, hp):
    res, raws = {}, {}
    for name in ("seen", "sparse", "unseen_fault", "unseen_topology"):
        r, raw = eval_condition(conds[name], hp, name)
        res[name], raws[name] = r, raw
    return res, raws


def pooled_rho(raws):
    c = np.concatenate([raws[k]["conf"] for k in raws])
    e = np.concatenate([raws[k]["abs_err"] for k in raws])
    if np.std(c) < 1e-12:
        return 0.0
    return float(stats.spearmanr(c, e).statistic)


def main():
    t0 = time.time()
    base_hp = json.load(open(os.path.join(HERE, "hp.json"), encoding="utf-8"))
    base_hp["novelty_aware"] = False
    topos = build_topologies()
    print("building dev conditions from train(101) + validation(202) ...")
    conds, _train, _val = build_conditions(topos, base_hp)

    # ---------------- baseline A on the dev conditions ----------------
    A_res, A_raws = eval_all(conds, dict(base_hp, novelty_aware=False))
    print("\nA (frozen) on dev conditions:")
    for k, v in A_res.items():
        print("   {:18s} MAE={:6.3f} blast={:5.3f} top1={:.3f} regret={:6.3f} "
              "cov={:.3f}".format(k, v["dur_mae"], v["blast_mae"], v["top1"],
                                  v["regret"], v["coverage"]))
    A_rho = pooled_rho(A_raws)
    print("   pooled rho(conf,|err|) = {:+.3f}".format(A_rho))

    log = {"A_dev": A_res, "A_pooled_rho": A_rho, "stage1": [], "stage2": [],
           "stage3": []}

    # ---------------- stage 1: kappa0, a ----------------
    print("\nstage 1: selecting nov_kappa0, nov_a "
          "(objective = mean MAE ratio, constraint = seen <= 1.02x A)")
    best, best_score = None, np.inf
    for k0 in KAPPA0_GRID:
        for a in A_GRID:
            hp = dict(base_hp, novelty_aware=True, nov_kappa0=k0, nov_a=a,
                      nov_gamma_c=0.0, nov_gamma_i=0.0)
            res, _ = eval_all(conds, hp)
            ratios = [res[c]["dur_mae"] / A_res[c]["dur_mae"] for c in res]
            score = float(np.mean(ratios))
            feas = res["seen"]["dur_mae"] <= 1.02 * A_res["seen"]["dur_mae"]
            log["stage1"].append({"kappa0": k0, "a": a, "mean_ratio": score,
                                  "feasible": bool(feas),
                                  "per_cond": {c: res[c]["dur_mae"] for c in res}})
            print("   k0={:4.1f} a={:3.1f}  mean ratio={:.4f}  seen={:.3f} "
                  "unseen_fault={:.3f}  {}".format(
                      k0, a, score, res["seen"]["dur_mae"],
                      res["unseen_fault"]["dur_mae"],
                      "ok" if feas else "VIOLATES seen constraint"))
            if feas and score < best_score - 1e-9:
                best_score, best = score, (k0, a)

    if best is None or best_score >= 1.0:
        print("\nSTAGE 1 OUTCOME: no feasible grid point improves the mean MAE "
              "ratio (best = {}). Mechanism REJECTED by the pre-registered "
              "rule.".format("none" if best is None else round(best_score, 4)))
        log["decision"] = {"accepted": False,
                           "reason": "no feasible point with mean MAE ratio < 1",
                           "best_score": None if best is None else best_score}
        json.dump(log, open(os.path.join(OUT, "dev_novelty.json"), "w"),
                  indent=2, default=float)
        print("wrote results/dev_novelty.json")
        return log

    k0, a = best
    print("\n   selected nov_kappa0={}, nov_a={} (mean MAE ratio {:.4f})".format(
        k0, a, best_score))

    # ---------------- stage 2: gamma_i (interval width) ----------------
    print("\nstage 2: selecting nov_gamma_i (objective = mean |coverage - 0.80|)")
    best_i, best_gap = 0.0, np.inf
    for gi in GAMMA_I_GRID:
        hp = dict(base_hp, novelty_aware=True, nov_kappa0=k0, nov_a=a,
                  nov_gamma_c=0.0, nov_gamma_i=gi)
        res, _ = eval_all(conds, hp)
        gap = float(np.mean([abs(res[c]["coverage"] - 0.80) for c in res]))
        log["stage2"].append({"gamma_i": gi, "mean_cov_gap": gap,
                              "per_cond": {c: res[c]["coverage"] for c in res}})
        print("   gamma_i={:.2f}  mean |cov-0.80| = {:.4f}   ({})".format(
            gi, gap, ", ".join("%s %.3f" % (c, res[c]["coverage"]) for c in res)))
        if gap < best_gap - 1e-9:
            best_gap, best_i = gap, gi
    print("   selected nov_gamma_i={}".format(best_i))

    # ---------------- stage 3: gamma_c (confidence discount) ----------------
    print("\nstage 3: selecting nov_gamma_c (objective = most negative pooled rho)")
    best_c, best_rho = 0.0, np.inf
    for gc in GAMMA_C_GRID:
        hp = dict(base_hp, novelty_aware=True, nov_kappa0=k0, nov_a=a,
                  nov_gamma_c=gc, nov_gamma_i=best_i)
        _res, raws = eval_all(conds, hp)
        rho = pooled_rho(raws)
        log["stage3"].append({"gamma_c": gc, "pooled_rho": rho})
        print("   gamma_c={:.2f}  pooled rho = {:+.4f}".format(gc, rho))
        if rho < best_rho - 1e-9:
            best_rho, best_c = rho, gc
    print("   selected nov_gamma_c={}".format(best_c))

    # ---------------- frozen candidate B, reported on dev ----------------
    frozen = dict(base_hp, novelty_aware=True, nov_kappa0=k0, nov_a=a,
                  nov_gamma_c=best_c, nov_gamma_i=best_i)
    B_res, B_raws = eval_all(conds, frozen)
    B_rho = pooled_rho(B_raws)
    print("\nB (novelty-aware) on dev conditions:")
    for k in A_res:
        va, vb = A_res[k], B_res[k]
        print("   {:18s} MAE {:6.3f} -> {:6.3f} ({:+.1%})   top1 {:.3f} -> {:.3f}"
              "   regret {:6.3f} -> {:6.3f}   cov {:.3f} -> {:.3f}".format(
                  k, va["dur_mae"], vb["dur_mae"],
                  vb["dur_mae"] / va["dur_mae"] - 1,
                  va["top1"], vb["top1"], va["regret"], vb["regret"],
                  va["coverage"], vb["coverage"]))
    print("   pooled rho {:+.3f} -> {:+.3f}".format(A_rho, B_rho))

    log["selected"] = {"nov_kappa0": k0, "nov_a": a, "nov_gamma_c": best_c,
                       "nov_gamma_i": best_i}
    log["frozen_hp"] = frozen
    log["B_dev"] = B_res
    log["B_pooled_rho"] = B_rho
    log["decision"] = {"accepted": True, "stage1_mean_ratio": best_score}
    log["dev_seconds"] = round(time.time() - t0, 1)
    json.dump(log, open(os.path.join(OUT, "dev_novelty.json"), "w"),
              indent=2, default=float)
    print("\nwrote results/dev_novelty.json  ({:.0f}s)".format(log["dev_seconds"]))
    return log


if __name__ == "__main__":
    main()
