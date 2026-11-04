#!/usr/bin/env python3
"""
=============================================================================
CYBERDECK CALENDAR // RFC 5545 iCAL & PROTON EXPORT ENGINE (export_ics.py)
=============================================================================
Generates standards-compliant iCalendar (.ics) files for seamless import and
subscription into Proton Calendar, Apple Calendar, Thunderbird, and Google Calendar.

Rules & Governance:
  - ZERO lightning bolts or thunderbolts (strictly architectural cyber runes).
  - Clean VCALENDAR / VEVENT schema with standard UIDs, DTSTAMP, DTSTART, DTEND.
  - Generates optional audio/display VALARM reminders (15-min notification).
  - Supports stream isolation: export CRM only, TPRM only, Ops only, or Unified.
=============================================================================
"""

import os
import sys
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from calendar_bridge import get_all_calendar_events
except ImportError:
    from .calendar_bridge import get_all_calendar_events

DEFAULT_EXPORT_DIR = Path.home() / "Documents"

def format_ics_datetime(dt_str: str) -> tuple:
    """
    Parses ISO date string and returns (ics_formatted_str, is_all_day).
    Example: '2026-11-04T09:00:00' -> ('20261104T090000', False)
             '2026-11-04' -> ('20261104', True)
    """
    if "T" in dt_str:
        clean = dt_str.replace("-", "").replace(":", "").split(".")[0]
        if not clean.endswith("Z"):
            clean += "Z"
        return clean, False
    else:
        clean = dt_str.replace("-", "")
        return clean, True

def escape_ics_text(text: str) -> str:
    """Escapes commas, semicolons, and backslashes per RFC 5545."""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text

def generate_ics_content(events: List[Dict[str, Any]], calendar_name: str = "Cyberdeck Calendar", glance_only: bool = False) -> str:
    """
    Builds the complete RFC 5545 .ics payload string.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Cyberdeck OS//Aura Calendar Engine//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics_text(calendar_name)}",
        "X-WR-TIMEZONE:America/New_York"
    ]

    for ev in events:
        eid = ev.get("id", "event-0")
        source = ev.get("source", "ops").upper()
        start_str = ev.get("start", "")
        if not start_str:
            continue

        start_val, is_all_day = format_ics_datetime(start_str)
        end_str = ev.get("end") or start_str
        end_val, _ = format_ics_datetime(end_str)

        # Title and Description selection based on privacy mode
        if glance_only:
            summary = ev.get("glance_title") or ev.get("badge") or f"[{source} EVENT]"
            desc = f"Cyberdeck Event // Stream: {source}"
        else:
            summary = ev.get("full_title") or ev.get("title") or "Scheduled Event"
            notes = ev.get("notes", "")
            counterparty = ev.get("counterparty", "")
            role = ev.get("role", "")
            desc_parts = [f"Source: Cyberdeck // {source}"]
            if counterparty:
                desc_parts.append(f"Counterparty: {counterparty}")
            if role:
                desc_parts.append(f"Role / Scope: {role}")
            if notes:
                desc_parts.append(f"Notes: {notes}")
            desc = " \\n".join(desc_parts)

        category = ev.get("category", source)

        event_lines = [
            "BEGIN:VEVENT",
            f"UID:{eid}@cyberdeck.local",
            f"DTSTAMP:{now_utc}",
            f"SUMMARY:{escape_ics_text(summary)}",
            f"DESCRIPTION:{escape_ics_text(desc)}",
            f"CATEGORIES:{escape_ics_text(category)}",
            "STATUS:CONFIRMED"
        ]

        if is_all_day:
            event_lines.append(f"DTSTART;VALUE=DATE:{start_val}")
            event_lines.append(f"DTEND;VALUE=DATE:{end_val}")
        else:
            event_lines.append(f"DTSTART:{start_val}")
            event_lines.append(f"DTEND:{end_val}")

        # Add 15-minute standard popup reminder alarm
        event_lines.extend([
            "BEGIN:VALARM",
            "TRIGGER:-PT15M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Reminder: {escape_ics_text(summary)}",
            "END:VALARM",
            "END:VEVENT"
        ])

        lines.extend(event_lines)

    lines.append("END:VCALENDAR")
    lines.append("")  # RFC 5545 trailing newline
    return "\r\n".join(lines)

def export_calendar(destination: Optional[Path] = None, stream: str = "all", glance_only: bool = False) -> Dict[str, Any]:
    """
    Exports events to an .ics file ready for Proton Calendar import.
    """
    data = get_all_calendar_events(glance_mode=glance_only)
    events = data.get("events", [])

    if stream != "all":
        events = [e for e in events if e.get("source") == stream]

    if not destination:
        DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.date.today().strftime("%Y-%m-%d")
        fname = f"cyberdeck_calendar_{stream}_{ts}.ics" if stream != "all" else f"cyberdeck_calendar_proton_{ts}.ics"
        destination = DEFAULT_EXPORT_DIR / fname

    content = generate_ics_content(events, calendar_name=f"Cyberdeck Calendar ({stream.upper()})", glance_only=glance_only)
    
    dest_path = Path(destination)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)

    return {
        "ok": True,
        "path": str(dest_path),
        "count": len(events),
        "stream": stream,
        "glance_only": glance_only,
        "size_bytes": os.path.getsize(dest_path)
    }

if __name__ == "__main__":
    result = export_calendar()
    print(f"[EXPORT] Successfully generated Proton-compatible calendar:")
    print(f"         Path : {result['path']}")
    print(f"         Count: {result['count']} events ({result['size_bytes']} bytes)")
