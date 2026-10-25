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

## Jobs, tracking, hand-out [Phase 4, built]

| Method | Path | Who | What |
|---|---|---|---|
| GET | `/admin/donations/{id}/rider-options` | admin | Approved riders: available first, then nearest (live GPS, else home area), then fewest active jobs |
| POST | `/admin/donations/{id}/assign` | admin | `{ "rider_id": "…" }` → job `assigned`, donation `rider_assigned` |
| POST | `/admin/donations/{id}/cancel-job` | admin | `{ "reason": "…" }`, only before pickup → donation back to `accepted` |
| GET | `/admin/tracking` | admin | Every active job with the rider's last GPS point and `stalled` |
| GET | `/rider/summary` | approved rider | Availability, active jobs, done today / total, rating |
| PATCH | `/rider/availability` | approved rider | `{ "is_available": true }` |
| GET | `/rider/jobs?filter=current\|history` | approved rider | Current = assigned, accepted, picked up, and delivered jobs still waiting for their hand-out |
| GET | `/rider/jobs/{id}` | the rider | One job |
| POST | `/rider/jobs/{id}/accept` | the rider | `assigned` → `accepted`. The donor's phone is shown after this |
| POST | `/rider/jobs/{id}/decline` | the rider | `{ "reason": "…" }`, before pickup → donation back to `accepted`, admins notified |
| POST | `/rider/jobs/{id}/pickup` | the rider | `{ "photo_url", "lat", "lng", "note"? }` → job and donation `picked_up` |
| POST | `/rider/jobs/{id}/deliver` | the rider | `{ "photo_url", "lat", "lng", "note"? }` → job `delivered`, donation `at_point` |
| POST | `/rider/jobs/{id}/ping` | the rider | `{ "lat", "lng" }` about every 15 s while the job screen is open (204) |
| GET | `/donations/{id}/tracking` | donor, admin, the rider | Rider, last GPS point, path (last 240 points), `stalled`, pickup and point |
| POST | `/donations/{id}/hand-out` | admin, the rider who delivered | `{ "quantity", "families_served"?, "photo_url"?, "note"? }` → `handed_out` |

The donation detail (`GET /donations/{id}`) now also has `job` (current rider), `proofs`
(pickup / delivery / hand-out photos with GPS and `distance_km` from where they should be) and
`hand_out`.

**Checks**
- Proof photos are taken with the camera, with GPS. A pickup photo more than 1 km from the pickup
  address raises a `far_from_pickup` flag (medium), and a delivery photo more than 1 km from the point
  raises `far_from_point` (high). The step still goes through; an admin reviews the flag (Phase 8 page).
- `stalled`: no GPS for 10+ minutes on an accepted or picked-up job.
- Hand-out quantity cannot be more than the donation's quantity.
- GPS is shared only while the rider's job screen is open (Expo Go has no background location).

Notifications are saved for the donor at every step (assigned, picked up, at point, handed out),
for the rider (new job, job taken off), and for admins (rider declined). The inbox screen and
`GET /notifications` come with the alerts in Phase 6.

## AI suggestions [Phase 5, built]

| Method | Path | Who | What |
|---|---|---|---|
| GET | `/ai/status` | logged in | `{ classifier: "ready" \| "not_installed" \| "no_model", version, accuracy, own_photo_accuracy, document_review }` |
| POST | `/ai/classify` | donor, admin | `{ "image_url" }` (our Cloudinary uploads only) → top 3 categories. 503 `classifier_not_ready` if the model is not installed |
| GET | `/admin/ai/stats` | admin | How often donors kept the AI's choice (top-1 / top-3) on real donations |
| GET | `/admin/donations/{id}/rider-options` | admin | Riders ranked by `score` (0–100) with `reasons` |
| POST | `/admin/riders/{id}/ai-review` | admin | Claude checks the rider's documents; result in the rider detail as `ai_review` |

```json
// POST /ai/classify   { "image_url": "https://res.cloudinary.com/<cloud>/image/upload/…/1.jpg" }
{ "model_version": "mobilenetv2-20261025-1030",
  "suggestions": [{ "category_id": 4, "name": "Blankets", "p": 0.92 },
                  { "category_id": 5, "name": "Winter support", "p": 0.05 },
                  { "category_id": 3, "name": "Clothes", "p": 0.02 }] }

// The donor app sends the suggestion with the donation (POST /donations "ai"):
{ "ai": { "category_id": 4, "confidence": 0.92, "top3": [{ "category_id": 4, "p": 0.92 }, …] } }

// GET /admin/donations/{id}/rider-options  (one item)
{ "id": "…", "full_name": "Usman Khan", "score": 87,
  "reasons": [{ "label": "1.2 km from pickup (live GPS)", "points": 37 }, { "label": "No active jobs", "points": 20 },
              { "label": "Available now", "points": 15 }, { "label": "New rider, no rating yet", "points": 10 },
              { "label": "Motorbike for a small load", "points": 10 }], … }
```

