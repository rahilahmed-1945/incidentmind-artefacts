"""
V1 full real-world validation campaign.

Phases, each independently checkpointed and resumable:
  0  stability batch      small run; verifies no leaks/restarts/telemetry loss
  1  persistence controls one no-recovery control per (fault, service) cell;
                          a cell is only admitted to the grid if its fault
                          both PERSISTS and produces observable degradation
  2  corpus               randomised incidents -> real precedent corpus
  3  heldout              repeated observations per (fault, service, action)
                          cell, enabling cell-level expected outcomes

The IncidentMind estimator is NOT imported here. This script only measures.
Nothing is tuned against any result. Grid membership is decided by the
persistence controls alone, never by outcome favourability.

All state is persisted after every incident. Re-running resumes.
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

RAW = os.path.join(RES, "v1_events.jsonl")
CONTROLS = os.path.join(RES, "v1_controls.jsonl")
INCIDENTS = os.path.join(RES, "v1_incidents.jsonl")
STABILITY = os.path.join(RES, "v1_stability.json")
HEALTH = os.path.join(RES, "v1_health.jsonl")
LOG = os.path.join(RES, "v1_run.log")

CONFIRM_FAIL = 2
STEADY_S = 8
STEADY_WAIT_S = 240
ONSET_WAIT_S = 90
CENSOR_S = 150
RESET_WAIT_S = 300
CONTROL_OBSERVE_S = 100

MASTER_SEED = 20260824
N_STABILITY = 10
N_CORPUS = 150
N_HELDOUT = 90
HELDOUT_TAU = 45          # heldout fixes tau so actions are compared like-for-like
HELDOUT_REPS = 3

SERVICES = ["adservice", "cartservice", "checkoutservice", "currencyservice",
            "emailservice", "frontend", "paymentservice", "productcatalogservice",
            "recommendationservice", "redis-cart", "shippingservice"]

# candidate cells; membership decided by phase-1 controls
CANDIDATE_SERVICES = ["productcatalogservice", "currencyservice", "shippingservice",
                      "recommendationservice", "cartservice", "redis-cart"]
FAULTS = ["service_crash", "deploy_misconfig", "resource_exhaustion"]
ACTIONS = ["pod_restart", "scale_replicas", "rollback_deploy"]
TAUS = [15, 45, 90]

# established by earlier pilots; retained so they are never silently retried
KNOWN_INVALID = {("deploy_misconfig", "cartservice"),          # V0: ignores PORT
                 ("resource_exhaustion", "productcatalogservice")}  # V1a: self-heals

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


def jread(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def jappend(path, obj):
    with open(path, "a") as fh:
        fh.write(json.dumps(obj, default=float) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# --------------------------------------------------------------- telemetry
class Feed:
    def __init__(self):
        self.ev, self.lock, self.stop = [], threading.Lock(), False
        self.reconnects = 0
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


# --------------------------------------------------------------- k8s state
def cluster_health():
    out = kc("get", "pods", "--no-headers", check=False)
    pods, restarts, notready = 0, 0, 0
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
        rec["status"] = "no_steady_pre"
        return rec
    t_inj = int(time.time() * 1000)
    inject(fault, svc)
    samples, degraded_seen = [], False
    t_end = time.time() + CONTROL_OBSERVE_S
    while time.time() < t_end:
        time.sleep(10)
        fails = failing_now(feed)
        down = any(n == svc for (_k, n) in fails)
        degraded_seen |= bool(fails)
        samples.append({"dt_s": round(time.time() - t_inj / 1000.0, 1),
                        "origin_down": bool(down), "n_failing": len(fails)})
    persisted = len(samples) > 1 and all(s["origin_down"] for s in samples[1:])
    rec.update({"samples": samples, "persistent": bool(persisted),
                "observable_degradation": bool(degraded_seen),
                "pods": pod_snapshot(svc),
                "admitted": bool(persisted and degraded_seen),
                "status": "persistent" if persisted else "self_healed"})
    log("  -> %s (admitted=%s)" % (rec["status"].upper(), rec["admitted"]))
    reset(svc)
    wait_steady(feed, RESET_WAIT_S)
    return rec


# --------------------------------------------------------------- injection
def run_one(feed, iid, phase, fault, origin, action, tau_s, seed):
    log("%s [%s] %s @ %s act=%s tau=%ds" % (iid, phase, fault, origin, action, tau_s))
    h0 = cluster_health()
    rec = {"id": iid, "phase": phase, "seed": seed, "fault": fault,
           "origin": origin, "action": action, "tau_target_s": tau_s,
           "cycle_start": time.time(), "health_pre": h0,
           "passed_persistence_control": True}
    if not wait_steady(feed, STEADY_WAIT_S):
        rec["status"] = "no_steady_pre"
        rec["invalid_reason"] = "cluster not steady before injection"
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
    rec["t_onset_ms"] = t_onset
    rec["detect_latency_ms"] = onset

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
        log("  CENSORED (no recovery within %ds)" % CENSOR_S)

    win = feed.window(t_inject, recovered)
    ons = onsets(win, t_onset)
    per_service, per_level = {}, {}
    for (level, target), dt in ons.items():
        per_level.setdefault(level, {})[target] = dt
        if target in SERVICES:
            per_service[target] = min(per_service.get(target, 10 ** 9), dt)
    affected = sorted(per_service)
    origin_dt = per_service.get(origin, 0)
    h1 = cluster_health()
    rec.update({
        "t_recovery_complete_ms": recovered,
        "duration_s": round((recovered - t_onset) / 1000.0, 3),
        "duration_min": round((recovered - t_onset) / 60000.0, 6),
        "tau_min": round((t_action - t_onset) / 60000.0, 6),
        "affected": affected, "blast": len(affected),
        "onset_ms_by_service": per_service, "onset_ms_by_level": per_level,
        "propagation_edges": {s: per_service[s] - origin_dt
                              for s in affected if s != origin},
        "arrivals": {s: round(per_service[s] / 60000.0, 8) for s in affected},
        "functional_failures": sorted(per_level.get("functional", {})),
        "dependency_failures": sorted(per_level.get("dependency", {})),
        "uservisible_failures": sorted(per_level.get("uservisible", {})),
        "censored": censored, "n_probe_events": len(win),
        "health_post": h1,
        "infra_anomaly": bool(h1["container_restarts"] != h0["container_restarts"]),
        "feed_reconnects": feed.reconnects,
        "status": "censored" if censored else "ok",
    })
    log("  dur %.1fs blast=%d prop=%s%s" % (
        rec["duration_s"], rec["blast"], rec["propagation_edges"],
        " [CENSORED]" if censored else ""))

    reset(origin)
    rec["reset_ok"] = bool(wait_steady(feed, RESET_WAIT_S))
    rec["cycle_s"] = round(time.time() - rec["cycle_start"], 1)
    feed.trim()
    feed.flush()
    return rec


# --------------------------------------------------------------- planning
def admitted_cells():
    cells = []
    for c in jread(CONTROLS):
        if c.get("admitted"):
            cells.append((c["fault"], c["origin"]))
    return sorted(set(cells))


def valid_actions(fault):
    return list(ACTIONS)


def build_corpus_plan(cells, n, rng):
    plan = []
    for i in range(n):
        f, s = rng.choice(cells)
        a = rng.choice(valid_actions(f))
        t = rng.choice(TAUS)
        plan.append(("c%03d" % (i + 1), "corpus", f, s, a, t,
                     rng.randint(0, 2 ** 31)))
    return plan


def build_heldout_plan(cells, n, rng):
    combos = [(f, s, a) for (f, s) in cells for a in valid_actions(f)]
    rng.shuffle(combos)
    plan, i = [], 0
    while len(plan) < n and combos:
        f, s, a = combos[i % len(combos)]
        rep = i // len(combos)
        if rep >= HELDOUT_REPS:
            break
        plan.append(("h%03d" % (len(plan) + 1), "heldout", f, s, a,
                     HELDOUT_TAU, rng.randint(0, 2 ** 31)))
        i += 1
    return plan


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

    rng = random.Random(MASTER_SEED)

    # ---------------- phase 1: persistence controls ----------------
    have = {(c["fault"], c["origin"]) for c in jread(CONTROLS)}
    todo = [(f, s) for f in FAULTS for s in CANDIDATE_SERVICES
            if (f, s) not in have and (f, s) not in KNOWN_INVALID]
    if todo and mode in ("all", "controls"):
        log("=== phase 1: %d persistence controls ===" % len(todo))
        for f, s in todo:
            try:
                r = run_control(feed, f, s)
            except Exception as ex:
                log("  control error %s@%s: %s" % (f, s, ex))
                r = {"fault": f, "origin": s, "status": "error",
                     "error": str(ex), "admitted": False}
                try:
                    reset(s)
                    wait_steady(feed, RESET_WAIT_S)
                except Exception:
                    pass
            jappend(CONTROLS, r)
    for f, s in sorted(KNOWN_INVALID):
        if (f, s) not in have:
            jappend(CONTROLS, {"fault": f, "origin": s, "admitted": False,
                               "status": "excluded_prior_pilot",
                               "note": "rejected in an earlier pilot; not retried"})

    cells = admitted_cells()
    log("admitted cells (%d): %s" % (len(cells), cells))
    if not cells:
        log("FATAL: no admitted cells")
        return 1
    if mode == "controls":
        feed.stop = True
        return 0

    # ---------------- phase 0: stability batch ----------------
    if not os.path.exists(STABILITY) and mode in ("all", "stability"):
        log("=== phase 0: stability batch (%d incidents) ===" % N_STABILITY)
        srng = random.Random(MASTER_SEED + 1)
        h_start = cluster_health()
        for i in range(N_STABILITY):
            f, s = srng.choice(cells)
            a, t = srng.choice(valid_actions(f)), srng.choice(TAUS)
            iid = "s%03d" % (i + 1)
            if iid in done:
                continue
            rec = run_one(feed, iid, "stability", f, s, a, t,
                          srng.randint(0, 2 ** 31))
            jappend(INCIDENTS, rec)
            jappend(HEALTH, cluster_health())
        h_end = cluster_health()
        recs = [r for r in jread(INCIDENTS) if r.get("phase") == "stability"]
        okc = sum(1 for r in recs if r.get("status") == "ok")
        stab = {
            "n": len(recs), "ok": okc,
            "container_restarts_delta": h_end["container_restarts"]
                                        - h_start["container_restarts"],
            "feed_reconnects": feed.reconnects,
            "resets_ok": sum(1 for r in recs if r.get("reset_ok")),
            "mean_cycle_s": (sum(r.get("cycle_s", 0) for r in recs)
                             / max(1, len(recs))),
            "mean_probe_events": (sum(r.get("n_probe_events", 0) for r in recs)
                                  / max(1, len(recs))),
            "pass": bool(okc >= N_STABILITY * 0.8
                         and h_end["container_restarts"]
                         == h_start["container_restarts"]),
        }
        json.dump(stab, open(STABILITY, "w"), indent=2)
        log("stability: %s" % stab)
        if not stab["pass"]:
            log("STABILITY GATE FAILED -- stopping before the campaign")
            feed.stop = True
            return 2
    if mode == "stability":
        feed.stop = True
        return 0

    # ---------------- phases 2-3: corpus then heldout ----------------
    plan = (build_corpus_plan(cells, N_CORPUS, random.Random(MASTER_SEED + 2))
            + build_heldout_plan(cells, N_HELDOUT, random.Random(MASTER_SEED + 3)))
    log("=== phases 2-3: %d planned incidents (%d already done) ==="
        % (len(plan), len([p for p in plan if p[0] in done])))
    for (iid, phase, f, s, a, t, seed) in plan:
        if iid in done:
            continue
        try:
            rec = run_one(feed, iid, phase, f, s, a, t, seed)
        except Exception as ex:
            log("  ERROR %s: %s" % (iid, ex))
            rec = {"id": iid, "phase": phase, "seed": seed, "fault": f,
                   "origin": s, "action": a, "tau_target_s": t,
                   "status": "error", "invalid_reason": str(ex)}
            try:
                reset(s)
                wait_steady(feed, RESET_WAIT_S)
            except Exception:
                pass
        jappend(INCIDENTS, rec)
        jappend(HEALTH, cluster_health())
    feed.stop = True
    feed.flush()
    log("V1 campaign complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
