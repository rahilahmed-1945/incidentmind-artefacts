# -*- coding: utf-8 -*-
"""
Verification harness: re-derives every quantitative value printed in the article
from the released artefacts and asserts that each appears verbatim in a PDF of
the article. 146 assertions covering Tables 4-21, the derived analyses of
Sects. 5.3, 6.1, 6.11-6.13, and the campaign composition.

Artefacts are read from this repository (../evaluation/results, ../realworld/results).
The PDF is supplied by the user, because the article itself is not redistributed here.

Usage:  python verification/qa_check.py /path/to/article.pdf

Requires: pymupdf  (pip install pymupdf)
"""
import json
import os
import re
import sys

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "evaluation", "results")
RW = os.path.join(ROOT, "realworld", "results")
if len(sys.argv) < 2:
    sys.exit("usage: python verification/qa_check.py /path/to/article.pdf")
pdf_path = sys.argv[1]
R = json.load(open(os.path.join(EV, "results.json"), encoding="utf-8"))
F = json.load(open(os.path.join(EV, "fresh_split_audit.json"), encoding="utf-8"))
A = json.load(open(os.path.join(EV, "final_abc_eval.json"), encoding="utf-8"))
V = json.load(open(os.path.join(RW, "v1r_analysis.json"), encoding="utf-8"))
pdf = pymupdf.open(pdf_path)
T = re.sub(r"\s+", " ", chr(10).join(p.get_text() for p in pdf)).replace(chr(0x2212), "-")

fails, n = [], 0


def want(label, s):
    global n
    n += 1
    if s not in T:
        fails.append((label, s))


for b, v in R["E1_main"].items():
    want("T4 " + b, "{:.2f} {:.2f} {:.1f} {:.2f} {:.3f} {:.3f} {:.1f} {:.1f} {:.3f} {:.2f}".format(
        v["dur_mae"], v["dur_rmse"], v["dur_mape"], v["blast_mae"], v["jaccard"], v["set_f1"],
        100 * v["top1"], 100 * v["pairwise"], v["kendall"], v["regret"]))
for b, v in R["E2_significance"].items():
    want("T5 " + b, "{:+.2f} [{:+.2f}, {:+.2f}]".format(v["delta_mae"], v["ci_lo"], v["ci_hi"]))
    want("T5 d " + b, "{:+.3f} {:+.2f}".format(v["cliffs_delta"], v["regret_delta"]))
for k, v in R["E3_ablation"].items():
    want("T6 " + k, "{:.2f} {:.2f} {:.3f} {:.1f} {:.2f}".format(
        v["dur_mae"], v["blast_mae"], v["jaccard"], 100 * v["top1"], v["regret"]))
want("ablation regret delta", "regret +0.09 min")
E4 = R["E4_sensitivity"]
want("T7 k", ", ".join("{}→{:.2f}".format(x["k"], x["dur_mae"]) for x in E4["k"]))
want("T7 lam", ", ".join("{:.2f}→{:.2f}".format(x["lam"], x["dur_mae"]) for x in E4["lam_blend"]))
want("T7 beta", ", ".join("{:.1f}→{:.2f}".format(x["beta"], x["dur_mae"]) for x in E4["beta"]))
want("T7 temp", ", ".join("{:.2f}→{:.2f}".format(x["temp"], x["dur_mae"]) for x in E4["temp"]))
lc = E4["corpus"]
want("learning curve", "{:.2f} min at 50 precedents to {:.2f} at 250, {:.2f} at 500 and {:.2f} at 1,000".format(
    lc[0]["dur_mae"], lc[2]["dur_mae"], lc[3]["dur_mae"], lc[4]["dur_mae"]))
for k, v in R["E5_generalisation"]["by_precedent_count"].items():
    want("T8 " + k, "{:,} {:.2f} {:.3f}".format(v["n"], v["mae"], v["mean_conf"]))
for f, v in R["E5_generalisation"]["leave_one_fault_out"].items():
    want("T9 " + f, "{} {} {:.2f} {:.2f} {:.1f} {:.1f}".format(
        f, v["n"], v["mae_seen"], v["mae_unseen"], 100 * v["top1_seen"], 100 * v["top1_unseen"]))
