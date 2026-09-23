"""
Compare two results.json files produced by experiments.py.

Wall-clock fields are excluded, since they legitimately differ between runs and
machines. Everything else -- every reported metric -- must match exactly.

Usage:  python compare_runs.py reference.json candidate.json
"""
import json
import sys

# measured wall-clock quantities; not reproducible by construction
TIMING_KEYS = {"eval_seconds", "runtime_seconds", "index_build_s",
               "ms_per_query", "ms_per_traversal", "ms_unbounded"}


def walk(a, b, path=""):
    diffs = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in TIMING_KEYS:
                continue
            if k not in a:
                diffs.append((path + "/" + str(k), "<absent>", b[k]))
            elif k not in b:
                diffs.append((path + "/" + str(k), a[k], "<absent>"))
            else:
                diffs += walk(a[k], b[k], path + "/" + str(k))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append((path, "len=%d" % len(a), "len=%d" % len(b)))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                diffs += walk(x, y, path + "[%d]" % i)
    elif isinstance(a, float) or isinstance(b, float):
        try:
            if float(a) != float(b):
                diffs.append((path, a, b))
        except (TypeError, ValueError):
            diffs.append((path, a, b))
    elif a != b:
        diffs.append((path, a, b))
    return diffs


def count_leaves(o):
    if isinstance(o, dict):
        return sum(count_leaves(v) for k, v in o.items() if k not in TIMING_KEYS)
    if isinstance(o, list):
        return sum(count_leaves(v) for v in o)
    return 1


if __name__ == "__main__":
    ref = json.load(open(sys.argv[1], encoding="utf-8"))
    cand = json.load(open(sys.argv[2], encoding="utf-8"))
    diffs = walk(ref, cand)
    n = count_leaves(ref)
    print("compared {} non-timing values".format(n))
    if not diffs:
        print("IDENTICAL: every reported value reproduces exactly")
        sys.exit(0)
    print("\n{} DIFFERENCE(S):".format(len(diffs)))
    for p, a, b in diffs[:60]:
        print("  {}\n     reference: {}\n     candidate: {}".format(p, a, b))
    sys.exit(1)
