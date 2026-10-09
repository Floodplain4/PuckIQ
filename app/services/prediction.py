"""Transparent, regularized heuristic probabilities, not a trained betting model.

All inputs are pregame aggregates. This version deliberately excludes unconfirmed
starting goalies and uses a neutral 50/50 fallback for insufficient data.
"""
from math import exp


def _number(value, fallback):
    try:
        return float(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def predict(away, home):
    ag = int(away.get('games_played') or 0)
    hg = int(home.get('games_played') or 0)
    if min(ag, hg) < 3:
        return {'available': False, 'away_pct': None, 'home_pct': None,
                'reasons': [], 'components': [], 'confidence': 'Insufficient data',
                'message': 'Both teams need at least 3 completed games this season.'}

    # All metrics are damped early in the season to reduce wild estimates.
    reliability = min(1.0, min(ag, hg) / 20.0)
    def win_rate(t):
        r = t.get('record', '0-0-0').split('-')
        try:
            w, l, ot = [int(x) for x in r]
            return (w + 0.5 * ot) / max(1, w + l + ot)
        except (ValueError, TypeError):
            return .5

    a_wr, h_wr = win_rate(away), win_rate(home)
    a_gd = _number(away.get('goals_per_game'), 3) - _number(away.get('goals_against_per_game'), 3)
    h_gd = _number(home.get('goals_per_game'), 3) - _number(home.get('goals_against_per_game'), 3)
    a_pp, h_pp = _number(away.get('power_play_pct'), 20), _number(home.get('power_play_pct'), 20)
    a_pk, h_pk = _number(away.get('penalty_kill_pct'), 80), _number(home.get('penalty_kill_pct'), 80)

    def recent_rate(t):
        games = t.get('recent', [])
        if not games:
            return .5
        return sum(g.get('result') == 'W' for g in games) / len(games)

    # Score expressed as home-team log odds. Home advantage is a modest prior.
    components = [
        ('Home ice', 0.16),
        ('Season results', reliability * 1.6 * (h_wr - a_wr)),
        ('Goal differential', reliability * 0.40 * max(-3, min(3, h_gd - a_gd))),
        ('Recent form', reliability * 0.40 * (recent_rate(home) - recent_rate(away))),
        ('Special teams', reliability * 0.012 * max(-30, min(30, (h_pp - a_pp) + (h_pk - a_pk)))),
    ]
    score = sum(x for _, x in components)
    home_pct = round(100 / (1 + exp(-score)))
    home_pct = min(85, max(15, home_pct))
    factors = sorted(components, key=lambda x: abs(x[1]), reverse=True)
    reasons = [{'label': label, 'team': home['abbr'] if value > 0 else away['abbr'],
                'detail': 'Favors ' + (home['name'] if value > 0 else away['name'])}
               for label, value in factors if abs(value) >= .045][:4]
    return {'available': True, 'away_pct': 100-home_pct, 'home_pct': home_pct,
            'reasons': reasons, 'components': [{'name': k, 'impact': round(v, 3)} for k,v in components],
            'confidence': 'Early season' if min(ag, hg) < 15 else 'Season sample',
            'message': 'Experimental heuristic, not a calibrated forecast. No starting-goalie or injury adjustment.'}
