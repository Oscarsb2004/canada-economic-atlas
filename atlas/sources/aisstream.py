"""
atlas.sources.aisstream — where Canadian-flagged vessels were last heard, from
aisstream.io's live AIS relay.

WHAT THIS SOURCE IS, AND IS NOT (docs/AIS.md)

No Canadian government publishes live ship positions. aisstream.io relays AIS
messages heard by shore-based receivers worldwide, free, under no terms of use
that could be found on 2026-09-12. It is a third-party feed and is labelled as
one. Its coverage is whatever receivers can hear, so a ship in open ocean is out
of range: a snapshot keeps each vessel's LAST position with the time it was
received, and never moves a ship it did not hear.

WHAT MAKES A VESSEL CANADIAN HERE

A flag is a state of registry. Two published signals are used, and kept apart:

- `mmsi_mid` — a ship station's radio identity (MMSI) begins with the Maritime
  Identification Digits of the administration that issued it, allocated by the
  ITU. Canada's are 316 (sources.yaml `aisstream.canadian_mids`). Only the
  nine-digit ship-station form counts: coast stations (00MID…), group calls
  (0MID…), aids to navigation (99MID…) and search-and-rescue aircraft (111MID…)
  are not vessels.
- `register_imo` — the IMO number the ship broadcasts is in Transport Canada's
  Canadian Register of Large Vessels (stage 07).

The register is joined only through the IMO number, because it publishes no
MMSI. Where it matches it adds what AIS does not carry: the official number,
port of registry, the register's own descriptor and gross tonnage.

READ FROM A MESSAGE, AND THE "NOT AVAILABLE" VALUES

Field names are aisstream.io's published models
(github.com/aisstream/ais-message-models). The AIS standard (ITU-R M.1371)
reserves values that mean "not available": longitude 181, latitude 91, speed
102.3 knots, course 360, heading 511. Those become null here, rather than a
ship off the edge of the earth or one doing 102 knots. Text fields are padded
with "@" in the standard; the padding is removed and nothing else is changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Overridden by sources.yaml in the collector; the default is what was read on
#: 2026-09-12 and what the tests use.
CANADIAN_MIDS: tuple[str, ...] = ("316",)

MESSAGE_TYPES = ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport",
                 "ShipStaticData", "StaticDataReport")
_POSITION_CLASS = {"PositionReport": "A", "StandardClassBPositionReport": "B",
                   "ExtendedClassBPositionReport": "B"}
FLAG_BASES = ("mmsi_mid", "register_imo")
NOTES = ("imo_not_in_register", "mmsi_prefix_not_canadian")
SNAPSHOT_SCHEMA = 1
_STATIC_FIELDS = ("name", "call_sign", "imo", "ship_type", "destination", "eta")


class SnapshotError(ValueError):
    """A snapshot is not fit to publish."""


def ship_station_mid(mmsi: object) -> str | None:
    """The MID of a nine-digit ship-station MMSI, or None for any other kind of identity."""
    s = str(mmsi).strip()
    if len(s) != 9 or not s.isdigit() or s[0] not in "234567":
        return None
    return s[:3]


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.replace("@", " ").strip()
    return s or None


def _speed(v: Any) -> float | None:
    return None if not isinstance(v, (int, float)) or v >= 102.3 or v < 0 else v


def _course(v: Any) -> float | None:
    return None if not isinstance(v, (int, float)) or v >= 360 or v < 0 else v


def _heading(v: Any) -> int | None:
    return None if not isinstance(v, int) or not 0 <= v < 360 else v


@dataclass
class Heard:
    """What one listening window heard from one MMSI."""

    mmsi: str
    klass: str | None = None
    position: dict[str, Any] | None = None
    position_received_at: str | None = None
    name: str | None = None
    call_sign: str | None = None
    imo: str | None = None
    ship_type: int | None = None
    destination: str | None = None
    eta: dict[str, Any] | None = None
    static_received_at: str | None = None


class Tracker:
    """
    Every vessel heard in a window, Canadian or not.

    Kept for all of them because the flag can arrive after the position: a ship
    whose MMSI is not Canadian is recognised only when its static message brings
    an IMO number that is in the register, minutes after its first position.
    """

    def __init__(self) -> None:
        self.heard: dict[str, Heard] = {}
        self.messages = 0

    def ingest(self, message: dict[str, Any], received_at: str) -> None:
        self.messages += 1
        kind = message.get("MessageType")
        body = (message.get("Message") or {}).get(kind)
        if not isinstance(body, dict) or body.get("Valid") is False or body.get("UserID") is None:
            return
        h = self.heard.setdefault(str(body["UserID"]), Heard(mmsi=str(body["UserID"])))

        if kind in _POSITION_CLASS:
            h.klass = _POSITION_CLASS[kind]
            lon, lat = body.get("Longitude"), body.get("Latitude")
            if not (isinstance(lon, (int, float)) and isinstance(lat, (int, float))
                    and -180 <= lon <= 180 and -90 <= lat <= 90):
                return
            h.position = {
                "lon": lon, "lat": lat,
                "sog": _speed(body.get("Sog")), "cog": _course(body.get("Cog")),
                "heading": _heading(body.get("TrueHeading")),
                "nav_status": body.get("NavigationalStatus") if kind == "PositionReport" else None,
            }
            h.position_received_at = received_at
        elif kind == "ShipStaticData":
            h.klass = h.klass or "A"
            h.name = _text(body.get("Name")) or h.name
            h.call_sign = _text(body.get("CallSign")) or h.call_sign
            imo = body.get("ImoNumber")
            if isinstance(imo, int) and imo > 0:
                h.imo = str(imo)
            if isinstance(body.get("Type"), int):
                h.ship_type = body["Type"]
            h.destination = _text(body.get("Destination")) or h.destination
            eta = body.get("Eta")
            if isinstance(eta, dict):
                h.eta = {k.lower(): eta.get(k) for k in ("Month", "Day", "Hour", "Minute")}
            h.static_received_at = received_at
        elif kind == "StaticDataReport":
            a, b = body.get("ReportA") or {}, body.get("ReportB") or {}
            if a.get("Valid"):
                h.name = _text(a.get("Name")) or h.name
            if b.get("Valid"):
                h.call_sign = _text(b.get("CallSign")) or h.call_sign
                if isinstance(b.get("ShipType"), int):
                    h.ship_type = b["ShipType"]
            h.static_received_at = received_at


def register_index(register_doc: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """
    Register entries by IMO number, from stage 07's output.

    A list per number, because the register lists one IMO against two rows of
    the same Official Number. Entries failing the IMO check digit are left out:
    no transponder can broadcast them, so a match would be a coincidence.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for v in register_doc.get("vessels", []):
        if v.get("imo") and v.get("imo_check_digit_valid"):
            out.setdefault(v["imo"], []).append({
                "official_number": v["official_number"], "register_row": v["register_row"],
                "name": v["name"], "port_of_registry": v["port_of_registry"],
                "descriptor": v["descriptor"], "gross_tonnage": v["gross_tonnage"],
            })
    return out


