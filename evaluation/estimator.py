"""
IncidentMind what-if recovery estimator (reference implementation).

Given a current incident I = (f, t0, ...) and a candidate recovery decision
(A, tau), produce (D_hat, B_hat, S_hat, c) with c a confidence score, plus a
prediction interval and an explicit precedent-conflict diagnostic.

The estimator observes ONLY:
  * the static service impact graph (topology; no hidden edge parameters), and
  * a corpus of past incident records emitted by environment.generate_corpus.
It never observes efficacy, per-edge delays/probabilities or noise scales.

Mechanism (Sec. IV of the paper):
  Step 1  precedent retrieval under a tiered relaxation policy
  Step 2  robust weighted fit of the timing-duration law
              r(tau) = ell + kappa * (1 - exp(-gamma * tau)),  D = tau + r(tau)
  Step 3  dependency-propagation blast radius with learned edge delays
  Step 4  precedent-agreement confidence, prediction interval, conflict flag

Retrieval and the Step-2 fit depend only on (topology, fault, origin, action),
never on tau, so both are cached per context; this is what makes exhaustive
counterfactual grids tractable.
"""
import heapq
import math

import numpy as np
from scipy.optimize import least_squares

ACTION_FAMILY = {
    "pod_restart": "restart", "pool_restart": "restart",
    "scale_replicas": "capacity",
    "rollback_deploy": "change",
    "reroute_traffic": "traffic", "circuit_breaker": "traffic",
    "degraded_mode": "traffic",
}

DEFAULT_HP = {
    "k": 12,              # max precedents retrieved
    "m_min": 5,           # precedents needed for the full 3-parameter fit
    "m_relax": 3,         # relax the retrieval constraint only below this count
    "tier_penalty": 0.25,  # extra weight discount per relaxation tier
    "temp": 0.18,         # softmax temperature on similarity -> weights
    "w_fault": 0.45,      # similarity kernel weights
    "w_struct": 0.35,
    "w_origin": 0.20,
    "beta": 0.55,         # spread-penalty exponent in the structural route
    "lam_blend": 0.35,    # weight of the structural route vs the reduced form
    "theta": 0.45,        # min path reliability for inclusion in S_hat
    "clag": 1.6,          # fallback containment lag when a cell is unlearnable
    "clag_scale": 1.0,    # global multiplier on learned lags (fit on validation)
    "lam": 1.10,          # confidence dispersion sensitivity
    "k0": 6.0,            # confidence support half-saturation
    "z": 1.28,            # prediction-interval multiplier (fit on validation)
    "conflict_sep": 3.5,  # bimodality separation threshold (robust scales)
    "use_law": True,      # ablation switch: Step 2 law vs weighted mean
    "use_dep": True,      # ablation switch: dependency correction
    "use_tiers": True,    # ablation switch: tiered relaxation
    "robust": True,       # ablation switch: robust vs squared loss

    # --- novelty-aware fallback (Sec. IV-G); OFF reproduces the frozen system
    "novelty_aware": False,
    "nov_kappa0": 4.0,    # half-saturation on the tier-1 precedent count
    "nov_sref": 0.6,      # similarity reference for full support
    "nov_a": 1.0,         # exponent shaping how sharply novelty engages
    "nov_gamma_c": 0.0,   # confidence discount per unit novelty
    "nov_gamma_i": 0.0,   # interval inflation per unit novelty

    # --- small-sample dispersion fix (Sec. IV-E); OFF reproduces A and B
    "interval_fix": False,
    "scale_prior_df": 4.0,  # prior weight on the pooled per-action scale
}

TIER_FACTOR = {1: 1.00, 2: 0.85, 3: 0.70, 4: 0.45}


# --------------------------------------------------------------------------
# Topology-derived, observable structure
# --------------------------------------------------------------------------
def _reachable_cached(topo):
    if not hasattr(topo, "_reach_cache"):
        topo._reach_cache = {}
    return topo._reach_cache


def reachable(topo, origin):
    c = _reachable_cached(topo)
    if origin not in c:
        c[origin] = topo.reachable(origin)
    return c[origin]


