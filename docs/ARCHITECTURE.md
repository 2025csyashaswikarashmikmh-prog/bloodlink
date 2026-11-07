# RaktaSetu — Architecture

## Containers

| Container | Image | Port | Role |
|---|---|---|---|
| frontend | `raktasetu-frontend` (nginx:1.27-alpine) | 8080→80 | Serves the web app; reverse-proxies `/api/*` and `/ws` (WebSocket upgrade) to the backend, so the browser talks to one origin. |
| backend | `raktasetu-backend` (python:3.12-slim, non-root user) | 8000 | REST API, WebSocket hub, voice assistant, matching + escalation engine. |
| ml-service | `raktasetu-ml` (python:3.12-slim) | 8001 | Trains models **during `docker build`** and serves predictions. |
| db | postgres:16-alpine | internal | Users, donor profiles, requests, matches, events, reports, blood banks. Named volume `pgdata`. |
| redis | redis:7-alpine | internal | OTP codes and assistant sessions with TTL. |

Start order is enforced with health checks: `db` + `redis` + `ml-service` healthy → `backend` healthy → `frontend`.
If the ML service is down, the backend falls back to a heuristic score (graceful degradation, shown as `HEURISTIC` in the timeline).

## Request lifecycle

```
Family (voice/form)            Backend                              Donors
──────────────────            ───────                              ──────
"B positive, 2 units,
 Victoria hospital, urgent" ─▶ NLU extracts slots
                               create_request()
                               find_candidates(radius=5km):
                                 compatible group (ABO/Rh)
                                 available + donation gap ok
                                 within radius
                               widen 5→10→25→50 km until a full wave
                               ML /predict/acceptance per donor
                               priority = 0.55·P(accept) + 0.20·proximity
                                          + 0.15·reliability + 0.10·exact
                               top N alerted ──── WebSocket / Telegram ─▶ alert + countdown
                                                                         "Yes, I will come"
                               accept → phone revealed to family ◀─────┘
                               ML /predict/noshow → risk shown
                               commitment deadline (90 min)
 live tracker ◀── WebSocket ── check-in at hospital (GPS ≤ 1 km) ◀────── "I've reached"
                               staff confirms donation → fulfilled
                               donor reliability ↑, cooldown starts
```

### Escalation worker (every 10 s)
- Alert not answered within `RESPONSE_WINDOW_SEC` → match `expired`, donor acceptance rate ↓, next wave sent.
- Committed donor misses the commitment deadline → `no_show`, reliability −15, next wave sent.
- No eligible donors left at 50 km → nearest blood banks with compatible stock attached to the timeline.

## ML models (ml-service)

| Model | Algorithm | Features | Metric |
|---|---|---|---|
| Donor acceptance | RandomForestClassifier | distance, hour, urgency, reliability, acceptance rate, no-show rate, days since donation, total donations, exact match | ROC-AUC ≈ 0.74 |
| No-show risk | RandomForestClassifier (class-balanced) | distance, hour, reliability, no-show rate, urgency, response delay, commitment window | ROC-AUC ≈ 0.71 |
| Demand forecast | GradientBoostingRegressor | zone, blood group, day of week, month, holiday flag (with monsoon-season effect) | MAE ≈ 0.65 req/day |

Data is synthetic, generated with realistic relationships (e.g. acceptance falls with distance and at night). The CI
pipeline retrains the models and fails the build if quality drops below the gate.

## Voice assistant

`backend/app/voice.py` is a slot-filling dialogue manager:

```
ask_phone → ask_otp → ask_intent ─┬─ need:   blood group → units → hospital → urgency → confirm → create request
                                  ├─ donate: name → blood group → gender → last donation → location → confirm
                                  └─ track:  open my requests
```

Each turn returns `reply` (in the chosen language), quick-reply `chips`, extracted `slots`, and an optional `action`
(login, open_request, donor_registered). The browser speaks the reply (Web Speech API or `/api/voice/tts` gTTS
fallback) and listens with `SpeechRecognition` in `en-IN / kn-IN / hi-IN / ta-IN / te-IN`.

## Security & privacy
- Phone + OTP login, JWT (HS256) sessions, role-based access (requester / donor / staff / admin).
- Donor phone masked (`90******12`) until that donor accepts; donor home coordinates never sent to clients.
- Fraud reports with admin suspension; suspended users can't log in or be matched.
- Containers run as non-root; secrets via environment variables / GitHub secrets, `.env` git-ignored.
