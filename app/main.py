from datetime import date
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.services.nhl_api import get_games, get_matchup

app = FastAPI(title="PuckIQ | NHL Matchup Intelligence")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request, day: str | None = None):
    if day:
        try:
            date.fromisoformat(day)
        except ValueError:
            raise HTTPException(400, "Use YYYY-MM-DD for day")
    selected = day or date.today().isoformat()
    error = None
    try:
        games = get_games(selected)
    except Exception:
        games = []
        error = "NHL data is temporarily unavailable. Try again shortly."
    return templates.TemplateResponse("index.html", {"request": request, "games": games, "day": selected, "error": error})

@app.get("/api/games")
def games(day: str | None = None):
    if day:
        try: date.fromisoformat(day)
        except ValueError: raise HTTPException(400, "Use YYYY-MM-DD for day")
    try: return {"date": day or date.today().isoformat(), "games": get_games(day)}
    except Exception: raise HTTPException(503, "NHL API unavailable")

@app.get("/health")
def health():
    return {"status": "ok", "app": "puckiq"}


@app.get("/matchup/{game_id}", response_class=HTMLResponse)
def matchup(request: Request, game_id: int, day: str):
    try:
        date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "Use YYYY-MM-DD for day")
    try:
        data = get_matchup(game_id, day)
    except Exception:
        raise HTTPException(503, "NHL data is temporarily unavailable. Please try again.")
    if data is None:
        raise HTTPException(404, "Game not found on selected date")
    return templates.TemplateResponse("matchup.html", {"request": request, **data, "day": day})
