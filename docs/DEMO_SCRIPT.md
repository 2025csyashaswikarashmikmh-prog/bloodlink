# Examiner demo script (about 10 minutes)

Before the examiner arrives:
- `docker compose up --build -d` and confirm http://localhost:8080 opens.
- Push a small commit so a fresh green GitHub Actions run is visible.
- Open these tabs: GitHub Actions run, GitHub Packages, app (window A), app in an incognito window (window B), terminal.
- Use Chrome or Edge (voice recognition needs them). Allow the microphone.

## 1. Problem (1 min)
"When someone needs blood urgently, families forward WhatsApp messages that reach the wrong people and go stale.
People who can't read English can't use most apps. RaktaSetu is a voice-first, multilingual, real-time donor network."

## 2. Docker (2 min) — in the terminal
```bash
docker compose ps                      # 5 containers: frontend, backend, ml-service, db, redis — all healthy
docker images | grep raktasetu         # 3 custom images we built
docker compose logs --tail=20 backend  # escalation worker + requests
docker exec -it raktasetu-db-1 psql -U raktasetu -c "select blood_group, count(*) from donor_profiles group by 1;"
```
Explain: nginx proxies the API and WebSockets, the ML image trains models while building, health checks control start order.
Optional: `docker compose stop ml-service`, create a request → the timeline says "ranked by HEURISTIC" (graceful fallback),
then `docker compose start ml-service`.

## 3. Voice assistant in Kannada (2 min) — window A
1. Pick **ಕನ್ನಡ** on the language screen.
2. Tap the mic and say your phone number; the demo OTP appears on screen — say it.
3. Say "ನನಗೆ ಬಿ ಪಾಸಿಟಿವ್ ರಕ್ತ ಬೇಕು" → units → "ವಿಕ್ಟೋರಿಯಾ ಆಸ್ಪತ್ರೆ" → urgency → "ಹೌದು".
4. It opens the live tracker: ML-ranked donors, radius, map, nearest blood banks.
(If the hall is noisy, type instead or tap the chips — same flow.)

## 4. Live donor response (2 min) — window B
1. Go to **Donor** → "Demo login" → choose a donor shown as Alerted on the tracker (same masked number).
2. The alert shows a countdown. Click **Yes, I will come** (or tap "Say yes / no" and say "yes").
3. Window A updates instantly: status "Donor on the way", phone now visible, no-show risk shown.
4. In window B click **Demo: check in at hospital location**, then log in as staff (8888888888) to confirm → Fulfilled.

## 5. Escalation + ML (1.5 min) — Admin (9999999999)
- Create another request; in the Admin requests table press **⏩** (simulate expiry) on it → alerts expire, wave 2 goes out, radius widens (watch the tracker in the other window).
- Dashboard: KPIs, live feed, supply vs demand, 7-day ML demand forecast per zone, model metrics + feature importance.

## 6. CI/CD (1.5 min) — GitHub
- Show `.github/workflows/ci-cd.yml` and the run graph: 3 test jobs in parallel → Docker build + 5-container smoke test → push to GHCR → deploy.
- Open the test job (68 tests) and the ML job (model quality gate, metrics artifact).
- Packages page: 3 images tagged `latest` and `sha-xxxxxxx`.
- Live: change a line (e.g. version in `backend/app/main.py`), commit, push → a new run starts.

## Likely examiner questions
- **Why not just a WhatsApp group?** Ranking, eligibility rules, escalation, privacy, accountability (no-shows), multilingual voice.
- **Is the ML real?** Real scikit-learn models with metrics; trained on synthetic data because real donor logs are private. The pipeline retrains them and gates quality.
- **What if no donor accepts?** Waves + widening radius + blood bank fallback, automatically.
- **Privacy?** Numbers masked until acceptance; donor locations never exposed; fraud reporting.
- **Scaling?** Stateless backend behind nginx, Redis for shared state, PostgreSQL; more backend replicas with `docker compose up --scale backend=3` behind a load balancer.
- **Medical safety?** We only coordinate; the blood centre screens and cross-matches. We enforce compatibility and donation gaps.
