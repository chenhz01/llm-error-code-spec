# -*- coding: utf-8 -*-
"""llm-error-code-spec: LLM gateway error taxonomy + exit-code mapping +
registry consistency tests.

Pure standard library. CLI via argparse.
Exit codes of this tool: 0 ok, 1 validation failure / unmapped error,
2 usage error (argparse).
"""
import argparse
import json
import re
import sys
import time

TAXONOMY = ("auth", "quota", "transient", "input", "upstream", "internal")
RETRYABLE_CLASSES = ("transient", "quota", "upstream")
CODE_RE = re.compile(r"^E\d{4}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
HTTP_RANGE = (400, 599)
EXIT_RANGE = (2, 125)


def validate_registry(reg):
    """Validate an error-code registry dict. Returns list of
    {rule, path, message}; empty = valid."""
    errs = []

    def err(rule, path, msg):
        errs.append({"rule": rule, "path": path, "message": msg})

    if not isinstance(reg, dict):
        err("R1", "$", "registry must be a JSON object")
        return errs
    if reg.get("version") != 1:
        err("R1", "$.version", "version must be 1")
    codes = reg.get("codes")
    if not isinstance(codes, list) or not codes:
        err("R2", "$.codes", "codes must be a non-empty array")
        return errs
    seen_code, seen_name, seen_http, seen_exit = set(), set(), set(), set()
    classes_hit = set()
    for i, c in enumerate(codes):
        path = "$.codes[%d]" % i
        if not isinstance(c, dict):
            err("R3", path, "code entry must be an object")
            continue
        code = c.get("code")
        if not isinstance(code, str) or not CODE_RE.match(code):
            err("R3", path + ".code", "code must match E\\d{4}")
        elif code in seen_code:
            err("R3", path + ".code", "duplicate code %s" % code)
        else:
            seen_code.add(code)
        name = c.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            err("R4", path + ".name", "name must be snake_case")
        elif name in seen_name:
            err("R4", path + ".name", "duplicate name %s" % name)
        else:
            seen_name.add(name)
        cls = c.get("class")
        if cls not in TAXONOMY:
            err("R5", path + ".class", "class must be one of %s" % (", ".join(TAXONOMY),))
        else:
            classes_hit.add(cls)
        http = c.get("http")
        if isinstance(http, bool) or not isinstance(http, int) \
                or not (HTTP_RANGE[0] <= http <= HTTP_RANGE[1]):
            err("R6", path + ".http", "http must be an int in [%d, %d]" % HTTP_RANGE)
        elif http in seen_http:
            err("R6", path + ".http", "duplicate http status %d" % http)
        else:
            seen_http.add(http)
        exitc = c.get("exit")
        if isinstance(exitc, bool) or not isinstance(exitc, int) \
                or not (EXIT_RANGE[0] <= exitc <= EXIT_RANGE[1]):
            err("R7", path + ".exit", "exit must be an int in [%d, %d]" % EXIT_RANGE)
        elif exitc in seen_exit:
            err("R7", path + ".exit", "duplicate exit code %d" % exitc)
        else:
            seen_exit.add(exitc)
        retryable = c.get("retryable")
        if not isinstance(retryable, bool):
            err("R8", path + ".retryable", "retryable must be a boolean")
        elif retryable and cls in TAXONOMY and cls not in RETRYABLE_CLASSES:
            err("R8", path + ".retryable",
                "class %s is never retryable" % cls)
        desc = c.get("description")
        if not isinstance(desc, str) or not desc.strip():
            err("R9", path + ".description", "description must be a non-empty string")
    for cls in TAXONOMY:
        if cls not in classes_hit:
            err("R10", "$.codes", "taxonomy class %r has no code" % cls)
    de = reg.get("default_exit", 1)
    if isinstance(de, bool) or not isinstance(de, int) \
            or not (1 <= de <= EXIT_RANGE[1]):
        err("R11", "$.default_exit", "default_exit must be an int in [1, %d]" % EXIT_RANGE[1])
    return errs


def _index(reg):
    """Build {http: entry} and {name: entry} lookup tables."""
    by_http, by_name = {}, {}
    for c in reg.get("codes", []):
        if isinstance(c, dict):
            if isinstance(c.get("http"), int):
                by_http[c["http"]] = c
            if isinstance(c.get("name"), str):
                by_name[c["name"]] = c
    return by_http, by_name


def map_code(reg, http=None, name=None):
    """Map an HTTP status or canonical name to a registry entry (or None)."""
    by_http, by_name = _index(reg)
    if http is not None:
        return by_http.get(http)
    if name is not None:
        return by_name.get(name)
    return None


def exit_for(reg, http=None, name=None):
    """Exit code for a given error; falls back to default_exit (default 1)."""
    entry = map_code(reg, http=http, name=name)
    if entry is not None and isinstance(entry.get("exit"), int):
        return entry["exit"]
    de = reg.get("default_exit", 1) if isinstance(reg, dict) else 1
    return de


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_validate(args):
    errs = validate_registry(_load(args.registry))
    if args.json:
        print(json.dumps({"errors": errs}, ensure_ascii=False, indent=2))
    else:
        for e in errs:
            print("%s %s: %s" % (e["rule"], e["path"], e["message"]))
        print("OK" if not errs else "%d error(s)" % len(errs))
    return 1 if errs else 0


def cmd_map(args):
    reg = _load(args.registry) if args.registry else SAMPLE_REGISTRY
    if args.http is None and args.name is None:
        print("provide --http or --name", file=sys.stderr)
        return 2
    entry = map_code(reg, http=args.http, name=args.name)
    if args.json:
        print(json.dumps({"entry": entry, "exit": exit_for(reg, http=args.http,
                                                            name=args.name)},
                         ensure_ascii=False, indent=2))
        return 0
    if entry is None:
        print("unmapped error")
        return 1
    print("%s %s class=%s http=%d exit=%d retryable=%s"
          % (entry["code"], entry["name"], entry["class"], entry["http"],
             entry["exit"], entry["retryable"]))
    return 0


def cmd_bench(args):
    reg = _load(args.registry) if args.registry else SAMPLE_REGISTRY
    t0 = time.perf_counter()
    hits = 0
    for i in range(args.lookups):
        if map_code(reg, http=HTTP_RANGE[0] + (i % 200)) is not None:
            hits += 1
    dt = time.perf_counter() - t0
    print("bench: %d lookups in %.3fs (%.0f lookups/s, %d hits)"
          % (args.lookups, dt, args.lookups / dt if dt > 0 else 0, hits))
    return 0


SAMPLE_REGISTRY = {
    "version": 1, "default_exit": 1,
    "codes": [
        {"code": "E4001", "name": "bad_request", "class": "input", "http": 400,
         "exit": 2, "retryable": False, "description": "malformed request"},
        {"code": "E4010", "name": "unauthorized", "class": "auth", "http": 401,
         "exit": 4, "retryable": False, "description": "missing or invalid credential"},
        {"code": "E4030", "name": "forbidden", "class": "auth", "http": 403,
         "exit": 5, "retryable": False, "description": "credential lacks scope"},
        {"code": "E4040", "name": "not_found", "class": "input", "http": 404,
         "exit": 6, "retryable": False, "description": "unknown resource"},
        {"code": "E4080", "name": "timeout", "class": "transient", "http": 408,
         "exit": 7, "retryable": True, "description": "upstream timed out"},
        {"code": "E4290", "name": "rate_limited", "class": "quota", "http": 429,
         "exit": 8, "retryable": True, "description": "quota or rate limit hit"},
        {"code": "E5000", "name": "internal_error", "class": "internal", "http": 500,
         "exit": 9, "retryable": False, "description": "unexpected gateway failure"},
        {"code": "E5020", "name": "bad_gateway", "class": "upstream", "http": 502,
         "exit": 10, "retryable": True, "description": "upstream returned garbage"},
        {"code": "E5030", "name": "service_unavailable", "class": "upstream", "http": 503,
         "exit": 11, "retryable": True, "description": "upstream temporarily down"},
        {"code": "E5040", "name": "gateway_timeout", "class": "upstream", "http": 504,
         "exit": 12, "retryable": True, "description": "upstream accept timed out"}]}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="llm-error-code-spec",
        description="LLM gateway error taxonomy + exit-code mapping + registry "
                    "consistency test suite.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="validate a registry JSON file")
    v.add_argument("registry")
    v.add_argument("--json", action="store_true")
    v.set_defaults(fn=cmd_validate)
    m = sub.add_parser("map", help="map an HTTP status / name to a canonical code")
    m.add_argument("registry", nargs="?", help="registry JSON (optional; sample used)")
    m.add_argument("--http", type=int)
    m.add_argument("--name")
    m.add_argument("--json", action="store_true")
    m.set_defaults(fn=cmd_map)
    b = sub.add_parser("bench", help="synthetic benchmark")
    b.add_argument("registry", nargs="?")
    b.add_argument("--lookups", type=int, default=100000)
    b.set_defaults(fn=cmd_bench)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
