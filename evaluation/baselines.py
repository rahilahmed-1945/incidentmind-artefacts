"""
Baseline recovery-outcome estimators and an oracle reference.

Every estimator exposes the same interface as IncidentMindEstimator:

    estimate(topo_name, fault, origin, action, tau) -> dict(
        duration, blast, affected, confidence)

so that all methods are scored by identical code on identical splits.

B0  RunbookSOP      diagnosis + fixed runbook (approximates current practice:
                    an RCA tool names the fault, the operator applies the
                    documented runbook action and its documented recovery time)
B1  GlobalMean      corpus mean; ignores action, timing and topology
B2  ActionMean      context-independent recovery estimation (per-action mean)
B3  NaiveLinear     per-action ordinary least squares, D ~ a + b*tau
B4  PrecedentFree   dependency propagation only, no retrieved history
B5  PrecedentKNN    similarity-weighted mean of retrieved precedent outcomes
B6  GradBoost       gradient-boosted regression trees on tabular features
ORACLE              privileged access to the hidden generator parameters;
                    reports the irreducible-noise floor, not a competitor
"""
import math

import numpy as np

from environment import _EFFICACY, _ELL, _spread_penalty
from estimator import predict_affected, reachable


# --------------------------------------------------------------------------
# helpers shared by the non-graph baselines
# --------------------------------------------------------------------------
def _cooccurrence_prior(records):
    """P(service affected | origin) frequency table, for set prediction."""
    tab = {}
    for r in records:
        key = (r["topology"], r["origin"])
        d = tab.setdefault(key, {})
        for s in r["affected"]:
            d[s] = d.get(s, 0) + 1
    return tab


def _set_from_prior(prior, topo, topo_name, origin, size):
    d = prior.get((topo_name, origin), {})
    ranked = [s for s, _ in sorted(d.items(), key=lambda z: -z[1]) if s != origin]
    if not ranked:
        ranked = [s for s in topo.adj.get(origin, [])]
    out = {origin}
    for s in ranked:
        if len(out) >= max(1, int(round(size))):
            break
        out.add(s)
    return out


class _Base:
    def fit(self, memory, records):
        self.mem, self.records = memory, records
        self.prior = _cooccurrence_prior(records)
        return self

    def _pack(self, topo_name, origin, D, B, conf=0.5):
        topo = self.mem.topos[topo_name]
        S = _set_from_prior(self.prior, topo, topo_name, origin, B)
        return {"duration": float(max(0.5, D)), "blast": int(max(1, round(B))),
                "affected": S, "confidence": conf, "lo": max(0.0, D * 0.6),
                "hi": D * 1.4, "n_precedent": 0, "tier": 0, "conflict": False}


# --------------------------------------------------------------------------
class RunbookSOP(_Base):
    name = "B0 Runbook/SOP"

    def fit(self, memory, records):
        super().fit(memory, records)
        self.dur, self.blast, self.act = {}, {}, {}
        for f in set(r["fault"] for r in records):
            sub = [r for r in records if r["fault"] == f]
            # runbook action = the action most often applied to this fault
            counts = {}
            for r in sub:
                counts[r["action"]] = counts.get(r["action"], 0) + 1
            a = max(counts, key=counts.get)
            self.act[f] = a
            rb = [r for r in sub if r["action"] == a]
            self.dur[f] = float(np.median([r["duration"] for r in rb]))
            self.blast[f] = float(np.median([r["blast"] for r in rb]))
        self.gd = float(np.median([r["duration"] for r in records]))
        self.gb = float(np.median([r["blast"] for r in records]))
        return self

    def estimate(self, topo_name, fault, origin, action, tau):
        # documented runbook outcome: independent of timing and of the action
        # actually contemplated (the runbook prescribes one action)
        return self._pack(topo_name, origin, self.dur.get(fault, self.gd),
                          self.blast.get(fault, self.gb), conf=0.5)


class GlobalMean(_Base):
    name = "B1 Global mean"

    def fit(self, memory, records):
        super().fit(memory, records)
        self.d = float(np.mean([r["duration"] for r in records]))
        self.b = float(np.mean([r["blast"] for r in records]))
        return self

    def estimate(self, topo_name, fault, origin, action, tau):
        return self._pack(topo_name, origin, self.d, self.b)


