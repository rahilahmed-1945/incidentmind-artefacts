"""
V1a instrument-validation pilot.

Runs a small number of injections against the dedicated `incidentmind-fi`
cluster using the tiered V1a prober, and measures whether the improved
instrument can resolve what V0 could not:

  * non-zero, reproducible propagation delays between services
  * affected-service sets larger than the origin alone
  * dependency-level degradation distinguishable from process/endpoint health
  * stable recovery durations
  * fault persistence (verified by explicit no-recovery controls)

The IncidentMind estimator is NOT involved here and is NOT imported. This
script only measures. Nothing is tuned against any earlier result.

Ground truth is derived post hoc from the raw probe event stream: for each
(level, target) the onset is the first of CONFIRM_FAIL consecutive failing
samples after the fault command returns, and recovery is the start of the first
sustained all-healthy window. No propagation timing is assumed.
"""
import json
import os
import subprocess
import sys
import threading
import time

CTX = "kind-incidentmind-fi"
HOME = os.path.expanduser("~/imfi")
MANIFEST = os.path.join(HOME, "online-boutique-noload.yaml")
RESULTS = os.path.join(HOME, "results")
RAW = os.path.join(RESULTS, "v1a_events.jsonl")
INCIDENTS = os.path.join(RESULTS, "v1a_incidents.jsonl")
CONTROLS = os.path.join(RESULTS, "v1a_controls.jsonl")
EVENTS = os.path.join(RESULTS, "v1a_events.log")

CONFIRM_FAIL = 2      # consecutive failing samples to declare degraded
CONFIRM_OK = 3        # consecutive healthy samples to declare recovered
STEADY_S = 8
STEADY_WAIT_S = 240
ONSET_WAIT_S = 90
CENSOR_S = 150
RESET_WAIT_S = 300
CONTROL_OBSERVE_S = 100

SERVICES = ["adservice", "cartservice", "checkoutservice", "currencyservice",
            "emailservice", "frontend", "paymentservice", "productcatalogservice",
            "recommendationservice", "redis-cart", "shippingservice"]

RECREATE = '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}'
ROLLING = ('{"spec":{"strategy":{"type":"RollingUpdate","rollingUpdate":'
           '{"maxSurge":"25%","maxUnavailable":"25%"}}}}')

# Only fault types V0 demonstrated genuinely manifest.
PLAN = [
    ("p01", "service_crash",       "productcatalogservice", "pod_restart",     15),
    ("p02", "service_crash",       "currencyservice",       "pod_restart",     30),
    ("p03", "service_crash",       "cartservice",           "scale_replicas",  20),
    ("p04", "service_crash",       "redis-cart",            "pod_restart",     20),
    ("p05", "service_crash",       "shippingservice",       "pod_restart",     25),
    ("p06", "service_crash",       "paymentservice",        "pod_restart",     15),
    ("p07", "deploy_misconfig",    "productcatalogservice", "rollback_deploy", 20),
    ("p08", "deploy_misconfig",    "shippingservice",       "rollback_deploy", 15),
    ("p09", "deploy_misconfig",    "currencyservice",       "rollback_deploy", 25),
    ("p10", "resource_exhaustion", "productcatalogservice", "rollback_deploy", 20),
    ("p11", "resource_exhaustion", "recommendationservice", "rollback_deploy", 25),
    ("p12", "service_crash",       "adservice",             "pod_restart",     15),
    ("p13", "service_crash",       "emailservice",          "pod_restart",     20),
    ("p14", "deploy_misconfig",    "recommendationservice", "rollback_deploy", 20),
]

# (fault, service) pairs needing a no-recovery persistence control
CONTROL_PAIRS = [
    ("service_crash", "productcatalogservice"),
    ("service_crash", "redis-cart"),
    ("deploy_misconfig", "productcatalogservice"),
    ("deploy_misconfig", "shippingservice"),
    ("deploy_misconfig", "currencyservice"),
    ("deploy_misconfig", "recommendationservice"),
    ("resource_exhaustion", "productcatalogservice"),
    ("resource_exhaustion", "recommendationservice"),
]


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(EVENTS, "a") as fh:
        fh.write(line + "\n")


