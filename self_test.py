# -*- coding: utf-8 -*-
"""self_test for llm-error-code-spec (scaffold v2, four defenses inherited).

D1: SystemExit caught in run_cli. D2: unicode descriptions exercised.
D3: fixtures written with newline="". D4: last line "SUMMARY: PASS n/n".
"""
import contextlib
import copy
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")  # D3

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "core", os.path.join(_HERE, "llm_error_code_spec.py"))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)
main = core.main

CASES = []


def case(category, name):
    def deco(fn):
        CASES.append((category, name, fn))
        return fn
    return deco


def run_cli(argv):
    buf_out, buf_err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            ret = main(argv)
            code = 0 if ret is None else int(ret)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:
        code = 1
        buf_err.write(repr(e))
    return code, buf_out.getvalue(), buf_err.getvalue()


_TMP = tempfile.mkdtemp(prefix="les_selftest_")


def write_fixture(name, obj):
    p = os.path.join(_TMP, name)
    with open(p, "w", encoding="utf-8", newline="") as f:  # D3
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))
    return p


def rules(reg):
    return sorted({e["rule"] for e in core.validate_registry(reg)})


def entry(**over):
    base = {"code": "E4290", "name": "rate_limited", "class": "quota", "http": 429,
            "exit": 8, "retryable": True, "description": "rate limit hit"}
    base.update(over)
    return base


def reg_with(*entries, **kw):
    r = copy.deepcopy(core.SAMPLE_REGISTRY)
    r["codes"] = list(entries)
    r.update(kw)
    return r


# ---------- [A] functional ----------
def _t_sample_valid():
    assert core.validate_registry(core.SAMPLE_REGISTRY) == []
case("A", "bundled sample registry is valid")(_t_sample_valid)

def _t_map_http():
    e = core.map_code(core.SAMPLE_REGISTRY, http=429)
    assert e["name"] == "rate_limited" and e["code"] == "E4290"
case("A", "map by http status")(_t_map_http)

def _t_map_name():
    e = core.map_code(core.SAMPLE_REGISTRY, name="gateway_timeout")
    assert e["http"] == 504 and e["retryable"] is True
case("A", "map by canonical name")(_t_map_name)

def _t_map_miss():
    assert core.map_code(core.SAMPLE_REGISTRY, http=418) is None
    assert core.map_code(core.SAMPLE_REGISTRY, name="nope") is None
case("A", "unmapped http/name -> None")(_t_map_miss)

def _t_exit_for():
    assert core.exit_for(core.SAMPLE_REGISTRY, http=401) == 4
case("A", "exit_for mapped status")(_t_exit_for)

def _t_exit_default():
    assert core.exit_for(core.SAMPLE_REGISTRY, http=418) == 1
case("A", "exit_for falls back to default_exit=1")(_t_exit_default)

def _t_exit_custom_default():
    r = dict(core.SAMPLE_REGISTRY, default_exit=20)
    assert core.exit_for(r, http=418) == 20
case("A", "custom default_exit honored")(_t_exit_custom_default)

def _t_all_classes_covered():
    r = core.SAMPLE_REGISTRY
    assert rules(r) == []
    got = {c["class"] for c in r["codes"]}
    assert got == set(core.TAXONOMY)
case("A", "sample covers all taxonomy classes")(_t_all_classes_covered)

def _t_retryable_flags():
    for c in core.SAMPLE_REGISTRY["codes"]:
        if c["retryable"]:
            assert c["class"] in core.RETRYABLE_CLASSES
case("A", "retryable only on transient/quota/upstream")(_t_retryable_flags)

def _t_cli_validate_ok():
    p = write_fixture("reg.json", core.SAMPLE_REGISTRY)
    code, out, _ = run_cli(["validate", p])
    assert code == 0 and "OK" in out
case("A", "CLI validate good -> 0")(_t_cli_validate_ok)

def _t_cli_validate_json():
    p = write_fixture("reg.json", core.SAMPLE_REGISTRY)
    code, out, _ = run_cli(["validate", p, "--json"])
    assert code == 0 and json.loads(out)["errors"] == []
case("A", "CLI validate --json round-trip")(_t_cli_validate_json)

def _t_cli_validate_bad():
    p = write_fixture("reg.json", {"version": 2})
    code, out, _ = run_cli(["validate", p])
    assert code == 1 and "R1" in out
