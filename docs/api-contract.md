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

## Auth and profile [Phase 2, built]

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/auth/register` | anyone | Create a donor or rider (admins are made with `python -m app.seed.create_admin`) |
| POST | `/auth/login` | anyone | Phone or email + password → tokens |
| POST | `/auth/refresh` | anyone | Refresh token → new access **and** refresh token (the old one stops working) |
| POST | `/auth/logout` | anyone | Revoke a refresh token. Always 204 |
| GET / PATCH | `/me` | logged in | Own profile: `full_name`, `email`, `location_id`, `address`, `lat`, `lng` |
| GET | `/me/rider-documents` | rider | My uploaded documents |
| POST | `/me/rider-documents` | rider | Add or replace one document (`cnic_front`, `cnic_back`, `driving_licence`, `vehicle_registration`) |
| POST | `/uploads/sign` | logged in | Cloudinary upload signature |
| GET | `/admin/riders/counts` | admin | `{ pending, approved, rejected, suspended }` for the tabs |
| GET | `/admin/riders?status=pending&q=&limit=&offset=` | admin | Riders by status; `q` searches name, phone, vehicle number |
| GET | `/admin/riders/{id}` | admin | Rider, documents, last review |
| POST | `/admin/riders/{id}/decision` | admin | `approve` / `reject` / `suspend` / `request_document` |

```json
// POST /auth/register
{
  "role": "rider",
  "full_name": "Usman Khan",
  "phone": "0300-1234567",          // any Pakistani format; saved as 03001234567
  "password": "********",           // 8–72 characters
  "location_id": "<area-id>",
  "rider": { "vehicle_type": "motorbike", "vehicle_number": "KHI-4821" }  // riders only
}
// 201
{ "user": { "id": "…", "role": "rider", "full_name": "Usman Khan", "phone": "03001234567",
            "email": null, "location_path": ["Sindh", "Karachi", "Karachi South", "Saddar"],
            "rider_status": "pending", "rider_note": null },
  "access_token": "…", "refresh_token": "…" }

// POST /auth/login
{ "login": "03001234567", "password": "********" }   // or an email
```

Error codes: `phone_taken`, `email_taken`, `bad_location` (409/422 on register); `wrong_login` (401),
`account_disabled` (403) on login; `invalid_refresh` (401); `not_authenticated` / `invalid_token` (401)
and `forbidden` (403) on any protected endpoint.

**Uploading a photo** (rider documents now; donation and proof photos in Phases 3–4):

```json
// POST /uploads/sign   { "purpose": "rider_document" }   // or donation_photo, proof_photo
{ "upload_url": "https://api.cloudinary.com/v1_1/<cloud>/image/upload", "cloud_name": "<cloud>",
  "api_key": "…", "timestamp": 1792831800, "folder": "raazicid/rider_document/<user-id>", "signature": "…" }
```

The app then POSTs the file as multipart to `upload_url` with `file`, `api_key`, `timestamp`, `folder`,
`signature`, and sends the returned `secure_url` to the API (`POST /me/rider-documents`
`{ "doc_type": "cnic_front", "file_url": "https://res.cloudinary.com/…" }`).
`503 uploads_not_configured` means the Cloudinary keys are missing from `backend/.env`.

**Rider status rules**

- A new rider starts as `pending` and only sees the documents screen in the app.
- Uploading a document again replaces the old one of that type. A `rejected` rider who uploads a
  document goes back to `pending`. A `suspended` rider cannot upload (403).
- `approve` needs at least one document (409 `no_documents`). `reject`, `suspend` and
  `request_document` need a `note`, which the rider sees in the app (`rider_note`).
- `request_document` keeps the rider `pending`. Every decision records who reviewed and when,
  and sends the rider a notification.

## Donations [Phase 3, built]

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/donations` | donor | Create donation (status `in_review`) |
| GET | `/donations/mine?filter=active\|done\|all&limit=&offset=` | donor | My donations, newest first |
| GET | `/donations/{id}` | owner, admin (rider on the job from Phase 4) | Detail + history + photos |
| POST | `/donations/{id}/cancel` | donor | Only while `in_review` or `accepted` (409 `cannot_cancel`) |
| GET | `/admin/donations/counts` | admin | Count per status, for the tabs |
| GET | `/admin/donations?status=&category_id=&location_id=&q=&sort=urgency\|newest\|oldest` | admin | Table. `location_id` can be a province, city, region or area and includes everything under it |
| GET | `/admin/donations/{id}/point-options` | admin | Open points that can take it, ranked (same area → region → city → province, then distance) |
| POST | `/admin/donations/{id}/accept` | admin | `{ "point_id": "…" }` → `accepted` (409 `point_cannot_take` if the point is closed, does not take the category, or cannot hand out cooked food) |
| POST | `/admin/donations/{id}/reject` | admin | `{ "reason": "…" }` → `rejected`; the donor sees the reason |

