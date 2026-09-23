"""Metrics, statistical tests and calibration diagnostics."""
import numpy as np
from scipy import stats


# ---------------- point-estimate error ----------------
def mae(y, p):
    return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))


def rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))


def mape(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.mean(np.abs(y - p) / np.maximum(np.abs(y), 1e-9)) * 100.0)


def smape(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.mean(2 * np.abs(y - p) / np.maximum(np.abs(y) + np.abs(p), 1e-9)) * 100.0)


# ---------------- set prediction ----------------
def set_scores(true_set, pred_set):
    t, p = set(true_set), set(pred_set)
    inter = len(t & p)
    union = len(t | p) or 1
    prec = inter / len(p) if p else 0.0
    rec = inter / len(t) if t else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"jaccard": inter / union, "precision": prec, "recall": rec, "f1": f1}


# ---------------- decision quality ----------------
def ranking_scores(true_d, pred_d, rng=None):
    """
    true_d, pred_d: arrays of ground-truth / predicted durations over the
    candidate decisions of ONE incident (lower is better).
    Ties in pred_d are broken uniformly at random, so a non-discriminating
    estimator scores at chance rather than benefiting from list order.
    """
    true_d = np.asarray(true_d, float)
    pred_d = np.asarray(pred_d, float)
    n = len(true_d)
    if n < 2:
        return None
    rng = rng or np.random.default_rng(0)
    jitter = rng.random(n) * 1e-9
    choice = int(np.argmin(pred_d + jitter))
    best = int(np.argmin(true_d))
    regret = float(true_d[choice] - true_d[best])
    worst = float(true_d.max() - true_d[best])
    # pairwise concordance
    conc = tot = 0
    for i in range(n):
        for j in range(i + 1, n):
            if true_d[i] == true_d[j]:
                continue
            tot += 1
            di, dj = pred_d[i] + jitter[i], pred_d[j] + jitter[j]
            if (true_d[i] < true_d[j]) == (di < dj):
                conc += 1
    pair = conc / tot if tot else 0.5
    try:
        kt = float(stats.kendalltau(true_d, pred_d + jitter).statistic)
    except Exception:
        kt = 0.0
    return {"top1": 1.0 if choice == best else 0.0, "regret": regret,
            "regret_norm": regret / worst if worst > 1e-9 else 0.0,
            "pairwise": pair, "kendall": 0.0 if np.isnan(kt) else kt}


# ---------------- uncertainty / calibration ----------------
def coverage(y, lo, hi):
    y, lo, hi = np.asarray(y), np.asarray(lo), np.asarray(hi)
    return float(np.mean((y >= lo) & (y <= hi)))


def confidence_diagnostics(conf, abs_err, n_bins=5):
    """
    Does the confidence score carry information about the error?
    Reports Spearman rho (expected negative), and mean error per tercile.
    """
    conf, abs_err = np.asarray(conf, float), np.asarray(abs_err, float)
    if np.std(conf) < 1e-12 or np.std(abs_err) < 1e-12:
        rho, pval = 0.0, 1.0
    else:
        rho, pval = stats.spearmanr(conf, abs_err)
    order = np.argsort(conf)
    thirds = np.array_split(order, 3)
    terciles = [float(np.mean(abs_err[t])) for t in thirds]
    qs = np.quantile(conf, np.linspace(0, 1, n_bins + 1))
    bins = []
    for i in range(n_bins):
        upper = (conf <= qs[i + 1]) if i == n_bins - 1 else (conf < qs[i + 1])
        m = (conf >= qs[i]) & upper
        if m.sum() > 0:
            bins.append({"conf": float(conf[m].mean()), "mae": float(abs_err[m].mean()),
                         "n": int(m.sum())})
    return {"spearman_rho": float(rho), "p_value": float(pval),
            "tercile_mae": terciles, "bins": bins}


# ---------------- statistical comparison ----------------
def paired_bootstrap(a, b, n_boot=10000, seed=7, stat=np.mean):
    """
    Bootstrap CI for stat(a) - stat(b) over paired samples (a, b = per-item
    errors of two methods on identical items).
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    boots = stat(d[idx], axis=1)
    return {"delta": float(stat(d)),
            "ci_lo": float(np.percentile(boots, 2.5)),
            "ci_hi": float(np.percentile(boots, 97.5))}


def wilcoxon(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    if np.allclose(d, 0):
        return {"stat": 0.0, "p": 1.0}
    try:
        r = stats.wilcoxon(a, b, zero_method="wilcox", alternative="two-sided")
        return {"stat": float(r.statistic), "p": float(r.pvalue)}
    except Exception:
        return {"stat": float("nan"), "p": float("nan")}


def cliffs_delta(a, b):
    """Non-parametric effect size for paired error distributions."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) > 4000:
        rng = np.random.default_rng(11)
        s = rng.choice(len(a), 4000, replace=False)
        a, b = a[s], b[s]
    gt = (a[:, None] > b[None, :]).sum()
    lt = (a[:, None] < b[None, :]).sum()
    return float((gt - lt) / (len(a) * len(b)))


def fmt_p(p):
    if p != p:
        return "n/a"
    if p < 1e-4:
        return "<10^-4"
    if p < 1e-3:
        return "<0.001"
    return "{:.3f}".format(p)