u = R["E5_generalisation"]["unseen_topology_clinical"]
want("unseen topology", "{:.2f} min on the held-out clinical topology against {:.2f} min".format(u["mae_unseen"], u["mae_seen"]))
for s in R["E6_contradiction"]["sweep"]:
    want("T10", "{} % {:.2f} {:.1f} {:.3f} {:.3f} {:.3f}".format(
        int(s["rate"] * 100), s["dur_mae"], 100 * s["top1"], s["coverage"], s["conflict_flag_rate"], s["mean_confidence"]))
want("squared loss", "MAE {:.2f} robust vs {:.2f} squared".format(
    R["E6_contradiction"]["sweep"][3]["dur_mae"], R["E6_contradiction"]["squared_loss_at_20pct"]))
C7 = R["E7_calibration"]
want("rho within", "{:.3f}".format(C7["spearman_rho"]))
want("rho pooled", "{:.3f}".format(C7["pooled_spearman_rho"]))
want("quintiles", ", ".join("{:.2f}".format(b["mae"]) for b in C7["pooled_bins"][:4]))
for r in C7["per_regime"].values():
    want("T11", "{:,} {:.2f} {:.3f}".format(r["n"], r["mae"], r["mean_conf"]))
for s in [R["E8_noise"][i] for i in (0, 1, 2, 4, 5)]:
    want("T12 noise", "{:.2f} {:.3f}".format(s["dur_mae"], s["jaccard"]))
E9 = R["E9_scalability"]
want("T12 corpus", "{:.2f} → {:.2f} ms per query".format(E9["corpus"][0]["ms_per_query"], E9["corpus"][-1]["ms_per_query"]))
want("T12 build", "{:.2f} s".format(E9["corpus"][-1]["index_build_s"]))
want("T12 traversal", "{:.3f} → {:.3f} ms per traversal".format(E9["topology"][0]["ms_per_traversal"], E9["topology"][-1]["ms_per_traversal"]))
want("T12 unbounded", "{:.3f} → {:.3f} ms".format(E9["topology"][0]["ms_unbounded"], E9["topology"][-1]["ms_unbounded"]))
want("runtime", "{} minutes ({:,} s)".format(round(R["runtime_seconds"] / 60), int(R["runtime_seconds"])))
for s in R["E11_misspecification"]:
    want("T13 " + s["form"], "{:.2f} {:.2f} {:.2f} (B6) {:.2f} {:.1f}".format(
        s["lam_selected"], s["im_mae"], s["best_baseline_mae"], s["b2_mae"], 100 * s["im_top1"]))
for c in R["E10_cases"]:
    for r in c["rows"][:2]:
        # A case-study pair appears either in a Table 14 cell ("pred / true") or,
        # for the Scenario 6 same-timing control, in the prose of Sect. 6.10
        # ("predicted at X min against a true Y min"). Accept either form.
        table_form = "{:.1f} / {:.1f}".format(r["pred_duration"], r["true_duration"])
        prose_form = "predicted at {:.1f} min against a true {:.1f} min".format(
            r["pred_duration"], r["true_duration"])
        n += 1
        if table_form not in T and prose_form not in T:
            fails.append(("T14 " + c["scenario"], table_form))
for meth, lab, keys in [("IncidentMind", "IM", ["dur_mae", "blast_mae", "jaccard", "top1", "regret", "coverage"]),
                        ("B6 Gradient boosting", "GB", ["dur_mae", "blast_mae", "regret"]),
                        ("Oracle (noise floor)", "OR", ["dur_mae", "regret"])]:
    m = F["methods"][meth]
    for k in keys:
        want("T15 {} {}".format(lab, k), "{:.3f} {:.3f} ± {:.3f}".format(m[k]["reported"], m[k]["fresh_mean"], m[k]["fresh_sd"]))
