"""Tiny time helpers. All timestamps in this app are naive local ISO strings
("YYYY-MM-DDTHH:MM"). The demo runs on a frozen "port clock" stored in
meta.now so plans are reproducible no matter when you run it.
"""
from datetime import datetime, timedelta

FMT = "%Y-%m-%dT%H:%M"


def parse(s: str) -> datetime:
    return datetime.strptime(s, FMT)


def iso(dt: datetime) -> str:
    return dt.strftime(FMT)


def add_min(s: str, minutes: int) -> str:
    return iso(parse(s) + timedelta(minutes=minutes))


def diff_min(a: str, b: str) -> int:
    """Minutes from b to a (a - b)."""
    return int((parse(a) - parse(b)).total_seconds() // 60)


def later(a: str, b: str) -> str:
    return a if a >= b else b


def hhmm(s: str) -> str:
    return s[11:16]