class ActionMean(_Base):
    name = "B2 Context-independent"

    def fit(self, memory, records):
        super().fit(memory, records)
        self.d, self.b = {}, {}
        for a in set(r["action"] for r in records):
            sub = [r for r in records if r["action"] == a]
            self.d[a] = float(np.mean([r["duration"] for r in sub]))
            self.b[a] = float(np.mean([r["blast"] for r in sub]))
        self.gd = float(np.mean([r["duration"] for r in records]))
        self.gb = float(np.mean([r["blast"] for r in records]))
        return self

    def estimate(self, topo_name, fault, origin, action, tau):
        return self._pack(topo_name, origin, self.d.get(action, self.gd),
                          self.b.get(action, self.gb))


class NaiveLinear(_Base):
    name = "B3 Naive linear"

    def fit(self, memory, records):
        super().fit(memory, records)
        self.coef = {}
        for a in set(r["action"] for r in records):
            sub = [r for r in records if r["action"] == a]
            if len(sub) >= 4:
                x = np.array([r["tau"] for r in sub])
                y = np.array([r["duration"] for r in sub])
                A = np.vstack([np.ones_like(x), x]).T
                self.coef[a] = np.linalg.lstsq(A, y, rcond=None)[0]
        x = np.array([r["tau"] for r in records])
        y = np.array([r["duration"] for r in records])
        self.gcoef = np.linalg.lstsq(np.vstack([np.ones_like(x), x]).T, y, rcond=None)[0]
        self.b = {}
        for a in set(r["action"] for r in records):
            sub = [r for r in records if r["action"] == a]
            self.b[a] = float(np.mean([r["blast"] for r in sub]))
        self.gb = float(np.mean([r["blast"] for r in records]))
        return self

    def estimate(self, topo_name, fault, origin, action, tau):
        c = self.coef.get(action, self.gcoef)
        return self._pack(topo_name, origin, c[0] + c[1] * tau,
                          self.b.get(action, self.gb))


class PrecedentFree(_Base):
    """Dependency propagation only: no incident memory is consulted."""
    name = "B4 Precedent-free"

    def fit(self, memory, records):
        super().fit(memory, records)
        hp = memory.hp
        X, y = [], []
        for r in records:
            topo = memory.topos[r["topology"]]
            S = predict_affected(memory, topo, r["origin"],
                                 r["tau"] + memory.clag_for(r["action"], r["fault"]),
                                 hp["theta"])
            X.append([1.0, r["tau"], len(S)])
            y.append(r["duration"])
        self.c = np.linalg.lstsq(np.array(X), np.array(y), rcond=None)[0]
        return self

    def estimate(self, topo_name, fault, origin, action, tau):
        hp = self.mem.hp
        topo = self.mem.topos[topo_name]
        S = predict_affected(self.mem, topo, origin,
                             tau + self.mem.clag_for(action, fault), hp["theta"])
        D = self.c[0] + self.c[1] * tau + self.c[2] * len(S)
        return {"duration": float(max(0.5, D)), "blast": len(S), "affected": S,
                "confidence": 0.5, "lo": max(0.0, D * 0.6), "hi": D * 1.4,
                "n_precedent": 0, "tier": 0, "conflict": False}


class PrecedentKNN(_Base):
    """Retrieval without the timing-duration law (isolates Step 2)."""
    name = "B5 Precedent k-NN"

    def estimate(self, topo_name, fault, origin, action, tau):
        idx, sims, ctier, tier = self.mem.retrieve(topo_name, fault, origin, action)
        if idx.size == 0:
            return self._pack(topo_name, origin, self.mem.mean_dur,
                              self.mem.mean_blast, conf=0.1)
        w = np.exp((sims - sims.max()) / self.mem.hp["temp"])
        w = w * np.power(self.mem.hp["tier_penalty"], ctier - 1)
        w /= max(w.sum(), 1e-12)
        d = float(np.average(self.mem.col_dur[idx], weights=w))
        b = float(np.average(self.mem.col_blast[idx], weights=w))
        return self._pack(topo_name, origin, d, b, conf=0.5)


# --------------------------------------------------------------------------
# Gradient-boosted regression trees (self-contained, squared loss)
# --------------------------------------------------------------------------
class _Node:
    __slots__ = ("j", "thr", "left", "right", "val")

    def __init__(self):
        self.j = self.thr = self.left = self.right = self.val = None