def _origin_features(topo, origin):
    reach = reachable(topo, origin)
    n = max(1, len(topo.nodes))
    frontier, seen, d, depth = [origin], {origin}, 0, 0
    while frontier:
        d += 1
        nxt = []
        for u in frontier:
            for v in topo.adj[u]:
                if v not in seen:
                    seen.add(v)
                    nxt.append(v)
        if nxt:
            depth = d
        frontier = nxt
    sinks = sum(1 for s in reach if not topo.adj[s])
    return np.array([len(topo.adj[origin]) / 4.0, len(reach) / n,
                     depth / 6.0, sinks / max(1, len(reach))], dtype=float)


def _hop_table(topo):
    """All-pairs undirected hop distances (topologies here are small)."""
    if hasattr(topo, "_hops"):
        return topo._hops
    und = {s: set(topo.adj[s]) for s in topo.nodes}
    for u in list(und):
        for v in list(und[u]):
            und[v].add(u)
    tab = {}
    for src in topo.nodes:
        dist, frontier, d = {src: 0}, [src], 0
        while frontier:
            d += 1
            nxt = []
            for u in frontier:
                for v in und[u]:
                    if v not in dist:
                        dist[v] = d
                        nxt.append(v)
            frontier = nxt
        tab[src] = dist
    topo._hops = tab
    return tab