def kc(*args, check=True, timeout=180):
    r = subprocess.run(["kubectl", "--context", CTX] + list(args),
                       capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError("kubectl %s: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout.strip()


# --------------------------------------------------------------- event feed
class Feed:
    def __init__(self):
        self.ev = []
        self.lock = threading.Lock()
        self.stop = False
        self.fh = open(RAW, "a")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self.stop:
            p = subprocess.Popen(
                ["kubectl", "--context", CTX, "logs", "-f", "--tail=0",
                 "im-prober-v1a"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
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
                time.sleep(0.5)

    def window(self, t0, t1=None):
        with self.lock:
            return [e for e in self.ev
                    if e["t"] >= t0 and (t1 is None or e["t"] <= t1)]

    def trim(self, keep_ms):
        with self.lock:
            cut = int(time.time() * 1000) - keep_ms
            self.ev = [e for e in self.ev if e["t"] >= cut]


def failing_now(feed, secs=2.0):
    """Targets currently failing, from the last `secs` of samples."""
    t0 = int((time.time() - secs) * 1000)
    last = {}
    for e in feed.window(t0):
        last[(e["k"], e["n"])] = e["ok"]
    return {k for k, ok in last.items() if ok == 0}


def wait_steady(feed, limit_s, need=STEADY_S):
    t_end = time.time() + limit_s
    ok_since = None
    while time.time() < t_end:
        if not failing_now(feed):
            ok_since = ok_since or time.time()
            if time.time() - ok_since >= need:
                return True
        else:
            ok_since = None
        time.sleep(0.3)
    return False


def onsets(events, t_from):
    """First confirmed failure per (level, target), as ms after t_from."""
    seq, out = {}, {}
    for e in sorted(events, key=lambda x: x["t"]):
        if e["t"] < t_from:
            continue
        key = (e["k"], e["n"])
        if e["ok"] == 0:
            seq[key] = seq.get(key, 0) + 1
            if seq[key] == CONFIRM_FAIL and key not in out:
                out[key] = e["t"] - t_from
        else:
            seq[key] = 0
    return out


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


def pod_states(svc):
    out = kc("get", "pods", "-l", "app=" + svc, "--no-headers", check=False)
    return [l.split() for l in out.splitlines() if l.strip()]


# --------------------------------------------------------------- controls
def run_control(feed, fault, svc):
    log("CONTROL %s @ %s  (no recovery action, observe %ds)"
        % (fault, svc, CONTROL_OBSERVE_S))
    rec = {"fault": fault, "origin": svc, "observe_s": CONTROL_OBSERVE_S}
    if not wait_steady(feed, STEADY_WAIT_S):
        rec["status"] = "no_steady_pre"
        return rec
    t_inj = int(time.time() * 1000)
    inject(fault, svc)
    samples = []
    t_end = time.time() + CONTROL_OBSERVE_S
    while time.time() < t_end:
        time.sleep(10)
        fails = failing_now(feed)
        down = any(n == svc for (_k, n) in fails)
        samples.append({"t_s": round(time.time() - t_inj / 1000.0, 1),
                        "origin_down": bool(down),
                        "n_failing_targets": len(fails)})
    persisted = all(s["origin_down"] for s in samples[1:]) and len(samples) > 1
    rec.update({"samples": samples, "persistent": bool(persisted),
                "pods": pod_states(svc),
                "status": "persistent" if persisted else "self_healed"})
    log("  -> %s" % rec["status"].upper())
    reset(svc)
    wait_steady(feed, RESET_WAIT_S)
    return rec


# --------------------------------------------------------------- injection
def run_one(feed, iid, fault, origin, action, tau_s):
    log("%s  %s @ %s  action=%s  tau=%ds" % (iid, fault, origin, action, tau_s))
    rec = {"id": iid, "fault": fault, "origin": origin, "action": action,
           "tau_target_s": tau_s, "cycle_start": time.time()}
    if not wait_steady(feed, STEADY_WAIT_S):
        log("  ABORT: no steady state")
        rec["status"] = "no_steady_pre"
        return rec

    t_inject = int(time.time() * 1000)
    inject(fault, origin)
    rec["t_inject_ms"] = t_inject

    origin_onset = None
    t_end = time.time() + ONSET_WAIT_S
    while time.time() < t_end and origin_onset is None:
        o = onsets(feed.window(t_inject), t_inject)
        cand = [v for (k, n), v in o.items() if n == origin]
        if cand:
            origin_onset = min(cand)
        time.sleep(0.2)
    if origin_onset is None:
        log("  ABORT: fault did not manifest")
        rec["status"] = "no_onset"
        reset(origin)
        wait_steady(feed, RESET_WAIT_S)
        return rec
    t_onset = t_inject + origin_onset
    rec["detect_latency_ms"] = origin_onset
    log("  onset +%d ms after injection" % origin_onset)

    while (time.time() * 1000 - t_onset) / 1000.0 < tau_s:
        time.sleep(0.1)
    t_action = int(time.time() * 1000)
    recover(action, fault, origin)
    rec["t_action_ms"] = t_action
    rec["tau_s"] = round((t_action - t_onset) / 1000.0, 2)

    recovered, censored = None, False
    t_end = time.time() + CENSOR_S
    ok_since = None
    while time.time() < t_end:
        if not failing_now(feed):
            ok_since = ok_since or time.time()
            if time.time() - ok_since >= STEADY_S:
                recovered = int(ok_since * 1000)
                break
        else:
            ok_since = None
        time.sleep(0.3)
    if recovered is None:
        censored = True
        recovered = int(time.time() * 1000)
        log("  CENSORED")

    win = feed.window(t_inject, recovered)
    ons = onsets(win, t_onset)
    per_service, per_level = {}, {}
    for (level, target), dt in ons.items():
        per_level.setdefault(level, {})[target] = dt
        if target in SERVICES:
            per_service[target] = min(per_service.get(target, 10 ** 9), dt)
    affected = sorted(per_service)
    rec.update({
        "t_onset_ms": t_onset, "t_recovered_ms": recovered,
        "duration_s": round((recovered - t_onset) / 1000.0, 2),
        "duration_min": round((recovered - t_onset) / 60000.0, 5),
        "tau_min": round((t_action - t_onset) / 60000.0, 5),
        "affected": affected, "blast": len(affected),
        "onset_ms_by_service": per_service,
        "onset_ms_by_level": per_level,
        "propagation_ms": {s: per_service[s] - per_service.get(origin, 0)
                           for s in affected if s != origin},
        "arrivals": {s: round((per_service[s]) / 60000.0, 6) for s in affected},
        "censored": censored, "n_events": len(win),
        "status": "censored" if censored else "ok",
    })
    log("  dur %.1fs  blast=%d  affected=%s" % (
        rec["duration_s"], rec["blast"], ",".join(affected)))
    if rec["propagation_ms"]:
        log("  propagation (ms after origin): %s" % rec["propagation_ms"])

    reset(origin)
    rec["reset_ok"] = bool(wait_steady(feed, RESET_WAIT_S))
    rec["cycle_s"] = round(time.time() - rec["cycle_start"], 1)
    log("  cycle %.0fs" % rec["cycle_s"])
    feed.trim(600000)
    return rec


def main():
    os.makedirs(RESULTS, exist_ok=True)
    done = set()
    if os.path.exists(INCIDENTS):
        for l in open(INCIDENTS):
            try:
                done.add(json.loads(l)["id"])
            except Exception:
                pass
    feed = Feed()
    log("waiting for probe stream ...")
    t0 = time.time()
    while not feed.window(0) and time.time() - t0 < 60:
        time.sleep(0.5)
    if not feed.window(0):
        log("FATAL: no probe data")
        return 1

    t_start = time.time()
    if not os.path.exists(CONTROLS):
        log("=== phase 1: fault-persistence controls ===")
        for fault, svc in CONTROL_PAIRS:
            try:
                r = run_control(feed, fault, svc)
            except Exception as ex:
                log("  control error: %s" % ex)
                r = {"fault": fault, "origin": svc, "status": "error",
                     "error": str(ex)}
                try:
                    reset(svc)
                    wait_steady(feed, RESET_WAIT_S)
                except Exception:
                    pass
            with open(CONTROLS, "a") as fh:
                fh.write(json.dumps(r) + "\n")

    log("=== phase 2: injections ===")
    for (iid, fault, origin, action, tau) in PLAN:
        if iid in done:
            continue
        try:
            rec = run_one(feed, iid, fault, origin, action, tau)
        except Exception as ex:
            log("  ERROR %s: %s" % (iid, ex))
            rec = {"id": iid, "fault": fault, "origin": origin,
                   "action": action, "status": "error", "error": str(ex)}
            try:
                reset(origin)
                wait_steady(feed, RESET_WAIT_S)
            except Exception:
                pass
        with open(INCIDENTS, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    feed.stop = True
    log("V1a complete in %.0f min" % ((time.time() - t_start) / 60.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
