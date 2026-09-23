"""
IncidentMind evaluation testbed -- GROUND-TRUTH ENVIRONMENT (frozen specification).

This module defines a stochastic generative model of cloud-native incidents.
It is the *oracle*: it owns hidden parameters (per-edge propagation delays and
probabilities, fault/action efficacy, recovery-noise scales) that the estimator
under test NEVER observes.  The estimator only ever sees emitted incident
*records* (fault type, origin, action, timing, duration, affected set with
arrival times) plus the static topology.

Because a single incident is materialised as a latent realisation omega
(sampled edge delays, Bernoulli propagation outcomes, noise draws), the same
incident can be *replayed* under any alternative recovery decision (A, tau).
This yields genuine counterfactual ground truth -- the quantity that is
unobtainable from production incident archives, and which makes quantitative
evaluation of what-if recovery estimation possible at all.

FROZEN: parameters below were fixed before the estimator was implemented.
"""
import hashlib
import heapq
import json
import math

import numpy as np

# --------------------------------------------------------------------------
# Fault and action vocabularies
# --------------------------------------------------------------------------
FAULTS = [
    "db_saturation", "service_crash", "network_latency", "api_timeout_cascade",
    "resource_exhaustion", "deploy_misconfig", "cache_failure",
]
ACTIONS = [
    "pod_restart", "pool_restart", "scale_replicas", "rollback_deploy",
    "reroute_traffic", "circuit_breaker", "degraded_mode",
]

# HIDDEN: intrinsic action latency (minutes) -- lower bound on recovery time.
_ELL = {
    "pod_restart": 1.2, "pool_restart": 1.5, "scale_replicas": 2.5,
    "rollback_deploy": 3.5, "reroute_traffic": 1.0, "circuit_breaker": 0.8,
    "degraded_mode": 1.0,
}

# HIDDEN: efficacy eps(f, A) in (0, 1].  Low efficacy => action/fault mismatch.
_EFFICACY = {
    "db_saturation": {"pool_restart": 0.88, "scale_replicas": 0.62, "degraded_mode": 0.46,
                      "pod_restart": 0.24, "reroute_traffic": 0.20, "circuit_breaker": 0.34,
                      "rollback_deploy": 0.18},
    "service_crash": {"pod_restart": 0.90, "scale_replicas": 0.58, "rollback_deploy": 0.44,
                      "reroute_traffic": 0.36, "circuit_breaker": 0.30, "degraded_mode": 0.26,
                      "pool_restart": 0.20},
    "network_latency": {"reroute_traffic": 0.84, "circuit_breaker": 0.66, "scale_replicas": 0.38,
                        "degraded_mode": 0.34, "pod_restart": 0.26, "pool_restart": 0.22,
                        "rollback_deploy": 0.18},
    "api_timeout_cascade": {"circuit_breaker": 0.86, "reroute_traffic": 0.56, "degraded_mode": 0.50,
                            "scale_replicas": 0.40, "pod_restart": 0.28, "rollback_deploy": 0.24,
                            "pool_restart": 0.18},
    "resource_exhaustion": {"scale_replicas": 0.87, "pod_restart": 0.55, "degraded_mode": 0.42,
                            "circuit_breaker": 0.30, "reroute_traffic": 0.26, "pool_restart": 0.24,
                            "rollback_deploy": 0.20},
    "deploy_misconfig": {"rollback_deploy": 0.94, "pod_restart": 0.30, "degraded_mode": 0.28,
                         "circuit_breaker": 0.24, "reroute_traffic": 0.20, "pool_restart": 0.16,
                         "scale_replicas": 0.14},
    "cache_failure": {"pod_restart": 0.72, "degraded_mode": 0.78, "scale_replicas": 0.44,
                      "reroute_traffic": 0.32, "circuit_breaker": 0.36, "pool_restart": 0.26,
                      "rollback_deploy": 0.18},
}

# HIDDEN: dynamics constants
_BETA = 0.90         # how strongly accrued spread inflates recovery work
_SIG_COMMON = 0.22   # incident-level (common random number) log-noise
_SIG_INDEP = 0.16    # decision-level independent log-noise
_TAU_MIN = 0.5       # detection floor (minutes)

