# IncidentMind -- measured evaluation results

Environment spec hash `b3b20acc837a2893`; train/val/test = 1500/500/600 incidents; 16 candidate decisions per test incident.


## Table A. Main comparison (test set)

| Method | Dur MAE (min) | Dur RMSE | MAPE (%) | Blast MAE | Jaccard | Set F1 | Top-1 (%) | Pairwise (%) | Kendall tau | Regret (min) |
|---|---|---|---|---|---|---|---|---|---|---|
| IncidentMind | 2.60 | 4.94 | 16.4 | 0.97 | 0.782 | 0.853 | 75.5 | 94.9 | 0.895 | 0.15 |
| B0 Runbook/SOP | 9.34 | 14.59 | 61.3 | 1.85 | 0.654 | 0.756 | 5.5 | 50.2 | 0.003 | 10.56 |
| B1 Global mean | 8.97 | 13.18 | 84.5 | 2.24 | 0.664 | 0.762 | 5.5 | 50.2 | 0.003 | 10.56 |
| B2 Context-independent | 7.91 | 11.66 | 70.8 | 2.18 | 0.669 | 0.766 | 11.7 | 67.6 | 0.351 | 5.14 |
| B3 Naive linear | 5.57 | 10.06 | 33.1 | 2.18 | 0.669 | 0.766 | 44.3 | 83.8 | 0.675 | 1.07 |
| B4 Precedent-free | 6.54 | 11.79 | 42.2 | 0.97 | 0.782 | 0.853 | 34.8 | 74.4 | 0.487 | 3.36 |
| B5 Precedent k-NN | 6.55 | 8.72 | 69.2 | 1.86 | 0.673 | 0.773 | 14.3 | 72.6 | 0.451 | 4.85 |
| B6 Gradient boosting | 3.26 | 6.06 | 20.5 | 0.90 | 0.766 | 0.845 | 64.8 | 91.0 | 0.819 | 0.41 |
| Oracle (noise floor) | 2.24 | 4.22 | 13.7 | 0.00 | 1.000 | 1.000 | 78.2 | 95.9 | 0.915 | 0.11 |

## Table B. Significance vs IncidentMind (paired, n=9600 predictions)

| Baseline | dMAE | 95% CI | Wilcoxon p | Cliff's delta | dRegret |
|---|---|---|---|---|---|
| B0 Runbook/SOP | +6.74 | [+6.56, +6.92] | <10^-4 | +0.581 | +10.41 |
| B1 Global mean | +6.38 | [+6.22, +6.53] | <10^-4 | +0.649 | +10.41 |
| B2 Context-independent | +5.31 | [+5.18, +5.45] | <10^-4 | +0.595 | +5.00 |
| B3 Naive linear | +2.97 | [+2.86, +3.09] | <10^-4 | +0.326 | +0.92 |
| B4 Precedent-free | +3.94 | [+3.80, +4.08] | <10^-4 | +0.413 | +3.21 |
| B5 Precedent k-NN | +3.96 | [+3.85, +4.07] | <10^-4 | +0.583 | +4.70 |
| B6 Gradient boosting | +0.66 | [+0.61, +0.72] | <10^-4 | +0.115 | +0.26 |
| Oracle (noise floor) | -0.36 | [-0.40, -0.33] | <10^-4 | -0.078 | -0.04 |

## Table C. Ablation

| Configuration | Dur MAE | Blast MAE | Jaccard | Top-1 (%) | Regret |
|---|---|---|---|---|---|
| Full mechanism | 2.60 | 0.97 | 0.782 | 75.5 | 0.15 |
| without timing-duration law (Step 2) | 2.59 | 0.97 | 0.782 | 78.3 | 0.12 |
| without dependency route (Step 3) | 2.80 | 0.97 | 0.782 | 71.0 | 0.24 |
| structural route only | 2.58 | 0.97 | 0.782 | 78.3 | 0.12 |
| without tiered relaxation (Step 1) | 2.60 | 0.97 | 0.782 | 75.5 | 0.15 |
| without robust loss | 2.59 | 0.97 | 0.782 | 75.8 | 0.14 |

