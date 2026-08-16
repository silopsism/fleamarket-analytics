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
| `app.py` | **The server.** FastAPI: `/` serves the dashboard (with an injected link banner), `/team/{id}` analyzes any FPL team **with a model-based transfer suggester** (budget/bank/3-per-club respected), `/team` is the ID-entry form, `/paste` is a manual squad builder (dropdown picker; `?mode=text` for free text; works pre-deadline while API picks are private). |
| `model.py` | Scoring model. `app.py` and `dashboard.py` exec it up to the `# --- SCORES-END ---` marker; run directly it also prints rankings + runs an optimizer (needs `pulp`). Imports `minutes.py`. |
| `minutes.py` | Expected-minutes subsystem (availability, depth rules, crowd signal, curated overrides). Run directly for the weekly crowd-vs-model discrepancy report. |
| `xmins_overrides.json` | Curated minutes facts with reasons/review triggers — edited from the project session, deploy alongside. |
| `context_adjustments.json` | Summer-2026 movers whose attack rates get a destination-club adjustment — deploy alongside; entries retire when current-season data takes over. |
| `dashboard.py` | Regenerates `dashboard.html` from the data files. Run after every data refresh. |
| `dashboard.html` | The **public** dashboard (value scatter + fixture heatmap only). Fully self-contained. |
| `my_dashboard.html` | David's **personal** dashboard (adds his squad table + squad markers). Deliberately not routed by `app.py` — do NOT add a static-file mount that would expose it; it stays private for local/artifact viewing. |
| `bootstrap.json`, `fixtures.json` | FPL API data snapshots — the app's only state. |
| `optimizer.py`, `validate_squad.py`, `analyze.py` | CLI tools used interactively from the project session; not needed by the server but harmless to copy. |

## Deploy

```bash
pip install fastapi uvicorn pulp        # pulp is imported by model.py
uvicorn app:app --host 0.0.0.0 --port 8000
```

Wrap in whatever this server uses for services (systemd unit / container /
supervisor — your call). Single worker is plenty.

## Data refresh — now automatic (no cron needed)

As of 2026-08-16 the app refreshes itself: on startup and every 6 hours it pulls
fresh FPL API data and regenerates the dashboard in-process. If a cron job was
set up from an earlier version of this doc, it can be removed (harmless if kept).
Deployment is git-based: push to `main` on GitHub → Coolify redeploys.

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

## Updating an existing deployment (2026-08-16 update)

Already deployed once? This update ships new analytics and model fixes. Steps:

1. Copy these files from the source folder over the deployed copies:
   `app.py`, `dashboard.py`, `model.py`, `minutes.py` (NEW), `xmins_overrides.json` (NEW), `context_adjustments.json` (NEW).
   (`bootstrap.json`/`fixtures.json` can be refreshed with the cron command instead of copied.)
2. Run `python dashboard.py` in the app directory — this regenerates `dashboard.html`
   (now the **public** general-analytics page) and `my_dashboard.html` (personal — do NOT route/expose it).
3. Restart the app service.
4. Verify: homepage shows "Differentials & traps" and "Best at every price point" sections
   and NO "Squad v4/v5" section; `/paste` shows a search-and-click player picker;
   `/team/437580` page has a "Remember as my team on this device" button.

What changed since first deploy: public/personal dashboard split (privacy), differentials +
traps + price-band value tables, transfer suggester on team/paste pages, dropdown squad
picker, expected-minutes subsystem with curated overrides, transfer-context adjustments,
penalty-taker bonuses, and model calibration fixes (defcon probability, goals-conceded and
card deductions, injury regression).

## Verification checklist

1. `GET /` → dashboard renders (check a player tooltip works).
2. `GET /team/437580` → "Fleamarket Bargains" page loads.
3. `GET /team/999999999` → "Team not found" (no stack trace).
4. Cron runs → `dashboard.html` mtime updates, page shows fresh data.
