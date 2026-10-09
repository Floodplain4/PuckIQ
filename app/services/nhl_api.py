from datetime import date
from time import time
import requests

BASE = "https://api-web.nhle.com/v1"
_cache = {}

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
            'goalies': sorted([{'name': f"{x.get('firstName', {}).get('default', '')} {x.get('lastName', {}).get('default', '')}".strip(), 'games': x.get('gamesPlayed'), 'save_pct': x.get('savePct'), 'gaa': x.get('goalsAgainstAverage')} for x in club.get('goalies', [])], key=lambda x: x['games'] or 0, reverse=True)[:3],
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
    return {'game': game, 'away': teams['away'], 'home': teams['home'], 'h2h': h2h[::-1]}