# Functional form by which accrued spread inflates recovery work.  "linear" is
# the frozen default.  The other forms are used ONLY by the misspecification
# experiment, to test the estimator under a generative law it does not assume.
_SPREAD_FORM = "linear"
SPREAD_FORMS = ("linear", "quadratic", "exponential", "sqrt")


def set_spread_form(name):
    global _SPREAD_FORM
    assert name in SPREAD_FORMS
    _SPREAD_FORM = name


def _spread_penalty(rho):
    if _SPREAD_FORM == "linear":
        return 1.0 + _BETA * rho
    if _SPREAD_FORM == "quadratic":
        return 1.0 + 1.8 * _BETA * rho * rho
    if _SPREAD_FORM == "exponential":
        return float(np.exp(_BETA * rho))
    return 1.0 + _BETA * math.sqrt(rho)

# --------------------------------------------------------------------------
# Topologies.  Edge (u -> v) means "degradation of u can degrade v".
# --------------------------------------------------------------------------
_ECOMMERCE_NODES = [
    "order-db", "order-service", "checkout-service", "api-gateway", "frontend-service",
    "inventory-service", "catalog-service", "payment-service", "recommendation-service",
    "search-service", "auth-service", "account-service", "cache-service", "product-service",
]
_ECOMMERCE_EDGES = [
    ("order-db", "order-service"), ("order-service", "checkout-service"),
    ("checkout-service", "api-gateway"), ("api-gateway", "frontend-service"),
    ("inventory-service", "catalog-service"), ("catalog-service", "checkout-service"),
    ("payment-service", "checkout-service"), ("recommendation-service", "api-gateway"),
    ("cache-service", "product-service"), ("product-service", "search-service"),
    ("product-service", "api-gateway"), ("search-service", "frontend-service"),
    ("auth-service", "api-gateway"), ("auth-service", "checkout-service"),
    ("auth-service", "account-service"),
]

_CLINICAL_NODES = [
    "device-gateway", "telemetry-ingest", "vitals-stream-processor", "alert-engine",
    "notification-service", "clinician-portal", "patient-db", "patient-record-service",
    "ehr-adapter", "billing-service", "imaging-store", "imaging-service",
    "clin-auth-service", "clin-api-gateway", "scheduling-service", "audit-log-service",
]
_CLINICAL_EDGES = [
    ("device-gateway", "telemetry-ingest"), ("telemetry-ingest", "vitals-stream-processor"),
    ("vitals-stream-processor", "alert-engine"), ("alert-engine", "notification-service"),
    ("alert-engine", "clinician-portal"), ("patient-db", "patient-record-service"),
    ("patient-record-service", "ehr-adapter"), ("patient-record-service", "clinician-portal"),
    ("patient-record-service", "audit-log-service"), ("ehr-adapter", "billing-service"),
    ("imaging-store", "imaging-service"), ("imaging-service", "clinician-portal"),
    ("clin-auth-service", "clin-api-gateway"), ("clin-api-gateway", "clinician-portal"),
    ("scheduling-service", "clinician-portal"),
]


def _layered_topology(name, n, rng, width=6):
    """Deterministic layered synthetic topology (used for scale + transfer tests)."""
    nodes = [name + "-svc-" + str(i).zfill(3) for i in range(n)]
    edges = []
    layers, i = [], 0
    while i < n:
        layers.append(nodes[i:i + width])
        i += width
    for li in range(len(layers) - 1):
        nxt = layers[li + 1]
        for u in layers[li]:
            k = 1 + int(rng.integers(0, 3))
            for v in rng.choice(nxt, size=min(k, len(nxt)), replace=False):
                edges.append((u, str(v)))
    return nodes, edges


