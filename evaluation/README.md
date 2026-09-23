# IncidentMind — evaluation package

Reproduces every quantitative result in Sect. 6 of the journal article (Layers A and B).
An earlier version of this package accompanied the ICCMM-2026 conference paper.

## Requirements

Python 3.10+ with `numpy`, `scipy` and `matplotlib`. No network access, no GPU,
no API keys. The full protocol runs in roughly 21 minutes on one commodity CPU.

```bash
pip install numpy scipy matplotlib
python experiments.py
```

Outputs are written to `results/`:

| File | Contents |
|---|---|
| `results.json` | Every measured quantity, keyed by experiment |
| `tables.md` | Rendered result tables |
| `fig_law.png`, `fig_sensitivity.png`, `fig_calibration.png` | Figures 4–6 |
| `run.log` | Console transcript of the released run |

## Modules

| File | Role |
|---|---|
| `environment.py` | **Frozen ground-truth generator.** Owns the hidden parameters (action efficacy, per-edge propagation delays and probabilities, spread-penalty coefficient, noise scales) that the estimator never observes. Materialises each incident as a latent realisation that can be replayed under any recovery decision, which is what supplies counterfactual ground truth. Identified by `spec_hash()` = `b3b20acc837a2893` |
| `estimator.py` | **IncidentMind reference implementation** (Sect. 4): tiered precedent retrieval, the robustly fitted timing–duration law, the structural spread route and their blend, dependency-propagation blast radius with learned edge delays and containment lags, confidence scoring, prediction intervals and conflict detection |
| `baselines.py` | Seven executed baselines (B0–B6) plus the privileged `Oracle` used to establish the irreducible noise floor |
| `metrics.py` | Error, set-overlap and decision-quality metrics; paired bootstrap, Wilcoxon, Cliff's δ; calibration diagnostics |
| `experiments.py` | The protocol of Sect. 5: split construction, staged validation calibration, experiments E1–E11, table and figure generation |

## Determinism and the separation of concerns

The estimator observes **only** emitted incident records (fault type, origin,
action, timing, resulting duration, affected set, per-service degradation times)
and the static impact graph. It has no access to any hidden generative
parameter. Train (1,500), validation (500) and test (600) incidents are drawn
from independent random streams and are disjoint at the incident level; the
incident memory contains training records only.

All randomness is seeded, so `experiments.py` is reproducible: rerunning it
yields identical `results.json` values (excluding wall-clock timings).

**Verified, not asserted.** `compare_runs.py` diffs two `results.json` files,
ignoring the six wall-clock fields that legitimately vary. The reported results
were checked by running the full protocol twice under deliberately different
`PYTHONHASHSEED` values:

```bash
cd runA && PYTHONHASHSEED=1      python experiments.py
cd runB && PYTHONHASHSEED=999999 python experiments.py
python compare_runs.py runA/results/results.json runB/results/results.json
# compared 1355 non-timing values
# IDENTICAL: every reported value reproduces exactly
```

Varying `PYTHONHASHSEED` matters because Python randomises string hashing per
process, so any code that draws one random number per key while iterating a
`set` is silently non-reproducible across runs. An earlier revision had exactly
that defect: `generate_corpus` built each record's `arrivals` map by iterating
the affected-service **set**, and the telemetry-jitter experiment (E8) drew one
jitter sample per key in that order. Record *contents* were unaffected, so no
ground truth and no learned parameter changed, but 12 of the 1,355 reported
values — the E8 rows with non-zero jitter — moved in the third decimal. The map
is now built from `sorted(...)`, and the two-hash-seed check above is the
regression test.

`fresh_split_audit.py` evaluates the frozen configuration on five test splits
drawn from seeds never inspected during development, quantifying adaptive
overfitting (Sec. VI-K of the manuscript).

## Experiment index

| Key in `results.json` | Manuscript | What it measures |
|---|---|---|
| `E1_main` | Table 4 | Accuracy and decision quality, all methods |
| `E2_significance` | Table 5 | Paired bootstrap, Wilcoxon, Cliff's δ vs IncidentMind |
| `E3_ablation` | Table 6 | Contribution of each mechanism component |
| `E4_sensitivity` | Table 7, Fig. 5 | Sweeps over *k*, *T*, *β*, λ, *m*_min and corpus size |
| `E5_generalisation` | Tables 8, 9 | Precedent sparsity, leave-one-fault-out, unseen topology |
| `E6_contradiction` | Table 10 | Injected contradictory precedent |
| `E7_calibration` | Table 11, Fig. 6 | Confidence and interval coverage by regime |
| `E8_noise` | Table 12 | Timestamp jitter and event loss |
| `E9_scalability` | Table 13 | Query and traversal latency vs corpus and topology size |
| `E10_cases` | Table 15 | The seven case-study scenarios with ground truth |
| `E11_misspecification` | Table 14 | Generative recovery-cost laws outside the assumed family |

## Scope

This is a simulation study. It supplies counterfactual ground truth that a
production incident archive cannot, and it is **not** a substitute for
validation against injected faults in real clusters. Absolute error magnitudes
are properties of this testbed; the comparative results are the transferable
finding. See Sec. VII-C of the manuscript for the full threats-to-validity
discussion.

## Experiment index (addendum)

| Key | Manuscript | What it measures |
|---|---|---|
| `fresh_split_audit.json` | Table 16 | Frozen configuration on five never-inspected test splits |

## The rest of Layer B

`experiments.py` covers Sect. 6.1-6.10. The remaining scripts, in run order:

| Script | Writes | Article element |
|---|---|---|
| `fresh_split_audit.py` | `results/fresh_split_audit.json` | Table 15, fresh-split ranking (Sect. 6.11) |
| `dev_novelty.py` | `results/dev_novelty.json` | Development of the novelty-aware fallback, train/validation only |
| `final_novelty_eval.py` | `results/final_novelty_eval.json` | Five never-inspected splits (seeds 50101-50505) |
| `dev_interval.py` | `results/dev_interval.json` | Development of the dispersion correction; the z-sweep control (0.1235); frozen configuration C |
| `final_abc_eval.py` | `results/final_abc_eval.json` | Tables 16-17, six untouched splits (seeds 700101-700606) |
| `compare_runs.py` | - | Utility: diff two `results.json` files |

`dev_interval.py` also writes the frozen configuration C that the Layer C analysis
in `../realworld/orchestrator/analyse_v1r.py` reads.

## Timings are not reproducible; everything else is

Re-running reproduces every value in `results.json` exactly, except the wall-clock
quantities (`E9_scalability`, `eval_seconds`, `runtime_seconds`). Those vary by up
to a factor of two between runs on one machine, which the article states in
Sect. 6.8.
