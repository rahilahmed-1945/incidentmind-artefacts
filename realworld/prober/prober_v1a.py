"""
V1a observability instrument for the IncidentMind fault-injection testbed.

V0 showed that readiness/TCP probing at 1 Hz cannot observe propagation: every
measured per-service arrival offset was exactly zero, and dependants stayed
"healthy" because their own readiness probes kept passing while they returned
errors. This instrument replaces that with tiered probing that separates five
distinct health levels and samples fast enough to resolve sub-second ordering.

LEVELS OBSERVED
  L1 reachable   TCP connect to the Service ClusterIP succeeds
                 -> the endpoint exists and something is listening
  L2 functional  a gRPC/HTTP call to the service's OWN api succeeds
                 -> the process is serving its own contract
  L3 dependency  a call that forces the service to call ITS dependencies
                 succeeds -> the dependency chain below it is intact
  L4 uservisible a frontend HTTP route returns 2xx
                 -> the user-facing path works
  (process liveness is sampled separately from the Kubernetes API by the
   orchestrator, at low rate, and recorded alongside these observations)

Each probe class runs in its own thread at its own rate, so an expensive deep
call cannot throttle the cheap fast ones. Every observation is emitted as a
raw timestamped event; nothing is aggregated or inferred in the prober.

Event: {"t": <epoch_ms>, "k": <level>, "n": <target>, "ok": 0|1,
        "ms": <latency>, "e": <short error>}
"""
import json
import os
import queue
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

import grpc

sys.path.insert(0, "/opt/prober/gen")
import demo_pb2        # noqa: E402
import demo_pb2_grpc   # noqa: E402

TCP_HZ = float(os.environ.get("TCP_HZ", "10"))
FUNC_HZ = float(os.environ.get("FUNC_HZ", "5"))
DEP_HZ = float(os.environ.get("DEP_HZ", "2"))
HTTP_HZ = float(os.environ.get("HTTP_HZ", "2"))
GRPC_TIMEOUT_S = float(os.environ.get("GRPC_TIMEOUT_S", "2.0"))
TCP_TIMEOUT_S = float(os.environ.get("TCP_TIMEOUT_S", "0.4"))
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", "3.0"))

PORTS = {
    "adservice": 9555, "cartservice": 7070, "checkoutservice": 5050,
    "currencyservice": 7000, "emailservice": 5000, "frontend": 80,
    "paymentservice": 50051, "productcatalogservice": 3550,
    "recommendationservice": 8080, "redis-cart": 6379, "shippingservice": 50051,
}

OUT = queue.Queue(maxsize=200000)


def emit(kind, name, ok, ms, err=""):
    try:
        OUT.put_nowait({"t": int(time.time() * 1000), "k": kind, "n": name,
                        "ok": int(ok), "ms": round(ms, 2), "e": err[:40]})
    except queue.Full:
        pass