## Table D. Precedent sparsity

| Retrieved precedents | n | Dur MAE | Mean confidence |
|---|---|---|---|
| 3-4 | 156 | 15.94 | 0.537 |
| 5-8 | 1412 | 5.23 | 0.593 |
| 9+ | 8032 | 1.87 | 0.641 |

## Table E. Unseen fault types (leave-one-fault-out)

| Fault held out of memory | n | MAE (seen) | MAE (unseen) | Top-1 seen | Top-1 unseen |
|---|---|---|---|---|---|
| db_saturation | 93 | 2.28 | 7.75 | 80.6 | 11.8 |
| service_crash | 90 | 1.82 | 3.67 | 84.4 | 33.3 |
| network_latency | 85 | 2.21 | 6.70 | 72.9 | 40.0 |
| api_timeout_cascade | 74 | 2.30 | 5.49 | 85.1 | 47.3 |
| resource_exhaustion | 88 | 2.18 | 6.21 | 63.6 | 33.0 |
| deploy_misconfig | 88 | 3.12 | 11.12 | 53.4 | 43.2 |
| cache_failure | 82 | 3.02 | 6.20 | 82.9 | 14.6 |

## Table F. Contradictory precedent

| Contradiction rate | Dur MAE | Top-1 (%) | Coverage | Conflict flagged | Mean confidence |
|---|---|---|---|---|---|
| 0% | 2.75 | 77.6 | 0.821 | 0.049 | 0.631 |
| 5% | 2.99 | 69.2 | 0.807 | 0.030 | 0.610 |
| 10% | 3.21 | 68.4 | 0.845 | 0.047 | 0.554 |
| 20% | 3.81 | 67.2 | 0.844 | 0.053 | 0.494 |
| 30% | 4.30 | 47.6 | 0.831 | 0.050 | 0.391 |
| 40% | 5.19 | 52.0 | 0.919 | 0.083 | 0.290 |

Squared-loss fit at 20% contradiction: MAE 3.84 (robust loss 3.81).


## Table G. Confidence behaviour by operating regime

| Regime | n | Duration MAE | Mean confidence |
|---|---|---|---|
| dense (main test) | 9600 | 2.60 | 0.632 |
| unseen fault type | 9600 | 6.77 | 0.405 |
| unseen topology | 3200 | 2.63 | 0.619 |
| contradictory precedent | 8000 | 4.74 | 0.340 |

Within the dense-precedent test population rho(confidence, |error|) = -0.119 (p <10^-4), and against relative error -0.121; the oracle noise floor is 2.24 min against IncidentMind's 2.60 min, so within-regime error is predominantly irreducible. Pooled across all regimes rho = -0.287 (p <10^-4), with tercile MAE 5.29 / 5.72 / 2.43 min from lowest to highest confidence. Empirical coverage of the nominal 80% interval is 0.834.


## Table H. Robustness to degraded telemetry

| Timestamp jitter (sigma) | Event drop | Dur MAE | Blast MAE | Jaccard | Top-1 (%) |
|---|---|---|---|---|---|
| 0.00 | 0% | 2.75 | 1.07 | 0.751 | 77.6 |
| 0.25 | 0% | 2.84 | 1.07 | 0.751 | 69.2 |
| 0.50 | 0% | 3.15 | 1.09 | 0.744 | 64.4 |
| 0.00 | 10% | 2.70 | 1.10 | 0.750 | 78.0 |
| 0.00 | 25% | 2.76 | 1.30 | 0.707 | 78.4 |
| 0.50 | 25% | 3.14 | 1.38 | 0.696 | 66.8 |

## Table I. Scalability

| Corpus size | Index build (s) | ms / what-if query |
|---|---|---|
| 250 | 0.09 | 1.88 |
| 500 | 0.13 | 2.25 |
| 1000 | 0.20 | 2.46 |
| 2000 | 0.29 | 2.68 |
| 4000 | 0.37 | 2.73 |
| 8000 | 0.53 | 3.04 |

