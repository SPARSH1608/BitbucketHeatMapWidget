"""Fetch Bitbucket commit activity for the authenticated user and render a
GitHub-style contribution heatmap (SVG) plus a stats.json summary.

Auth: Bitbucket's scoped API tokens use a bearer token, not basic auth,
read from BITBUCKET_API_TOKEN. The commit author is matched by Bitbucket
account UUID (not by name/email), so it works regardless of what git
identity was used to make the commit.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import requests

API = "https://api.bitbucket.org/2.0"
DAYS = 371  # 53 weeks, matches GitHub's profile heatmap span

API_TOKEN = os.environ["BITBUCKET_API_TOKEN"]
WORKSPACES_ENV = os.environ.get("BITBUCKET_WORKSPACES", "").strip()

session = requests.Session()
session.headers["Authorization"] = f"Bearer {API_TOKEN}"


def get_json(url, params=None):
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def paginate(url, params=None):
    while url:
        data = get_json(url, params=params)
        params = None  # `next` already includes query params
        for item in data.get("values", []):
            yield item
        url = data.get("next")


def get_own_uuid():
    return get_json(f"{API}/user")["uuid"]


def get_workspaces():
    if WORKSPACES_ENV:
        return [w.strip() for w in WORKSPACES_ENV.split(",") if w.strip()]
    return [w["slug"] for w in paginate(f"{API}/workspaces", {"role": "member", "pagelen": 100})]


def get_repos(workspace):
    url = f"{API}/repositories/{workspace}"
    params = {"role": "member", "pagelen": 100, "fields": "values.slug,next"}
    return [r["slug"] for r in paginate(url, params)]


def parse_commit_date(raw):
    # e.g. "2026-09-04T12:34:56+00:00"
    return datetime.fromisoformat(raw).date()


def collect_commit_counts(own_uuid, cutoff):
    daily_counts = {}
    repos_touched = set()

    for workspace in get_workspaces():
        try:
            repo_slugs = get_repos(workspace)
        except requests.HTTPError as e:
            print(f"skip workspace {workspace}: {e}", file=sys.stderr)
            continue

        for slug in repo_slugs:
            url = f"{API}/repositories/{workspace}/{slug}/commits"
            params = {
                "pagelen": 100,
                "fields": "values.author,values.date,next",
            }
            try:
                for commit in paginate(url, params):
                    commit_date = parse_commit_date(commit["date"])
                    if commit_date < cutoff:
                        break  # commits are newest-first; nothing older is relevant
                    author_user = (commit.get("author") or {}).get("user") or {}
                    if author_user.get("uuid") != own_uuid:
                        continue
                    daily_counts[commit_date] = daily_counts.get(commit_date, 0) + 1
                    repos_touched.add(f"{workspace}/{slug}")
            except requests.HTTPError as e:
                print(f"skip repo {workspace}/{slug}: {e}", file=sys.stderr)
                continue

    return daily_counts, repos_touched


def build_week_grid(end_date, start_date):
    # Align the grid start back to the preceding Sunday so columns are full weeks.
    offset = (start_date.weekday() + 1) % 7
    grid_start = start_date - timedelta(days=offset)

    weeks = []
    cursor = grid_start
    while cursor <= end_date:
        week = [cursor + timedelta(days=i) for i in range(7)]
        weeks.append(week)
        cursor += timedelta(days=7)
    return weeks


def level_for(count):
    if count == 0:
        return 0
    if count <= 2:
        return 1
    if count <= 4:
        return 2
    if count <= 6:
        return 3
    return 4


PALETTE = {
    "light": {
        "bg": "#ffffff",
        "text": "#24292f",
        "muted": "#57606a",
        "levels": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    },
    "dark": {
        "bg": "#0d1117",
        "text": "#c9d1d9",
        "muted": "#8b949e",
        "levels": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
    },
}

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAY_LABELS = {1: "Mon", 3: "Wed", 5: "Fri"}


def render_svg(weeks, daily_counts, total_commits, total_repos, theme):
    colors = PALETTE[theme]
    cell = 11
    gap = 3
    step = cell + gap
    left_margin = 30
    top_margin = 42

    width = left_margin + len(weeks) * step
    height = top_margin + 7 * step + 30

    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">'
    )
    parts.append(f'<rect width="100%" height="100%" fill="{colors["bg"]}" rx="6"/>')

    parts.append(
        f'<text x="{left_margin}" y="16" font-size="13" font-weight="600" fill="{colors["text"]}">'
        f"Bitbucket Contributions</text>"
    )
    parts.append(
        f'<text x="{left_margin}" y="30" font-size="11" fill="{colors["muted"]}">'
        f"{total_commits} commits in the last year across {total_repos} repositories</text>"
    )

    last_month = None
    for col, week in enumerate(weeks):
        x = left_margin + col * step
        month = week[0].month
        if month != last_month:
            parts.append(
                f'<text x="{x}" y="{top_margin - 6}" font-size="10" fill="{colors["muted"]}">'
                f"{MONTH_NAMES[month - 1]}</text>"
            )
            last_month = month

    for row, label in WEEKDAY_LABELS.items():
        y = top_margin + row * step + cell - 1
        parts.append(f'<text x="0" y="{y}" font-size="9" fill="{colors["muted"]}">{label}</text>')

    for col, week in enumerate(weeks):
        x = left_margin + col * step
        for row, day in enumerate(week):
            y = top_margin + row * step
            if day > date.today():
                continue
            count = daily_counts.get(day, 0)
            color = colors["levels"][level_for(count)]
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}">'
                f"<title>{day.isoformat()}: {count} commit{'s' if count != 1 else ''}</title></rect>"
            )

    legend_y = top_margin + 7 * step + 14
    parts.append(f'<text x="{left_margin}" y="{legend_y + 8}" font-size="10" fill="{colors["muted"]}">Less</text>')
    lx = left_margin + 32
    for lvl, color in enumerate(colors["levels"]):
        parts.append(f'<rect x="{lx}" y="{legend_y}" width="{cell}" height="{cell}" rx="2" fill="{color}"/>')
        lx += step
    parts.append(f'<text x="{lx + 4}" y="{legend_y + 8}" font-size="10" fill="{colors["muted"]}">More</text>')

    parts.append("</svg>")
    return "".join(parts)


def main():
    end_date = date.today()
    start_date = end_date - timedelta(days=DAYS - 1)

    own_uuid = get_own_uuid()
    daily_counts, repos_touched = collect_commit_counts(own_uuid, start_date)
    weeks = build_week_grid(end_date, start_date)
    total_commits = sum(daily_counts.values())

    for theme in ("light", "dark"):
        svg = render_svg(weeks, daily_counts, total_commits, len(repos_touched), theme)
        filename = "heatmap.svg" if theme == "light" else "heatmap-dark.svg"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(svg)

    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_commits": total_commits,
        "total_repositories": len(repos_touched),
        "repositories": sorted(repos_touched),
        "daily_counts": {d.isoformat(): c for d, c in sorted(daily_counts.items())},
    }
    with open("stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    print(f"total_commits={total_commits} total_repositories={len(repos_touched)}")


if __name__ == "__main__":
    main()