Scoring rules and evaluation: `docs/ai-evaluation.md`. Food urgency now also adds distance to the
nearest same-day food point and is refreshed while the food waits.

## Needs by area and disaster alerts [Phase 6A, built]

| Method | Path | Who | What |
|---|---|---|---|
| GET | `/needs?parent_id=` | logged in | Provinces (no `parent_id`) or the places inside one place, each with its need level per category and the reasons |
| POST | `/admin/needs/recompute` | admin | Rebuild need levels now (also runs every hour and after each data fetch) |
| GET | `/alerts` | logged in | Confirmed disasters of the last 30 days (donor app) |
| GET | `/admin/alerts?status=&limit=` | admin | All alerts, newest first |
| GET | `/admin/alerts/counts` | admin | `{unconfirmed, confirmed, handled, dismissed}` |
| GET | `/admin/alerts/{id}` | admin | One alert with places, figures, needs, sources, camps |
| POST | `/admin/alerts` | admin | Add an alert by hand (confirmed straight away) |
| POST | `/admin/alerts/{id}/status` | admin | `{"status": "confirmed" \| "dismissed" \| "handled" \| "unconfirmed"}` |
| PUT | `/admin/alerts/{id}/needs` | admin | Replace "what is needed": `[{"category_id": 2, "quantity_needed": 150}]` |
| POST | `/admin/alerts/{id}/camp` | admin | Open a relief camp (temporary distribution point, `alert_id` set) |
| GET | `/admin/sources` | admin | Data sources with last run and result |
| POST | `/admin/sources/{kind}/run` | admin | Fetch now: `gdacs`, `hdx_hapi`, `web_search` (Claude news scan) |

**Need levels.** Each (area, category) gets a score 0–100: the strongest signal plus 5 for each other signal
of 25+. 80+ urgent (3), 55+ high (2), 30+ some (1).

| Signal | Source | Points |
|---|---|---|
| IPC Phase 3+ share (food, ration) | HDX HAPI `food-security` | ≥30% 85 · ≥20% 65 · ≥10% 40 |
| Staple price rise over ~3 months (ration; food −10) | HDX HAPI `food-prices-market-monitor` (WFP) | ≥20% 60 · ≥10% 45 |
| Poverty headcount (ration, food, clothes, school, hygiene) | HDX HAPI `poverty-rate` | ≥40% 40 · ≥25% 25 |
| Disaster alert, last 30 days (categories by type) | GDACS, Claude web scan, admin | severe 90 · moderate 65 · watch 40; unconfirmed ×0.7 |
| Open requests at a distribution point | our points | 40, or 60 if 50+ items |

A place shows the highest level found anywhere inside it.

```json
// GET /needs?parent_id=<sindh-id>
{ "place": { "id": "…", "name": "Sindh", "level": "province", "parent_id": null },
  "summary": [{ "category_id": 12, "name": "Emergency relief", "level": 3, "level_name": "urgent", "score": 90,
                "reasons": [{ "why": "Urban flooding in Lyari", "source": "Disaster alert", "date": "21 Aug 2026",
                              "place": "Lyari", "points": 90, "alert_id": "…" }] }],
  "children": [{ "id": "…", "name": "Karachi", "level": "city", "lat": 24.86, "lng": 67.0,
                 "has_children": true, "max_level": 3, "needs": [ /* same shape as summary */ ] }],
  "computed_at": "2026-10-25T08:00:00Z" }

// POST /admin/alerts/{id}/camp
{ "name": "Lyari Relief Camp", "location_id": "…", "address": "Govt school ground", "lat": 24.867, "lng": 67.0,
  "contact_name": "Bilal", "contact_phone": "03001112223", "open_days": 30 }
// 201: the new distribution point (type relief_camp, same-day food, categories = the alert's needs)
```

**Where alerts come from.** GDACS every 30 minutes (Pakistan events only, placed by name or nearest city) and the
Claude web scan (NDMA, PDMA, PMD, ReliefWeb, Dawn, Express Tribune, The News, Geo, ARY, APP; last 72 hours).
Both create *unconfirmed* alerts with their source links; donors see an alert only after an admin confirms it.
"What is needed" is suggested from the disaster type and the affected families (6 people per family).

## Report library, RAG need finder, appeals [Phase 6B]

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/admin/need-finder/ask` | admin | RAG question, optional web search |
| GET / POST | `/admin/reports`, `/admin/reports/upload` | admin | Report library |
| PATCH | `/admin/reports/{id}/tags` | admin | Fix location tags |
| POST | `/admin/appeals` | admin | Send appeal to donors in chosen provinces |
| GET | `/appeals/active` | donor | Appeals for my province |

```json
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