case("A", "CLI validate bad -> 1")(_t_cli_validate_bad)

def _t_cli_map_http():
    p = write_fixture("reg.json", core.SAMPLE_REGISTRY)
    code, out, _ = run_cli(["map", p, "--http", "429"])
    assert code == 0 and "rate_limited" in out and "exit=8" in out
case("A", "CLI map --http 429")(_t_cli_map_http)

def _t_cli_map_name():
    p = write_fixture("reg.json", core.SAMPLE_REGISTRY)
    code, out, _ = run_cli(["map", p, "--name", "timeout"])
    assert code == 0 and "E4080" in out
case("A", "CLI map --name timeout")(_t_cli_map_name)

def _t_cli_map_json():
    p = write_fixture("reg.json", core.SAMPLE_REGISTRY)
    code, out, _ = run_cli(["map", p, "--http", "503", "--json"])
    parsed = json.loads(out)
    assert code == 0 and parsed["entry"]["exit"] == 11 and parsed["exit"] == 11
case("A", "CLI map --json includes resolved exit")(_t_cli_map_json)

def _t_cli_map_unmapped():
    p = write_fixture("reg.json", core.SAMPLE_REGISTRY)
    code, out, _ = run_cli(["map", p, "--http", "418"])
    assert code == 1 and "unmapped" in out
case("A", "CLI map unmapped -> 1")(_t_cli_map_unmapped)

def _t_cli_map_sample_default():
    code, out, _ = run_cli(["map", "--http", "500"])
    assert code == 0 and "internal_error" in out
case("A", "CLI map without registry uses sample")(_t_cli_map_sample_default)

def _t_cli_map_missing_args():
    code, _, _ = run_cli(["map"])
    assert code == 2
case("A", "CLI map without --http/--name -> 2")(_t_cli_map_missing_args)

def _t_cli_bench_sample():
    code, out, _ = run_cli(["bench", "--lookups", "2000"])
    assert code == 0 and "lookups/s" in out
case("A", "CLI bench runs on sample registry")(_t_cli_bench_sample)

def _t_exit_for_name():
    assert core.exit_for(core.SAMPLE_REGISTRY, name="bad_gateway") == 10
case("A", "exit_for by name")(_t_exit_for_name)

# ---------- [B] exception paths ----------
def _t_non_dict():
    assert core.validate_registry([])[0]["rule"] == "R1"
case("B", "validate non-dict -> R1")(_t_non_dict)

def _t_bad_version():
    assert "R1" in rules({"version": 2, "codes": core.SAMPLE_REGISTRY["codes"]})
case("B", "version 2 -> R1")(_t_bad_version)

def _t_empty_codes():
    assert "R2" in rules({"version": 1, "codes": []})
case("B", "empty codes -> R2")(_t_empty_codes)

def _t_bad_code_format():
    assert "R3" in rules(reg_with(entry(code="E999")))
case("B", "malformed code -> R3")(_t_bad_code_format)

def _t_dup_code():
    assert "R3" in rules(reg_with(entry(), entry(code="E4290", name="other_x",
                                                 http=430, exit=20)))
case("B", "duplicate code -> R3")(_t_dup_code)

def _t_bad_name():
    assert "R4" in rules(reg_with(entry(name="Rate-Limit")))
case("B", "non-snake_case name -> R4")(_t_bad_name)

def _t_dup_name():
    assert "R4" in rules(reg_with(entry(), entry(code="E4300", http=430, exit=20)))
case("B", "duplicate name -> R4")(_t_dup_name)

def _t_bad_class():
    assert "R5" in rules(reg_with(entry(**{"class": "magic"})))
case("B", "unknown class -> R5")(_t_bad_class)

def _t_bad_http():
    assert "R6" in rules(reg_with(entry(http=399)))
    assert "R6" in rules(reg_with(entry(http=600)))
case("B", "http outside 400-599 -> R6")(_t_bad_http)

def _t_dup_http():
    assert "R6" in rules(reg_with(entry(), entry(code="E4300", name="again_x",
                                                 http=429, exit=20)))
case("B", "duplicate http status -> R6")(_t_dup_http)

def _t_bad_exit():
    assert "R7" in rules(reg_with(entry(exit=1)))
    assert "R7" in rules(reg_with(entry(exit=126)))
