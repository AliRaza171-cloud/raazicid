# RAAZICID API contract (v1)

The agreement between the backend and both apps. **Change this file first, then the code**,
so the frontend and backend developers never guess. When the backend runs, live interactive
docs are at `http://localhost:8000/docs`.

## Conventions

- Base URL: `/api/v1`. JSON in, JSON out. Times are ISO 8601 in UTC (`2026-10-24T09:30:00Z`).
- Auth: `Authorization: Bearer <access_token>`. Access token lasts 30 min; refresh with `/auth/refresh`.
- Roles: `donor`, `rider`, `admin`. Each endpoint below lists who may call it.
- Lists are paged: `?limit=20&offset=0` and return `{ "items": [...], "total": 128 }`.
- Errors always look like this, with a matching HTTP status (400, 401, 403, 404, 409, 422):
  ```json
  { "detail": { "code": "donation_not_found", "message": "Donation not found" } }
  ```
- Photos: the app uploads straight to Cloudinary with a signature from `POST /uploads/sign`,
  then sends only the resulting URL to the API.

Phase in brackets = when it gets built.

---

## Health and reference data [Phase 1, built]

| Method | Path | Who | What |
|---|---|---|---|
| GET | `/health` | anyone | API is up |
| GET | `/health/db` | anyone | Database reachable, pgvector installed |
| GET | `/categories` | anyone | The 12 categories |
| GET | `/locations?parent_id=` | anyone | Provinces (no parent) or the children of a place |

```json
// GET /locations?parent_id=<karachi-id>
[{ "id": "8f1c…", "name": "Karachi South", "level": "region", "parent_id": "<karachi-id>" }]
```

## Auth and profile [Phase 2]

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/auth/register` | anyone | Create donor or rider |
| POST | `/auth/login` | anyone | Phone/email + password → tokens |
| POST | `/auth/refresh` | anyone | Refresh token → new access token |
| POST | `/auth/logout` | logged in | Revoke refresh token |
| GET / PATCH | `/me` | logged in | Own profile and location |
| POST | `/me/rider-documents` | rider | Add a verification document URL |
| GET | `/admin/riders?status=pending` | admin | Riders by status |
| GET | `/admin/riders/{id}` | admin | Rider, documents, AI review |
| POST | `/admin/riders/{id}/decision` | admin | `approve` / `reject` / `suspend` / `request_document` |

```json
// POST /auth/register
{
  "role": "rider",
  "full_name": "Usman Khan",
  "phone": "03001234567",
  "password": "********",
  "location_id": "<area-id>",
  "rider": { "vehicle_type": "motorbike", "vehicle_number": "KHI-4821" }
}
// 201
{ "user": { "id": "…", "role": "rider", "full_name": "Usman Khan", "rider_status": "pending" },
  "access_token": "…", "refresh_token": "…" }
```

## Donations [Phase 3]

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/uploads/sign` | logged in | Cloudinary upload signature |
| POST | `/donations` | donor | Create donation |
| GET | `/donations/mine?filter=active\|done\|all` | donor | My donations |
| GET | `/donations/{id}` | owner, rider on it, admin | Detail + timeline + photos |
| POST | `/donations/{id}/cancel` | donor | Only while `in_review` or `accepted` |
| GET | `/admin/donations?status=&category=&province_id=&city_id=&sort=urgency` | admin | Table |
| POST | `/admin/donations/{id}/accept` | admin | `{ "point_id": "…" }` |
| POST | `/admin/donations/{id}/reject` | admin | `{ "reason": "…" }` |

```json
// POST /donations
{
  "category_id": 4,
  "ai": { "category_id": 4, "confidence": 0.92, "top3": [{"category_id": 4, "p": 0.92}, {"category_id": 5, "p": 0.06}] },
  "title": "10 blankets",
  "quantity": 10,
  "condition": "good",
  "description": "Double-bed size, washed",
  "is_food": false,
  "pickup": { "address": "House 14, Block 7, Gulshan-e-Iqbal", "lat": 24.92, "lng": 67.09,
              "location_id": "<area-id>", "from": "2026-10-24T11:00:00Z", "to": "2026-10-24T14:00:00Z" },
  "photo_urls": ["https://res.cloudinary.com/…/1.jpg"]
}
// 201 → full donation object, status "in_review"
```

## Distribution points [Phase 3]

| Method | Path | Who | What |
|---|---|---|---|
| GET | `/points?city_id=&category_id=` | admin, rider | List (map + table) |
| POST / PATCH | `/admin/points`, `/admin/points/{id}` | admin | Create / edit |
| POST | `/admin/points/{id}/requests` | admin, rider | Point request: `{ "category_id": 4, "quantity": 50, "note": "…" }` |

