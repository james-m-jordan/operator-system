#!/usr/bin/env python3
"""Evaluate numeric five-field cron schedules in their configured IANA timezone."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def cron_values(field: str, low: int, high: int) -> set[int]:
    values = set()
    for item in field.split(','):
        base, slash, step_text = item.partition('/')
        step = int(step_text) if slash else 1
        if step <= 0:
            raise ValueError("cron steps must be positive")
        if base == '*':
            first, last = low, high
        elif '-' in base:
            first, last = map(int, base.split('-'))
        else:
            first = int(base)
            last = high if slash else first
        if first < low or last > high or first > last:
            raise ValueError(f"cron value outside {low}..{high}: {field}")
        values.update(range(first, last + 1, step))
    return values


def parse_cron(cron: str) -> tuple[list[str], list[set[int]]]:
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError("expected five numeric cron fields")
    values = [cron_values(field, low, high) for field, (low, high) in zip(fields, [(0,59),(0,23),(1,31),(1,12),(0,7)])]
    values[4] = {value % 7 for value in values[4]}
    return fields, values


def latest_due(cron: str, zone: str, before: datetime) -> datetime:
    fields, values = parse_cron(cron)
    minutes, hours, days, months, weekdays = values
    tz = ZoneInfo(zone)
    local_day = before.astimezone(tz).date()
    # Include leap-day schedules; invalid combinations fail visibly.
    for offset in range(1462):
        day = local_day - timedelta(days=offset)
        if day.month not in months:
            continue
        dom, dow = day.day in days, (day.weekday() + 1) % 7 in weekdays
        day_matches = (dom and dow) if fields[2].startswith('*') or fields[4].startswith('*') else (dom or dow)
        if not day_matches:
            continue
        candidates = []
        for hour in hours:
            for minute in minutes:
                for fold in (0, 1):
                    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz, fold=fold)
                    utc = local.astimezone(timezone.utc)
                    roundtrip = utc.astimezone(tz)
                    if roundtrip.replace(tzinfo=None) == local.replace(tzinfo=None) and utc <= before:
                        candidates.append(utc)
        if candidates:
            return max(candidates)
    raise ValueError("no scheduled occurrence in the last four years")
