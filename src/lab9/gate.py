"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    from lab9.eval import aggregate
    from lab9.graders import GRADERS

    problems: list[str] = []
    man, bman = pr.get("manifest") or {}, base.get("manifest") or {}
    rows, brows = pr.get("rows") or [], base.get("rows") or []

    # 1. Metric values must be real numbers: NaN/inf compare False against every threshold.
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (not a finite number)")

    # 2. Grader crashes: a crashed grader turns into None and silently drops out of the mean.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    missing = [(r.get("item_id"), r.get("seed"), m) for r in rows for m in graded
               if not isinstance(r.get(m), bool)]
    if missing:
        problems.append(f"{len(missing)} row value(s) are not a grader verdict (None/missing/non-bool), "
                        f"first {missing[0]}")

    # 3. Coverage: every (item, seed) exactly once, the same set as the baseline.
    seeds = man.get("seeds") or []
    want = (man.get("items") or 0) * len(seeds)
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(seeds)} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    seen: set = set()
    dups = []
    for k in keys:
        if k in seen:
            dups.append(k)
        seen.add(k)
    if dups:
        problems.append(f"{len(dups)} duplicated (item, seed) row(s), first {dups[0]}")
    bkeys = {(r.get("item_id"), r.get("seed")) for r in brows}
    if seen != bkeys:
        gone, extra = bkeys - seen, seen - bkeys
        problems.append(f"(item, seed) set differs from the baseline: {len(gone)} missing, {len(extra)} extra")
    if sorted(seeds) != sorted(bman.get("seeds") or []) or man.get("items") != bman.get("items"):
        problems.append(f"manifest {man.get('items')} items / seeds {seeds} differs from the baseline's "
                        f"{bman.get('items')} items / seeds {bman.get('seeds')}")
    if {r.get("seed") for r in rows} - set(seeds):
        problems.append("rows carry seeds that the manifest does not list")

    # 4. Slice tags come from the label; relabelling an item out of a slice hides its regression.
    tags = {r.get("item_id"): sorted(r.get("slices") or []) for r in brows}
    own: dict = {}
    for r in rows:
        own.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
    moved = sorted((i for i, t in own.items() if i in tags and t != {tuple(tags[i])}), key=str)
    if moved:
        problems.append(f"slice tags differ from the baseline for {len(moved)} item(s), first {moved[0]}")

    # 5. The headline numbers must be what the rows say (a hand-edited metrics block).
    if rows and not missing:
        ids = [m for m in graded if m in (pr.get("metrics") or {})]
        try:
            again = aggregate([{**r, "cost": r.get("cost", 0.0)} for r in rows], ids,
                              k_values=spec.get("pass_k", []))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"cannot recompute metrics from rows: {exc}")
            again = {}
        for k, v in again.items():
            if k == "cost_per_success" or k not in (pr.get("metrics") or {}):
                continue
            got = pr["metrics"][k]
            if (v is None) != (got is None):
                problems.append(f"metric {k} = {got} but its rows give {v}")
            elif v is not None and isinstance(got, (int, float)) and abs(float(v) - float(got)) > 1e-3:
                problems.append(f"metric {k} = {got} but its rows give {v}")

    # 6. Every blocking spec metric the baseline measured must be measured on the PR too.
    for m in spec.get("metrics", []):
        if (m.get("blocking") and (base.get("metrics") or {}).get(m["id"]) is not None
                and (pr.get("metrics") or {}).get(m["id"]) is None):
            problems.append(f"blocking metric {m['id']} is missing from the PR report")

    if base_spec is not None:
        problems += ratchet_problems(spec, base_spec)
    return problems


def _looser(th: dict, bth: dict) -> list[str]:
    out = []
    if "min" in bth and ("min" not in th or th["min"] < bth["min"]):
        out.append(f"min {bth['min']} -> {th.get('min')}")
    for key in ("max", "max_increase"):
        if key in bth and (key not in th or th[key] > bth[key]):
            out.append(f"{key} {bth[key]} -> {th.get(key)}")
    if bth.get("no_significant_drop") and not th.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    return out


def ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    """Same eval set => thresholds may only get stricter. Bumping eval_set_version while keeping the
    same eval set file is still the same eval set, so the ratchet applies."""
    same_set = (spec.get("eval_set_version") == base_spec.get("eval_set_version")
                or spec.get("eval_set") == base_spec.get("eval_set"))
    if not same_set:
        return []
    probs: list[str] = []
    cur = {m["id"]: m for m in spec.get("metrics", [])}
    for bm in base_spec.get("metrics", []):
        m = cur.get(bm["id"])
        if m is None:
            probs.append(f"RATCHET metric {bm['id']} removed from the spec")
            continue
        if bm.get("blocking") and not m.get("blocking"):
            probs.append(f"RATCHET metric {bm['id']} no longer blocking")
        for d in _looser(m.get("threshold") or {}, bm.get("threshold") or {}):
            probs.append(f"RATCHET metric {bm['id']} looser: {d}")
    cur_sl = {(x.get("name"), x.get("metric")): x for x in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        key = (bs.get("name"), bs.get("metric"))
        x = cur_sl.get(key)
        if x is None:
            probs.append(f"RATCHET slice {key[0]}/{key[1]} removed from the spec")
            continue
        if bs.get("blocking") and not x.get("blocking"):
            probs.append(f"RATCHET slice {key[0]}/{key[1]} no longer blocking")
        for d in _looser(x, bs):
            probs.append(f"RATCHET slice {key[0]}/{key[1]} looser: {d}")
    if sorted(spec.get("seeds") or []) != sorted(base_spec.get("seeds") or []):
        probs.append(f"RATCHET seeds changed {base_spec.get('seeds')} -> {spec.get('seeds')}")
    if base_spec.get("adversarial_pack") and spec.get("adversarial_pack") != base_spec.get("adversarial_pack"):
        probs.append("RATCHET adversarial_pack removed or changed")
    bb, cb = base_spec.get("bootstrap") or {}, spec.get("bootstrap") or {}
    if cb.get("confidence", 0.95) > bb.get("confidence", 0.95):
        probs.append(f"RATCHET bootstrap confidence {bb.get('confidence')} -> {cb.get('confidence')} (wider CI)")
    for k in sorted(set(base_spec.get("pass_k") or []) - set(spec.get("pass_k") or [])):
        probs.append(f"RATCHET pass_k {k} removed")
    return probs


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"                       # a slice with no rows cannot vouch for anything
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000),
                                                   rng=bs.get("rng", 2027),
                                                   confidence=bs.get("confidence", 0.95))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} n={len(a):<3} {json.dumps(th):<36} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