class Topology:
    """Static service impact-graph with HIDDEN per-edge propagation parameters."""

    def __init__(self, name, nodes, edges, seed):
        self.name, self.nodes, self.edges = name, list(nodes), list(edges)
        self.index = {s: i for i, s in enumerate(self.nodes)}
        self.adj = {s: [] for s in self.nodes}
        for u, v in self.edges:
            self.adj[u].append(v)
        rng = np.random.default_rng(seed)
        self._delay_mu = {}   # HIDDEN lognormal location of propagation delay (min)
        self._edge_p = {}     # HIDDEN probability the edge actually propagates
        for e in self.edges:
            self._delay_mu[e] = float(rng.uniform(0.25, 1.35))
            self._edge_p[e] = float(rng.uniform(0.72, 0.98))

    def reachable(self, origin):
        seen, stack = {origin}, [origin]
        while stack:
            u = stack.pop()
            for v in self.adj[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        return seen


def build_topologies(seed=20260828):
    tops = {
        "ecommerce": Topology("ecommerce", _ECOMMERCE_NODES, _ECOMMERCE_EDGES, seed + 1),
        "clinical": Topology("clinical", _CLINICAL_NODES, _CLINICAL_EDGES, seed + 2),
    }
    n41, e41 = _layered_topology("tt", 41, np.random.default_rng(seed + 3), width=6)
    tops["trainticket"] = Topology("trainticket", n41, e41, seed + 4)
    return tops


# --------------------------------------------------------------------------
# Latent realisation and replay
# --------------------------------------------------------------------------
class Realisation:
    """
    A single sampled incident world omega: fixed edge delays, fixed Bernoulli
    propagation outcomes, fixed noise draws.  Replayable under any (A, tau).
    """

    def __init__(self, topo, fault, origin, seed):
        self.topo, self.fault, self.origin, self.seed = topo, fault, origin, int(seed)
        rng = np.random.default_rng(self.seed % (2 ** 32))
        mod = {"network_latency": 0.75, "api_timeout_cascade": 0.70,
               "cache_failure": 0.85}.get(fault, 1.0)
        self.delay, self.open_edge = {}, {}
        for e in topo.edges:
            self.delay[e] = float(rng.lognormal(topo._delay_mu[e], 0.30) * mod)
            self.open_edge[e] = bool(rng.random() < topo._edge_p[e])
        self.z_common = float(rng.normal())
        self._arrival = self._compute_arrivals()
        self.reach = set(self._arrival.keys())
        self._noise_cache = {}

    def _compute_arrivals(self):
        """Dijkstra over open edges: earliest degradation time per service."""
        arr = {self.origin: 0.0}
        pq = [(0.0, self.origin)]
        while pq:
            t, u = heapq.heappop(pq)
            if t > arr.get(u, np.inf) + 1e-12:
                continue
            for v in self.topo.adj[u]:
                if not self.open_edge[(u, v)]:
                    continue
                nt = t + self.delay[(u, v)]
                if nt < arr.get(v, np.inf):
                    arr[v] = nt
                    heapq.heappush(pq, (nt, v))
        return arr

    def affected_at(self, t):
        return {s for s, a in self._arrival.items() if a <= t}

    def _noise(self, action):
        if action not in self._noise_cache:
            h = hashlib.sha256((str(self.seed) + "|" + action).encode()).digest()
            r = np.random.default_rng(int.from_bytes(h[:8], "big") % (2 ** 32))
            z = float(r.normal())
            self._noise_cache[action] = float(
                np.exp(_SIG_COMMON * self.z_common + _SIG_INDEP * z))
        return self._noise_cache[action]

    def outcome(self, action, tau):
        """GROUND TRUTH for decision (action, tau)."""
        tau = max(float(tau), _TAU_MIN)
        eps = _EFFICACY[self.fault].get(action, 0.20)
        ell = _ELL[action]
        c_lag = ell * (0.5 + 1.5 * (1.0 - eps))   # effective actions contain sooner
        S = self.affected_at(tau + c_lag)
        S.add(self.origin)
        n_reach = max(1, len(self.reach))
        R = (ell / eps) * _spread_penalty(len(S) / n_reach) * self._noise(action)
        return {"duration": float(tau + R), "affected": S, "blast": len(S),
                "action": action, "tau": tau}


# --------------------------------------------------------------------------
# Corpus generation
# --------------------------------------------------------------------------
_ORIGIN_HINT = {
    "db_saturation": ["db"],
    "cache_failure": ["cache", "imaging-store"],
    "deploy_misconfig": None,
    "service_crash": None,
    "network_latency": None,
    "api_timeout_cascade": ["gateway", "api", "portal"],
    "resource_exhaustion": None,
}


def _pick_origin(topo, fault, rng):
    hint = _ORIGIN_HINT.get(fault)
    cands = [n for n in topo.nodes if topo.adj[n]]   # must be able to propagate
    if hint:
        hinted = [n for n in cands if any(h in n for h in hint)]
        if hinted and rng.random() < 0.75:
            cands = hinted
    return str(rng.choice(cands))


def _operator_action(fault, rng):
    """
    HIDDEN operator-behaviour model producing the *factual* action of a past
    incident.  Deliberately imperfect: operators often pick a reasonable but
    suboptimal action, so the precedent corpus is not a clean read-out of the
    efficacy matrix.
    """
    eff = _EFFICACY[fault]
    acts = list(eff.keys())
    w = np.array([eff[a] for a in acts]) ** 1.6
    w = w / w.sum()
    return str(rng.choice(acts, p=w))


def _operator_timing(rng):
    """Mixture of fast, typical and slow responses (minutes from onset)."""
    u = rng.random()
    if u < 0.30:
        return float(np.clip(rng.gamma(2.0, 0.9), _TAU_MIN, 30))
    if u < 0.80:
        return float(np.clip(rng.gamma(4.0, 1.5), _TAU_MIN, 30))
    return float(np.clip(rng.gamma(7.0, 2.2), _TAU_MIN, 30))


def generate_corpus(topos, n, seed, topo_names=None, faults=None):
    """
    Emit n incident RECORDS (all the estimator may see) plus latent Realisation
    objects (used only by the oracle, for counterfactual ground truth).
    """
    rng = np.random.default_rng(seed)
    topo_names = topo_names or list(topos.keys())
    faults = faults or FAULTS
    out = []
    for i in range(n):
        tname = str(rng.choice(topo_names))
        topo = topos[tname]
        fault = str(rng.choice(faults))
        origin = _pick_origin(topo, fault, rng)
        real = Realisation(topo, fault, origin, seed * 1000003 + i)
        action = _operator_action(fault, rng)
        tau = _operator_timing(rng)
        gt = real.outcome(action, tau)
        rec = {
            "id": "inc-" + str(seed) + "-" + str(i).zfill(6), "topology": tname,
            "fault": fault, "origin": origin, "action": action, "tau": gt["tau"],
            "duration": gt["duration"], "blast": gt["blast"],
            "affected": sorted(gt["affected"]),
            # sorted, not set-ordered: set iteration order depends on Python's
            # randomised string hashing, which would make any downstream
            # consumer that draws one random number per key non-reproducible
            # across processes (the contents are identical either way).
            "arrivals": {s: round(real._arrival[s], 3)
                         for s in sorted(gt["affected"]) if s in real._arrival},
        }
        out.append({"record": rec, "realisation": real})
    return out


def spec_hash():
    """Stable hash of the frozen environment specification (reported in paper)."""
    blob = json.dumps({"F": FAULTS, "A": ACTIONS, "ell": _ELL, "eps": _EFFICACY,
                       "beta": _BETA, "sc": _SIG_COMMON, "si": _SIG_INDEP,
                       "ecom_e": _ECOMMERCE_EDGES, "clin_e": _CLINICAL_EDGES},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


if __name__ == "__main__":
    tops = build_topologies()
    print("spec hash:", spec_hash())
    for k, t in tops.items():
        print(k.ljust(12), "nodes=" + str(len(t.nodes)).rjust(3),
              "edges=" + str(len(t.edges)).rjust(3))
    c = generate_corpus(tops, 6, 1)
    for e in c:
        r = e["record"]
        print("  {:20s} @{:22s} {:15s} tau={:5.1f} D={:6.2f} B={}".format(
            r["fault"], r["origin"], r["action"], r["tau"], r["duration"], r["blast"]))
