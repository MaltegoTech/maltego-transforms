#!/usr/bin/env python3
"""
std_entity_lookup.py — Look up a standard Maltego entity class by name or wire type.

Accepts a class name (Person), wire TYPE_NAME (maltego.Person), or fuzzy search term.
Tries to import maltego.entities from the installed SDK package (or a local source
tree if --local-src is provided).

CLI: python std_entity_lookup.py <entity-name-or-type> [--local-src <path>]
"""

import argparse
import json
import sys

# Built-in static mapping (wire type → class name) for offline fallback
BUILTIN_MAPPING: dict[str, str] = {
    "maltego.Phrase": "Phrase",
    "maltego.DNSName": "DNSName",
    "maltego.IPv4Address": "IPv4Address",
    "maltego.Domain": "Domain",
    "maltego.Person": "Person",
    "maltego.EmailAddress": "EmailAddress",
    "maltego.PhoneNumber": "PhoneNumber",
    "maltego.URL": "URL",
    "maltego.Website": "Website",
    "maltego.Alias": "Alias",
    "maltego.AS": "AS",
    "maltego.Netblock": "Netblock",
    "maltego.Organization": "Organization",
    "maltego.Location": "Location",
    "maltego.Company": "Company",
    "maltego.MaltegoTransform": "MaltegoTransform",
}


def _normalise_query(query: str) -> tuple[str, str]:
    """Return (class_name_guess, wire_type_guess) from any query form."""
    q = query.strip()
    if "." in q:
        # Likely a wire type like maltego.Person
        wire = q
        cls = q.split(".")[-1]
    else:
        # Class name only
        cls = q
        wire = f"maltego.{q}"
    return cls, wire


def lookup_entity(query: str, local_src: str | None = None) -> dict:
    if local_src:
        sys.path.insert(0, local_src)

    cls_guess, wire_guess = _normalise_query(query)

    # --- Try live import ---
    source_label: str | None = None
    found_class = None
    module_name: str | None = None
    type_name: str | None = None
    category: str | None = None

    try:
        import importlib
        entities_mod = importlib.import_module("maltego.entities")
        source_label = "local" if local_src else "installed"

        # Walk namespace for exact class name match
        for name in dir(entities_mod):
            if name == cls_guess:
                obj = getattr(entities_mod, name)
                if isinstance(obj, type):
                    found_class = obj
                    module_name = getattr(obj, "__module__", "maltego.entities")
                    type_name = getattr(obj, "TYPE_NAME", None) or wire_guess
                    category = getattr(obj, "CATEGORY", None)
                    break

        if found_class is None:
            # Fuzzy: search by TYPE_NAME attribute
            for name in dir(entities_mod):
                obj = getattr(entities_mod, name)
                if isinstance(obj, type):
                    tn = getattr(obj, "TYPE_NAME", "") or ""
                    if tn.lower() == wire_guess.lower() or name.lower() == cls_guess.lower():
                        found_class = obj
                        module_name = getattr(obj, "__module__", "maltego.entities")
                        type_name = tn or wire_guess
                        category = getattr(obj, "CATEGORY", None)
                        break

    except ImportError:
        source_label = None

    if found_class is not None:
        return {
            "class_name": found_class.__name__,
            "module": module_name,
            "type_name": type_name,
            "category": category,
            "found": True,
            "source": source_label,
        }

    # --- Fallback: static mapping ---
    # Try exact wire type
    for wt, cn in BUILTIN_MAPPING.items():
        if wt.lower() == wire_guess.lower() or cn.lower() == cls_guess.lower():
            return {
                "class_name": cn,
                "module": "maltego.entities",
                "type_name": wt,
                "category": None,
                "found": True,
                "source": "builtin-mapping",
            }

    # --- Not found ---
    suggestions = [
        cn for wt, cn in BUILTIN_MAPPING.items()
        if cls_guess.lower() in cn.lower() or cls_guess.lower() in wt.lower()
    ]
    return {
        "found": False,
        "query": query,
        "suggestions": suggestions,
    }


def main():
    parser = argparse.ArgumentParser(description="Look up a standard Maltego entity class.")
    parser.add_argument("entity", help="Class name, wire TYPE_NAME, or search term.")
    parser.add_argument("--local-src", metavar="PATH", help="Add path to sys.path for local SDK source.")
    args = parser.parse_args()

    result = lookup_entity(args.entity, local_src=args.local_src)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
