#!/usr/bin/env python3
"""Validate elk-stomp-ports.yaml and regenerate its JSON twin.

    tools/validate-ports.py           # validate + write the .json twin
    tools/validate-ports.py --check   # validate only (use in CI)

The file's whole value is that its verification levels mean something. That only
holds if the rules are enforced rather than remembered, so this checks them:

  1. Every graded entry below `verified` carries an `evidence` string.
  2. Every verification value is one of the five defined levels.
  3. A `<field>_verification` override names a field that actually exists.
  4. `engine_channel` is a list of ints or null -- never a bare int, never [].
  5. `routing.blocks[].relates_to` resolves to a real port id, or is null.
  6. `controls.*.ids` flattens to exactly the 41 ids sensei_config.json declares,
     with no duplicates.

It also prints the level tally, which downstream docs quote and which silently
goes stale after every edit.
"""
import json, os, sys

try:
    import yaml
except ImportError:
    sys.exit("needs pyyaml:  pip install pyyaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_PATH = os.path.join(ROOT, "elk-stomp-ports.yaml")
JSON_PATH = os.path.join(ROOT, "elk-stomp-ports.json")
SENSEI_ELEMENT_COUNT = 41

errors, warnings = [], []


def err(path, msg):
    errors.append(f"{path}: {msg}")


def walk(node, path, levels, doc):
    """Recursively check every dict that carries a verification key."""
    if isinstance(node, list):
        for i, item in enumerate(node):
            walk(item, f"{path}[{i}]", levels, doc)
        return
    if not isinstance(node, dict):
        return

    v = node.get("verification")
    if v is not None:
        if v not in levels:
            err(path, f"unknown verification level {v!r}; expected one of {sorted(levels)}")
        elif v != "verified" and not str(node.get("evidence", "")).strip():
            err(path, f"verification: {v} (below `verified`) with no `evidence` string")

    # field-level overrides
    for key, val in node.items():
        if not key.endswith("_verification") or key == "verification":
            continue
        field = key[: -len("_verification")]
        if field not in node:
            err(path, f"`{key}` grades `{field}`, which is not present on this entry")
        if val not in levels:
            err(path, f"{key}: unknown level {val!r}")
        elif val != "verified":
            ev = node.get(f"{field}_evidence") or node.get("evidence")
            if not str(ev or "").strip():
                err(path, f"{key}: {val} with neither `{field}_evidence` nor `evidence`")

    for key, val in node.items():
        if isinstance(val, (dict, list)):
            walk(val, f"{path}.{key}", levels, doc)


def main():
    doc = yaml.safe_load(open(YAML_PATH))
    levels = doc.get("meta", {}).get("verification_levels", {})
    if not levels:
        sys.exit("meta.verification_levels is missing -- the taxonomy must ship as data, "
                 "not only as YAML comments, or the JSON twin has an undefined enum.")

    walk(doc, "$", levels, doc)

    # engine_channel encoding
    port_ids = set()
    for i, p in enumerate(doc.get("ports", [])):
        pid = p.get("id")
        port_ids.add(pid)
        if "engine_channel" not in p:
            continue
        ec = p["engine_channel"]
        if ec is None:
            continue
        if not isinstance(ec, list):
            err(f"ports[{i}] ({pid})", f"engine_channel must be a list or null, got {ec!r}")
        elif not ec:
            err(f"ports[{i}] ({pid})", "engine_channel is [] -- use null for 'not determined'; "
                                       "[] reads as a positive claim of no channel")
        elif not all(isinstance(x, int) for x in ec):
            err(f"ports[{i}] ({pid})", f"engine_channel must contain ints, got {ec!r}")

    # routing foreign keys
    for i, b in enumerate(doc.get("routing", {}).get("blocks", [])):
        rel = b.get("relates_to")
        if rel is None:
            if not str(b.get("note", "")).strip():
                warnings.append(f"routing.blocks[{i}] ({b.get('label')}): relates_to null with no note")
        elif rel not in port_ids:
            err(f"routing.blocks[{i}] ({b.get('label')})",
                f"relates_to {rel!r} matches no ports[].id")

    # control-surface id accounting
    ids, dupes = [], []
    for name, grp in doc.get("controls", {}).items():
        if isinstance(grp, dict) and isinstance(grp.get("ids"), list):
            for x in grp["ids"]:
                if isinstance(x, int):
                    (dupes if x in ids else ids).append(x)
                else:
                    err(f"controls.{name}.ids", f"expected flat ints, got {x!r}")
    if dupes:
        err("controls", f"duplicate ids across groups: {sorted(set(dupes))}")
    if len(set(ids)) != SENSEI_ELEMENT_COUNT:
        err("controls", f"ids flatten to {len(set(ids))} unique, but the section's own evidence "
                        f"cites {SENSEI_ELEMENT_COUNT} addressable elements. "
                        f"Missing: {sorted(set(range(1, SENSEI_ELEMENT_COUNT + 1)) - set(ids))}")

    # tally
    tally = {}

    def count(n):
        if isinstance(n, list):
            for i in n:
                count(i)
        elif isinstance(n, dict):
            for k, val in n.items():
                if k == "verification" or (k.endswith("_verification") and k != "verification"):
                    if isinstance(val, str):
                        key = "entry" if k == "verification" else "field-override"
                        tally.setdefault(val, {"entry": 0, "field-override": 0})[key] += 1
                if isinstance(val, (dict, list)):
                    count(val)

    count({k: v for k, v in doc.items() if k != "meta"})

    print(f"== {os.path.basename(YAML_PATH)}")
    print(f"   ports {len(doc.get('ports', []))} · expansion headers "
          f"{len(doc.get('expansion', {}).get('headers', []))} · "
          f"open questions {len(doc.get('open_questions', []))}")
    print("   verification tally (entry-level / field-override):")
    for lvl in sorted(tally, key=lambda l: -levels.get(l, {}).get("rank", 0)):
        t = tally[lvl]
        print(f"     {lvl:<11} {t['entry']:>3}  / {t['field-override']:>2}")

    for w in warnings:
        print(f"   warn  {w}")
    if errors:
        print(f"\n!! {len(errors)} problem(s):")
        for e in errors:
            print(f"   - {e}")
        return 1

    print("   schema problems: NONE")
    if "--check" not in sys.argv:
        with open(JSON_PATH, "w") as f:
            json.dump(doc, f, indent=2, sort_keys=False)
            f.write("\n")
        rt = json.load(open(JSON_PATH))
        assert rt == doc, "JSON twin does not round-trip the YAML"
        print(f"   wrote {os.path.basename(JSON_PATH)} (round-trip verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