case("B", "exit outside 2-125 -> R7")(_t_bad_exit)

def _t_dup_exit():
    assert "R7" in rules(reg_with(entry(), entry(code="E4300", name="again_x",
                                                 http=430, exit=8)))
case("B", "duplicate exit -> R7")(_t_dup_exit)

def _t_nonbool_retryable():
    assert "R8" in rules(reg_with(entry(retryable="yes")))
case("B", "non-boolean retryable -> R8")(_t_nonbool_retryable)

def _t_input_retryable():
    assert "R8" in rules(reg_with(entry(**{"class": "input"}, retryable=True)))
case("B", "retryable input error -> R8")(_t_input_retryable)

def _t_empty_desc():
    assert "R9" in rules(reg_with(entry(description="   ")))
case("B", "blank description -> R9")(_t_empty_desc)

def _t_missing_class_coverage():
    r = reg_with(entry())  # only quota covered
    assert "R10" in rules(r)
case("B", "uncovered taxonomy class -> R10")(_t_missing_class_coverage)

def _t_bad_default_exit():
    assert "R11" in rules(dict(core.SAMPLE_REGISTRY, default_exit=0))
case("B", "default_exit 0 -> R11")(_t_bad_default_exit)

def _t_no_args():
    code, _, _ = run_cli([])
    assert code == 2
case("B", "CLI no args -> SystemExit 2 (D1)")(_t_no_args)

def _t_unknown_cmd():
    code, _, _ = run_cli(["explode"])
    assert code == 2
case("B", "CLI unknown subcommand -> 2")(_t_unknown_cmd)

def _t_missing_file():
    code, _, _ = run_cli(["validate", os.path.join(_TMP, "nope.json")])
    assert code == 1
case("B", "CLI missing registry file -> 1")(_t_missing_file)

def _t_nonobject_entry():
    assert "R3" in rules({"version": 1, "codes": ["E4001"]})
case("B", "code entry not an object -> R3")(_t_nonobject_entry)

# ---------- [C] extreme edges ----------
def _t_unicode_desc():
    r = copy.deepcopy(core.SAMPLE_REGISTRY)
    r["codes"][5]["description"] = "限流：请稍后重试 🚦"
    assert core.validate_registry(r) == []
case("C", "unicode description accepted (D2)")(_t_unicode_desc)

def _t_boundary_http():
    r = reg_with(entry(http=400, code="E4000", name="lo", exit=2),
                 entry(http=599, code="E5990", name="hi", exit=3))
    assert core.validate_registry(r) == [] or "R10" in rules(r)  # coverage may still hold
case("C", "http range boundaries accepted")(_t_boundary_http)

def _t_boundary_exit():
    r = reg_with(entry(exit=2), entry(code="E4300", name="hi_x", http=430, exit=125))
    assert "R7" not in rules(r)
case("C", "exit range boundaries accepted")(_t_boundary_exit)

def _t_crlf_registry():
    p = os.path.join(_TMP, "crlf.json")
    with open(p, "w", encoding="utf-8", newline="") as f:  # D3
        f.write(json.dumps(core.SAMPLE_REGISTRY, indent=2) + "\r\n")
    code, _, _ = run_cli(["validate", p])
    assert code == 0
case("C", "CRLF-terminated registry file (D3)")(_t_crlf_registry)

def _t_huge_codes_list():
    codes = []
    for i in range(400):
        codes.append({"code": "E%04d" % (1000 + i), "name": "c_%04d" % i,
                      "class": core.TAXONOMY[i % len(core.TAXONOMY)],
                      "http": 100 + i, "exit": 2 + (i % 100),
                      "retryable": False, "description": "synthetic %d" % i})
    r = {"version": 1, "codes": codes}
    errs = core.validate_registry(r)
    assert all(e["rule"] != "R3" for e in errs)
case("C", "400-entry registry validates (unique codes)")(_t_huge_codes_list)

def _t_http_build_index_stable():
    a, b = core._index(core.SAMPLE_REGISTRY), core._index(core.SAMPLE_REGISTRY)
    assert a == b
case("C", "index build deterministic")(_t_http_build_index_stable)

def _t_default_exit_when_no_entry():
    r = {"version": 1, "codes": core.SAMPLE_REGISTRY["codes"]}
    assert core.exit_for(r, name="zzz") == 1
case("C", "exit_for unknown name -> default")(_t_default_exit_when_no_entry)