| Topology size (services) | Edges | ms / propagation traversal |
|---|---|---|
| 14 | 23 | 0.013 |
| 41 | 67 | 0.024 |
| 100 | 179 | 0.021 |
| 500 | 981 | 0.017 |
| 1000 | 1977 | 0.048 |
| 2500 | 4964 | 0.054 |
| 5000 | 9931 | 0.067 |

## Table J. Misspecified recovery-cost law

| Generative spread law | IncidentMind MAE | Best baseline MAE | B2 MAE | IM Top-1 (%) |
|---|---|---|---|---|
| linear | 2.58 | 3.11 (B6 Gradient boosting) | 7.79 | 75.2 |
| quadratic | 3.68 | 4.20 (B6 Gradient boosting) | 9.76 | 74.0 |
| exponential | 3.37 | 3.95 (B6 Gradient boosting) | 9.24 | 74.4 |
| sqrt | 2.61 | 3.21 (B6 Gradient boosting) | 7.70 | 75.6 |

## Table K. Seven case-study scenarios (held out, with ground truth)

| # | Scenario | Decision | tau | Pred dur | True dur | Pred blast | True blast | Jaccard | Conf |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Database failure | pool_restart (baseline) | 10 | 12.5 | 12.5 | 4 | 4 | 1.00 | 0.66 |
|  |  | pool_restart (alt 1) | 2 | 4.2 | 3.7 | 2 | 1 | 0.50 | 0.63 |
|  |  | scale_replicas (alt 2) | 3 | 9.2 | 7.8 | 3 | 3 | 1.00 | 0.50 |
| 2 | Service crash | pod_restart (baseline) | 5 | 7.2 | 6.3 | 3 | 3 | 1.00 | 0.80 |
|  |  | pod_restart (alt 1) | 1 | 2.9 | 2.1 | 1 | 2 | 0.50 | 0.79 |
|  |  | scale_replicas (alt 2) | 2 | 9.1 | 6.8 | 3 | 3 | 1.00 | 0.73 |
| 3 | Network latency | reroute_traffic (baseline) | 8 | 10.5 | 11.1 | 4 | 4 | 1.00 | 0.64 |
|  |  | reroute_traffic (alt 1) | 2 | 4.2 | 4.4 | 2 | 2 | 1.00 | 0.63 |
|  |  | scale_replicas (alt 2) | 3 | 15.1 | 15.4 | 3 | 4 | 0.75 | 0.56 |
| 4 | API timeout cascade | circuit_breaker (baseline) | 6 | 7.8 | 8.0 | 3 | 1 | 0.33 | 0.72 |
|  |  | circuit_breaker (alt 1) | 1 | 2.6 | 3.0 | 2 | 1 | 0.50 | 0.72 |
|  |  | rollback_deploy (alt 2) | 3 | 34.9 | 29.6 | 3 | 1 | 0.33 | 0.42 |
| 5 | Resource exhaustion | scale_replicas (baseline) | 5 | 10.1 | 11.8 | 2 | 2 | 1.00 | 0.69 |
|  |  | scale_replicas (alt 1) | 1 | 6.0 | 7.8 | 2 | 2 | 1.00 | 0.69 |
|  |  | rollback_deploy (alt 2) | 4 | 34.0 | 46.1 | 2 | 2 | 1.00 | 0.73 |
| 6 | Deployment misconfiguration | scale_replicas (baseline) | 5 | 37.7 | 40.3 | 5 | 3 | 0.60 | 0.61 |
|  |  | rollback_deploy (alt 1) | 5 | 11.0 | 13.5 | 5 | 3 | 0.60 | 0.66 |
|  |  | rollback_deploy (alt 2) | 2 | 7.5 | 10.5 | 3 | 3 | 0.50 | 0.65 |
| 7 | Cascading dependency failure | pod_restart (baseline) | 9 | 12.1 | 13.2 | 5 | 4 | 0.80 | 0.70 |
|  |  | pod_restart (alt 1) | 2 | 4.7 | 5.2 | 2 | 2 | 1.00 | 0.68 |
|  |  | degraded_mode (alt 2) | 3 | 5.3 | 6.0 | 2 | 3 | 0.67 | 0.57 |

Correct identification of the best of three decisions: 7/7 scenarios.