# --------------------------------------------------------------------------
# Incident memory (retrieval layer)
# --------------------------------------------------------------------------
class IncidentMemory:
    """Outcome-indexed precedent store with a learned propagation model."""

    def __init__(self, topos, records, hp=None):
        self.hp = dict(DEFAULT_HP)
        if hp:
            self.hp.update(hp)
        self.topos = topos
        self.records = list(records)
        self._vectorise()
        self._learn_propagation()
        self._learn_clag()
        self._learn_action_priors()
        self._sim_cache = {}
        self._ctx_cache = {}

    # ---- learned containment lag (Step 3 parameter estimation) ----
    def _learn_clag(self, max_per_cell=60, grid=None):
        """
        Estimate the containment lag h(A, f): how long propagation continues
        after the action is applied.  Fitted per (action, fault) cell by
        minimising blast-radius error on TRAIN records, with hierarchical
        backoff to per-action and then to a global constant.
        """
        grid = grid if grid is not None else np.arange(0.2, 4.01, 0.3)
        by_cell, by_act = {}, {}
        for r in self.records:
            by_cell.setdefault((r["action"], r["fault"]), []).append(r)
            by_act.setdefault(r["action"], []).append(r)

        def best_lag(rows):
            if len(rows) > max_per_cell:
                step = max(1, len(rows) // max_per_cell)
                rows = rows[::step][:max_per_cell]
            best, bl = np.inf, self.hp["clag"]
            for cl in grid:
                err = 0.0
                for r in rows:
                    S = predict_affected(self, self.topos[r["topology"]], r["origin"],
                                         r["tau"] + cl, self.hp["theta"])
                    err += abs(len(S) - r["blast"])
                err /= len(rows)
                if err < best:
                    best, bl = err, float(cl)
            return bl

        self.clag_action = {a: best_lag(rows) for a, rows in by_act.items()
                            if len(rows) >= 8}
        self.clag_cell = {c: best_lag(rows) for c, rows in by_cell.items()
                          if len(rows) >= 12}

    def clag_for(self, action, fault):
        v = self.clag_cell.get((action, fault))
        if v is None:
            v = self.clag_action.get(action, self.hp["clag"])
        return v * self.hp["clag_scale"]

    # ---- columnar view of the corpus (vectorised similarity) ----
    def _vectorise(self):
        R = self.records
        self.n = len(R)
        self.faults_u = sorted(set(r["fault"] for r in R))
        self.actions_u = sorted(set(r["action"] for r in R))
        fi = {f: i for i, f in enumerate(self.faults_u)}
        ai = {a: i for i, a in enumerate(self.actions_u)}
        self.col_fault = np.array([fi[r["fault"]] for r in R], dtype=np.int32)
        self.col_action = np.array([ai[r["action"]] for r in R], dtype=np.int32)
        self.col_topo = np.array([r["topology"] for r in R], dtype=object)
        self.col_origin = np.array([r["origin"] for r in R], dtype=object)
        self.col_tau = np.array([r["tau"] for r in R], dtype=float)
        self.col_dur = np.array([r["duration"] for r in R], dtype=float)
        self.col_blast = np.array([r["blast"] for r in R], dtype=float)
        self._fi, self._ai = fi, ai
        feats, self.col_rho = [], []
        for r in R:
            t = self.topos[r["topology"]]
            feats.append(_origin_features(t, r["origin"]))
            self.col_rho.append(r["blast"] / max(1, len(reachable(t, r["origin"]))))
        self.X = np.vstack(feats)
        self.col_rho = np.array(self.col_rho, dtype=float)
        fam = {a: ACTION_FAMILY.get(a, a) for a in self.actions_u}
        self.col_family = np.array([fam[r["action"]] for r in R], dtype=object)

    # ---- learned propagation model (from observable arrival timelines) ----
    def _learn_propagation(self):
        obs_delay, obs_hit, obs_tot = {}, {}, {}
        for r in self.records:
            topo = self.topos[r["topology"]]
            arr, aff = r["arrivals"], set(r["affected"])
            for e in topo.edges:
                u, v = e
                if u in aff:
                    obs_tot[e] = obs_tot.get(e, 0) + 1
                    if v in aff:
                        obs_hit[e] = obs_hit.get(e, 0) + 1
                if u in arr and v in arr and arr[v] >= arr[u]:
                    obs_delay.setdefault(e, []).append(arr[v] - arr[u])
        all_d = [d for lst in obs_delay.values() for d in lst]
        self._global_delay = float(np.median(all_d)) if all_d else 2.0
        self.edge_delay, self.edge_prob = {}, {}
        for topo in self.topos.values():
            for e in topo.edges:
                lst = obs_delay.get(e, [])
                self.edge_delay[e] = (float(np.median(lst)) if len(lst) >= 3
                                      else self._global_delay)
                h, t = obs_hit.get(e, 0), obs_tot.get(e, 0)
                self.edge_prob[e] = (h + 1.0) / (t + 2.0) if t > 0 else 0.85

    def _learn_action_priors(self):
        """Pooled per-action law parameters, used when precedent is sparse."""
        self.pooled = {}
        for a in self.actions_u:
            m = self.col_action == self._ai[a]
            if m.sum() >= 8:
                self.pooled[a] = _fit_law(self.col_tau[m],
                                          self.col_dur[m] - self.col_tau[m],
                                          np.ones(int(m.sum())), self.hp)
            else:
                self.pooled[a] = (2.0, 4.0, 0.25)
        self.pooled_global = _fit_law(self.col_tau, self.col_dur - self.col_tau,
                                      np.ones(self.n), self.hp)
        self.mean_rho = float(self.col_rho.mean())
        self.mean_dur = float(self.col_dur.mean())
        self.mean_blast = float(self.col_blast.mean())
        self._pool_level_cache = {}

        # Pooled per-action residual dispersion, used as the prior scale by the
        # small-sample shrinkage of Sec. IV-E. A weighted MAD over a handful of
        # points is degenerate -- with m <= p fitted parameters the residuals
        # are identically zero -- so a per-action pooled scale estimated over
        # the whole corpus provides the fallback the local estimate cannot.
        self.pooled_scale = {}
        res_all = self.col_dur - self.col_tau
        for a in self.actions_u:
            sel = self.col_action == self._ai[a]
            if int(sel.sum()) >= 8:
                r = res_all[sel] - _law(self.pooled[a], self.col_tau[sel])
                self.pooled_scale[a] = _robust_scale(r, np.ones(int(sel.sum())))
        r_g = res_all - _law(self.pooled_global, self.col_tau)
        self.pooled_scale_global = max(_robust_scale(r_g, np.ones(self.n)), 1e-3)

    def prior_scale(self, action):
        return self.pooled_scale.get(action, self.pooled_scale_global)

    def pooled_intrinsic_level(self, action):
        """
        Action-marginal intrinsic recovery cost: the geometric mean of
        r_i / (1 + beta * rho_i) over EVERY training record using this action,
        pooled across all fault types.

        Under a novel fault the tier-1 pool is empty and retrieval falls back to
        same-action precedent drawn from arbitrary other faults, selected by
        graph position rather than by fault. That selection can concentrate on a
        few unrepresentative faults. This action-marginal estimate is biased for
        any particular fault but has far lower variance, and is the shrinkage
        target used by the novelty-aware fallback.
        """
        beta = self.hp["beta"]
        key = (action, round(beta, 6))
        hit = self._pool_level_cache.get(key)
        if hit is not None:
            return hit
        m = self.col_action == self._ai.get(action, -1)
        if int(m.sum()) < 3:
            m = np.ones(self.n, dtype=bool)
        r = self.col_dur[m] - self.col_tau[m]
        adj = np.maximum(r / (1.0 + beta * self.col_rho[m]), 1e-3)
        val = float(np.exp(np.mean(np.log(adj))))
        self._pool_level_cache[key] = val
        return val

    # ---- vectorised similarity ----
    def _similarity_vector(self, topo_name, fault, origin):
        key = (topo_name, fault, origin)
        if key in self._sim_cache:
            return self._sim_cache[key]
        hp = self.hp
        topo = self.topos[topo_name]
        x = _origin_features(topo, origin)
        s_struct = np.exp(-np.linalg.norm(self.X - x[None, :], axis=1))
        s_fault = (self.col_fault == self._fi.get(fault, -1)).astype(float)
        same_topo = (self.col_topo == topo_name)
        hops = _hop_table(topo).get(origin, {})
        s_orig = np.zeros(self.n)
        if same_topo.any():
            idx = np.flatnonzero(same_topo)
            s_orig[idx] = [math.exp(-hops.get(self.col_origin[i], 6) / 2.0) for i in idx]
        s = hp["w_fault"] * s_fault + hp["w_struct"] * s_struct + hp["w_origin"] * s_orig
        if len(self._sim_cache) > 4000:
            self._sim_cache.clear()
        self._sim_cache[key] = s
        return s

    # ---- Step 1: tiered retrieval ----
    def retrieve(self, topo_name, fault, origin, action):
        hp = self.hp
        s = self._similarity_vector(topo_name, fault, origin)
        a_i, f_i = self._ai.get(action, -1), self._fi.get(fault, -1)
        m_act = self.col_action == a_i
        t1 = np.flatnonzero(m_act & (self.col_fault == f_i))
        if hp["use_tiers"]:
            t2 = np.flatnonzero(m_act & (self.col_fault != f_i))
            fam = ACTION_FAMILY.get(action, action)
            t3 = np.flatnonzero((self.col_family == fam) & ~m_act)
            tiers = [t1, t2, t3]
        else:
            tiers = [t1]
        # Relaxation is engaged only when same-fault/same-action precedent is
        # genuinely thin; relaxed evidence is additionally weight-discounted.
        picked, ptier, tier = [], [], 4
        for ti, idx in enumerate(tiers, start=1):
            if idx.size == 0:
                continue
            if ti > 1 and sum(p.size for p in picked) >= hp["m_relax"]:
                break
            if not picked:
                tier = ti
            take = (idx if idx.size <= hp["k"]
                    else idx[np.argpartition(-s[idx], hp["k"])[:hp["k"]]])
            picked.append(take)
            ptier.append(np.full(take.size, ti, dtype=np.int8))
        if not picked:
            return np.array([], dtype=int), np.array([]), np.array([]), 4
        cand = np.concatenate(picked)
        ct = np.concatenate(ptier)
        order = np.argsort(-s[cand])[:hp["k"]]
        cand, ct = cand[order], ct[order]
        return cand, s[cand], ct, tier


# --------------------------------------------------------------------------
# Step 2: the timing-duration law
# --------------------------------------------------------------------------
def _law(params, tau):
    ell, kappa, gamma = params
    return ell + kappa * (1.0 - np.exp(-gamma * tau))


def _fit_law(tau, res, w, hp, fixed=None):
    """
    Robust weighted fit of r(tau) = ell + kappa*(1 - exp(-gamma*tau)).

    fixed=None          -> free 3-parameter fit           (m >= m_min)
    fixed=("gamma", g)  -> 2-parameter fit, gamma pooled  (3 <= m < m_min)
    fixed=("kg", k, g)  -> level-only fit                 (1 <= m < 3)
    """
    w = np.asarray(w, dtype=float)
    sw = np.sqrt(np.maximum(w, 1e-9))
    lo = 0.30
    loss = "soft_l1" if hp.get("robust", True) else "linear"

    if fixed is None:
        x0 = [max(lo, float(np.min(res)) * 0.8), max(0.5, float(np.ptp(res))), 0.25]
        bounds = ([lo, 0.0, 0.02], [40.0, 80.0, 2.0])

        def resid(p):
            return sw * (_law(p, tau) - res)
    elif fixed[0] == "gamma":
        g = fixed[1]
        x0 = [max(lo, float(np.min(res)) * 0.8), max(0.5, float(np.ptp(res)))]
        bounds = ([lo, 0.0], [40.0, 80.0])

        def resid(p):
            return sw * (_law([p[0], p[1], g], tau) - res)
    else:
        k, g = fixed[1], fixed[2]
        base = k * (1.0 - np.exp(-g * tau))
        x0 = [max(lo, float(np.average(res - base, weights=w)))]
        bounds = ([lo], [40.0])

        def resid(p):
            return sw * ((p[0] + base) - res)

    try:
        sol = least_squares(resid, x0, bounds=bounds, loss=loss, f_scale=1.5,
                            max_nfev=300)
        p = list(sol.x)
    except Exception:
        p = list(x0)
    if fixed is None:
        return tuple(p)
    if fixed[0] == "gamma":
        return (p[0], p[1], fixed[1])
    return (p[0], fixed[1], fixed[2])


def _wquantile(x, w, q):
    idx = np.argsort(x)
    x, w = np.asarray(x)[idx], np.asarray(w)[idx]
    cw = np.cumsum(w) / max(np.sum(w), 1e-12)
    return float(np.interp(q, cw, x))


def _robust_scale(x, w):
    med = _wquantile(x, w, 0.5)
    return 1.4826 * max(_wquantile(np.abs(x - med), w, 0.5), 1e-6)


def _detect_conflict(res, w, hp):
    """Weighted 1-D 2-means on precedent residuals: contradictory precedent."""
    if len(res) < 4:
        return False, None
    lo, hi = float(np.min(res)), float(np.max(res))
    if hi - lo < 1e-6:
        return False, None
    c = np.array([lo, hi], dtype=float)
    for _ in range(25):
        lab = np.abs(res[:, None] - c[None, :]).argmin(axis=1)
        for j in (0, 1):
            m = lab == j
            if w[m].sum() > 0:
                c[j] = float(np.average(res[m], weights=w[m]))
    lab = np.abs(res[:, None] - c[None, :]).argmin(axis=1)
    w0, w1 = w[lab == 0].sum(), w[lab == 1].sum()
    tot = w0 + w1
    if tot <= 0 or min(w0, w1) / tot < 0.25:
        return False, None
    sep = abs(c[1] - c[0]) / max(_robust_scale(res, w), 1e-6)
    if sep >= hp["conflict_sep"]:
        return True, (float(min(c)), float(max(c)))
    return False, None


# --------------------------------------------------------------------------
# Step 3: dependency-propagation blast radius
# --------------------------------------------------------------------------
def predict_affected(memory, topo, origin, horizon, theta):
    """Reliability-gated shortest-propagation-time reachability within horizon."""
    best_t = {origin: 0.0}
    best_r = {origin: 1.0}
    pq = [(0.0, origin)]
    out = {origin}
    while pq:
        t, u = heapq.heappop(pq)
        if t > best_t.get(u, math.inf) + 1e-12:
            continue
        for v in topo.adj[u]:
            e = (u, v)
            nt = t + memory.edge_delay.get(e, memory._global_delay)
            nr = best_r[u] * memory.edge_prob.get(e, 0.85)
            if nt <= horizon and nr >= theta and nt < best_t.get(v, math.inf):
                best_t[v], best_r[v] = nt, nr
                out.add(v)
                heapq.heappush(pq, (nt, v))
    return out


# --------------------------------------------------------------------------
# The estimator
# --------------------------------------------------------------------------
class IncidentMindEstimator:
    name = "IncidentMind"

    def __init__(self, memory):
        self.mem = memory
        self.hp = memory.hp

    def _context(self, topo_name, fault, origin, action):
        """Retrieval + law fit: independent of tau, so cached per context."""
        key = (topo_name, fault, origin, action)
        hit = self.mem._ctx_cache.get(key)
        if hit is not None:
            return hit
        mem, hp = self.mem, self.hp
        idx, sims, ctier, tier = mem.retrieve(topo_name, fault, origin, action)
        m = int(idx.size)
        if m == 0:
            pooled = mem.pooled.get(action, mem.pooled_global)
            scale0 = mem.prior_scale(action) if hp["interval_fix"] else 3.0
            ctx = {"m": 0, "tier": 4, "params": pooled, "scale": scale0,
                   "scale_local": scale0, "p_fit": 0,
                   "conflict": False, "modes": None,
                   "level_struct": float(_law(pooled, 4.0)) / (1.0 + hp["beta"] * mem.mean_rho),
                   "rho_prec": mem.mean_rho, "q_sim": 0.0, "m1": 0}
        else:
            w = np.exp((sims - sims.max()) / hp["temp"])
            w = w * np.power(hp["tier_penalty"], ctier - 1)
            w = w / max(w.sum(), 1e-12)
            tau_i = mem.col_tau[idx]
            res_i = mem.col_dur[idx] - tau_i
            if not hp["use_law"]:
                lvl = float(np.average(res_i, weights=w))
                params = (max(0.3, lvl), 0.0, 0.25)
                p_fit = 1
            elif m >= hp["m_min"]:
                params = _fit_law(tau_i, res_i, w, hp)
                p_fit = 3
            elif m >= 3:
                g = mem.pooled.get(action, mem.pooled_global)[2]
                params = _fit_law(tau_i, res_i, w, hp, fixed=("gamma", g))
                p_fit = 2
            else:
                _, k_p, g_p = mem.pooled.get(action, mem.pooled_global)
                params = _fit_law(tau_i, res_i, w, hp, fixed=("kg", k_p, g_p))
                p_fit = 1
            resid = res_i - _law(params, tau_i)
            conflict, modes = _detect_conflict(resid, w, hp)
            scale_local = _robust_scale(resid, w)
            if hp["interval_fix"]:
                # moderated dispersion: combine the local estimate with the
                # pooled per-action scale, weighted by residual degrees of
                # freedom. With m <= p_fit the local estimate carries no
                # information and the pooled scale is used outright.
                d_loc = max(0, m - p_fit)
                d0 = hp["scale_prior_df"]
                sbar = mem.prior_scale(action)
                scale_used = float(np.sqrt(
                    (d0 * sbar ** 2 + d_loc * scale_local ** 2) / (d0 + d_loc)))
            else:
                scale_used = scale_local
            # structural route: strip each precedent's own accrued-spread
            # penalty, leaving a scale-free estimate of the action's intrinsic
            # recovery cost for this fault (geometric mean, log-normal noise).
            rho_i = mem.col_rho[idx]
            adj = np.maximum(res_i / (1.0 + hp["beta"] * rho_i), 1e-3)
            level_struct = float(np.exp(np.average(np.log(adj), weights=w)))
            ctx = {"m": m, "tier": tier, "params": params,
                   "scale": scale_used, "scale_local": scale_local,
                   "p_fit": p_fit, "conflict": conflict,
                   "modes": modes, "level_struct": level_struct,
                   "rho_prec": float(np.average(rho_i, weights=w)),
                   "q_sim": float(np.average(sims, weights=w)),
                   "m1": int((ctier == 1).sum())}
        # ---- novelty score (Sec. IV-G): how far this query is from the
        # evidence the retrieval layer is designed to exploit.  Depends only on
        # retrieval, so it is cached alongside the rest of the context.
        s_count = ctx["m1"] / (ctx["m1"] + hp["nov_kappa0"])
        s_sim = float(np.clip(ctx["q_sim"] / max(hp["nov_sref"], 1e-6), 0.0, 1.0))
        ctx["support"] = float(np.sqrt(max(s_count, 0.0) * max(s_sim, 0.0)))
        ctx["novelty"] = float(np.clip(1.0 - ctx["support"], 0.0, 1.0))

        if hp["novelty_aware"]:
            nu = ctx["novelty"] ** hp["nov_a"]
            ctx["nu_eff"] = float(nu)
            # shrink the retrieved intrinsic level toward the action-marginal
            # prior in proportion to novelty (geometric, matching the
            # log-normal noise the level estimator assumes)
            pool = mem.pooled_intrinsic_level(action)
            ctx["level_struct"] = float(np.exp(
                (1.0 - nu) * np.log(max(ctx["level_struct"], 1e-3))
                + nu * np.log(max(pool, 1e-3))))
        else:
            ctx["nu_eff"] = 0.0

        if len(mem._ctx_cache) > 20000:
            mem._ctx_cache.clear()
        mem._ctx_cache[key] = ctx
        return ctx

    def estimate(self, topo_name, fault, origin, action, tau):
        hp, mem = self.hp, self.mem
        topo = mem.topos[topo_name]
        ctx = self._context(topo_name, fault, origin, action)

        # Step 3: blast radius, using the learned containment lag h(A, f)
        S_hat = predict_affected(mem, topo, origin, tau + mem.clag_for(action, fault),
                                 hp["theta"])
        B_hat = len(S_hat)
        rho_hat = B_hat / max(1, len(reachable(topo, origin)))

        # Step 2 -- two routes to the post-action recovery time r(tau):
        #   reduced form : the timing-duration law fitted directly on precedent
        #   structural   : intrinsic action cost x this incident's spread penalty
        # They parameterise the same dependence, so they are blended rather than
        # composed; lam_blend is selected on validation.
        r_reduced = float(_law(ctx["params"], tau))
        r_struct = ctx["level_struct"] * (1.0 + hp["beta"] * rho_hat)
        lam = hp["lam_blend"] if hp["use_dep"] else 0.0
        if hp["novelty_aware"] and hp["use_dep"]:
            # novelty shifts weight from the precedent-fitted timing curve onto
            # the dependency-derived route, which needs only a scalar level
            nu = ctx["nu_eff"]
            lam = lam + (1.0 - lam) * nu
        r_hat = float(np.exp((1.0 - lam) * np.log(max(r_reduced, 1e-3))
                             + lam * np.log(max(r_struct, 1e-3))))
        D_hat = float(max(0.5, tau + r_hat))

        # Step 4: confidence + interval
        m, scale = ctx["m"], ctx["scale"]
        q_disp = math.exp(-hp["lam"] * (scale / max(1e-6, abs(r_hat))))
        q_sup = m / (m + hp["k0"])
        q_sim = float(np.clip(ctx["q_sim"] / 0.6, 0.0, 1.0))
        c = (TIER_FACTOR.get(ctx["tier"], 0.45) * q_disp
             * math.sqrt(max(q_sup, 1e-6)) * math.sqrt(max(q_sim, 1e-6)))
        if ctx["conflict"]:
            c *= 0.6
        if hp["novelty_aware"]:
            c *= max(0.0, 1.0 - hp["nov_gamma_c"] * ctx["nu_eff"])
        c = float(np.clip(c, 0.02, 0.99))

        half = hp["z"] * scale * (1.6 if ctx["conflict"] else 1.0) * (1.0 + 2.0 / (m + 2.0))
        if hp["novelty_aware"]:
            half *= (1.0 + hp["nov_gamma_i"] * ctx["nu_eff"])
        return {"duration": D_hat, "blast": B_hat, "affected": S_hat,
                "confidence": c, "lo": max(0.0, D_hat - half), "hi": D_hat + half,
                "n_precedent": m, "tier": ctx["tier"], "conflict": ctx["conflict"],
                "modes": ctx["modes"], "params": ctx["params"],
                "novelty": ctx["novelty"], "support": ctx["support"],
                "n_tier1": ctx["m1"]}
