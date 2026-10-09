from datetime import date, datetime, timezone
from time import time
import requests

BASE = "https://api-web.nhle.com/v1"
_cache = {}

def _eastern_datetime(value):
    """Convert an NHL UTC timestamp to US Eastern, with no tzdata dependency.

    US DST begins at 02:00 local standard time on the second Sunday of March
    (07:00 UTC), and ends at 02:00 local daylight time on the first Sunday
    of November (06:00 UTC). NHL dates are after the 2007 rule change.
    """
    from datetime import timedelta

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        utc_dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        utc_dt = utc_dt.astimezone(timezone.utc)
        year = utc_dt.year

        march_first = datetime(year, 3, 1, tzinfo=timezone.utc)
        first_sunday_march = 1 + (6 - march_first.weekday()) % 7
        dst_start = datetime(year, 3, first_sunday_march + 7, 7, tzinfo=timezone.utc)

        november_first = datetime(year, 11, 1, tzinfo=timezone.utc)
        first_sunday_nov = 1 + (6 - november_first.weekday()) % 7
        dst_end = datetime(year, 11, first_sunday_nov, 6, tzinfo=timezone.utc)

        offset_hours = -4 if dst_start <= utc_dt < dst_end else -5
        eastern_zone = timezone(timedelta(hours=offset_hours))
        return utc_dt.astimezone(eastern_zone)
    except (ValueError, TypeError, OverflowError):
        return None


def format_start(value):
    """Readable game start time in US Eastern, independent of Windows tzdata."""
    eastern = _eastern_datetime(value)
    if eastern is None:
        return "Time TBD"
    return eastern.strftime("%I:%M %p").lstrip("0") + " ET"


def format_game_date(value):
    """Readable Eastern calendar date, including games crossing UTC midnight."""
    eastern = _eastern_datetime(value)
    if eastern is None:
        return "Date TBD"
    return f"{eastern.strftime('%A, %B')} {eastern.day}, {eastern.year}"


def localized(value):
    return value.get("default", "") if isinstance(value, dict) else (value or "")


def player_photo(player, team, season):
    if player.get("headshot"):
        return player["headshot"]
    pid = player.get("playerId") or player.get("id")
    if not pid:
        return None
    return f"https://assets.nhle.com/mugs/nhl/{season}/{team}/{pid}.png"


def get_games(day: str | None = None):
    day = day or date.today().isoformat()
    key = f"score:{day}"
    cached = _cache.get(key)
    if cached and time() - cached[0] < 180:
        return cached[1]
    response = requests.get(f"{BASE}/score/{day}", timeout=15)
    response.raise_for_status()
    data = response.json()
    games = []
    for game in data.get("games", []):
        away = game.get("awayTeam") or {}
        home = game.get("homeTeam") or {}
        games.append({
            "id": game.get("id"),
            "start_time_utc": game.get("startTimeUTC"),
            "time_label": format_start(game.get("startTimeUTC")),
            "date_label": format_game_date(game.get("startTimeUTC")),
            "state": game.get("gameState", "UNKNOWN"),
            "venue": (game.get("venue") or {}).get("default", ""),
            "away": {"abbr": away.get("abbrev", "???"), "name": (away.get("name") or {}).get("default", away.get("abbrev", "Away")), "score": away.get("score"), "logo": away.get("logo")},
            "home": {"abbr": home.get("abbrev", "???"), "name": (home.get("name") or {}).get("default", home.get("abbrev", "Home")), "score": home.get("score"), "logo": home.get("logo")},
        })
    _cache[key] = (time(), games)
    return games


def fetch_json(path: str, ttl: int = 900):
    """Small process-local TTL cache; safe to lose on Render restarts."""
    key = f"nhl:{path}"
    cached = _cache.get(key)
    if cached and time() - cached[0] < ttl:
        return cached[1]
    response = requests.get(f"{BASE}/{path}", timeout=12)
    response.raise_for_status()
    payload = response.json()
    _cache[key] = (time(), payload)
    return payload


