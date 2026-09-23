# -*- coding: utf-8 -*-
"""Redraw Fig. 1 (architecture) and Fig. 2 (mechanism workflow).

Content follows Sects. 3 and 4 of the article; no measured values appear, so these
two figures are schematic and depend on no artefact. Fig. 3 is a static illustration
of the demonstration dashboard (Table 2, status D) and is shipped as Fig3.png; it
contributes to no quantitative result and has no generating script here.

Usage:  python make_figs.py        # writes Fig1.png and Fig2.png at 600 dpi
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = HERE          # this script lives in figures/ and writes beside itself
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})

LIGHT, MID = "#f0f0f0", "#d9d9d9"


def box(ax, x, y, w, h, title, sub=None, fill=LIGHT, lw=0.9, title_size=8.5, sub_size=7.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.08",
                                fc=fill, ec="black", lw=lw))
    if sub:
        ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center", fontsize=title_size, weight="bold")
        ax.text(x + w / 2, y + h * 0.30, sub, ha="center", va="center", fontsize=sub_size, style="italic")
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=title_size, weight="bold")


def arrow(ax, x0, y0, x1, y1):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=9,
                                 lw=0.9, color="black", shrinkA=0, shrinkB=0))


def fig1():
    fig, ax = plt.subplots(figsize=(7.2, 10.5))
    ax.set_xlim(0, 10); ax.set_ylim(0, 14.6); ax.axis("off")
    # sources
    ax.add_patch(FancyBboxPatch((0.5, 12.05), 9.0, 2.35, boxstyle="round,pad=0,rounding_size=0.1",
                                fc="white", ec="black", lw=0.8, ls=(0, (3, 2))))
    ax.text(5, 14.12, "Heterogeneous operational data sources", ha="center", fontsize=8, weight="bold")
    srcs = ["Logs", "Alerts", "Deployments", "Tickets", "Communication\n(chat)", "Observability\ndata", "Topology"]
    xs = [0.8, 3.05, 5.3, 7.55]
    for i, s in enumerate(srcs[:4]):
        box(ax, xs[i], 13.05, 1.95, 0.8, s, title_size=7.4)
    for i, s in enumerate(srcs[4:]):
        box(ax, 1.9 + i * 2.25, 12.2, 1.95, 0.72, s, title_size=6.8)
    arrow(ax, 5, 12.05, 5, 11.35)
    # ingestion
    box(ax, 0.5, 10.3, 9.0, 1.05, "Incident data ingestion layer",
        "source adapters · canonical event schema · time-aligned, provenance-tagged")
    for x in (2.0, 5.0, 8.0):
        arrow(ax, 5, 10.3, x, 9.55)
    # reconstruction
    box(ax, 0.5, 7.85, 2.9, 1.7, "Incident memory",
        "outcome-indexed precedent:\naction, timing, duration,\naffected set", fill=MID, title_size=8)
    box(ax, 3.55, 7.85, 2.9, 1.7, "Dependency &\nblast radius",
        "forward propagation\nover the service\nimpact graph", fill=MID, title_size=8)
    box(ax, 6.6, 7.85, 2.9, 1.7, "Timeline\nreconstruction",
        "ordered chronology;\nper-service degradation\ntimes; action marked", fill=MID, title_size=8)
    for x in (2.0, 5.0, 8.0):
        arrow(ax, x, 7.85, x, 6.95)
    # replay
    box(ax, 0.5, 5.7, 9.0, 1.25, "What-if recovery scenario replay layer",
        "estimates the outcome of an alternative decision (A′, τ′) — the only layer claimed as novel",
        lw=2.2, sub_size=7)
    arrow(ax, 5, 5.7, 5, 4.95)
    # decision support
    box(ax, 0.5, 3.9, 9.0, 1.05, "Decision support layer",
        "side-by-side comparison of alternatives · human-in-the-loop · no execution")
    arrow(ax, 5, 3.9, 5, 3.2)
    ax.text(5, 2.95, "Operator-facing outputs (per alternative)", ha="center", fontsize=7.8, weight="bold")
    outs = ["Predicted\nduration D̂", "Predicted blast\nradius B̂", "Affected\nservices Ŝ",
            "Confidence c and\ninterval [D_lo, D_hi]"]
    for i, o in enumerate(outs):
        box(ax, 0.5 + i * 2.3, 1.8, 2.1, 0.95, o, fill="white", title_size=6.9)
    # legend
    ax.add_patch(FancyBboxPatch((1.6, 0.15), 6.8, 1.3, boxstyle="round,pad=0,rounding_size=0.05",
                                fc="white", ec="black", lw=0.6))
    for j, (lab, fc, lw) in enumerate([("Supporting infrastructure layer", LIGHT, 0.9),
                                       ("Reconstruction layer feeding replay", MID, 0.9),
                                       ("Primary contribution (scenario replay)", LIGHT, 2.2)]):
        y = 1.15 - j * 0.4
        ax.add_patch(FancyBboxPatch((1.85, y - 0.13), 0.6, 0.27, boxstyle="square,pad=0", fc=fc, ec="black", lw=lw))
        ax.text(2.65, y, lab, va="center", fontsize=7)
    fig.savefig(os.path.join(OUT, "Fig1.png"), dpi=600, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


def fig2():
    fig, ax = plt.subplots(figsize=(7.4, 12.0))
    ax.set_xlim(0, 10); ax.set_ylim(0, 16.2); ax.axis("off")
    box(ax, 0.5, 14.9, 9.0, 1.15, "Current incident and candidate decision",
        "I = (f, t₀, o) with impact graph G and precedent corpus P;  candidate (A, τ)")
    arrow(ax, 5, 14.9, 5, 14.25)
    box(ax, 0.5, 12.65, 9.0, 1.6, "Step 1 — Precedent retrieval",
        "structural descriptor x(o), Eq. (3); similarity s(I, Iᵢ), Eq. (4);\n"
        "tiers T₁–T₃ relaxed only below m_relax; top-k weights wᵢ, Eq. (5)")
    arrow(ax, 5, 12.65, 5, 12.0)
    box(ax, 0.5, 9.95, 9.0, 2.05, "Step 2 — Timing–duration law",
        "reduced form r_red(τ) = ℓ + κ(1 − e^(−γτ)), robust fit Eqs. (6)–(7), sparse-precedent policy;\n"
        "structural level ĉ, Eq. (8); residual scale σ̂ and conflict test, Eq. (10);\n"
        "novelty ν, Eqs. (17)–(18); moderated dispersion, Eq. (21)")
    arrow(ax, 5, 9.95, 5, 9.3)
    box(ax, 0.5, 7.4, 9.0, 1.9, "Step 3 — Dependency-propagation blast radius",
        "learned edge delays d̂ and probabilities p̂, Eqs. (11)–(12); containment lag ĥ(A, f), Eq. (13);\n"
        "horizon-bounded Dijkstra → Ŝ(A, τ), B̂ = |Ŝ|, spread fraction ρ̂, Eq. (14)")
    arrow(ax, 5, 7.4, 5, 6.75)
    box(ax, 0.5, 5.55, 9.0, 1.2, "Blend and duration estimate",
        "r̂ = r_red^(1−λ) · r_str^λ with r_str = ĉ(1 + βρ̂);  D̂ = τ + r̂, Eq. (9); λ_eff under novelty, Eq. (19)")
    arrow(ax, 5, 5.55, 5, 4.9)
    box(ax, 0.5, 3.45, 9.0, 1.45, "Step 4 — Confidence and prediction interval",
        "c from tier, dispersion, support and similarity, Eq. (15); interval [D̂ ± z σ̂ ψ], Eq. (16);\n"
        "conflict and novelty adjustments, Eqs. (10), (20)")
    arrow(ax, 5, 3.45, 5, 2.8)
    box(ax, 0.5, 1.65, 9.0, 1.15, "Decision support output",
        "(D̂, B̂, Ŝ, c, [D_lo, D_hi], conflict flag) per alternative; compared side by side, presented to the operator",
        lw=2.0, sub_size=6.8)
    # side note: caching
    ax.add_patch(FancyBboxPatch((0.5, 0.15), 9.0, 1.1, boxstyle="round,pad=0,rounding_size=0.08",
                                fc="white", ec="black", lw=0.6, ls=(0, (3, 2))))
    ax.text(5, 0.7, "Steps 1–2 depend only on (f, o, A), not on τ: computed once per candidate action\n"
                    "and reused across the timing sweep (Algorithm 1)", ha="center", va="center", fontsize=6.9, style="italic")
    fig.savefig(os.path.join(OUT, "Fig2.png"), dpi=600, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


if __name__ == "__main__":
    fig1(); fig2()
    print("figures written")
