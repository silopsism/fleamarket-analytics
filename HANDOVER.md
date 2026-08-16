# Handover: Fleamarket Analytics → home server deployment

**From:** the FPL project session (working dir `C:\Code\fpl` on David's Windows machine)
**To:** the home-server session
**Goal:** host this FPL analytics app so David can view it from home or away, and
friends can paste their FPL team IDs to get their squads analyzed.

## What this is

A small self-contained FPL (Fantasy Premier League) analytics toolkit for the
2026/27 season. It scores every player from prior-season Opta rates (xG/xA/clean
sheets/defensive contributions) via the free official FPL API, renders a static
dashboard, and serves a per-team analysis page. No accounts, no secrets, no
database — two JSON files are the entire state.

## Files to deploy (copy the whole folder)

| File | Role |
|---|---|
| `app.py` | **The server.** FastAPI: `/` serves the dashboard, `/team/{id}` analyzes any FPL team, `/team` is the ID-entry form. |
| `model.py` | Scoring model. `app.py` and `dashboard.py` exec it up to the `# --- SCORES-END ---` marker; run directly it also prints rankings + runs an optimizer (needs `pulp`). |
| `dashboard.py` | Regenerates `dashboard.html` from the data files. Run after every data refresh. |
| `dashboard.html` | The static dashboard (value scatter, fixture heatmap, squad table). Fully self-contained. |
| `bootstrap.json`, `fixtures.json` | FPL API data snapshots — the app's only state. |
| `optimizer.py`, `validate_squad.py`, `analyze.py` | CLI tools used interactively from the project session; not needed by the server but harmless to copy. |

## Deploy

```bash
pip install fastapi uvicorn pulp        # pulp is imported by model.py
uvicorn app:app --host 0.0.0.0 --port 8000
```

Wrap in whatever this server uses for services (systemd unit / container /
supervisor — your call). Single worker is plenty.

## Data refresh (cron)

Prices/injuries change daily during the season; the dashboard bakes data in at
generation time. Schedule this daily (e.g. 07:00), from the app directory:

```bash
curl -s "https://fantasy.premierleague.com/api/bootstrap-static/" -o bootstrap.json \
 && curl -s "https://fantasy.premierleague.com/api/fixtures/" -o fixtures.json \
 && python dashboard.py
```

`app.py` auto-reloads its model cache when `bootstrap.json`'s mtime changes; no
restart needed.

## Access requirements (your discretion how)

- David wants it reachable **away from home** — reverse proxy with HTTPS, or
  Tailscale/VPN if that's the house pattern. If exposed publicly, consider basic
  rate limiting: `/team/{id}` makes 1–2 outbound calls to the FPL API per hit,
  and we want to stay polite to their servers. No auth is built in; the app is
  read-only and holds nothing sensitive.
- Friends will be given the `/team` URL — that flow must work without any login.

## Behavior notes

- **Team picks are private until each gameweek's deadline** (FPL API design).
  Before the GW1 deadline (Fri 2026-08-21 17:30 UTC) `/team/{id}` shows the team
  name + an explanation; after it, full squad analysis with upgrade suggestions.
  This is expected, not a bug.
- David's team ID is **437580** ("Fleamarket Bargains") — good test case.
- The model intentionally underrates players who were part-timers last season
  (documented Phase 1 limitation); a Phase 2 model will replace `model.py`
  in-place later in the season — the exec-marker interface will stay stable, so
  deployment shouldn't need changes beyond pulling the new file.

## Verification checklist

1. `GET /` → dashboard renders (check a player tooltip works).
2. `GET /team/437580` → "Fleamarket Bargains" page loads.
3. `GET /team/999999999` → "Team not found" (no stack trace).
4. Cron runs → `dashboard.html` mtime updates, page shows fresh data.
