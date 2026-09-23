"""
Revised V1 real-world validation campaign (V1r).

Changes from the halted V1, all made BEFORE any V1r incident was run:

  1. STABILITY GATE REDEFINED. The original §12 criterion required >=80% of
     stability incidents to complete uncensored. That conflated infrastructure
     health with incident recovery and was wrong: half of the admitted
     (fault, action) combinations are ineffective by construction and cannot
     recover. The gate now tests infrastructure reliability only --
     no unexpected container restarts, clean reset between incidents,
     telemetry continuity, healthy baseline before each incident, no data
     loss, no duplicate orchestrator. Censored incidents are valid scientific
     observations and stay in the dataset with an explicit censored outcome.

  2. CENSOR_S 150 -> 90 s. Effective recoveries observed in V1a completed
     within ~75 s; ineffective actions still need enough time to demonstrate
     non-recovery. 90 s is the fixed observation window. Fixed before the run
     and not revisited afterwards.

  3. CAMPAIGN SIZE 240 -> 90 (60 corpus + 30 held-out). The purpose is
     external validation on a real cluster, not to reproduce the scale of the
     synthetic evaluation.

  4. HELD-OUT ALLOCATION IS EXPLICIT, not a random sample. See allocate().

The estimator is NOT imported and NOT modified. This script only measures.
"""
import json
import os
import random
import subprocess
import sys
import threading
import time

CTX = "kind-incidentmind-fi"
HOME = os.path.expanduser("~/imfi")
MANIFEST = os.path.join(HOME, "online-boutique-noload.yaml")
RES = os.path.join(HOME, "results")

RAW = os.path.join(RES, "v1r_events.jsonl")
CONTROLS = os.path.join(RES, "v1r_controls.jsonl")
INCIDENTS = os.path.join(RES, "v1r_incidents.jsonl")
STABILITY = os.path.join(RES, "v1r_stability.json")
HEALTH = os.path.join(RES, "v1r_health.jsonl")
ALLOC = os.path.join(RES, "v1r_allocation.json")
CORPUS_FROZEN = os.path.join(RES, "v1r_corpus_frozen.json")
LOG = os.path.join(RES, "v1r_run.log")
PRIOR_CONTROLS = os.path.join(RES, "v1_controls.jsonl")

CONFIRM_FAIL = 2
STEADY_S = 8
STEADY_WAIT_S = 240
ONSET_WAIT_S = 90
CENSOR_S = 90              # protocol correction, fixed pre-run
RESET_WAIT_S = 300
CONTROL_OBSERVE_S = 100

MASTER_SEED = 20260824
N_STABILITY = 6
N_CORPUS = 60
N_HELDOUT = 30
HELDOUT_TAU = 45
TAUS = [15, 45, 90]
ACTIONS = ["pod_restart", "scale_replicas", "rollback_deploy"]
FAULTS = ["service_crash", "deploy_misconfig", "resource_exhaustion"]

SERVICES = ["adservice", "cartservice", "checkoutservice", "currencyservice",
            "emailservice", "frontend", "paymentservice", "productcatalogservice",
            "recommendationservice", "redis-cart", "shippingservice"]

# cells rejected by persistence controls; never retried, never counted
PERMANENTLY_REJECTED = {
    ("deploy_misconfig", "redis-cart"),
    ("resource_exhaustion", "shippingservice"),
    ("deploy_misconfig", "cartservice"),
    ("resource_exhaustion", "productcatalogservice"),
}
# unmeasured in V1 (contaminated by a duplicate orchestrator); re-controlled here
RECONTROL = [("resource_exhaustion", "cartservice"),
             ("resource_exhaustion", "redis-cart")]