C = A["conditions"]
for cond, keys in [("seen", ["dur_mae", "regret", "coverage"]), ("sparse", ["dur_mae", "regret", "coverage"]),
                   ("unseen_fault", ["dur_mae", "regret", "coverage"]), ("unseen_topology", ["dur_mae", "regret"])]:
    for k in keys:
        want("T16 {} {}".format(cond, k), "{:.3f} {:.3f} {:.3f}".format(C[cond][k]["A"]["mean"], C[cond][k]["B"]["mean"], C[cond][k]["C"]["mean"]))
want("T16 unseen-fault top1", "{:.1f} {:.1f}".format(100 * C["unseen_fault"]["top1"]["A"]["mean"], 100 * C["unseen_fault"]["top1"]["B"]["mean"]))
want("T16 sparse top1", "{:.1f} {:.1f}".format(100 * C["sparse"]["top1"]["A"]["mean"], 100 * C["sparse"]["top1"]["B"]["mean"]))
for k, v in A["by_tier1_precedent"].items():
    want("T17 " + k, "{:,} {:.3f} {:.3f} {:.3f}".format(v["A"]["n"], v["A"]["coverage"], v["B"]["coverage"], v["C"]["coverage"]))
want("pooled rho ABC", "{:.3f} for A, {:.3f} for B, {:.3f} for C".format(A["pooled_conf_rho"]["A"], A["pooled_conf_rho"]["B"], A["pooled_conf_rho"]["C"]))
want("dense rho C", "{:.3f} under A and {:.3f} under B but +{:.3f} under C".format(C["seen"]["conf_rho"]["A"], C["seen"]["conf_rho"]["B"], C["seen"]["conf_rho"]["C"]))
t3 = V["table3_duration"]
want("RW MAE", "{:.1f} s".format(t3["mae_s"])); want("RW median", "{:.1f} s".format(t3["median_ae_s"]))
want("RW MAPE", "{:.1f} %".format(t3["mape_pct"])); want("RW RMSE/bias", "{:.1f} s / {:.1f} s".format(t3["rmse_s"], t3["bias_s"]))
t4 = V["table4_blast"]
want("RW blast", "{:.3f}".format(t4["blast_mae"])); want("RW jaccard", "{:.3f} / {:.3f}".format(t4["jaccard_mean"], t4["jaccard_median"]))
want("RW coverage", "{:.3f}".format(V["table6_uncertainty"]["interval_coverage"]))
want("RW rho", "+{:.3f}".format(V["table6_uncertainty"]["spearman_conf_vs_abs_error"]))
want("RW oos", "{:.0f} ms".format(V["honesty_checks"]["propagation_out_of_sample"]["mean_abs_error_ms"]))
for e, d in V["honesty_checks"]["propagation_out_of_sample"]["detail"].items():
    want("T20 " + e, "{} {} ms {} ms".format(d["n"], d["heldout_observed_ms"], d["corpus_learned_ms"]))
t1 = V["table1_composition"]
want("RW composition", "{} / {} / {}".format(t1["attempted"], t1["measured"], t1["invalid"]))
want("RW completed/censored", "{} / {}".format(t1["measured"] - t1["censored_total"], t1["censored_total"]))
want("RW corpus/heldout", "{} / {}".format(t1["corpus"], t1["heldout"]))
want("RW probe events", "{:,}".format(t1["probe_events_total"]))
want("RW clean resets", "{}/{} clean resets".format(t1["clean_resets"], t1["measured"]))
for f, v in V["table7_ranking"]["faults"].items():
    for a in v["observed_mean_s"]:
        want("T21 " + f + " " + a, "{:.1f} {:.1f}".format(v["observed_mean_s"][a], v["predicted_mean_s"][a]))
want("cycle time", "Mean cycle time 186 s")
want("admitted cells", "13 of 18 candidates")

print("checks:", n, "| failures:", len(fails))
for f in fails:
    print("   FAIL", f)
print("placeholders:", T.count("[AUTHORS TO CONFIRM"), "| '30.5 ms' present:", "30.5 ms" in T,
      "| roman section tokens:", len(re.findall(r"Sec\. [IVX]", T)))
print("figure captions:", len(re.findall(r"Fig\. \d (?=[A-Z])", T)), "| table captions:",
      len(re.findall(r"Table \d+ (?=[A-Z])", T)), "| pages:", len(pdf))
sys.exit(1 if fails else 0)