def get_matchup(game_id: int, day: str):
    """Use NHL standings, club stats and recent schedule. No fabricated metrics."""
    games = get_games(day)
    game = next((g for g in games if g['id'] == game_id), None)
    if game is None:
        return None
    standings = fetch_json(f"standings/{day}", 1800).get('standings', [])
    standings_by_team = {row.get('teamAbbrev', {}).get('default'): row for row in standings}
    teams = {}
    season_start = int(day[:4]) if int(day[5:7]) >= 7 else int(day[:4]) - 1
    season = f"{season_start}{season_start+1}"
    for side in ('away', 'home'):
        abbr = game[side]['abbr']
        row = standings_by_team.get(abbr, {})
        # Club stats may be missing early in a season; avoid failing entire page.
        try:
            club = fetch_json(f"club-stats/{abbr}/now", 1800)
        except requests.RequestException:
            club = {}
        try:
            schedule = fetch_json(f"club-schedule-season/{abbr}/now", 1800)
            previous = []
            for match in schedule.get('games', []):
                if match.get('gameDate', '') >= day or match.get('gameState') not in ('OFF', 'FINAL'):
                    continue
                is_home = match.get('homeTeam', {}).get('abbrev') == abbr
                own = match.get('homeTeam' if is_home else 'awayTeam', {})
                opp = match.get('awayTeam' if is_home else 'homeTeam', {})
                if own.get('score') is None or opp.get('score') is None:
                    continue
                previous.append({'date': match.get('gameDate'), 'opponent': opp.get('abbrev'), 'goals_for': own['score'], 'goals_against': opp['score'], 'result': 'W' if own['score'] > opp['score'] else 'L', 'opponent_id': opp.get('id')})
            previous = previous[-10:][::-1]
        except requests.RequestException:
            previous = []
        gp = row.get('gamesPlayed') or 0
        teams[side] = {
            **game[side],
            'record': f"{row.get('wins', 0)}-{row.get('losses', 0)}-{row.get('otLosses', 0)}" if gp else '—',
            'points': row.get('points') if gp else None,
            'games_played': gp,
            'goals_per_game': round(row['goalFor'] / gp, 2) if gp and row.get('goalFor') is not None else None,
            'goals_against_per_game': round(row['goalAgainst'] / gp, 2) if gp and row.get('goalAgainst') is not None else None,
            'power_play_pct': round(row['powerPlayPct'] * 100, 1) if row.get('powerPlayPct') is not None else None,
            'penalty_kill_pct': round(row['penaltyKillPct'] * 100, 1) if row.get('penaltyKillPct') is not None else None,
            'recent': previous,
            'recent_record': f"{sum(g['result'] == 'W' for g in previous)}-{sum(g['result'] == 'L' for g in previous)}" if previous else '—',
            'goalies': sorted([{'name': f"{localized(x.get('firstName'))} {localized(x.get('lastName'))}".strip(), 'games': x.get('gamesPlayed'), 'save_pct': x.get('savePct'), 'gaa': x.get('goalsAgainstAverage'), 'photo': player_photo(x, abbr, season), 'number': x.get('sweaterNumber')} for x in club.get('goalies', [])], key=lambda x: x['games'] or 0, reverse=True)[:3],
            'skaters': sorted([{'name': f"{localized(x.get('firstName'))} {localized(x.get('lastName'))}".strip(), 'points': x.get('points'), 'goals': x.get('goals'), 'assists': x.get('assists'), 'photo': player_photo(x, abbr, season), 'number': x.get('sweaterNumber'), 'position': x.get('positionCode')} for x in club.get('skaters', [])], key=lambda x: x['points'] or 0, reverse=True)[:5],
        }
    # Historical head-to-head from away team's schedule; results only before selected game.
    try:
        schedule = fetch_json(f"club-schedule-season/{game['away']['abbr']}/now", 1800)
        h2h = []
        for m in schedule.get('games', []):
            if m.get('gameDate', '') >= day or m.get('gameState') not in ('OFF', 'FINAL'):
                continue
            if {m.get('homeTeam', {}).get('abbrev'), m.get('awayTeam', {}).get('abbrev')} != {game['home']['abbr'], game['away']['abbr']}:
                continue
            h2h.append({'date': m.get('gameDate'), 'home': m['homeTeam'].get('abbrev'), 'away': m['awayTeam'].get('abbrev'), 'home_score': m['homeTeam'].get('score'), 'away_score': m['awayTeam'].get('score')})
    except requests.RequestException:
        h2h = []
    from app.services.prediction import predict
    # Only show pregame estimates for future dates. Historical standings would leak results.
    prediction = predict(teams['away'], teams['home']) if day >= date.today().isoformat() and game['state'] in ('FUT', 'PRE') else None
    return {'game': game, 'away': teams['away'], 'home': teams['home'], 'h2h': h2h[::-1], 'season': season, 'prediction': prediction} 
