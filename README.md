# 🏒 PuckIQ — starter MVP

Derived from the application structure and styling of PitchIQ, with its MLB-specific code removed.

## Local run

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit http://127.0.0.1:8000. API: `/api/games`, health: `/health`.

## Render

Create a new **Web Service** connected to a new PuckIQ GitHub repository. Choose Python runtime and **Free** instance (if available). Build command: `pip install -r requirements.txt`. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## Scope

First milestone: daily NHL schedule, team logos, scores and game state. No prediction model or persistent database yet. NHL API is an unofficial public interface; handle outages and changes gracefully.

The HTML templates are intentionally simpler than PitchIQ's baseball-specific views. No production persistence; memory cache lasts 3 minutes and resets on Render restarts.


## Matchup analysis
Click **Explore matchup** on any game card. The `/matchup/{game_id}?day=YYYY-MM-DD` page shows season-to-date team stats, recent results, leading goalies, and earlier head-to-head meetings in the current season. The app uses NHL public web API data; some metrics may be unavailable at the start of a season. Goalie leaders are **not** confirmed starters.

Run locally alongside OpenCase:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```
