# Reproducibility record

What was verified before this repository was released, on an isolated copy of the
repository itself (not the authors' working tree), on 23 September 2026.

Environment: Windows 11, Python 3.14, numpy 2.4.6, scipy 1.18.0, matplotlib 3.11.1,
one commodity CPU. No network access, no GPU, no API keys.

## 1. Layer A — full protocol re-executed from this repository

```
cd evaluation && python experiments.py        # 1208 s
```

- Environment specification digest: `b3b20acc837a2893` — identical to the released
  `results.json` and to the digest quoted in the article.
- **908 of 908 numeric values in `results.json` reproduced exactly** (E1 main
  comparison, E2 significance, E3 ablation, E4 sensitivity and learning curve,
  E5 stratifications and held-out regimes, E6 contradiction sweep, E7 calibration,
  E8 telemetry degradation, E10 case studies, E11 misspecification, and the
  calibration outcome), comparing at a relative tolerance of 1e-12.
- The only quantities that differ are wall-clock timings (`E9_scalability`,
  `eval_seconds`, `runtime_seconds`). The article states this in Sect. 6.8: the
  released run took 1254 s and this one 1208 s, and per-traversal latencies differ
  by up to a factor of two between runs.

## 2. Layer C — analysis re-executed from this repository

```
cd realworld/orchestrator && python analyse_v1r.py
```

All seven computed tables of `v1r_analysis.json` (`table1_composition` …
`table7_ranking`, plus `memory` and `protocol`) reproduced exactly. The released
file additionally carries a `honesty_checks` key, which this script does not
write; see §3.

## 3. Layer C — quoted quantities not written by the analysis script

```
python verification/recompute_honesty_checks.py
```

Re-derived from the raw records in `realworld/results/v1r_incidents.jsonl`:

| Quantity | Article | Recomputed |
|---|---|---|
| Mean cycle time (Table 18) | 186 s | 185.9 s |
| Out-of-sample propagation-delay MAE (Table 20) | 181 ms | 180.7 ms over 3 edges |
| Co-failure artefact edge (Sect. 6.13) | `cartservice → adservice`, 101.7 s | 101.7 s, recorded once |
| Out-of-combination subset (Sect. 6.13) | n = 4, MAE 17.4 s | n = 4, MAE 17.4 s |

## 4. Figures regenerated from this repository

```
python figures/make_figs.py             # Fig. 1, Fig. 2 (schematic, 600 dpi)
python figures/regen_figs.py . figures  # Figs. 4-7 from the artefacts (300 dpi)
```

Both complete without error and reproduce the published figures. `Fig3.png` is a
static illustration with no generating script (see `README.md`).

## 5. Article checked against these artefacts

```
python verification/qa_check.py /path/to/article.pdf
```

**146 assertions, 0 failures.** Every quantity re-derived from
`evaluation/results/` and `realworld/results/` appears verbatim in the article,
including all of Tables 4–21, the normalised-regret column, the validation
selection surface, the fresh-split ranking of every baseline, the per-split
ranges of the A/B/C comparison and the complete campaign composition.

## 6. What is *not* bit-reproducible, and why

| Quantity | Reason |
|---|---|
| Wall-clock latencies (Table 12 scalability, runtimes) | Machine- and run-dependent; the article reports single-run measurements and says so |
| The live-cluster campaign itself | A physical measurement on a Kubernetes cluster, not a deterministic simulation. The released records are the evidence; re-running `run_v1r.py` will produce different timings |
| `Fig3.png` | Static illustration of the demonstration dashboard, not derived from any artefact |
