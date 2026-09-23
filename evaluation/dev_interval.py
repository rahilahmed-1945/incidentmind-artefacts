"""
Development of the small-sample dispersion fix (configuration C).
TRAIN + VALIDATION ONLY.

DATA DISCIPLINE
    Seeds 101 (train) and 202 (validation) only. Never touches seed 303, seeds
    50101-50505, or any previously reported final-test result.

DEFECT
    The interval half-width and the confidence dispersion term both derive from
    a weighted MAD of the law-fit residuals. Under the sparse-precedent policy a
    query with m <= p_fit precedents fits as many parameters as it has points,
    so residuals are identically zero, the MAD is zero, and the interval
    collapses to ~0 width while the confidence term saturates at 1. The least
    supported predictions therefore receive the narrowest intervals and the
    highest confidence -- exactly backwards.

CORRECTION
    Moderated dispersion: combine the local scale with a pooled per-action
    scale, weighted by residual degrees of freedom d_loc = max(0, m - p_fit),

        sigma^2 = (d0 * sigma_pooled^2 + d_loc * sigma_local^2) / (d0 + d_loc)

    so that d_loc = 0 yields the pooled scale outright. This is the standard
    pooled/moderated variance estimator.

PRE-REGISTERED SELECTION RULE (fixed before any result was inspected)
    Select (scale_prior_df, z) jointly to minimise the mean over the four
    development conditions of |coverage - 0.80|. Ties break toward smaller
    scale_prior_df, then toward z nearest the incumbent 2.5.
    CONTROL: the same z sweep with the fix disabled, to establish whether the
    interval multiplier alone can repair the defect.
    ACCEPT C only if (i) it beats B's mean |coverage - 0.80| on dev, and
    (ii) duration MAE, top-1 and regret are unchanged (the fix touches only
    dispersion, so any change would indicate an implementation error).

Run:  python dev_interval.py
Writes: results/dev_interval.json
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
D0_GRID = [1.0, 2.0, 4.0, 8.0, 16.0]
Z_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
CONDS = ["seen", "sparse", "unseen_fault", "unseen_topology"]


def probe(mem, data, hp):
    """
    Evaluate once, recording the half-width PER UNIT z so that coverage can be
    computed analytically for every z without re-running the estimator.
    """
    X.set_hp(mem, **hp)
    est = IncidentMindEstimator(mem)
    rng = np.random.default_rng(1)
    y, pred, half_u, conf, n1, per = [], [], [], [], [], []
    z_used = hp["z"]
    for i, e in enumerate(data):
        rec, real = e["record"], e["realisation"]
        tv, pv = [], []
        for (a, t) in X.candidate_grid(e, np.random.default_rng(1000 + i)):
            gt = real.outcome(a, t)
            pr = est.estimate(rec["topology"], rec["fault"], rec["origin"], a, t)
            y.append(gt["duration"]); pred.append(pr["duration"])
            half_u.append((pr["hi"] - pr["lo"]) / 2.0 / max(z_used, 1e-9))
            conf.append(pr["confidence"]); n1.append(pr["n_tier1"])
            tv.append(gt["duration"]); pv.append(pr["duration"])
        r = M.ranking_scores(tv, pv, rng)
        if r:
            per.append(r)
    y, pred, half_u = np.array(y), np.array(pred), np.array(half_u)
    return {"y": y, "pred": pred, "half_u": half_u, "conf": np.array(conf),
            "n1": np.array(n1), "abs_err": np.abs(y - pred),
            "dur_mae": M.mae(y, pred),
            "top1": float(np.mean([p["top1"] for p in per])),
            "regret": float(np.mean([p["regret"] for p in per]))}


def coverage_at(p, z):
    return float(np.mean(np.abs(p["y"] - p["pred"]) <= z * p["half_u"]))


def build_conditions(topos, hp):
    train = [e["record"] for e in generate_corpus(topos, 1500, X.SEED_TRAIN)]
    val = generate_corpus(topos, 500, X.SEED_VAL)
    c = {}
    c["seen"] = (IncidentMemory(topos, train, hp=dict(hp)), val[:250])
    c["sparse"] = (IncidentMemory(topos, train[:150], hp=dict(hp)), val[:250])
    c["unseen_topology"] = (
        IncidentMemory(topos, [r for r in train if r["topology"] != "clinical"],
                       hp=dict(hp)),
        [e for e in val if e["record"]["topology"] == "clinical"])
    lofo = []
    for f in FAULTS:
        held = [e for e in val if e["record"]["fault"] == f]
        if len(held) >= 10:
            lofo.append((IncidentMemory(topos, [r for r in train if r["fault"] != f],
                                        hp=dict(hp)), held))
    c["unseen_fault"] = lofo
    return c


def probe_all(conds, hp):
    out = {}
    for name in CONDS:
        if name == "unseen_fault":
            ps = [probe(mem, d, hp) for mem, d in conds[name]]
            merged = {k: np.concatenate([p[k] for p in ps])
                      for k in ("y", "pred", "half_u", "conf", "n1", "abs_err")}
            w = np.array([len(p["y"]) for p in ps], float); w /= w.sum()
            for k in ("dur_mae", "top1", "regret"):
                merged[k] = float(np.sum([p[k] * wi for p, wi in zip(ps, w)]))
            out[name] = merged
        else:
            mem, data = conds[name]
            out[name] = probe(mem, data, hp)
    return out


def score(probes, z):
    return float(np.mean([abs(coverage_at(probes[c], z) - 0.80) for c in CONDS]))


def main():
    t0 = time.time()
    hp_B = json.load(open(os.path.join(OUT, "dev_novelty.json"),
                          encoding="utf-8"))["frozen_hp"]
    topos = build_topologies()
    print("building dev conditions (train 101 + validation 202) ...")
    conds = build_conditions(topos, dict(hp_B, interval_fix=False))
    log = {"grid_d0": D0_GRID, "grid_z": Z_GRID}

    # ---- incumbent B, and the control: z sweep with the fix OFF ----
    pB = probe_all(conds, dict(hp_B, interval_fix=False))
    B_score = score(pB, hp_B["z"])
    print("\nB (no fix, z={}): mean |cov-0.80| = {:.4f}".format(hp_B["z"], B_score))
    for c in CONDS:
        print("    {:18s} coverage {:.3f}".format(c, coverage_at(pB[c], hp_B["z"])))
    ctrl = [{"z": z, "score": score(pB, z)} for z in Z_GRID]
    best_ctrl = min(ctrl, key=lambda r: r["score"])
    print("  CONTROL (fix off, best z on dev): z={} -> mean |cov-0.80| = {:.4f}"
          .format(best_ctrl["z"], best_ctrl["score"]))
    log["control_z_sweep"] = ctrl
    log["B_score"] = B_score

    # ---- C: sweep d0, each probe gives every z analytically ----
    print("\nselecting scale_prior_df and z (objective = mean |coverage - 0.80|)")
    rows, best = [], None
    for d0 in D0_GRID:
        p = probe_all(conds, dict(hp_B, interval_fix=True, scale_prior_df=d0))
        for z in Z_GRID:
            s = score(p, z)
            rows.append({"d0": d0, "z": z, "score": s,
                         "cov": {c: coverage_at(p[c], z) for c in CONDS}})
            if best is None or s < best["score"] - 1e-9:
                best = rows[-1]
        bz = min([r for r in rows if r["d0"] == d0], key=lambda r: r["score"])
        print("   d0={:4.1f}  best z={:.1f}  mean |cov-0.80| = {:.4f}   ({})".format(
            d0, bz["z"], bz["score"],
            ", ".join("%s %.3f" % (c, bz["cov"][c]) for c in CONDS)))
    log["grid"] = rows
    log["selected"] = {"scale_prior_df": best["d0"], "z": best["z"],
                       "score": best["score"]}
    print("\n   selected scale_prior_df={}, z={}  (mean |cov-0.80| = {:.4f})".format(
        best["d0"], best["z"], best["score"]))

    # ---- verify C changes only dispersion, and check the m<=2 regime ----
    hp_C = dict(hp_B, interval_fix=True, scale_prior_df=best["d0"], z=best["z"])
    pC = probe_all(conds, hp_C)
    print("\ncheck: point estimates and decision quality must be unchanged")
    same = True
    for c in CONDS:
        d_mae = abs(pC[c]["dur_mae"] - pB[c]["dur_mae"])
        d_t1 = abs(pC[c]["top1"] - pB[c]["top1"])
        d_rg = abs(pC[c]["regret"] - pB[c]["regret"])
        same &= (d_mae < 1e-9 and d_t1 < 1e-9 and d_rg < 1e-9)
        print("   {:18s} dMAE {:.2e}  dtop1 {:.2e}  dregret {:.2e}".format(
            c, d_mae, d_t1, d_rg))
    print("   unchanged:", same)
    log["decision_quality_unchanged"] = bool(same)

    n1 = np.concatenate([pB[c]["n1"] for c in CONDS])
    eB = np.concatenate([pB[c]["abs_err"] for c in CONDS])
    hB = np.concatenate([pB[c]["half_u"] for c in CONDS]) * hp_B["z"]
    hC = np.concatenate([pC[c]["half_u"] for c in CONDS]) * hp_C["z"]
    cB = np.concatenate([pB[c]["conf"] for c in CONDS])
    cC = np.concatenate([pC[c]["conf"] for c in CONDS])
    log["by_bin"] = {}
    print("\ncoverage by tier-1 precedent count (dev):")
    print("   {:>6s} {:>8s} {:>9s} {:>9s} {:>10s} {:>10s}".format(
        "bin", "n", "cov B", "cov C", "halfwid B", "halfwid C"))
    for lo_, hi_, lbl in [(0, 0, "0"), (1, 2, "1-2"), (3, 4, "3-4"),
                          (5, 8, "5-8"), (9, 99, "9+")]:
        m = (n1 >= lo_) & (n1 <= hi_)
        if not m.any():
            continue
        cov_b = float(np.mean(eB[m] <= hB[m]))
        cov_c = float(np.mean(eB[m] <= hC[m]))
        log["by_bin"][lbl] = {"n": int(m.sum()), "cov_B": cov_b, "cov_C": cov_c,
                              "half_B": float(hB[m].mean()),
                              "half_C": float(hC[m].mean())}
        print("   {:>6s} {:>8d} {:9.3f} {:9.3f} {:10.4f} {:10.4f}".format(
            lbl, int(m.sum()), cov_b, cov_c, hB[m].mean(), hC[m].mean()))

    rho_b = float(stats.spearmanr(cB, eB).statistic)
    rho_c = float(stats.spearmanr(cC, eB).statistic)
    log["pooled_conf_rho"] = {"B": rho_b, "C": rho_c}
    print("\npooled rho(confidence, |error|) on dev:  B {:+.4f}   C {:+.4f}".format(
        rho_b, rho_c))

    accept = (best["score"] < B_score) and same
    log["decision"] = {"accepted": bool(accept), "B_score": B_score,
                       "C_score": best["score"],
                       "control_best": best_ctrl}
    log["frozen_hp_C"] = hp_C
    print("\nDECISION: {} (dev mean |cov-0.80|: B {:.4f} -> C {:.4f}; "
          "control best {:.4f})".format("ACCEPT C" if accept else "REJECT C",
                                        B_score, best["score"], best_ctrl["score"]))
    log["dev_seconds"] = round(time.time() - t0, 1)
    json.dump(log, open(os.path.join(OUT, "dev_interval.json"), "w"),
              indent=2, default=float)
    print("wrote results/dev_interval.json ({:.0f}s)".format(log["dev_seconds"]))
    return log


if __name__ == "__main__":
    main()