```json
// POST /donations
{
  "category_id": 1,
  "ai": null,                                  // filled by the classifier from Phase 5
  "title": "Cooked rice, 40 plates",
  "quantity": 40,
  "condition": null,                           // new | good | used, not used for food
  "description": "Packed in foil trays",
  "is_food": true,
  "food_type": "cooked",                       // cooked | dry; required when is_food
  "prepared_at": "2026-10-24T08:00:00Z",       // required for cooked food
  "pickup": { "address": "Shadi hall, Tariq Road", "lat": 24.87, "lng": 67.06,
              "location_id": "<area-id>", "from": "2026-10-24T11:00:00Z", "to": "2026-10-24T14:00:00Z" },
  "photo_urls": ["https://res.cloudinary.com/…/1.jpg"]   // 1–5, uploaded first with /uploads/sign
}
// 201 → full donation:
{ "id": "…", "ref": "D-3F9A1C", "title": "…", "category": { "id": 1, "name": "Food" }, "quantity": 40,
  "status": "in_review", "is_food": true, "urgency_score": 74,
  "urgency_reasons": [{ "label": "Food type: cooked", "points": 35 }, { "label": "Time since prepared: 2 h", "points": 25 },
                      { "label": "Quantity: 40", "points": 14 }],
  "photo_url": "…", "photos": ["…"], "pickup_area": ["Karachi East", "PECHS"],
  "pickup": { "address": "…", "lat": 24.87, "lng": 67.06, "location_path": ["Sindh", "Karachi", "Karachi East", "PECHS"],
              "from": "…", "to": "…" },
  "point": null, "point_name": null, "reject_reason": null,
  "history": [{ "from_status": null, "to_status": "in_review", "note": "Created by donor", "by_name": "Hamza", "at": "…" }],
  "donor": { "id": "…", "full_name": "Hamza", "phone": "03215550192", "donations_count": 4 },
  "ai": null, "can_cancel": true, "created_at": "…" }
```

Rules: pickup must be inside Pakistan (catches swapped lat/lng), end after it starts, not be over
already, and start within 7 days. The Food category is always saved as food.

**Urgency (food only, 0–100, rule-based):** cooked +35 (dry +5); cooked time since prepared
<1 h +10, 1–3 h +25, 3–6 h +35, 6 h+ +40; quantity +0.35 per item up to +20. Other categories have
no score and sort after food. Phase 5 adds pickup distance.

Every status move writes a `status_changes` row and notifies the donor (accepted, rejected, and
the Phase 4 rider steps).

## Distribution points [Phase 3, built]

| Method | Path | Who | What |
|---|---|---|---|
| GET | `/points?location_id=&category_id=&open_only=` | admin, approved rider | List; riders only see open points |
| GET | `/points/{id}` | admin, approved rider | Point + its requests |
| POST | `/admin/points` | admin | Create |
| PATCH | `/admin/points/{id}` | admin | Edit any field; `category_ids: []` = accepts everything |
| POST | `/points/{id}/requests` | admin, approved rider | What people there need: `{ "category_id": 4, "quantity": 50, "note": "…" }` |
| PATCH | `/admin/point-requests/{id}` | admin | `{ "status": "fulfilled" \| "cancelled" }` |

```json
// POST /admin/points
{ "name": "Noor Community Point", "type": "mosque", "location_id": "<lyari-id>", "address": "Near Chakiwara Chowk",
  "lat": 24.866, "lng": 67.0, "contact_name": "Bilal Ahmed", "contact_phone": "0300 1112223",
  "same_day_food": true, "is_active": true, "closes_at": null, "category_ids": [] }
// → point with "location_path", "categories": [{id, name}], "items_30d", "open_requests", "requests": []
```

A point is open when `is_active` is true and `closes_at` (for temporary relief camps) has not passed.

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
