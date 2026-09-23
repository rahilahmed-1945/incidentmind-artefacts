# IncidentMind — evaluation artefacts

Code, data and results for the article

> **Precedent-Grounded Counterfactual Estimation of Recovery Decision Outcomes in Cloud-Native Systems**
> Rahil Ahmed, Sogra Sana, P. Sowjanya — submitted to *SN Computer Science* (Springer Nature).

This repository contains everything needed to reproduce every table, figure and
quantitative claim in the article. The article itself is not redistributed here;
see [Citation](#citation).

An earlier, narrower version of this work was accepted for presentation at
**ICCMM 2026** (IEEE). The artefacts here are those of the journal article.

---

## What is here

| Directory | Contents | Needed to reproduce results? |
|---|---|---|
| `evaluation/` | The frozen generative testbed, the reference estimator, seven baselines, the metrics and the full experimental protocol (Layers A and B) | **Yes — essential** |
| `evaluation/results/` | Every result file the article quotes, plus the console transcripts of the runs that produced them | **Yes — essential** |
| `realworld/` | The Kubernetes fault-injection harness, the tiered prober, the campaign records and the analysis script (Layer C) | **Yes — essential** |
| `figures/` | The seven figures as published, and the scripts that generate them | **Yes — essential** |
| `verification/` | A harness that re-derives every printed value from the artefacts and checks it against a PDF of the article | Optional but recommended |
| `system/` | The IncidentMind demonstration dashboard and its synthetic evidence corpus | **No — optional.** Supports the component-status claims of Table 2 only; **no quantitative result in the article depends on it** |

Roughly: `evaluation/` + `realworld/` + `figures/` are the artefact; `system/` is
context.

---

## Requirements

```bash
python -m pip install numpy scipy matplotlib
```

Python 3.10 or newer. No GPU, no network access and no API keys are required for
any result in the article. Verified with numpy 2.4.6, scipy 1.18.0 and
matplotlib 3.11.1.

For the verification harness only, additionally: `python -m pip install pymupdf`.

---

## Reproducing the results

### Layer A — the controlled counterfactual evaluation (Tables 4–14, Figs. 4–6)

```bash
cd evaluation
python experiments.py
```

About 21 minutes on one commodity CPU core. Writes `results/results.json`,
`results/tables.md` and three figures. The environment specification is
identified by `spec_hash()` = `b3b20acc837a2893`, printed at the start of the run;
if that digest differs, the ground-truth generator has changed and the numbers are
not comparable.

All randomness is seeded. Re-running reproduces `results.json` **exactly** for
every quantity except wall-clock timings (`E9_scalability`, `eval_seconds`,
`runtime_seconds`), which vary between machines and between runs on one machine —
the article says so explicitly in Sect. 6.8.

### Layer B — adaptive-overfitting audit and the two mechanism corrections (Tables 15–17)

```bash
cd evaluation
python fresh_split_audit.py     # Table 15   (requires results/results.json)
python dev_novelty.py           # development of the novelty-aware fallback (train/validation only)
python final_novelty_eval.py    # five never-inspected splits, seeds 50101-50505
python dev_interval.py          # development of the dispersion correction; the z-sweep control (0.1235)
python final_abc_eval.py        # Tables 16-17, six untouched splits, seeds 700101-700606
```

Run in this order: `dev_novelty.py` writes the configuration that
`final_novelty_eval.py`, `dev_interval.py` and `final_abc_eval.py` consume, and
`dev_interval.py` writes the frozen configuration C that Layer C uses.

### Layer C — the live-cluster campaign (Tables 18–21, Fig. 7)

The campaign itself needs a Kubernetes cluster and takes about five hours; its
records are released, so the analysis can be re-run directly:

```bash
cd realworld/orchestrator
python analyse_v1r.py
```

Reads `realworld/results/v1r_incidents.jsonl`, `v1r_protocol.json` and
`v1r_allocation.json`, and the frozen configuration C from
`evaluation/results/dev_interval.json`. Rewrites `realworld/results/v1r_analysis.json`
(all seven computed tables reproduce exactly) and `fig_v1r_summary.png`.

Note: the released `v1r_analysis.json` carries one extra top-level key,
`honesty_checks`, which `analyse_v1r.py` does not write. Those quantities are
recomputed by:

```bash
python verification/recompute_honesty_checks.py
```

which re-derives the out-of-sample propagation-delay MAE (181 ms), the mean cycle
time (186 s), the co-failure artefact edge (101.7 s) and the out-of-combination
subset (n = 4, 17.4 s) from the raw records.

> **Note.** `analyse_v1r.py` and `figures/regen_figs.py` both **overwrite**
> `realworld/results/v1r_analysis.json`, and the file they write does not contain
> the `honesty_checks` key that the released copy carries (those quantities are
> computed by `verification/recompute_honesty_checks.py`, not by the analysis
> script). Restore the released copy with
> `git checkout -- realworld/results/v1r_analysis.json`, or work on a copy of the
> repository.

To repeat the campaign from scratch, see [`realworld/README.md`](realworld/README.md).

### Figures

```bash
python figures/make_figs.py            # Fig. 1 and Fig. 2 (schematic, 600 dpi)
python figures/regen_figs.py . figures # Figs. 4-7 from the artefacts (300 dpi)
```

`Fig3.png` is a static illustration of the demonstration dashboard (Table 2,
status **D**). It contributes to no quantitative result and has no generating
script.

### Verifying the article against these artefacts

```bash
python verification/qa_check.py /path/to/article.pdf
```

Re-derives 146 quantities from `evaluation/results/` and `realworld/results/` and
asserts that each appears verbatim in the PDF. Use the published article, or your
own copy of the accepted manuscript.

---

## Map from the article to the artefacts

| Article element | Artefact |
|---|---|
| Table 2 (implementation status) | `evaluation/`, `realworld/`, `system/` (line counts, 325-record corpus, retrieval depths) |
| Table 3 (baselines) | `evaluation/baselines.py` |
| Tables 4–14, Figs. 4–6, Sect. 5.3 validation surface | `evaluation/results/results.json` (`calibration_trace` for the surface) |
| Table 15, fresh-split ranking (Sect. 6.11) | `evaluation/results/fresh_split_audit.json` |
| Tables 16–17, Sect. 6.12 | `evaluation/results/final_abc_eval.json`, `final_novelty_eval.json` |
| Sect. 6.12 z-sweep control (0.1235) | `evaluation/results/dev_interval.json` |
| Tables 18–21, Fig. 7, Sect. 6.13 | `realworld/results/v1r_*.json`, `v1r_incidents.jsonl` |
| Instrument validation (12/12 edges; 10 of 14 pilot incidents) | `realworld/results/v1a_assessment.json` |
| Five of eighteen candidate cells rejected | `realworld/results/v1_grid_decision.json`, `v1_stability.json` |
| The 1 Hz pilot that measured zero arrival offsets | `realworld/results/v0_ingest.json`, `v0_provenance.json` |
| 823,717 probe events | `realworld/results/v1r_events.jsonl.gz` |
| Image digests, cluster and tool versions | `realworld/results/provenance_raw.txt` |

---

## Notes on the data

- **Layer A and B data are generated, not collected.** The testbed materialises
  each incident as a latent realisation that can be replayed under any recovery
  decision; that is what supplies counterfactual ground truth. The hidden
  generative parameters live in `evaluation/environment.py` and are never visible
  to the estimator.
- **Layer C data are measurements from our own single-node `kind` cluster** running
  the Online Boutique benchmark. They contain probe timestamps, service names,
  success flags, latencies and gRPC/HTTP status strings. They contain no personal
  data, no IP addresses, no credentials and no third-party system data.
- **`system/datasets/` is synthetic**, produced by
  `system/datasets/generate_evidence.js`. The names in it (`alice`, `bob`,
  `charlie`) are fictional.

## Verification performed before release

Running this repository from a clean copy reproduced **908 of 908 non-timing
values** in `evaluation/results/results.json` exactly, and all seven computed
tables of `realworld/results/v1r_analysis.json` exactly; the verification harness
passes **146 of 146** assertions against the article. Full record:
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

## Reproducibility caveats stated in the article

- Wall-clock latencies are single-run measurements and vary by up to a factor of
  two between runs (Sect. 6.8).
- The development test split (seed 303) was inspected during development; Sect. 6.11
  quantifies the resulting optimism on five never-inspected splits.
- 41 of 90 measured real incidents are right-censored, and the estimator has no
  censoring model (Sects. 6.13, 7.3, 8).

## Licence

- Original code: **MIT** — see [`LICENSE`](LICENSE).
- Original data, results and figures: **CC BY 4.0** — see [`LICENSE-DATA`](LICENSE-DATA).
- Third-party files retain their own licences — see [`THIRD_PARTY.md`](THIRD_PARTY.md)
  and [`NOTICE`](NOTICE).

## Citation

See [`CITATION.cff`](CITATION.cff). Please cite the journal article; if you use the
artefacts themselves, cite the archived release as well.