def writer():
    while True:
        ev = OUT.get()
        sys.stdout.write(json.dumps(ev, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def ticker(hz, fn, label):
    """Run fn() at hz, resynchronising if it falls behind."""
    period = 1.0 / hz
    nxt = time.time()
    while True:
        try:
            fn()
        except Exception as ex:
            emit("err", label, 0, 0.0, repr(ex))
        nxt += period
        d = nxt - time.time()
        if d > 0:
            time.sleep(d)
        else:
            nxt = time.time()


# ------------------------------------------------------------------ L1 TCP
def tcp_sweep():
    for name, port in PORTS.items():
        t0 = time.perf_counter()
        try:
            with socket.create_connection((name, port), timeout=TCP_TIMEOUT_S):
                emit("reachable", name, 1, (time.perf_counter() - t0) * 1000)
        except Exception as ex:
            emit("reachable", name, 0, (time.perf_counter() - t0) * 1000,
                 type(ex).__name__)


# ------------------------------------------------------- gRPC channels/stubs
CH = {}


def chan(name):
    if name not in CH:
        CH[name] = grpc.insecure_channel("%s:%d" % (name, PORTS[name]))
    return CH[name]


ADDRESS = demo_pb2.Address(street_address="1600 Amphitheatre Parkway",
                           city="Mountain View", state="CA", country="USA",
                           zip_code=94043)
CARD = demo_pb2.CreditCardInfo(credit_card_number="4432-8015-6152-0454",
                               credit_card_cvv=672,
                               credit_card_expiration_year=2039,
                               credit_card_expiration_month=1)


def _call(kind, name, fn):
    t0 = time.perf_counter()
    try:
        fn()
        emit(kind, name, 1, (time.perf_counter() - t0) * 1000)
    except grpc.RpcError as e:
        emit(kind, name, 0, (time.perf_counter() - t0) * 1000, e.code().name)
    except Exception as ex:
        emit(kind, name, 0, (time.perf_counter() - t0) * 1000, type(ex).__name__)


# ---- L2: each service's own contract, no downstream dependency
def func_sweep():
    _call("functional", "productcatalogservice", lambda: demo_pb2_grpc
          .ProductCatalogServiceStub(chan("productcatalogservice"))
          .ListProducts(demo_pb2.Empty(), timeout=GRPC_TIMEOUT_S))
    _call("functional", "currencyservice", lambda: demo_pb2_grpc
          .CurrencyServiceStub(chan("currencyservice"))
          .GetSupportedCurrencies(demo_pb2.Empty(), timeout=GRPC_TIMEOUT_S))
    _call("functional", "adservice", lambda: demo_pb2_grpc
          .AdServiceStub(chan("adservice"))
          .GetAds(demo_pb2.AdRequest(context_keys=["clothing"]),
                  timeout=GRPC_TIMEOUT_S))
    _call("functional", "shippingservice", lambda: demo_pb2_grpc
          .ShippingServiceStub(chan("shippingservice"))
          .GetQuote(demo_pb2.GetQuoteRequest(
              address=ADDRESS,
              items=[demo_pb2.CartItem(product_id="OLJCESPC7Z", quantity=1)]),
              timeout=GRPC_TIMEOUT_S))
    _call("functional", "paymentservice", lambda: demo_pb2_grpc
          .PaymentServiceStub(chan("paymentservice"))
          .Charge(demo_pb2.ChargeRequest(
              amount=demo_pb2.Money(currency_code="USD", units=1, nanos=0),
              credit_card=CARD), timeout=GRPC_TIMEOUT_S))
    _call("functional", "emailservice", lambda: demo_pb2_grpc
          .EmailServiceStub(chan("emailservice"))
          .SendOrderConfirmation(demo_pb2.SendOrderConfirmationRequest(
              email="probe@example.com",
              order=demo_pb2.OrderResult(
                  order_id="probe", shipping_tracking_id="t",
                  shipping_cost=demo_pb2.Money(currency_code="USD", units=1),
                  shipping_address=ADDRESS, items=[])),
              timeout=GRPC_TIMEOUT_S))


# ---- L3: calls that force the service to exercise its dependencies
def dep_sweep():
    # cartservice -> redis-cart
    _call("dependency", "cartservice", lambda: demo_pb2_grpc
          .CartServiceStub(chan("cartservice"))
          .GetCart(demo_pb2.GetCartRequest(user_id="probe-user"),
                   timeout=GRPC_TIMEOUT_S))
    # recommendationservice -> productcatalogservice
    _call("dependency", "recommendationservice", lambda: demo_pb2_grpc
          .RecommendationServiceStub(chan("recommendationservice"))
          .ListRecommendations(demo_pb2.ListRecommendationsRequest(
              user_id="probe-user", product_ids=["OLJCESPC7Z"]),
              timeout=GRPC_TIMEOUT_S))
    # checkoutservice -> cart, catalog, currency, shipping, payment, email
    _call("dependency", "checkoutservice", lambda: demo_pb2_grpc
          .CheckoutServiceStub(chan("checkoutservice"))
          .PlaceOrder(demo_pb2.PlaceOrderRequest(
              user_id="probe-user", user_currency="USD", address=ADDRESS,
              email="probe@example.com", credit_card=CARD),
              timeout=GRPC_TIMEOUT_S))


# ---- L4: user-visible frontend routes
ROUTES = ["/", "/product/OLJCESPC7Z", "/cart"]


def http_sweep():
    for path in ROUTES:
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request("http://frontend" + path,
                                         headers={"User-Agent": "im-prober/1a"})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
                code = r.status
                r.read(2048)
            emit("uservisible", path, 1 if 200 <= code < 400 else 0,
                 (time.perf_counter() - t0) * 1000, str(code))
        except urllib.error.HTTPError as e:
            emit("uservisible", path, 0, (time.perf_counter() - t0) * 1000,
                 str(e.code))
        except Exception as ex:
            emit("uservisible", path, 0, (time.perf_counter() - t0) * 1000,
                 type(ex).__name__)


def main():
    sys.stderr.write("v1a prober: tcp=%.0fHz func=%.0fHz dep=%.0fHz http=%.0fHz\n"
                     % (TCP_HZ, FUNC_HZ, DEP_HZ, HTTP_HZ))
    sys.stderr.flush()
    threading.Thread(target=writer, daemon=True).start()
    for hz, fn, lbl in ((TCP_HZ, tcp_sweep, "tcp"), (FUNC_HZ, func_sweep, "func"),
                        (DEP_HZ, dep_sweep, "dep"), (HTTP_HZ, http_sweep, "http")):
        threading.Thread(target=ticker, args=(hz, fn, lbl), daemon=True).start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
