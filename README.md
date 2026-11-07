# RaktaSetu — Voice-first, multilingual emergency blood donor network

> "Rakta" (blood) + "Setu" (bridge). A real-time platform that connects patients' families with nearby
> compatible blood donors in minutes — usable by anyone who can **speak**, in **English, ಕನ್ನಡ, हिन्दी, தமிழ், తెలుగు**.

![CI/CD](https://github.com/<your-username>/raktasetu/actions/workflows/ci-cd.yml/badge.svg)

## The problem

In Indian cities, families still find blood by forwarding WhatsApp messages: "URGENT B+ needed at Victoria Hospital".
These messages go stale, reach people who are not eligible (wrong group, donated last month, 40 km away), and nobody
knows if a donor is actually coming. People who cannot read English, or cannot read at all, are left out completely.

## What RaktaSetu does differently

| Feature | How it works |
|---|---|
| **AI voice assistant (5 languages)** | On first open the user picks a language. A conversational assistant then logs them in (phone + OTP), and asks one question at a time: blood group, units, hospital, urgency. Speech-to-text and text-to-speech in the browser, with server-side gTTS fallback for Kannada/Tamil/Telugu. A non-literate user can finish the whole flow by voice. |
| **Multilingual NLU** | Rule-based extractor understands "ಬಿ ಪಾಸಿಟಿವ್", "बी पॉज़िटिव", "O negative", spoken digits ("nine eight seven..."), Indic numerals, hospital names in native scripts, yes/no in each language. |
| **ML donor ranking** | A RandomForest model predicts each donor's probability of accepting (distance, hour, reliability, past acceptance, days since donation...). Donors are alerted in **waves** ranked by ML probability + distance + reliability. |
| **No-show risk model** | A second model predicts no-show risk when a donor commits, shown to the family and staff. |
| **Demand forecasting** | GradientBoosting model forecasts 7-day blood demand per blood group per city zone for blood-bank planning. |
| **Live escalation engine** | Background worker: if donors don't respond within the window, the alert expires and the next wave goes out; the search radius widens 5 → 10 → 25 → 50 km; when donors run out, nearest blood banks with compatible stock are shown. |
| **Real-time everything** | WebSockets push alerts to donors (with countdown, sound and spoken alert) and live status to the family's tracker (timeline, map, progress). Optional Telegram bot for real phone notifications. |
| **Medical rules built in** | ABO/Rh compatibility matrix, 90-day (men) / 120-day (women) donation gap, only "available" donors are alerted. |
| **Privacy & safety** | Donor phone numbers are masked until the donor accepts; donor home locations never shown. Report button for "asked for money" / fake profile; admin can suspend. Clear "never pay for blood" warning. |
| **Operations dashboard** | KPIs, live event feed, supply vs demand chart, ML forecast, model metrics and feature importance, fraud reports. |

## Architecture

```
            ┌──────────────┐   /api, /ws    ┌───────────────┐   HTTP   ┌──────────────┐
 Browser ──▶│  frontend    │ ─────────────▶ │   backend     │ ───────▶ │  ml-service  │
 (voice UI) │ nginx:alpine │   (reverse     │ FastAPI +     │          │ FastAPI +    │
            │  :8080       │    proxy)      │ WebSockets    │          │ scikit-learn │
            └──────────────┘                │ :8000         │          │ :8001        │
                                            └──┬─────────┬──┘          └──────────────┘
                                               │         │
                                     ┌─────────▼──┐  ┌───▼──────┐
                                     │ PostgreSQL │  │  Redis   │
                                     │  16        │  │  7 (OTP, │
                                     │ (data)     │  │ sessions)│
                                     └────────────┘  └──────────┘
```

Five containers orchestrated with Docker Compose. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

| Layer | Tech |
|---|---|
| Frontend | HTML/CSS/vanilla JS, Web Speech API, Leaflet maps, Chart.js, served by nginx |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, WebSockets, JWT auth, gTTS |
| ML | scikit-learn (RandomForest, GradientBoosting), pandas, joblib |
| Data | PostgreSQL 16, Redis 7 (falls back to SQLite / in-memory for local dev) |
| DevOps | Docker, Docker Compose, GitHub Actions, GitHub Container Registry |

## Run it (one command)

```bash
git clone https://github.com/<your-username>/raktasetu.git
cd raktasetu
cp .env.example .env        # optional
docker compose up --build
```

Open **http://localhost:8080**. API docs (Swagger): **http://localhost:8000/docs**. ML service: **http://localhost:8001/docs**.

```bash
docker compose ps                    # 5 running containers
docker images | grep raktasetu       # 3 custom images
./scripts/smoke_test.sh              # end-to-end test against the running stack
docker compose down -v               # stop and wipe data
```

### Demo accounts (DEMO_MODE=true)

OTP is shown on screen in demo mode (no SMS gateway needed).

| Role | Phone | Use |
|---|---|---|
| Admin | 9999999999 | Operations dashboard |
| Blood-centre staff | 8888888888 | Confirm donations |
| 30 seeded donors | 90000000xx | Donor console (or use "Demo login" on the Donor page) |
| Any other 10-digit number | — | New requester / new donor |

## CI/CD pipeline (GitHub Actions)

`.github/workflows/ci-cd.yml` runs on every push and pull request to `main`:

```
 backend-test ──┐
 ml-test ───────┼──▶ docker-integration ──▶ publish (GHCR) ──▶ deploy
 frontend-check ┘     build 3 images,        backend, frontend,   SSH / Render hook
                      compose up 5 containers, ml images tagged    (skips cleanly if
                      run smoke_test.sh        latest + sha-xxxx    no secrets set)
```

1. **backend-test** — ruff lint + 68 pytest tests (blood compatibility, NLU in 5 languages, voice dialogue, full emergency flow, escalation, fraud reports).
2. **ml-test** — trains all three models, enforces a **model quality gate** (AUC ≥ 0.65 / 0.60), runs tests, uploads `metrics.json` as an artifact.
3. **frontend-check** — JavaScript syntax check.
4. **docker-integration** — builds all images, starts the full 5-container stack, runs the end-to-end smoke test (OTP login → create request → ML-ranked donors alerted → Kannada assistant), prints logs on failure.
5. **publish** — pushes `raktasetu-backend`, `raktasetu-frontend`, `raktasetu-ml` to GitHub Container Registry (`ghcr.io/<user>/...`) with `latest` and `sha-<commit>` tags, using layer caching.
6. **deploy** — if `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY` secrets are set, SSHes into a server and runs `docker compose pull && up -d`; or calls a `RENDER_DEPLOY_HOOK`. Writes a deployment summary.

Pull requests run steps 1–4 only (no publishing).

## Push to GitHub

```bash
git remote add origin https://github.com/<your-username>/raktasetu.git
git branch -M main
git push -u origin main
```

Then open the **Actions** tab to watch the pipeline. After the first run, images appear under your profile → **Packages**.
Optional deploy: add repository secrets under Settings → Secrets and variables → Actions.

## Local development without Docker

```bash
cd ml-service && pip install -r requirements.txt && python -m app.train && uvicorn app.main:app --port 8001
cd backend && pip install -r requirements.txt -r requirements-dev.txt
ML_SERVICE_URL=http://localhost:8001 STATIC_DIR=../frontend uvicorn app.main:app --port 8000
# open http://localhost:8000
pytest -q
```

## Project structure

```
raktasetu/
├── backend/           FastAPI API, matching engine, voice assistant, NLU, tests
├── ml-service/        model training (train.py) + prediction API
├── frontend/          voice-first web app + nginx config
├── scripts/           smoke_test.sh
├── docs/              ARCHITECTURE.md, DEMO_SCRIPT.md
├── docker-compose.yml
└── .github/workflows/ci-cd.yml
```

## Honest limitations

- ML models are trained on **synthetic** data (clearly labelled in the dashboard). In production they would be retrained on real response logs.
- Blood-bank stock shown is demo data; live government stock is on [e-RaktKosh](https://eraktkosh.mohfw.gov.in/).
- SMS OTP is simulated in demo mode; plug in an SMS gateway (e.g. MSG91/Twilio) for production.
- Kannada, Hindi, Tamil and Telugu prompts should be reviewed by native speakers before real use.
- RaktaSetu coordinates voluntary donors. It does **not** give medical clearance — screening and cross-matching are done by the licensed blood centre.