def _classify(rec: dict[str, Any], register: dict[str, list[dict[str, Any]]],
              mids: tuple[str, ...]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    basis: list[str] = []
    notes: list[str] = []
    if ship_station_mid(rec["mmsi"]) in mids:
        basis.append("mmsi_mid")
    entries = register.get(rec.get("imo") or "", [])
    if entries:
        basis.append("register_imo")
    if "mmsi_mid" in basis and rec.get("imo") and not entries:
        notes.append("imo_not_in_register")
    if basis == ["register_imo"]:
        notes.append("mmsi_prefix_not_canadian")
    return basis, notes, entries


def build_snapshot(tracker: Tracker, previous: dict[str, Any] | None,
                   register: dict[str, list[dict[str, Any]]], *, window_from: str, window_to: str,
                   feed: dict[str, Any], register_source: dict[str, Any],
                   mids: tuple[str, ...] = CANADIAN_MIDS) -> dict[str, Any]:
    """
    The previous snapshot, updated with what this window heard.

    A vessel not heard keeps its last position and time. A heard vessel takes
    its new position; its static fields change only where this window heard one.
    Every record is classified again against the current register, so a vessel
    is published only while one of the two signals holds, and only once a
    position has been heard for it.
    """
    blank = {"class": None, "position": None, "position_received_at": None,
             "static_received_at": None, **{k: None for k in _STATIC_FIELDS}}
    records: dict[str, dict[str, Any]] = {
        v["mmsi"]: dict(v) for v in (previous or {}).get("vessels", [])
    }
    for mmsi, h in tracker.heard.items():
        rec = dict(records.get(mmsi) or {"mmsi": mmsi, **blank})
        if h.klass:
            rec["class"] = h.klass
        if h.position is not None:
            rec["position"] = h.position
            rec["position_received_at"] = h.position_received_at
        if h.static_received_at:
            for key in _STATIC_FIELDS:
                value = getattr(h, key)
                if value is not None:
                    rec[key] = value
            rec["static_received_at"] = h.static_received_at
        records[mmsi] = rec

    vessels = []
    for mmsi in sorted(records):
        rec = records[mmsi]
        basis, notes, entries = _classify(rec, register, mids)
        if not basis or rec.get("position") is None:
            continue
        rec.update(flag_basis=basis, notes=notes, register=entries)
        vessels.append(rec)

    heard = sum(1 for v in vessels if v["mmsi"] in tracker.heard and tracker.heard[v["mmsi"]].position)
    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "generated_at": window_to,
        "window": {"from": window_from, "to": window_to, "messages": tracker.messages,
                   "vessels_heard_worldwide": len(tracker.heard), "canadian_heard_this_window": heard},
        "feed": feed,
        "register_source": register_source,
        "canadian_mids": list(mids),
        "vessels": vessels,
    }


def validate_snapshot(doc: dict[str, Any]) -> None:
    """Refuse a snapshot that would put something on the map it cannot justify."""
    if doc.get("schema_version") != SNAPSHOT_SCHEMA:
        raise SnapshotError(f"schema_version {doc.get('schema_version')!r} is not {SNAPSHOT_SCHEMA}")
    seen: set[str] = set()
    for v in doc.get("vessels", []):
        where = f"vessel {v.get('mmsi')!r}"
        if not (isinstance(v.get("mmsi"), str) and len(v["mmsi"]) == 9 and v["mmsi"].isdigit()):
            raise SnapshotError(f"{where}: MMSI is not nine digits")
        if v["mmsi"] in seen:
            raise SnapshotError(f"{where}: listed twice")
        seen.add(v["mmsi"])
        if not v.get("flag_basis") or set(v["flag_basis"]) - set(FLAG_BASES):
            raise SnapshotError(f"{where}: no recognised reason to call it Canadian")
        if set(v.get("notes", [])) - set(NOTES):
            raise SnapshotError(f"{where}: unknown note {v.get('notes')}")
        if ("register_imo" in v["flag_basis"]) != bool(v.get("register")):
            raise SnapshotError(f"{where}: register basis and register entries disagree")
        pos = v.get("position") or {}
        if not (-180 <= pos.get("lon", 999) <= 180 and -90 <= pos.get("lat", 999) <= 90):
            raise SnapshotError(f"{where}: position {pos} is not on the earth")
        if not v.get("position_received_at"):
            raise SnapshotError(f"{where}: no time for its position")
