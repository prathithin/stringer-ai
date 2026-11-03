"""Hardcoded Georgia Tech building → nearest Stinger stop + walk times.

Walk minutes are campus estimates (not GPS). Origin defaults to West Village
when the student does not name a starting point.
"""

from __future__ import annotations

BUILDINGS: dict[str, dict] = {
    "klaus": {
        "name": "Klaus Advanced Computing Building",
        "aliases": ["klaus", "kacb", "klaus building"],
        "nearest_stop": "Klaus Building EB",
        "walk_from_stop_minutes": 2,
    },
    "clough": {
        "name": "Clough Undergraduate Learning Commons",
        "aliases": ["clough", "culc", "clough commons"],
        "nearest_stop": "Clough Commons",
        "walk_from_stop_minutes": 1,
    },
    "crc": {
        "name": "Campus Recreation Center",
        "aliases": ["crc", "stamps", "campus recreation"],
        "nearest_stop": "CRC & Stamps Health",
        "walk_from_stop_minutes": 2,
    },
    "student_center": {
        "name": "Student Center",
        "aliases": ["student center", "stamps student center", "sc"],
        "nearest_stop": "Student Center",
        "walk_from_stop_minutes": 1,
    },
    "coc": {
        "name": "College of Computing",
        "aliases": ["college of computing", "ccb", "computing"],
        "nearest_stop": "Klaus Building WB",
        "walk_from_stop_minutes": 4,
    },
    "howey": {
        "name": "Howey Physics Building",
        "aliases": ["howey", "physics", "cherry emerson"],
        "nearest_stop": "Cherry Emerson",
        "walk_from_stop_minutes": 2,
    },
    "ic": {
        "name": "Instructional Center",
        "aliases": ["instructional center", "ic", "instructional"],
        "nearest_stop": "Ferst Drive & Student Center",
        "walk_from_stop_minutes": 4,
    },
    "scheller": {
        "name": "Scheller College of Business",
        "aliases": ["scheller", "college of business", "tech square", "business"],
        "nearest_stop": "College of Business",
        "walk_from_stop_minutes": 2,
    },
}

# Door-to-door walking fallback between common origin/destination names.
WALK_FALLBACK_MINUTES: dict[tuple[str, str], int] = {
    ("west village", "klaus"): 18,
    ("west village", "clough"): 16,
    ("west village", "crc"): 8,
    ("west village", "student_center"): 10,
    ("west village", "coc"): 18,
    ("west village", "howey"): 14,
    ("west village", "ic"): 12,
    ("west village", "scheller"): 22,
    ("student_center", "klaus"): 8,
    ("student_center", "clough"): 8,
    ("student_center", "crc"): 6,
    ("student_center", "coc"): 8,
    ("student_center", "howey"): 7,
    ("student_center", "ic"): 4,
    ("student_center", "scheller"): 14,
    ("north avenue apts", "klaus"): 16,
    ("north avenue apts", "clough"): 12,
    ("north avenue apts", "crc"): 18,
    ("north avenue apts", "student_center"): 14,
    ("north avenue apts", "coc"): 16,
    ("north avenue apts", "howey"): 14,
    ("north avenue apts", "ic"): 12,
    ("north avenue apts", "scheller"): 18,
}

DEFAULT_ORIGIN = "west village"


def resolve_building(query: str) -> dict | None:
    q = (query or "").strip().lower()
    if not q:
        return None
    for key, info in BUILDINGS.items():
        if q == key or q in info["aliases"] or info["name"].lower() in q:
            return {"id": key, **info}
        for alias in info["aliases"]:
            if alias in q:
                return {"id": key, **info}
    return None


def walking_fallback_minutes(origin: str, building_id: str) -> int:
    origin_key = (origin or DEFAULT_ORIGIN).strip().lower()
    if origin_key in BUILDINGS:
        origin_key = origin_key
    for key, info in BUILDINGS.items():
        if origin_key in info["aliases"] or origin_key == key:
            origin_key = "student_center" if key in {"student_center"} else key
            break
    pair = (origin_key, building_id)
    if pair in WALK_FALLBACK_MINUTES:
        return WALK_FALLBACK_MINUTES[pair]
    # Unknown origin: conservative campus walk.
    return 20
