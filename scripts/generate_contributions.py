#!/usr/bin/env python3
"""Render a contribution calendar using only daily counts from GitHub."""
import argparse
import datetime as dt
import html
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

MONTHS = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')
LEVELS = ('NONE', 'FIRST_QUARTILE', 'SECOND_QUARTILE', 'THIRD_QUARTILE', 'FOURTH_QUARTILE')
QUERY = '''query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}'''


def fetch_calendar(login, now):
    token = os.environ.get('GH_TOKEN')
    if not token:
        raise ValueError('GH_TOKEN is required to fetch contributions.')
    start = dt.datetime(now.year, 1, 1, tzinfo=now.tzinfo)
    variables = {'login': login, 'from': start.isoformat(), 'to': now.isoformat()}
    request = urllib.request.Request(
        'https://api.github.com/graphql',
        data=json.dumps({'query': QUERY, 'variables': variables}).encode(),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
                 'User-Agent': 'kekotek-contribution-calendar'},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError(f'GitHub returned HTTP {error.code}; the existing chart was preserved.') from None
    if payload.get('errors'):
        raise ValueError('GitHub could not return the calendar; the existing chart was preserved.')
    return payload['data']['user']['contributionsCollection']['contributionCalendar']


def validate(calendar, today):
    start = dt.date(today.year, 1, 1)
    days = {}
    for week in calendar['weeks']:
        for day in week['contributionDays']:
            date = dt.date.fromisoformat(day['date'])
            if not start <= date <= today:
                continue
            count = day['contributionCount']
            level = day['contributionLevel']
            if date in days or type(count) is not int or count < 0 or level not in LEVELS:
                raise ValueError('Invalid or duplicate contribution data.')
            if (count == 0) != (level == 'NONE'):
                raise ValueError('Contribution count and intensity disagree.')
            days[date] = (count, LEVELS.index(level))
    if len(days) != (today - start).days + 1:
        raise ValueError('Incomplete calendar; the existing chart was preserved.')
    if sum(count for count, _ in days.values()) != calendar['totalContributions']:
        raise ValueError('The calendar total does not match its daily counts.')
    return days


def render(calendar, today, login):
    days = validate(calendar, today)
    start, end = dt.date(today.year, 1, 1), dt.date(today.year, 12, 31)
    grid_start = start - dt.timedelta(days=(start.weekday() + 1) % 7)
    columns = (end - grid_start).days // 7 + 1
    pitch, cell, left, top = 16, 12, 58, 76
    width = left + columns * pitch + 22
    total = calendar['totalContributions']
    label = f'{total:,}'.replace(',', '.')
    title = f'{label} contribuciones en {today.year}'
    updated = f'{today.day} {MONTHS[today.month - 1].lower()} {today.year}'
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="230" viewBox="0 0 {width} 230" role="img" aria-labelledby="title description">
<title id="title">{title}</title>
<desc id="description">Calendario de contribuciones de {html.escape(login)}. Cada cuadrado corresponde a un día; el verde indica su actividad. Actualizado el {updated}. Los días futuros no tienen datos.</desc>
<style>
svg{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}}
.bg{{fill:#0d1117;stroke:#30363d}}.heading{{fill:#f0f6fc;font-size:18px;font-weight:600}}.label{{fill:#8b949e;font-size:11px}}.footer{{fill:#8b949e;font-size:10px}}
.day{{stroke:#ffffff08;stroke-width:1}}.l0{{fill:#161b22}}.l1{{fill:#0e4429}}.l2{{fill:#006d32}}.l3{{fill:#26a641}}.l4{{fill:#39d353}}.future{{fill:#161b22;opacity:.35}}
@media(prefers-color-scheme:light){{.bg{{fill:#ffffff;stroke:#d0d7de}}.heading{{fill:#1f2328}}.label,.footer{{fill:#656d76}}.day{{stroke:#1f232808}}.l0,.future{{fill:#ebedf0}}.l1{{fill:#9be9a8}}.l2{{fill:#40c463}}.l3{{fill:#30a14e}}.l4{{fill:#216e39}}}}
</style>
<rect class="bg" x=".5" y=".5" width="{width - 1}" height="229" rx="9"/>
<text class="heading" x="24" y="33">{title}</text>''']
    for month, name in enumerate(MONTHS, 1):
        first = dt.date(today.year, month, 1)
        x = left + ((first - grid_start).days // 7) * pitch
        parts.append(f'<text class="label" x="{x}" y="62">{name}</text>')
    for row, name in ((1, 'Lun'), (3, 'Mié'), (5, 'Vie')):
        parts.append(f'<text class="label" x="24" y="{top + row * pitch + 10}">{name}</text>')
    date = start
    while date <= end:
        offset = (date - grid_start).days
        x, y = left + (offset // 7) * pitch, top + (offset % 7) * pitch
        if date <= today:
            count, level = days[date]
            text = f'{date.isoformat()}: {count} ' + ('contribución' if count == 1 else 'contribuciones')
            css = f'day l{level}'
        else:
            text, css = f'{date.isoformat()}: fecha futura', 'day future'
        parts.append(f'<rect class="{css}" x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2"><title>{text}</title></rect>')
        date += dt.timedelta(days=1)
    parts.append(f'<text class="footer" x="24" y="210">Actualizado el {updated}</text>')
    legend_x = width - 160
    parts.append(f'<text class="label" x="{legend_x - 40}" y="210">Menos</text>')
    for level in range(5):
        parts.append(f'<rect class="day l{level}" x="{legend_x + level * pitch}" y="200" width="{cell}" height="{cell}" rx="2"/>')
    parts.append(f'<text class="label" x="{legend_x + 87}" y="210">Más</text>')
    parts.append('</svg>\n')
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', default='kekotek')
    parser.add_argument('--output', default='assets/contributions.svg', type=Path)
    parser.add_argument('--input', type=Path, help='Optional saved contributionCalendar JSON for local previews.')
    args = parser.parse_args()
    now = dt.datetime.now(ZoneInfo('America/Santiago'))
    calendar = json.loads(args.input.read_text()) if args.input else fetch_calendar(args.user, now)
    svg = render(calendar, now.date(), args.user)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(svg, encoding='utf-8')
    temporary.replace(args.output)
    print(f'Calendar updated: {calendar["totalContributions"]} contributions in {now.year}.')


if __name__ == '__main__':
    main()