## Jobs, tracking, hand-out [Phase 4]

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/admin/donations/{id}/assign` | admin | `{ "rider_id": "…" }` → creates job |
| GET | `/rider/jobs?status=assigned\|active` | rider | My jobs |
| POST | `/rider/jobs/{id}/accept` · `/decline` | rider | Decline takes `{ "reason": "…" }` |
| POST | `/rider/jobs/{id}/pickup` | rider | `{ "photo_url", "lat", "lng" }` |
| POST | `/rider/jobs/{id}/deliver` | rider | `{ "photo_url", "lat", "lng", "received_by" }` |
| POST | `/rider/location` | rider | `{ "job_id", "lat", "lng", "recorded_at" }` every 15 s |
| POST | `/rider/availability` | rider | `{ "is_available": true }` |
| GET | `/donations/{id}/tracking` | donor, admin | Latest rider position, route, ETA |
| GET | `/admin/tracking/active` | admin | All active jobs for the live map |
| POST | `/donations/{id}/hand-out` | rider, admin | `{ "quantity", "families_served", "photo_url", "note" }` → `handed_out` |
| GET | `/notifications` · POST `/notifications/read` | logged in | Inbox, mark read |

## AI suggestions [Phase 5]

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/ai/classify` | donor | `{ "image_url" }` → top 3 categories with confidence |
| GET | `/admin/donations/{id}/recommended-riders` | admin | Top 3 riders with score parts |
| GET | `/admin/donations/{id}/recommended-points` | admin | Top 3 points with reasons |
| POST | `/admin/riders/{id}/ai-review` | admin | Run Claude document review |

```json
// GET /admin/donations/{id}/recommended-riders
[{ "rider_id": "…", "name": "Usman Khan", "score": 94,
   "parts": { "distance_km": 1.2, "active_jobs": 0, "available": true, "rating": 4.8 } }]
```

## Needs, need finder, alerts, appeals [Phase 6]

| Method | Path | Who | What |
|---|---|---|---|
| GET | `/needs?province_id=&city_id=` | anyone | Need level per area × category (Needs by area page, donor app) |
| GET | `/needs/{location_id}` | anyone | Top needs with reasons and sources |
| POST | `/admin/need-finder/ask` | admin | RAG question, optional web search |
| GET / POST | `/admin/reports`, `/admin/reports/upload` | admin | Report library |
| PATCH | `/admin/reports/{id}/tags` | admin | Fix location tags |
| GET / PATCH | `/admin/sources`, `/admin/sources/{id}` | admin | Automatic sources on/off |
| GET | `/admin/alerts?status=` | admin | Disaster alerts |
| POST | `/admin/alerts/{id}/confirm` · `/dismiss` · `/handled` | admin | Alert status |
| PATCH | `/admin/alerts/{id}/needs` | admin | Edit needed quantities |
| POST | `/admin/appeals` | admin | Send appeal to donors in chosen provinces |
| GET | `/appeals/active` | donor | Appeals for my province |

```json
// GET /needs?province_id=<sindh-id>
{ "categories": [{ "id": 1, "name": "Food" }, …],
  "areas": [{
    "location_id": "…", "name": "Lyari", "path": "Sindh › Karachi › Karachi South",
    "levels": [1, 2, 2, 3, 3, 1, 1, 1, 1, 1, 0, 0],        // one per category, same order
    "top": [{ "category_id": 4, "level": 3,
              "why": "Point asked for 50 blankets; only 10 delivered in 30 days.",
              "sources": ["Point request", "RAAZICID deliveries", "Season"] }],
    "updated_at": "2026-10-24T08:20:00Z" }] }

// POST /admin/need-finder/ask
{ "question": "Where in Karachi are blankets needed most this winter?",
  "province_id": "…", "city_id": "…", "category_id": 4, "web_search": true }
// 200
{ "answer": "Three areas stand out…",
  "areas": [{ "location_id": "…", "name": "Lyari", "need": 5, "categories": ["Blankets", "Warm clothes"],
              "reason": "…", "sources": [{ "title": "karachi-winter-needs.pdf", "page": 4, "report_id": "…" }] }],
  "web_results": [{ "title": "…", "url": "https://dawn.com/…", "snippet": "…" }] }
```

## Seasonal, flags, analytics, ratings [Phases 7–8]

| Method | Path | Who | What |
|---|---|---|---|
| GET | `/suggestions?province_id=` | anyone | Top 3–5 categories needed now, with reasons |
| GET / POST / PATCH | `/admin/seasonal-rules` | admin | Rules editor |
| GET | `/admin/seasonal/forecast?province_id=` | admin | 12-month need grid |
| GET | `/admin/flags?status=open` · POST `/admin/flags/{id}/decision` | admin | Fraud flags |
| GET | `/admin/analytics/summary` | admin | Dashboard numbers |
| POST | `/donations/{id}/rating` | donor | `{ "score": 5, "comment": "…" }` |
