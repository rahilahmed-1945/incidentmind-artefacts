# -*- coding: utf-8 -*-
"""
Regenerate Figs. 4-7 for the journal manuscript from the released artefacts and
code, with journal panel labels (a)(b)(c), no in-figure titles, 300 dpi.

Figs. 4-6 reproduce evaluation/experiments.make_figures() (same data selection:
test[0] for Fig. 4; results.json for Figs. 5-6). Fig. 6(a) additionally shows the
pooled-regime quintiles that the text discusses, alongside the dense-split bins the
original figure showed. Fig. 7 reproduces realworld/orchestrator/analyse_v1r.make_plots
with a log-scale delay axis so the 101,737 ms co-failure artefact does not hide the
sub-second distribution.

Usage: python regen_figs.py <repro_root> <out_dir>
  <repro_root> holds evaluation/ (with results/results.json) and realworld/ as on the
  evidence branch.
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(root, "evaluation"))
sys.path.insert(0, os.path.join(root, "realworld", "orchestrator"))
from environment import build_topologies, generate_corpus, set_spread_form  # noqa: E402
from estimator import IncidentMemory, IncidentMindEstimator, _law              # noqa: E402
import experiments as X                                                       # noqa: E402

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5,
                     "axes.labelsize": 8.5, "legend.fontsize": 7.5,
                     "xtick.labelsize": 7.5, "ytick.labelsize": 7.5})
DPI = 300


def label(ax, s):
    ax.text(-0.12, 1.04, s, transform=ax.transAxes, fontsize=10, weight="bold", va="bottom")


R = json.load(open(os.path.join(root, "evaluation", "results", "results.json")))
set_spread_form("linear")
topos = build_topologies()
train = generate_corpus(topos, X.N_TRAIN, X.SEED_TRAIN)
test = generate_corpus(topos, X.N_TEST, X.SEED_TEST)
mem = IncidentMemory(topos, [e["record"] for e in train], hp=R["setup"]["hp"])
im = IncidentMindEstimator(mem)

# ---------------------------------------------------------------- Fig. 4
fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.7))
e = test[0]; rec = e["record"]
idx, sims, ctier, tier = mem.retrieve(rec["topology"], rec["fault"], rec["origin"], rec["action"])
ctx = im._context(rec["topology"], rec["fault"], rec["origin"], rec["action"])
ts = np.linspace(0.5, 20, 60)
if idx.size:
    ax[0].scatter(mem.col_tau[idx], mem.col_dur[idx] - mem.col_tau[idx], s=22, alpha=0.75,
                  color="#4c72b0", label="retrieved precedent")
ax[0].plot(ts, _law(ctx["params"], ts), lw=1.8, color="#dd8452", label="fitted law $r_{red}(\\tau)$")
ax[0].set_xlabel("intervention timing $\\tau$ (min)"); ax[0].set_ylabel("post-action recovery $r$ (min)")
ax[0].legend(); label(ax[0], "(a)")
real = e["realisation"]
true_d = [real.outcome(rec["action"], t)["duration"] for t in ts]
pred = [im.estimate(rec["topology"], rec["fault"], rec["origin"], rec["action"], t) for t in ts]
ax[1].plot(ts, true_d, lw=1.8, color="#4c72b0", label="ground truth")
ax[1].plot(ts, [p["duration"] for p in pred], lw=1.8, ls="--", color="#dd8452", label="estimate $\\hat D$")
ax[1].fill_between(ts, [p["lo"] for p in pred], [p["hi"] for p in pred], alpha=0.18, color="#dd8452",
                   label="80 % interval")
ax[1].set_xlabel("intervention timing $\\tau$ (min)"); ax[1].set_ylabel("incident duration $D$ (min)")
ax[1].legend(); label(ax[1], "(b)")
fig.tight_layout(); fig.savefig(os.path.join(out, "Fig4.png"), dpi=DPI); plt.close(fig)

# ---------------------------------------------------------------- Fig. 5
fig, ax = plt.subplots(1, 3, figsize=(7.2, 2.5))
lc = R["E4_sensitivity"]["corpus"]
ax[0].plot([v["n"] for v in lc], [v["dur_mae"] for v in lc], "o-", ms=4, color="#4c72b0", label="IncidentMind")
ax[0].plot([v["n"] for v in lc], [v["knn_dur_mae"] for v in lc], "s--", ms=4, color="#8172b2", label="B5 precedent k-NN")
ax[0].set_xscale("log"); ax[0].set_xlabel("precedent corpus size"); ax[0].set_ylabel("duration MAE (min)")
ax[0].legend(); label(ax[0], "(a)")
ks = R["E4_sensitivity"]["k"]
ax[1].plot([v["k"] for v in ks], [v["dur_mae"] for v in ks], "o-", ms=4, color="#4c72b0")
ax[1].set_xlabel("retrieved precedents $k$"); ax[1].set_ylabel("duration MAE (min)"); label(ax[1], "(b)")
sw = R["E6_contradiction"]["sweep"]
ax[2].plot([v["rate"] for v in sw], [v["dur_mae"] for v in sw], "o-", ms=4, color="#4c72b0", label="duration MAE")
ax2 = ax[2].twinx()
ax2.plot([v["rate"] for v in sw], [v["mean_confidence"] for v in sw], "s--", ms=4, color="#c44e52", label="mean confidence")
ax[2].set_xlabel("contradictory precedent rate"); ax[2].set_ylabel("duration MAE (min)"); ax2.set_ylabel("mean confidence")
h1, l1 = ax[2].get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax[2].legend(h1 + h2, l1 + l2, loc="center left"); label(ax[2], "(c)")
fig.tight_layout(); fig.savefig(os.path.join(out, "Fig5.png"), dpi=DPI); plt.close(fig)

# ---------------------------------------------------------------- Fig. 6
fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.7))
bins = R["E7_calibration"]["bins"]; pbins = R["E7_calibration"]["pooled_bins"]
ax[0].plot([b["conf"] for b in bins], [b["mae"] for b in bins], "o-", ms=4, color="#4c72b0",
           label="dense-precedent test split")
ax[0].plot([b["conf"] for b in pbins], [b["mae"] for b in pbins], "s--", ms=4, color="#c44e52",
           label="pooled across regimes")
ax[0].set_xlabel("mean confidence in bin"); ax[0].set_ylabel("duration MAE (min)"); ax[0].legend(); label(ax[0], "(a)")
names = list(R["E1_main"].keys()); vals = [R["E1_main"][n]["dur_mae"] for n in names]
cols = ["#dd8452" if n == "IncidentMind" else ("#999999" if n.startswith("Oracle") else "#4c72b0") for n in names]
ax[1].barh(range(len(names)), vals, color=cols)
ax[1].set_yticks(range(len(names))); ax[1].set_yticklabels(names, fontsize=6.5); ax[1].invert_yaxis()
ax[1].set_xlabel("duration MAE (min)"); label(ax[1], "(b)")
fig.tight_layout(); fig.savefig(os.path.join(out, "Fig6.png"), dpi=DPI); plt.close(fig)

# ---------------------------------------------------------------- Fig. 7
import analyse_v1r as AV  # noqa: E402

captured = {}


def _capture(preds, unc, obs_edges, learned, out_):
    captured.update(preds=preds, unc=unc, obs_edges=obs_edges)


AV.make_plots = _capture
AV.main() if hasattr(AV, "main") else None
preds, unc, obs_edges = captured["preds"], captured["unc"], captured["obs_edges"]
fig, ax = plt.subplots(1, 3, figsize=(7.2, 2.5))
ob = [r["duration_min"] * 60 for r, _ in preds]; pr = [p["duration"] * 60 for _, p in preds]
cen = [r.get("censored", False) for r, _ in preds]
ax[0].scatter([o for o, c in zip(ob, cen) if not c], [p for p, c in zip(pr, cen) if not c], s=22, color="#4c72b0", label="uncensored")
ax[0].scatter([o for o, c in zip(ob, cen) if c], [p for p, c in zip(pr, cen) if c], s=26, marker="x", color="#c44e52", label="censored (lower bound)")
lim = max(ob + pr) * 1.05
ax[0].plot([0, lim], [0, lim], "k--", lw=0.8)
ax[0].set_xlabel("observed duration (s)"); ax[0].set_ylabel("predicted duration (s)"); ax[0].legend(); label(ax[0], "(a)")
allp = [v for vs in obs_edges.values() for v in vs]
ax[1].hist(allp, bins=np.logspace(2, 5.1, 22), color="#4c72b0")
ax[1].set_xscale("log"); ax[1].set_xlabel("observed propagation delay (ms, log scale)"); ax[1].set_ylabel("count"); label(ax[1], "(b)")
conf = [p["confidence"] for _, p in unc]; ae = [abs(p["duration"] - r["duration_min"]) * 60 for r, p in unc]
ax[2].scatter(conf, ae, s=22, color="#4c72b0")
ax[2].set_xlabel("confidence"); ax[2].set_ylabel("absolute error (s)"); label(ax[2], "(c)")
fig.tight_layout(); fig.savefig(os.path.join(out, "Fig7.png"), dpi=DPI); plt.close(fig)
print("wrote Fig4-7 to", out, "| Fig7 points:", len(preds), "delays:", len(allp), "unc:", len(unc))