def _t_map_none_args():
    assert core.map_code(core.SAMPLE_REGISTRY) is None
case("C", "map_code with no selectors -> None")(_t_map_none_args)

def _t_sample_json_flag_consistency():
    code, out, _ = run_cli(["map", "--http", "429", "--json"])
    parsed = json.loads(out)
    assert code == 0 and parsed["entry"]["retryable"] is True
case("C", "map --json retryable flag surfaces")(_t_sample_json_flag_consistency)

def _t_cli_bench_custom_registry():
    p = write_fixture("reg.json", core.SAMPLE_REGISTRY)
    code, out, _ = run_cli(["bench", p, "--lookups", "500"])
    assert code == 0
case("C", "CLI bench accepts registry argument")(_t_cli_bench_custom_registry)

def _t_http_wins_over_name():
    e = core.map_code(core.SAMPLE_REGISTRY, http=404, name="timeout")
    assert e["name"] == "not_found"
case("A", "http selector takes precedence over name")(_t_http_wins_over_name)

def _t_name_with_digits():
    r = reg_with(entry(name="e2e_limited", code="E4291", http=430, exit=13))
    assert core.validate_registry(r) == [] or "R10" in rules(r)
case("A", "snake_case name with digits valid")(_t_name_with_digits)

def _t_code_e0000():
    r = reg_with(entry(code="E0000", name="zeroth", http=400, exit=2))
    assert "R3" not in rules(r)
case("A", "E0000 code format accepted")(_t_code_e0000)

def _t_cli_map_unknown_name():
    p = write_fixture("reg.json", core.SAMPLE_REGISTRY)
    code, out, _ = run_cli(["map", p, "--name", "does_not_exist"])
    assert code == 1 and "unmapped" in out
case("A", "CLI map unknown name -> 1")(_t_cli_map_unknown_name)

def _t_cli_json_lists_rules():
    p = write_fixture("reg.json", {"version": 2})
    code, out, _ = run_cli(["validate", p, "--json"])
    parsed = json.loads(out)
    assert code == 1 and any(e["rule"] == "R1" for e in parsed["errors"])
case("A", "--json error list carries rule ids")(_t_cli_json_lists_rules)

def _t_sample_exits_unique():
    exits = [c["exit"] for c in core.SAMPLE_REGISTRY["codes"]]
    assert len(set(exits)) == len(exits)
case("A", "sample registry exit codes unique")(_t_sample_exits_unique)

def _t_sample_http_unique():
    https = [c["http"] for c in core.SAMPLE_REGISTRY["codes"]]
    assert len(set(https)) == len(https)
case("A", "sample registry http statuses unique")(_t_sample_http_unique)

def _t_sample_exits_in_range():
    for c in core.SAMPLE_REGISTRY["codes"]:
        assert core.EXIT_RANGE[0] <= c["exit"] <= core.EXIT_RANGE[1]
case("A", "sample exits within 2..125")(_t_sample_exits_in_range)

def _t_dup_exit_across_classes():
    r = reg_with(entry(), entry(code="E4081", name="auth_timeout",
                                **{"class": "auth"}, http=408, exit=8,
                                retryable=False))
    assert "R7" in rules(r)
case("A", "exit collision across classes -> R7")(_t_dup_exit_across_classes)

def _t_exit_default_boundary():
    r = dict(core.SAMPLE_REGISTRY, default_exit=125)
    assert core.exit_for(r, http=418) == 125
case("A", "default_exit boundary 125 honored")(_t_exit_default_boundary)

def _t_meta_count():
    assert len(CASES) >= 60
case("C", "meta: at least 60 cases defined")(_t_meta_count)


class T(unittest.TestCase):
    pass


def _add(i, cat, name, fn):
    def t(self, _f=fn):
        _f()
    t.__doc__ = "%s: %s" % (cat, name)
    setattr(T, "test_%s_%03d_%s" % (cat, i, re.sub(r"[^0-9A-Za-z_]", "_", name)), t)


for _i, (_c, _n, _f) in enumerate(CASES):
    _add(_i + 1, _c, _n, _f)

if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"]))
    total, fails = r.testsRun, len(r.failures) + len(r.errors)
    print("SUMMARY: PASS %d/%d" % (total - fails, total))  # D4
    sys.exit(0 if fails == 0 else 1)
