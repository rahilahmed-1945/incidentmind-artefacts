"""
V0 pilot orchestrator: controlled fault injection against Online Boutique.

Runs inside WSL against the dedicated `incidentmind-fi` kind cluster. Streams
the 1 Hz prober trace, injects a fault, applies a recovery action at a chosen
delay, and measures the resulting incident from the trace alone.

GROUND TRUTH IS MEASURED, NEVER ASSUMED
    onset      first sweep in which the origin service is unhealthy after the
               fault command returns
    arrivals   per service, the first sweep in which it is unhealthy at or
               after onset
    affected   services unhealthy at any point between onset and recovery
    recovery   start of the first sustained all-healthy window of STEADY_S
    duration   recovery - onset, in seconds
    tau        time from onset to the recovery action being applied

If a run does not recover within CENSOR_S the record is marked censored, a
forced remediation is applied, and the duration is recorded as a lower bound.
Censored runs are reported, not discarded.

Resumable: completed incidents are appended to the results file and skipped on
a subsequent run.
"""
import json
import os
import subprocess
import sys
import threading
import time

CTX = "kind-incidentmind-fi"
MANIFEST = os.path.expanduser("~/imfi/online-boutique-noload.yaml")
RESULTS = os.path.expanduser("~/imfi/results")
TRACE = os.path.join(RESULTS, "v0_trace.jsonl")
INCIDENTS = os.path.join(RESULTS, "v0_incidents.jsonl")
EVENTS = os.path.join(RESULTS, "v0_events.log")

STEADY_S = 10        # consecutive healthy sweeps required for "steady"
STEADY_WAIT_S = 180  # max wait for steady state
ONSET_WAIT_S = 90    # max wait for the fault to manifest
CENSOR_S = 150       # max time from action to recovery before censoring
RESET_WAIT_S = 240

# ---------------------------------------------------------------- V0 grid
# Three fault types x three actions, several origins, deliberately including
# one action that should NOT work (misconfig repaired by a restart).
PLAN = [
    ("i01", "service_crash",       "productcatalogservice", "pod_restart",     15),
    ("i02", "service_crash",       "cartservice",           "scale_replicas",  30),
    ("i03", "service_crash",       "currencyservice",       "pod_restart",     45),
    ("i04", "deploy_misconfig",    "productcatalogservice", "rollback_deploy", 15),
    ("i05", "deploy_misconfig",    "currencyservice",       "rollback_deploy", 45),
    ("i06", "deploy_misconfig",    "cartservice",           "pod_restart",     30),
    ("i07", "resource_exhaustion", "productcatalogservice", "rollback_deploy", 20),
    ("i08", "resource_exhaustion", "recommendationservice", "rollback_deploy", 40),
    ("i09", "service_crash",       "paymentservice",        "pod_restart",     25),
    ("i10", "deploy_misconfig",    "shippingservice",       "rollback_deploy", 20),
]

SERVICES = ["adservice", "cartservice", "checkoutservice", "currencyservice",
            "emailservice", "frontend", "paymentservice", "productcatalogservice",
            "recommendationservice", "redis-cart", "shippingservice"]


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(EVENTS, "a") as fh:
        fh.write(line + "\n")


