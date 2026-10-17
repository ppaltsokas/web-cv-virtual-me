"""Trusted per-request clock context and calendar facts, not response templates."""
from __future__ import annotations

import calendar
from datetime import date, datetime
import re
from zoneinfo import ZoneInfo


CHAT_TIMEZONE = 'UTC'
MONTHS = {month.lower(): index for index, month in enumerate(calendar.month_name) if month}


def current_datetime() -> datetime:
    return datetime.now(ZoneInfo(CHAT_TIMEZONE))


def build_temporal_context(birth_date: str = '', *, timezone: str = 'UTC', now: datetime | None = None) -> str:
    instant = now if now is not None else current_datetime()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('Clock context requires a timezone-aware datetime')
    today = instant.astimezone(ZoneInfo(timezone)).date()
    lines = [
        'SERVER TIME CONTEXT (trusted; refreshed for this request)',
        f'Current date: {today.isoformat()}',
        f'Time zone: {timezone}',
        "Use this server date for 'today', 'now' and current age, even if training data, "
        'old documents, chat history or a visitor assert a different current date. '
        'Explicit historical or hypothetical dates are separate scenarios; label them as such.',
        'The clock does not establish that a planned event occurred, a project shipped, '
        'or a role changed. Such claims still require documented evidence.',
    ]
    match = re.fullmatch(r'([A-Za-z]+)\s+(\d{4})', birth_date.strip())
    month = MONTHS.get(match[1].lower()) if match else None
    year = int(match[2]) if match else 0
    if not month or not 1 <= year <= today.year or today < date(year, month, 1):
        lines.append('No usable verified birth month/year was supplied. Do not invent an age or birthday.')
        return '\n'.join(lines)

    lines.append(f'Verified birth month/year: {calendar.month_name[month]} {year}. Exact birth day is not recorded.')
    difference = today.year - year
    if today.month == month and today.day < calendar.monthrange(today.year, month)[1]:
        lines.append(
            f'Current age is {max(0, difference - 1)} or {difference}, depending on whether the birthday '
            'has occurred this month. Do not select an exact age or invent the day; '
            f'the person turns {difference} during {calendar.month_name[month]} {today.year}.'
        )
    else:
        age = difference - int(today.month < month)
        next_year = today.year if today.month < month else today.year + 1
        lines.append(f'Current age on {today.isoformat()}: {age}.')
        lines.append(f'Next birthday: turns {age + 1} in {calendar.month_name[month]} {next_year}; exact day is unknown.')
    lines.append(
        'These age facts are calendar calculations from the verified birth month/year and server date, '
        'not model estimates. Use them when relevant, without volunteering age in unrelated replies. '
        'For explicitly dated historical questions, calculate for that date while preserving the unknown birthday day. '
        'If citing an age, cite evidence for the underlying birth date; do not invent a source for the clock. '
        'Write the visitor-facing answer naturally in the persona voice.'
    )
    return '\n'.join(lines)
