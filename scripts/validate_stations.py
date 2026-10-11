#!/usr/bin/env python3
"""Validate the station files read by swi-metobs-caching.

swi-metobs-caching runs ``git pull origin main`` on this repository before every cron
run and reads stations/fixed_stations.json and stations/mobile_stations.json. Its loader
only logs a problem and carries on: a malformed file silently drops its stations, and a
``datasource`` name it does not know silently falls back to FrostSource (FrostBoatSource
for mobile stations), so a typo sends a station through the wrong service. This script
makes those mistakes fail before they are merged.

Usage:
  validate_stations.py STATIONS_DIR
      Check the structure of both files.
  validate_stations.py STATIONS_DIR --check-datasources
      Also check each ``datasource`` against DATASOURCE_MAPPING of the swi-metobs-caching
      code; run inside its image with PYTHONPATH=/swi.
"""

import json
import re
import sys
from pathlib import Path

FILES = {"fixed": "fixed_stations.json", "mobile": "mobile_stations.json"}
ID = re.compile(r"[A-Za-z0-9_.\-]{1,64}")
IMPORT_FUNCTION = re.compile(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+")


def _is_text(value):
    return isinstance(value, str) and value.strip() != ""


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_station(station, kind, known_datasources=None):
    """Problems of one station, as a list of messages."""
    if not isinstance(station, dict):
        return ["is not an object"]
    problems = []
    if not (isinstance(station.get("id"), str) and ID.fullmatch(station["id"])):
        problems.append("'id' must be 1-64 letters, digits, '_', '.' or '-'")
    for field in ("name", "project", "icon"):
        if not _is_text(station.get(field)):
            problems.append(f"'{field}' must be a non-empty string")

    # An empty object is allowed (stations listed before their variables are mapped) and
    # a null value marks a variable the station does not provide.
    variables = station.get("variables")
    if not isinstance(variables, dict):
        problems.append("'variables' must be an object")
    elif not all(_is_text(k) and (v is None or _is_text(v)) for k, v in variables.items()):
        problems.append("'variables' keys must be non-empty strings and values strings or null")

    if "url" in station and not (_is_text(station["url"]) and station["url"].startswith("https://")):
        problems.append("'url' must be an https:// address")

    if "datasource" in station:
        name = station["datasource"]
        if not _is_text(name):
            problems.append("'datasource' must be a non-empty string")
        elif known_datasources is not None and name not in known_datasources:
            problems.append(
                f"'datasource' {name!r} is unknown to swi-metobs-caching "
                f"(known: {', '.join(sorted(known_datasources))}); it would silently fall back to a Frost source"
            )

    has_position = "lat" in station or "lon" in station
    if kind == "fixed" or has_position:
        lat, lon = station.get("lat"), station.get("lon")
        if not (_is_number(lat) and -90 <= lat <= 90):
            problems.append("'lat' must be a number between -90 and 90")
        if not (_is_number(lon) and -180 <= lon <= 180):
            problems.append("'lon' must be a number between -180 and 180")

    if kind == "mobile" and not (
        isinstance(station.get("import_function"), str)
        and IMPORT_FUNCTION.fullmatch(station["import_function"])
    ):
        problems.append("'import_function' must look like 'module.function'")
    return problems


def check_files(contents, known_datasources=None):
    """``contents`` maps 'fixed'/'mobile' to the parsed JSON of the file."""
    errors = []
    seen = {}
    for kind, data in contents.items():
        filename = FILES[kind]
        if not isinstance(data, list) or not data:
            errors.append(f"{filename}: must be a non-empty list of stations")
            continue
        for index, station in enumerate(data):
            label = station.get("id") if isinstance(station, dict) and station.get("id") else f"#{index}"
            for problem in check_station(station, kind, known_datasources):
                errors.append(f"{filename} [{label}]: {problem}")
            if isinstance(station, dict) and isinstance(station.get("id"), str):
                if station["id"] in seen:
                    errors.append(f"{filename} [{label}]: id also used in {seen[station['id']]}")
                seen.setdefault(station["id"], filename)
    return errors


def notices(contents):
    """Things that are valid but worth seeing, e.g. stations that will return no data."""
    notes = []
    for kind, data in contents.items():
        if not isinstance(data, list):
            continue
        empty = [s["id"] for s in data if isinstance(s, dict) and s.get("variables") == {} and "id" in s]
        if empty:
            notes.append(f"{FILES[kind]}: {len(empty)} stations have no variables and return no data: {', '.join(empty)}")
    return notes


def load_files(directory):
    contents, errors = {}, []
    for kind, filename in FILES.items():
        path = Path(directory) / filename
        try:
            contents[kind] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            errors.append(f"{filename}: file not found")
        except json.JSONDecodeError as error:
            errors.append(f"{filename}: invalid JSON ({error})")
    return contents, errors


def known_datasources_from_package():
    from source.datasource.datasourceFactory import DATASOURCE_MAPPING

    return set(DATASOURCE_MAPPING)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    if len(args) != 1 or flags - {"--check-datasources"}:
        print(__doc__, file=sys.stderr)
        return 2
    contents, errors = load_files(args[0])
    known = None
    if "--check-datasources" in flags:
        try:
            known = known_datasources_from_package()
        except ImportError as error:
            print(f"error: cannot import swi-metobs-caching (is PYTHONPATH=/swi set?): {error}", file=sys.stderr)
            return 1
    errors += check_files(contents, known)
    for message in notices(contents):
        print(f"NOTE {message}")
    for message in errors:
        print(f"FAIL {message}")
    if not errors:
        total = sum(len(v) for v in contents.values())
        suffix = f", datasources checked against {len(known)} known" if known else ""
        print(f"OK   {total} stations in {len(contents)} files{suffix}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
