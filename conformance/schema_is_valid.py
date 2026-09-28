"""Check that every schema in `schema/` is itself a valid JSON Schema document.

A malformed schema silently degrades every downstream check, so this runs first.
"""

import json
import pathlib
import sys

import jsonschema

SCHEMA_DIR = pathlib.Path(__file__).parent.parent / "schema"

# Each schema's expected `$id`. Listed rather than derived, so that renaming a
# file or bumping a version is a deliberate edit here and not a silent pass.
EXPECTED_IDS = {
    "envelope.schema.json": "https://github.com/kingb/glassworks-envelope/schema/envelope/v1",
}


def check(name: str, expected_id: str) -> list[str]:
    path = SCHEMA_DIR / name
    if not path.exists():
        return [f"{path} does not exist"]

    try:
        schema = json.loads(path.read_text())
    except ValueError as exc:
        return [f"{name} is not parseable JSON: {exc}"]

    failures: list[str] = []

    validator_cls = jsonschema.validators.validator_for(schema)
    try:
        validator_cls.check_schema(schema)
    except jsonschema.exceptions.SchemaError as exc:
        failures.append(f"{name} is not a valid JSON Schema: {exc}")

    if schema.get("$id") != expected_id:
        failures.append(f"{name}: unexpected $id: {schema.get('$id')}")

    # A `$ref` to a definition that does not exist is not a schema error — it is
    # a runtime resolution failure, which surfaces only if a fixture happens to
    # reach that branch. A large schema can carry a dangling ref through review
    # untouched, so the refs are walked here instead.
    defs = schema.get("$defs", {})
    for ref in walk_refs(schema):
        if not ref.startswith("#/$defs/"):
            failures.append(f"{name}: unexpected non-local $ref: {ref}")
        elif ref.removeprefix("#/$defs/") not in defs:
            failures.append(f"{name}: $ref points at a missing definition: {ref}")

    # An unreferenced definition is dead weight that still generates a type in
    # every binding, which is how a contract accumulates vocabulary nobody sends.
    referenced = {r.removeprefix("#/$defs/") for r in walk_refs(schema)}
    for orphan in sorted(set(defs) - referenced):
        failures.append(f"{name}: definition is never referenced: {orphan}")

    return failures


def walk_refs(node: object) -> list[str]:
    """Every `$ref` string anywhere in the document."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(walk_refs(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(walk_refs(item))
    return found


def main() -> int:
    failures: list[str] = []
    for name, expected_id in EXPECTED_IDS.items():
        failures.extend(check(name, expected_id))

    present = {p.name for p in SCHEMA_DIR.glob("*.schema.json")}
    for unlisted in sorted(present - set(EXPECTED_IDS)):
        failures.append(f"{unlisted}: present in schema/ but not checked here")

    for line in failures:
        print(f"FAIL: {line}")
    if failures:
        return 1

    print(f"OK: {len(EXPECTED_IDS)} schemas are valid JSON Schema documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
