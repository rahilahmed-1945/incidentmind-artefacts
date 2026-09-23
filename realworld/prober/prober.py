"""
1 Hz service-health prober for the IncidentMind fault-injection pilot.

Runs inside the cluster. Once per second it opens a TCP connection to every
Online Boutique service and records success plus connect latency, emitting one
JSON line per sweep on stdout.

OPERATIONAL DEFINITION OF HEALTH
    A service is healthy at time t if a TCP connection to its ClusterIP:port
    completes within TIMEOUT_MS.

    Kubernetes removes a Pod from a Service's endpoint set as soon as its
    readiness probe fails, and every Online Boutique deployment defines a gRPC
    health readiness probe. A connection to the ClusterIP therefore fails once
    the platform itself considers the backend unhealthy, and this signal covers
    hard outages (scale-to-0), crash-looping misconfiguration, and resource
    starvation severe enough to fail the readiness probe.

    It does NOT capture soft degradation -- a service that is slow but still
    passes its readiness probe registers as healthy. That limitation is
    reported rather than worked around; latency-only faults are out of scope
    for this pilot.

FUNCTIONAL PROBING OF THE FRONTEND
    A setup smoke test showed that when a backend fails, its dependants keep
    passing their own readiness probes and therefore remain "healthy" at the
    TCP level, even though they return errors to users. Readiness alone
    consequently cannot observe propagation at all. The frontend is therefore
    additionally probed functionally over HTTP on routes that exercise
    different backends, and is counted unhealthy if TCP fails OR any probed
    route fails. This makes user-visible propagation observable.

    Intermediate gRPC services are still observed only through readiness, so
    propagation *between* backends remains unobservable in this pilot. That is
    reported as a measurement limitation, not worked around.

Output line:
    {"t": <epoch_ms>,
     "r": {"<svc>": [<ok 0|1>, <ms>], ...},
     "h": {"<route>": [<ok 0|1>, <ms>, <status>], ...}}
"""
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

TIMEOUT_MS = int(os.environ.get("PROBE_TIMEOUT_MS", "500"))
PERIOD_S = float(os.environ.get("PROBE_PERIOD_S", "1.0"))

# service -> port, as declared by the pinned v0.10.6 manifest
TARGETS = {
    "adservice": 9555,
    "cartservice": 7070,
    "checkoutservice": 5050,
    "currencyservice": 7000,
    "emailservice": 5000,
    "frontend": 80,
    "paymentservice": 50051,
    "productcatalogservice": 3550,
    "recommendationservice": 8080,
    "redis-cart": 6379,
    "shippingservice": 50051,
}


# frontend routes and the backends each exercises (for the record only)
ROUTES = {
    "/": "productcatalog,currency,ad",
    "/product/OLJCESPC7Z": "productcatalog,recommendation,ad,currency",
    "/cart": "cart,currency,productcatalog,shipping,recommendation",
}
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", "3.0"))


def probe(host, port, timeout_s):
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return 1, round((time.perf_counter() - t0) * 1000.0, 2)
    except Exception:
        return 0, round((time.perf_counter() - t0) * 1000.0, 2)


def probe_http(path):
    url = "http://frontend" + path
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "im-prober/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            code = resp.status
            resp.read(2048)
        ok = 1 if 200 <= code < 400 else 0
        return ok, round((time.perf_counter() - t0) * 1000.0, 2), code
    except urllib.error.HTTPError as e:
        return 0, round((time.perf_counter() - t0) * 1000.0, 2), e.code
    except Exception:
        return 0, round((time.perf_counter() - t0) * 1000.0, 2), 0


def main():
    timeout_s = TIMEOUT_MS / 1000.0
    names = sorted(TARGETS)
    sys.stderr.write("prober up: %d targets, period %.2fs, timeout %dms\n"
                     % (len(names), PERIOD_S, TIMEOUT_MS))
    sys.stderr.flush()
    next_t = time.time()
    while True:
        sweep = {}
        for n in names:
            sweep[n] = probe(n, TARGETS[n], timeout_s)
        http = {p: probe_http(p) for p in ROUTES}
        # the frontend is the one service we can observe functionally: a route
        # failure means users are affected even if its readiness probe passes
        if sweep["frontend"][0] == 1 and any(v[0] == 0 for v in http.values()):
            sweep["frontend"] = [0, sweep["frontend"][1]]
        line = {"t": int(time.time() * 1000), "r": sweep, "h": http}
        sys.stdout.write(json.dumps(line, separators=(",", ":")) + "\n")
        sys.stdout.flush()
        next_t += PERIOD_S
        delay = next_t - time.time()
        if delay > 0:
            time.sleep(delay)
        else:
            next_t = time.time()   # fell behind; resynchronise


if __name__ == "__main__":
    main()