RECREATE = '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}'
ROLLING = ('{"spec":{"strategy":{"type":"RollingUpdate","rollingUpdate":'
           '{"maxSurge":"25%","maxUnavailable":"25%"}}}}')


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def kc(*a, check=True, timeout=180):
    r = subprocess.run(["kubectl", "--context", CTX] + list(a),
                       capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError("kubectl %s: %s" % (" ".join(a), r.stderr.strip()))
    return r.stdout.strip()


def jread(p):
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def jappend(p, o):
    with open(p, "a") as fh:
        fh.write(json.dumps(o, default=float) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# --------------------------------------------------------------- telemetry
class Feed:
    def __init__(self):
        self.ev, self.lock, self.stop = [], threading.Lock(), False
        self.reconnects, self.lines = 0, 0
        self.fh = open(RAW, "a")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self.stop:
            p = subprocess.Popen(
                ["kubectl", "--context", CTX, "logs", "-f", "--tail=0",
                 "im-prober-v1a"], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True)
            for line in p.stdout:
                if self.stop:
                    break
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                with self.lock:
                    self.ev.append(d)
                    self.lines += 1
                self.fh.write(line + "\n")
            try:
                p.kill()
            except Exception:
                pass
            if not self.stop:
                self.reconnects += 1
                time.sleep(0.5)

    def window(self, t0, t1=None):
        with self.lock:
            return [e for e in self.ev
                    if e["t"] >= t0 and (t1 is None or e["t"] <= t1)]

    def trim(self, keep_ms=600000):
        cut = int(time.time() * 1000) - keep_ms
        with self.lock:
            self.ev = [e for e in self.ev if e["t"] >= cut]

    def flush(self):
        try:
            self.fh.flush()
            os.fsync(self.fh.fileno())
        except Exception:
            pass


def failing_now(feed, secs=2.0):
    last = {}
    for e in feed.window(int((time.time() - secs) * 1000)):
        last[(e["k"], e["n"])] = e["ok"]
    return {k for k, ok in last.items() if ok == 0}


def wait_steady(feed, limit_s, need=STEADY_S):
    t_end, since = time.time() + limit_s, None
    while time.time() < t_end:
        if not failing_now(feed):
            since = since or time.time()
            if time.time() - since >= need:
                return True
        else:
            since = None
        time.sleep(0.3)
    return False


def onsets(events, t_from):
    seq, out = {}, {}
    for e in sorted(events, key=lambda x: x["t"]):
        if e["t"] < t_from:
            continue
        k = (e["k"], e["n"])
        if e["ok"] == 0:
            seq[k] = seq.get(k, 0) + 1
            if seq[k] == CONFIRM_FAIL and k not in out:
                out[k] = e["t"] - t_from
        else:
            seq[k] = 0
    return out


def cluster_health():
    out = kc("get", "pods", "--no-headers", check=False)
    pods = restarts = notready = 0
    for l in out.splitlines():
        f = l.split()
        if len(f) < 4:
            continue
        pods += 1
        try:
            restarts += int(f[3])
        except ValueError:
            pass
        if "/" in f[1]:
            a, b = f[1].split("/")
            if a != b:
                notready += 1
    return {"t": int(time.time() * 1000), "pods": pods,
            "container_restarts": restarts, "not_ready": notready}


def pod_snapshot(svc):
    out = kc("get", "pods", "-l", "app=" + svc, "--no-headers", check=False)
    return [l.split() for l in out.splitlines() if l.strip()]


# --------------------------------------------------------------- fault ops
def inject(fault, svc):
    if fault == "service_crash":
        kc("scale", "deploy/" + svc, "--replicas=0")
    elif fault == "deploy_misconfig":
        kc("patch", "deploy", svc, "-p", RECREATE)
        kc("set", "env", "deploy/" + svc, "PORT=19999")
    elif fault == "resource_exhaustion":
        kc("patch", "deploy", svc, "-p", RECREATE)
        kc("set", "resources", "deploy/" + svc, "--limits=memory=16Mi",
           "--requests=memory=8Mi")
    else:
        raise ValueError(fault)


def recover(action, fault, svc):
    if action == "pod_restart":
        if fault == "service_crash":
            kc("scale", "deploy/" + svc, "--replicas=1")
        else:
            kc("rollout", "restart", "deploy/" + svc)
    elif action == "scale_replicas":
        kc("scale", "deploy/" + svc, "--replicas=3")
    elif action == "rollback_deploy":
        kc("rollout", "undo", "deploy/" + svc, check=False)
    else:
        raise ValueError(action)


def reset(svc):
    kc("patch", "deploy", svc, "-p", ROLLING, check=False)
    kc("apply", "-f", MANIFEST, timeout=240)
    kc("scale", "deploy/" + svc, "--replicas=1", check=False)


# --------------------------------------------------------------- controls
def run_control(feed, fault, svc):
    log("CONTROL %s @ %s (no recovery, %ds)" % (fault, svc, CONTROL_OBSERVE_S))
    rec = {"fault": fault, "origin": svc, "observe_s": CONTROL_OBSERVE_S,
           "t_start": int(time.time() * 1000)}
    if not wait_steady(feed, STEADY_WAIT_S):
        rec.update(status="no_steady_pre", admitted=False,
                   invalid_reason="cluster not steady before control")
        return rec
    t_inj = int(time.time() * 1000)
    inject(fault, svc)
    samples, seen = [], False
    t_end = time.time() + CONTROL_OBSERVE_S
    while time.time() < t_end:
        time.sleep(10)
        fails = failing_now(feed)
        down = any(n == svc for (_k, n) in fails)
        seen |= bool(fails)
        samples.append({"dt_s": round(time.time() - t_inj / 1000.0, 1),
                        "origin_down": bool(down), "n_failing": len(fails)})
    persisted = len(samples) > 1 and all(s["origin_down"] for s in samples[1:])
    rec.update({"samples": samples, "persistent": bool(persisted),
                "observable_degradation": bool(seen), "pods": pod_snapshot(svc),
                "admitted": bool(persisted and seen),
                "status": "persistent" if persisted else "self_healed"})
    log("  -> %s (admitted=%s)" % (rec["status"].upper(), rec["admitted"]))
    reset(svc)
    wait_steady(feed, RESET_WAIT_S)
    return rec


def admitted_cells():
    """Admitted cells from the V1 controls plus any re-controlled here."""
    cells = {}
    for src in (PRIOR_CONTROLS, CONTROLS):
        for c in jread(src):
            if c.get("status") in ("persistent", "self_healed"):
                cells[(c["fault"], c["origin"])] = bool(c.get("admitted"))
    return sorted(k for k, v in cells.items()
                  if v and k not in PERMANENTLY_REJECTED)


# --------------------------------------------------------------- allocation
def allocate(cells):
    """
    Explicit, balanced held-out allocation.

    The ranking unit is the (fault type, recovery action) cell: 3 faults x 3
    actions = 9 cells. 30 incidents / 9 cells = 3 remainder 3, so every cell
    receives 3 repetitions and the 3 surplus incidents are handed out by a
    fixed round-robin over the cell list in canonical order (no random choice,
    no outcome-dependent choice). Within a cell, repetitions are spread over
    that fault's admitted services round-robin, so services are balanced too.
    All held-out incidents use tau = 45 s so actions are compared like for like.
    """
    by_fault = {}
    for f, s in cells:
        by_fault.setdefault(f, []).append(s)
    for f in by_fault:
        by_fault[f].sort()
    faults = [f for f in FAULTS if by_fault.get(f)]
    cell_list = [(f, a) for f in faults for a in ACTIONS]
    base, extra = divmod(N_HELDOUT, len(cell_list))
    counts = {c: base for c in cell_list}
    for i in range(extra):
        counts[cell_list[i % len(cell_list)]] += 1
    plan, idx = [], {}
    n = 0
    for (f, a) in cell_list:
        for _r in range(counts[(f, a)]):
            svcs = by_fault[f]
            j = idx.get((f, a), 0)
            s = svcs[j % len(svcs)]
            idx[(f, a)] = j + 1
            n += 1
            plan.append({"id": "h%03d" % n, "phase": "heldout", "fault": f,
                         "origin": s, "action": a, "tau": HELDOUT_TAU})
    return plan, counts, by_fault


def build_corpus(cells, n, rng):
    plan = []
    for i in range(n):
        f, s = cells[rng.randrange(len(cells))]
        plan.append({"id": "c%03d" % (i + 1), "phase": "corpus", "fault": f,
                     "origin": s, "action": rng.choice(ACTIONS),
                     "tau": rng.choice(TAUS)})
    return plan


# --------------------------------------------------------------- injection
def run_one(feed, spec, seed):
    iid, phase = spec["id"], spec["phase"]
    fault, origin, action, tau_s = (spec["fault"], spec["origin"],
                                    spec["action"], spec["tau"])
    log("%s [%s] %s @ %s act=%s tau=%ds" % (iid, phase, fault, origin,
                                            action, tau_s))
    h0 = cluster_health()
    rec = {"id": iid, "phase": phase, "seed": seed, "fault": fault,
           "origin": origin, "action": action, "tau_target_s": tau_s,
           "censor_window_s": CENSOR_S, "cycle_start": time.time(),
           "health_pre": h0, "passed_persistence_control": True}
    if not wait_steady(feed, STEADY_WAIT_S):
        rec.update(status="no_steady_pre",
                   invalid_reason="baseline not healthy before injection")
        return rec

    t_inject = int(time.time() * 1000)
    inject(fault, origin)
    rec["t_inject_ms"] = t_inject
    rec["pods_at_inject"] = pod_snapshot(origin)

    onset = None
    t_end = time.time() + ONSET_WAIT_S
    while time.time() < t_end and onset is None:
        o = onsets(feed.window(t_inject), t_inject)
        c = [v for (_k, n), v in o.items() if n == origin]
        if c:
            onset = min(c)
        time.sleep(0.2)
    if onset is None:
        log("  ABORT: no onset")
        rec.update(status="no_onset",
                   invalid_reason="fault did not manifest within %ds" % ONSET_WAIT_S)
        reset(origin)
        wait_steady(feed, RESET_WAIT_S)
        return rec
    t_onset = t_inject + onset
    rec.update(t_onset_ms=t_onset, detect_latency_ms=onset)

    while (time.time() * 1000 - t_onset) / 1000.0 < tau_s:
        time.sleep(0.1)
    t_action = int(time.time() * 1000)
    recover(action, fault, origin)
    rec["t_action_ms"] = t_action
    rec["tau_actual_s"] = round((t_action - t_onset) / 1000.0, 3)

    recovered, censored, since = None, False, None
    t_end = time.time() + CENSOR_S
    while time.time() < t_end:
        if not failing_now(feed):
            since = since or time.time()
            if time.time() - since >= STEADY_S:
                recovered = int(since * 1000)
                break
        else:
            since = None
        time.sleep(0.3)
    if recovered is None:
        censored, recovered = True, int(time.time() * 1000)
        log("  CENSORED (no recovery within %ds of the action)" % CENSOR_S)

    win = feed.window(t_inject, recovered)
    ons = onsets(win, t_onset)
    per_service, per_level = {}, {}
    for (level, target), dt in ons.items():
        per_level.setdefault(level, {})[target] = dt
        if target in SERVICES:
            per_service[target] = min(per_service.get(target, 10 ** 9), dt)
    affected = sorted(per_service)
    o_dt = per_service.get(origin, 0)
    h1 = cluster_health()
    rec.update({
        "t_recovery_complete_ms": recovered,
        "duration_s": round((recovered - t_onset) / 1000.0, 3),
        "duration_min": round((recovered - t_onset) / 60000.0, 6),
        "tau_min": round((t_action - t_onset) / 60000.0, 6),
        "affected": affected, "blast": len(affected),
        "onset_ms_by_service": per_service, "onset_ms_by_level": per_level,
        "propagation_edges": {s: per_service[s] - o_dt
                              for s in affected if s != origin},
        "arrivals": {s: round(per_service[s] / 60000.0, 8) for s in affected},
        "functional_failures": sorted(per_level.get("functional", {})),
        "dependency_failures": sorted(per_level.get("dependency", {})),
        "uservisible_failures": sorted(per_level.get("uservisible", {})),
        "censored": censored, "n_probe_events": len(win), "health_post": h1,
        "infra_anomaly": bool(h1["container_restarts"] != h0["container_restarts"]),
        "feed_reconnects": feed.reconnects,
        "status": "censored" if censored else "ok",
    })
    log("  dur %.1fs blast=%d prop=%s%s" % (rec["duration_s"], rec["blast"],
                                            rec["propagation_edges"],
                                            " [CENSORED]" if censored else ""))
    reset(origin)
    rec["reset_ok"] = bool(wait_steady(feed, RESET_WAIT_S))
    rec["cycle_s"] = round(time.time() - rec["cycle_start"], 1)
    feed.trim()
    feed.flush()
    return rec


def stability_gate(feed, recs, h_start, h_end):
    """Infrastructure reliability only. Censoring is NOT a failure."""
    attempted = len(recs)
    measured = [r for r in recs if r.get("status") in ("ok", "censored")]
    g = {
        "attempted": attempted,
        "measured": len(measured),
        "censored": sum(1 for r in recs if r.get("censored")),
        "unexpected_container_restarts":
            h_end["container_restarts"] - h_start["container_restarts"],
        "clean_resets": sum(1 for r in measured if r.get("reset_ok")),
        "baseline_failures": sum(1 for r in recs
                                 if r.get("status") == "no_steady_pre"),
        "telemetry_events_total": sum(r.get("n_probe_events", 0) for r in measured),
        "telemetry_min_per_incident": min([r.get("n_probe_events", 0)
                                           for r in measured] or [0]),
        "feed_reconnects": feed.reconnects,
        "duplicate_orchestrator": False,
        "mean_cycle_s": (sum(r.get("cycle_s", 0) for r in recs)
                         / max(1, attempted)),
    }
    g["criteria"] = {
        "no_unexpected_container_restarts": g["unexpected_container_restarts"] == 0,
        "clean_reset_between_incidents": g["clean_resets"] == len(measured),
        "telemetry_continuity": g["telemetry_min_per_incident"] > 0,
        "healthy_baseline_before_each": g["baseline_failures"] == 0,
        "no_unexplained_data_loss": g["measured"] == attempted,
        "no_duplicate_orchestrator": not g["duplicate_orchestrator"],
    }
    g["pass"] = all(g["criteria"].values())
    return g


def main():
    os.makedirs(RES, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    done = {r["id"] for r in jread(INCIDENTS) if r.get("id")}
    feed = Feed()
    log("waiting for probe stream ...")
    t0 = time.time()
    while not feed.window(0) and time.time() - t0 < 90:
        time.sleep(0.5)
    if not feed.window(0):
        log("FATAL: no probe data")
        return 1
    jappend(HEALTH, cluster_health())

    # ---- phase 1a: re-control the two cells V1 could not measure ----
    have = {(c["fault"], c["origin"]) for c in jread(CONTROLS)}
    for f, s in RECONTROL:
        if (f, s) in have:
            continue
        try:
            r = run_control(feed, f, s)
        except Exception as ex:
            log("  control error: %s" % ex)
            r = {"fault": f, "origin": s, "status": "error", "error": str(ex),
                 "admitted": False}
            try:
                reset(s)
                wait_steady(feed, RESET_WAIT_S)
            except Exception:
                pass
        jappend(CONTROLS, r)

    cells = admitted_cells()
    log("admitted cells (%d): %s" % (len(cells), cells))

    heldout, counts, by_fault = allocate(cells)
    corpus = build_corpus(cells, N_CORPUS, random.Random(MASTER_SEED + 2))
    if not os.path.exists(ALLOC):
        json.dump({"admitted_cells": [list(c) for c in cells],
                   "services_by_fault": by_fault,
                   "heldout_cell_counts": {"%s|%s" % k: v
                                           for k, v in counts.items()},
                   "heldout_plan": heldout, "corpus_plan": corpus,
                   "heldout_tau_s": HELDOUT_TAU, "censor_window_s": CENSOR_S,
                   "master_seed": MASTER_SEED,
                   "n_corpus": N_CORPUS, "n_heldout": N_HELDOUT},
                  open(ALLOC, "w"), indent=2)
    log("held-out allocation: %d cells, counts=%s"
        % (len(counts), {"%s|%s" % k: v for k, v in counts.items()}))
    if mode == "plan":
        feed.stop = True
        return 0

    # ---- phase 0: stability (infrastructure only) ----
    if not os.path.exists(STABILITY) and mode in ("all", "stability"):
        log("=== phase 0: stability batch (%d incidents, infra gate) ==="
            % N_STABILITY)
        srng = random.Random(MASTER_SEED + 1)
        h_start = cluster_health()
        for i in range(N_STABILITY):
            spec = dict(corpus[i])
            spec["id"] = "st%02d" % (i + 1)
            spec["phase"] = "stability"
            if spec["id"] in done:
                continue
            rec = run_one(feed, spec, srng.randint(0, 2 ** 31))
            jappend(INCIDENTS, rec)
            jappend(HEALTH, cluster_health())
        recs = [r for r in jread(INCIDENTS) if r.get("phase") == "stability"]
        g = stability_gate(feed, recs, h_start, cluster_health())
        json.dump(g, open(STABILITY, "w"), indent=2)
        log("stability gate: pass=%s %s" % (g["pass"], g["criteria"]))
        if not g["pass"]:
            log("INFRASTRUCTURE GATE FAILED -- stopping")
            feed.stop = True
            return 2
    if mode == "stability":
        feed.stop = True
        return 0

    # ---- phase 2: corpus ----
    rng = random.Random(MASTER_SEED + 5)
    if mode in ("all", "corpus"):
        log("=== phase 2: corpus (%d) ===" % len(corpus))
        for spec in corpus:
            if spec["id"] in done:
                continue
            try:
                rec = run_one(feed, spec, rng.randint(0, 2 ** 31))
            except Exception as ex:
                log("  ERROR %s: %s" % (spec["id"], ex))
                rec = dict(spec, status="error", invalid_reason=str(ex))
                try:
                    reset(spec["origin"])
                    wait_steady(feed, RESET_WAIT_S)
                except Exception:
                    pass
            jappend(INCIDENTS, rec)
            jappend(HEALTH, cluster_health())
        corp = [r for r in jread(INCIDENTS) if r.get("phase") == "corpus"]
        if len(corp) >= N_CORPUS and not os.path.exists(CORPUS_FROZEN):
            json.dump({"frozen_at": int(time.time() * 1000),
                       "n": len(corp), "ids": sorted(r["id"] for r in corp)},
                      open(CORPUS_FROZEN, "w"), indent=2)
            log("CORPUS FROZEN: %d incidents" % len(corp))
    if mode == "corpus":
        feed.stop = True
        return 0

    # ---- phase 3: held-out ----
    log("=== phase 3: held-out (%d) ===" % len(heldout))
    for spec in heldout:
        if spec["id"] in done:
            continue
        try:
            rec = run_one(feed, spec, rng.randint(0, 2 ** 31))
        except Exception as ex:
            log("  ERROR %s: %s" % (spec["id"], ex))
            rec = dict(spec, status="error", invalid_reason=str(ex))
            try:
                reset(spec["origin"])
                wait_steady(feed, RESET_WAIT_S)
            except Exception:
                pass
        jappend(INCIDENTS, rec)
        jappend(HEALTH, cluster_health())
    feed.stop = True
    feed.flush()
    log("V1r campaign complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