def _grow(X, g, depth, min_leaf):
    node = _Node()
    if depth == 0 or len(g) < 2 * min_leaf:
        node.val = float(np.mean(g))
        return node
    best = (np.inf, None, None)
    n, p = X.shape
    for j in range(p):
        col = X[:, j]
        qs = np.unique(np.quantile(col, [0.15, 0.3, 0.45, 0.6, 0.75, 0.9]))
        for thr in qs:
            m = col <= thr
            nl, nr = int(m.sum()), int((~m).sum())
            if nl < min_leaf or nr < min_leaf:
                continue
            sse = float(g[m].var() * nl + g[~m].var() * nr)
            if sse < best[0]:
                best = (sse, j, float(thr))
    if best[1] is None:
        node.val = float(np.mean(g))
        return node
    _, j, thr = best
    m = X[:, j] <= thr
    node.j, node.thr = j, thr
    node.left = _grow(X[m], g[m], depth - 1, min_leaf)
    node.right = _grow(X[~m], g[~m], depth - 1, min_leaf)
    return node


def _pred_tree(node, x):
    while node.val is None:
        node = node.left if x[node.j] <= node.thr else node.right
    return node.val


class GradBoost(_Base):
    """Strong supervised reference trained on exactly the same corpus."""
    name = "B6 Gradient boosting"

    def __init__(self, rounds=150, lr=0.08, depth=3, min_leaf=8):
        self.rounds, self.lr, self.depth, self.min_leaf = rounds, lr, depth, min_leaf

    def _feats(self, memory, topo_name, fault, origin, action, tau):
        topo = memory.topos[topo_name]
        reach = reachable(topo, origin)
        hp = memory.hp
        S = predict_affected(memory, topo, origin,
                             tau + memory.clag_for(action, fault), hp["theta"])
        v = [tau, len(topo.adj[origin]), len(reach), len(S), len(topo.nodes)]
        v += [1.0 if fault == f else 0.0 for f in self.faults]
        v += [1.0 if action == a else 0.0 for a in self.actions]
        v += [1.0 if topo_name == t else 0.0 for t in self.tnames]
        return v

    def fit(self, memory, records):
        super().fit(memory, records)
        self.faults = sorted(set(r["fault"] for r in records))
        self.actions = sorted(set(r["action"] for r in records))
        self.tnames = sorted(memory.topos.keys())
        Xd = np.array([self._feats(memory, r["topology"], r["fault"], r["origin"],
                                   r["action"], r["tau"]) for r in records], dtype=float)
        for target in ("duration", "blast"):
            y = np.array([r[target] for r in records], dtype=float)
            base = float(np.mean(y))
            pred = np.full_like(y, base)
            trees = []
            for _ in range(self.rounds):
                resid = y - pred
                t = _grow(Xd, resid, self.depth, self.min_leaf)
                step = np.array([_pred_tree(t, x) for x in Xd])
                pred += self.lr * step
                trees.append(t)
            setattr(self, "_base_" + target, base)
            setattr(self, "_trees_" + target, trees)
        return self

    def _predict(self, target, x):
        v = getattr(self, "_base_" + target)
        for t in getattr(self, "_trees_" + target):
            v += self.lr * _pred_tree(t, x)
        return v

    def estimate(self, topo_name, fault, origin, action, tau):
        x = np.array(self._feats(self.mem, topo_name, fault, origin, action, tau),
                     dtype=float)
        d = self._predict("duration", x)
        b = self._predict("blast", x)
        return self._pack(topo_name, origin, d, b, conf=0.5)


# --------------------------------------------------------------------------
class Oracle:
    """
    Privileged reference: knows the hidden efficacy/latency/beta constants and
    the true propagation realisation, but not the multiplicative noise draw.
    Its residual error is therefore the irreducible noise floor of the testbed.
    NOT a competing method -- reported only to bound achievable accuracy.
    """
    name = "Oracle (noise floor)"

    def fit(self, memory, records):
        self.mem = memory
        return self

    def estimate_with_realisation(self, real, action, tau):
        eps = _EFFICACY[real.fault].get(action, 0.20)
        ell = _ELL[action]
        c_lag = ell * (0.5 + 1.5 * (1.0 - eps))
        S = real.affected_at(tau + c_lag)
        S.add(real.origin)
        R = (ell / eps) * _spread_penalty(len(S) / max(1, len(real.reach)))
        D = tau + R
        return {"duration": float(D), "blast": len(S), "affected": S,
                "confidence": 0.99, "lo": D * 0.75, "hi": D * 1.35,
                "n_precedent": 0, "tier": 0, "conflict": False}


ALL_BASELINES = [RunbookSOP, GlobalMean, ActionMean, NaiveLinear,
                 PrecedentFree, PrecedentKNN, GradBoost]
