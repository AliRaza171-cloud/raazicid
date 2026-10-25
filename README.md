# RAAZICID

AI-guided donation collection and distribution for Pakistan. Donors give items through the mobile app,
RAAZICID riders collect them and our team hands them out at distribution points in the areas that
need them most. Need is found with a RAG over official reports (IPC, NDMA / PDMA via ReliefWeb,
GDACS, HDX) plus Claude web search, and seasonal rules.

Final Year Project, Department of Software Engineering.

| Folder | What | Tech |
|---|---|---|
| `backend/` | API, database, AI / RAG (later phases) | Python, FastAPI, SQLAlchemy, PostgreSQL (Neon) + pgvector |
| `admin/` | Web app for RAAZICID admins | React + TypeScript (Vite) |
| `mobile/` | App for donors and riders | React Native (Expo) |
| `docs/` | Database design, API contract, status flow | Markdown + Mermaid diagrams |

Start with [`docs/ERD.md`](docs/ERD.md), [`docs/api-contract.md`](docs/api-contract.md) and
[`docs/status-flow.md`](docs/status-flow.md).

---

## First-time setup (Windows)

You need: **Python 3.12 or 3.13**, **Node.js 20+**, **Git**, the **Expo Go** app on your Android phone,
and a free **Neon** account (neon.tech).

### 1. Database (Neon)

1. In Neon, create a project named `raazicid`.
2. Copy the connection string (Dashboard → Connect). It looks like
   `postgresql://user:password@ep-xxx.aws.neon.tech/neondb?sslmode=require`.
3. Change the start to `postgresql+psycopg://` — that is the `DATABASE_URL` for step 2.

### 2. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then open .env and paste your DATABASE_URL
alembic upgrade head            # creates all tables + pgvector
python -m app.seed.run          # adds categories, provinces, cities, Karachi areas, seasonal rules
python -m app.seed.create_admin --name "Your Name" --phone 03001234567 --email you@example.com
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs — you should see the API, and `GET /api/v1/health/db` should say
`"database": "reachable", "pgvector": true`.

`create_admin` asks for a password and makes the account you use to sign in to the admin web app
(there is no sign-up for admins on purpose).

**Cloudinary (for rider documents and photos):** make a free account at cloudinary.com, open
Dashboard → API Keys, and put the cloud name, API key and API secret in `backend/.env`
(`CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`). Also set `JWT_SECRET`
to a long random string, e.g. the output of `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

**Tests:** `pytest`. The database tests only run when `TEST_DATABASE_URL` is set, and they **delete
everything** in that database, so point it at a separate Neon branch (Neon → Branches → New branch
`test`, then copy that branch's connection string with `postgresql+psycopg://`):

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://…test-branch…"
pytest
```

### 3. Admin web app

```powershell
cd admin
npm install
copy .env.example .env.local
npm run dev
```

Open http://localhost:5173 and sign in with the admin account from `create_admin`. The Dashboard
shows green checks when it can reach the backend and database. **Riders** lists riders waiting for
approval; click one to see their documents and approve, reject, suspend or ask for a document.

### 4. Mobile app (one-time install)

Expo Go on your phone only runs the **latest** Expo version, so install the packages with Expo's
own installer, which picks matching versions:

```powershell
cd mobile
npm install expo@latest
npx expo install react react-native react-native-screens react-native-safe-area-context expo-secure-store expo-image-picker expo-location react-native-webview expo-font expo-asset @expo/vector-icons @react-navigation/native @react-navigation/native-stack @react-navigation/bottom-tabs
npm install -D typescript @types/react
copy .env.example .env          # put your laptop's Wi-Fi IP (ipconfig → IPv4 Address)
npx expo start
```

If Expo Go says the project needs a newer version, update Expo Go from the Play Store. If it is
already up to date, check the SDK number in Expo Go → Settings and run
`npm install expo@~<that number>.0.0` then `npx expo install --fix`.

Scan the QR code with Expo Go. Phone and laptop must be on the **same Wi-Fi**, and the backend must
run with `--host 0.0.0.0`. If Windows Firewall asks, allow Python on private networks.
Commit the updated `package.json` and `package-lock.json` after this step.

Already installed from an earlier phase? Add the new packages:
`npx expo install expo-image-picker expo-location react-native-webview` (photo picker from Phase 2, GPS from Phase 3, maps from Phase 4).

### 5. AI (Phase 5, optional)

Everything works without these; the AI parts switch on when they are set up.

- **Photo classifier:** train it in Google Colab with `ml/train_classifier.ipynb` (see `ml/README.md`),
  copy `raazicid_classifier.pt` and `labels.json` into `backend/models/`, then in the backend venv:
  ```powershell
  pip install -r requirements.txt
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  ```
- **AI document check:** add `ANTHROPIC_API_KEY=` (from console.anthropic.com) to `backend/.env`.

Restart the backend. The admin Dashboard's **AI** card shows what is ready.

### 6. Needs and disaster data (Phase 6)

In the backend venv:
```powershell
pip install -r requirements.txt     # adds apscheduler (background fetching)
python -m app.seed.run              # adds map coordinates for provinces and cities
```
Add to `backend/.env`:
```
HDX_EMAIL=you@example.com           # HDX HAPI needs an email to identify the app (free, no sign-up)
WEB_SCAN_EVERY_HOURS=0              # 0 = Claude news scan only when you press "Scan news now"
```
While the backend runs it fetches GDACS every 30 minutes and HDX (IPC, food prices, poverty) once a day,
then recomputes need levels. Admin web: **Disaster alerts** (check, confirm, open a relief camp, data sources)
and **Needs by area**. Donor app: **Alerts** tab, the Home banner and "What is needed where".

---

## Working together

- `main` always works. Build each feature on a branch (`feat/donations-api`), open a pull request,
  the other person reviews.
- Change `docs/api-contract.md` **before** changing an endpoint.
- Database change = model change + `alembic revision --autogenerate -m "what changed"` + `alembic upgrade head`.
- Never commit `.env` files or keys.

## Phase status

- [x] Phase 1 — design (ERD, API contract, status flow), skeletons, data source check
- [x] Phase 2 — accounts and authentication (sign-up, login, rider documents and approval)
- [x] Phase 3 — donations and distribution points (donate flow, admin review, points and requests)
- [x] Phase 4 — pickup, delivery, tracking (assign rider, proofs with GPS checks, hand-out, live map)
- [x] Phase 5 — AI: photo classifier (PyTorch), rider score, urgency v2, Claude document check
- [x] Phase 6A — needs by area, disaster alerts (GDACS, HDX, Claude web scan), relief camps
- [ ] Phase 6B — report library, RAG need finder, appeals, ReliefWeb
- [ ] Phase 7 — seasonal suggestions
- [ ] Phase 8 — analytics, fraud flags, ratings
- [ ] Phase 9 — testing, evaluation, deployment
