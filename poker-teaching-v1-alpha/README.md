# Poker Teaching System – v0.4 (Full with tests)

Teaching-first scaffold with Django + DRF + OpenAPI, decoupled domain, CI baseline,
docs site, PostgreSQL option, annotations in teaching view, and PR test suite.

## Quickstart (SQLite default)
```bash
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev]'
cd apps/web-django
python manage.py makemigrations api
python manage.py migrate
python manage.py runserver
```
Open:
- Demo: http://127.0.0.1:8000/
- API docs: http://127.0.0.1:8000/api/docs
- Teaching view: http://127.0.0.1:8000/teaching/hand/<hand_id>

## Key API Routes (v0.4+)
- `POST /api/v1/session/start`: create a HU session
- `GET  /api/v1/session/<session_id>/state`: session view
  - `stacks`: carry-over stacks before blinds (P0,P1)
  - `stacks_after_blinds`: current hand stacks after blinds (nullable when no hand yet)
- `POST /api/v1/session/next`: advance to next hand in the session
- `POST /api/v1/hand/start`: start a hand in a session (optional `seed`)
- `GET  /api/v1/hand/<hand_id>/state`: query current hand state + `legal_actions`
- `POST /api/v1/hand/<hand_id>/act`: apply an action (`check/call/bet/raise/fold/allin`)
- `GET  /api/v1/hand/<hand_id>/replay`: fetch replay payload (primary route)
  - Compat alias: `GET /api/v1/replay/<hand_id>`
- `POST /api/v1/suggest`: get a minimal suggestion for `{hand_id, actor}`
  - Response: `{hand_id, actor, suggested{action,amount?}, rationale[], policy}`
  - Errors: `404 not found`, `409 not actor's turn / hand ended`, `422 cannot produce a legal suggestion`

## PostgreSQL (optional)
```bash
docker compose -f infra/docker-compose.yml up -d
cp .env.example .env
export $(cat .env | xargs)   # Windows: set manually
cd apps/web-django && python manage.py migrate
```

## Tests & Coverage
```bash
pytest
coverage run -m pytest
coverage report --fail-under=60
coverage report --include "packages/poker_core/*" --fail-under=80
```

## Docs (MkDocs)
```bash
pip install mkdocs
mkdocs serve -a 127.0.0.1:9000
```