def kc(*args, check=True, timeout=120):
    cmd = ["kubectl", "--context", CTX] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError("kubectl %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout.strip()


# ---------------------------------------------------------------- trace feed
class Trace:
    """Background reader of the prober stream; keeps an in-memory sweep list."""

    def __init__(self):
        self.sweeps = []
        self.lock = threading.Lock()
        self.stop = False
        self.fh = open(TRACE, "a")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self.stop:
            p = subprocess.Popen(
                ["kubectl", "--context", CTX, "logs", "-f", "--tail=1", "im-prober"],
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
                    self.sweeps.append(d)
                self.fh.write(line + "\n")
                self.fh.flush()
            try:
                p.kill()
            except Exception:
                pass
            if not self.stop:
                time.sleep(1)

    def since(self, t_ms):
        with self.lock:
            return [s for s in self.sweeps if s["t"] >= t_ms]

    def latest(self):
        with self.lock:
            return self.sweeps[-1] if self.sweeps else None


def unhealthy(sweep):
    return {k for k, v in sweep["r"].items() if v[0] == 0}


def wait_steady(tr, limit_s, need=STEADY_S):
    """Block until `need` consecutive sweeps show every service healthy."""
    t_end = time.time() + limit_s
    streak, last_t = 0, 0
    while time.time() < t_end:
        s = tr.latest()
        if s and s["t"] != last_t:
            last_t = s["t"]
            streak = streak + 1 if not unhealthy(s) else 0
            if streak >= need:
                return True
        time.sleep(0.25)
    return False


# ---------------------------------------------------------------- faults
RECREATE = ('{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}')
ROLLING = ('{"spec":{"strategy":{"type":"RollingUpdate","rollingUpdate":'
           '{"maxSurge":"25%","maxUnavailable":"25%"}}}}')


def inject(fault, svc):
    """
    Fault mechanisms, corrected during setup after smoke testing (see the V0
    report). The original podspec-level definitions did not manifest at all:
    a RollingUpdate keeps the healthy old Pod serving while the defective new
    Pod fails its readiness probe, so the Service never loses an endpoint.
    Podspec faults are therefore applied with strategy=Recreate, which models a
    deployment whose rollout does not gate on readiness.
    """
    if fault == "service_crash":
        kc("scale", "deploy/" + svc, "--replicas=0")
    elif fault == "deploy_misconfig":
        # server binds the wrong port; readiness still targets the declared
        # containerPort, so the pod never becomes ready
        kc("patch", "deploy", svc, "-p", RECREATE)
        kc("set", "env", "deploy/" + svc, "PORT=19999")
    elif fault == "resource_exhaustion":
        # memory ceiling below the runtime's footprint -> OOMKill -> crash loop
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
    """
    Return the deployment set to the pinned manifest state. The Recreate patch
    must be undone explicitly: `kubectl apply` cannot remove a field the
    manifest never declared.
    """
    kc("patch", "deploy", svc, "-p", ROLLING, check=False)
    kc("apply", "-f", MANIFEST, timeout=180)
    kc("scale", "deploy/" + svc, "--replicas=1", check=False)


# ---------------------------------------------------------------- one run
def run_one(tr, iid, fault, origin, action, tau_target):
    log("%s  %s @ %s  action=%s  tau=%ds" % (iid, fault, origin, action, tau_target))
    rec = {"id": iid, "fault": fault, "origin": origin, "action": action,
           "tau_target_s": tau_target, "cycle_start": time.time()}

    if not wait_steady(tr, STEADY_WAIT_S):
        log("  ABORT: no steady state before injection")
        rec.update(status="no_steady_pre")
        return rec

    t_inject_ms = int(time.time() * 1000)
    inject(fault, origin)
    rec["t_inject_ms"] = t_inject_ms

    # --- measured onset: origin first observed unhealthy
    onset_ms, t_end = None, time.time() + ONSET_WAIT_S
    while time.time() < t_end and onset_ms is None:
        for s in tr.since(t_inject_ms):
            if s["r"].get(origin, [1])[0] == 0:
                onset_ms = s["t"]
                break
        time.sleep(0.25)
    if onset_ms is None:
        log("  ABORT: fault did not manifest within %ds" % ONSET_WAIT_S)
        rec.update(status="no_onset")
        reset(origin)
        wait_steady(tr, RESET_WAIT_S)
        return rec
    rec["onset_ms"] = onset_ms
    rec["detect_latency_s"] = round((onset_ms - t_inject_ms) / 1000.0, 2)
    log("  onset +%.1fs after injection" % rec["detect_latency_s"])

    # --- hold until tau, then act
    while (time.time() * 1000 - onset_ms) / 1000.0 < tau_target:
        time.sleep(0.2)
    t_action_ms = int(time.time() * 1000)
    recover(action, fault, origin)
    rec["t_action_ms"] = t_action_ms
    rec["tau_s"] = round((t_action_ms - onset_ms) / 1000.0, 2)

    # --- wait for sustained recovery, else censor
    recovered_ms, censored = None, False
    t_end = time.time() + CENSOR_S
    streak, last_t, win_start = 0, 0, None
    while time.time() < t_end:
        s = tr.latest()
        if s and s["t"] != last_t:
            last_t = s["t"]
            if not unhealthy(s):
                if streak == 0:
                    win_start = s["t"]
                streak += 1
                if streak >= STEADY_S:
                    recovered_ms = win_start
                    break
            else:
                streak, win_start = 0, None
        time.sleep(0.25)
    if recovered_ms is None:
        censored = True
        recovered_ms = int(time.time() * 1000)
        log("  CENSORED: no recovery within %ds of the action" % CENSOR_S)

    # --- derive the incident record from the trace
    window = [s for s in tr.since(onset_ms) if s["t"] <= recovered_ms]
    arrivals, affected = {}, set()
    for s in window:
        for svc in unhealthy(s):
            affected.add(svc)
            arrivals.setdefault(svc, round((s["t"] - onset_ms) / 60000.0, 4))
    rec.update({
        "t_recovered_ms": recovered_ms,
        "duration_s": round((recovered_ms - onset_ms) / 1000.0, 2),
        "duration_min": round((recovered_ms - onset_ms) / 60000.0, 4),
        "tau_min": round((t_action_ms - onset_ms) / 60000.0, 4),
        "affected": sorted(affected), "blast": len(affected),
        "arrivals": arrivals, "censored": censored,
        "sweeps_in_window": len(window),
        "status": "censored" if censored else "ok",
    })
    log("  duration %.1fs  blast=%d  affected=%s%s" % (
        rec["duration_s"], rec["blast"], ",".join(sorted(affected)),
        "  [CENSORED]" if censored else ""))

    reset(origin)
    ok = wait_steady(tr, RESET_WAIT_S)
    rec["reset_ok"] = bool(ok)
    rec["cycle_s"] = round(time.time() - rec["cycle_start"], 1)
    if not ok:
        log("  WARNING: cluster did not return to steady state after reset")
    log("  cycle %.0fs" % rec["cycle_s"])
    return rec


def main():
    os.makedirs(RESULTS, exist_ok=True)
    done = set()
    if os.path.exists(INCIDENTS):
        for line in open(INCIDENTS):
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                pass
    if done:
        log("resuming; already complete: %s" % ",".join(sorted(done)))

    tr = Trace()
    log("waiting for prober stream ...")
    t0 = time.time()
    while tr.latest() is None and time.time() - t0 < 60:
        time.sleep(0.5)
    if tr.latest() is None:
        log("FATAL: no prober data")
        return 1

    t_start = time.time()
    for (iid, fault, origin, action, tau) in PLAN:
        if iid in done:
            continue
        try:
            rec = run_one(tr, iid, fault, origin, action, tau)
        except Exception as ex:
            log("  ERROR in %s: %s" % (iid, ex))
            rec = {"id": iid, "fault": fault, "origin": origin, "action": action,
                   "status": "error", "error": str(ex)}
            try:
                reset(origin)
                wait_steady(tr, RESET_WAIT_S)
            except Exception:
                pass
        with open(INCIDENTS, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    tr.stop = True
    log("V0 complete in %.0f min" % ((time.time() - t_start) / 60.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
