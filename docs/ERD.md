# RAAZICID database design (ERD)

PostgreSQL on Neon with the **pgvector** extension. 31 tables in 6 groups. The source of truth
is the code in `backend/app/models/`; this page explains it. GitHub draws the diagrams below automatically.

Conventions
- Primary keys are UUIDs (safe in URLs), except small fixed tables (`categories`, `sources`) and
  high-volume logs (`rider_pings`, `need_levels`) which use integers.
- Fixed value lists (roles, statuses, types) are stored as text; the allowed values are in
  `backend/app/models/enums.py`.
- Every main table has `created_at` / `updated_at`.

## 1. People and places

```mermaid
erDiagram
    LOCATIONS ||--o{ LOCATIONS : "parent of"
    LOCATIONS ||--o{ USERS : "home of"
    USERS ||--o| RIDER_PROFILES : "is a rider"
    RIDER_PROFILES ||--o{ RIDER_DOCUMENTS : uploads
    RIDER_PROFILES ||--o{ DOCUMENT_REVIEWS : "AI review"
    USERS ||--o{ REFRESH_TOKENS : has

    LOCATIONS {
        uuid id PK
        string name
        string level "province | city | region | area"
        uuid parent_id FK
        string admin_code "HDX admin1/admin2 code"
        float lat
        float lng
    }
    USERS {
        uuid id PK
        string role "donor | rider | admin"
        string full_name
        string phone UK
        string email UK
        string password_hash
        bool is_active
        uuid location_id FK
        text address
    }
    RIDER_PROFILES {
        uuid user_id PK,FK
        string vehicle_type
        string vehicle_number
        string status "pending | approved | rejected | suspended"
        bool is_available
        float last_lat
        float last_lng
        float rating_avg
    }
    RIDER_DOCUMENTS {
        uuid id PK
        uuid rider_id FK
        string doc_type "cnic_front | cnic_back | driving_licence | vehicle_registration"
        text file_url
    }
    DOCUMENT_REVIEWS {
        uuid id PK
        uuid rider_id FK
        text summary
        json checks
    }
```

**Location tree:** Sindh › Karachi › Karachi South › Lyari. Rural districts from IPC / HDX data
(e.g. Tharparkar, Kech) are stored as `region` directly under their province, matched by `admin_code`.

## 2. Donations

```mermaid
erDiagram
    USERS ||--o{ DONATIONS : donates
    CATEGORIES ||--o{ DONATIONS : "category"
    DONATIONS ||--o{ DONATION_IMAGES : photos
    DONATIONS ||--o{ STATUS_CHANGES : history
    DONATIONS ||--o{ HAND_OUTS : "handed out"
    DONATIONS ||--o{ RATINGS : rated
    DISTRIBUTION_POINTS ||--o{ DONATIONS : "sent to"
    APPEALS ||--o{ DONATIONS : "answered"

    DONATIONS {
        uuid id PK
        uuid donor_id FK
        int category_id FK
        int ai_category_id FK
        float ai_confidence
        json ai_top3
        string title
        int quantity
        bool is_food
        string food_type "cooked | dry"
        datetime prepared_at
        int urgency_score "0-100"
        text pickup_address
        float pickup_lat
        float pickup_lng
        string status
        uuid point_id FK
        uuid appeal_id FK
    }
    DONATION_IMAGES {
        uuid id PK
        uuid donation_id FK
        string kind "donor_photo | pickup_proof | delivery_proof | distribution_proof"
        text url
        float lat
        float lng
    }
    STATUS_CHANGES {
        uuid id PK
        uuid donation_id FK
        string from_status
        string to_status
        uuid changed_by FK
    }
    HAND_OUTS {
        uuid id PK
        uuid donation_id FK
        uuid point_id FK
        uuid handed_out_by FK "rider or admin"
        int quantity
        int families_served
        text photo_url
    }
```

## 3. Logistics

```mermaid
erDiagram
    LOCATIONS ||--o{ DISTRIBUTION_POINTS : "area of"
    DISTRIBUTION_POINTS }o--o{ CATEGORIES : "accepts (point_categories)"
    DONATIONS ||--o{ JOBS : "rider jobs"
    USERS ||--o{ JOBS : "rider"
    JOBS ||--o{ RIDER_PINGS : "GPS every 15 s"
    DISTRIBUTION_POINTS ||--o{ POINT_REQUESTS : "asks for"

    DISTRIBUTION_POINTS {
        uuid id PK
        string name
        string type "mosque | school | community_centre | relief_camp"
        uuid location_id FK
        float lat
        float lng
        bool same_day_food
        datetime closes_at "relief camps"
        uuid alert_id FK
    }
    JOBS {
        uuid id PK
        uuid donation_id FK
        uuid rider_id FK
        string status "assigned | accepted | declined | picked_up | delivered | cancelled"
        float recommendation_score
        uuid replaces_job_id FK
    }
    POINT_REQUESTS {
        uuid id PK
        uuid point_id FK
        int category_id FK
        int quantity
        string status "open | fulfilled"
    }
```

## 4. RAG knowledge base

```mermaid
erDiagram
    SOURCES ||--o{ REPORTS : provides
    REPORTS ||--o{ REPORT_CHUNKS : "split into"
    REPORT_CHUNKS ||--o{ CHUNK_LOCATIONS : "mentions"
    LOCATIONS ||--o{ CHUNK_LOCATIONS : ""

    SOURCES {
        int id PK
        string kind "gdacs | reliefweb | hdx_hapi | pbs_spi | pmd | web_search | upload"
        int every_minutes
        datetime last_run_at
    }
    REPORTS {
        uuid id PK
        int source_id FK
        string external_id
        text title
        string publisher "NDMA, PDMA KP, IPC..."
        datetime published_at
        string content_hash UK
        string status
    }
    REPORT_CHUNKS {
        uuid id PK
        uuid report_id FK
        int chunk_index
        text text
        vector embedding "384 dims, HNSW index"
    }
```

## 5. Needs, seasons, disasters

```mermaid
erDiagram
    LOCATIONS ||--o{ NEED_INDICATORS : about
    LOCATIONS ||--o{ NEED_LEVELS : "need per category"
    CATEGORIES ||--o{ NEED_LEVELS : ""
    CATEGORIES ||--o{ SEASONAL_RULES : ""
    DISASTER_ALERTS }o--o{ LOCATIONS : "alert_locations"
    DISASTER_ALERTS }o--o{ REPORTS : "alert_reports"
    DISASTER_ALERTS ||--o{ ALERT_NEEDS : needs
    DISASTER_ALERTS ||--o{ APPEALS : triggers

    NEED_INDICATORS {
        uuid id PK
        uuid location_id FK
        int category_id FK
        string indicator "ipc_phase3plus_share, price_change_3m..."
        float value
        date period_end
        int source_id FK
    }
    NEED_LEVELS {
        int id PK
        uuid location_id FK
        int category_id FK
        int level "0 none | 1 some | 2 high | 3 urgent"
        float score
        json reasons
    }
    DISASTER_ALERTS {
        uuid id PK
        string type
        string severity "watch | moderate | severe"
        string status "unconfirmed | confirmed | handled | dismissed"
        json reported_figures
        string gdacs_event_id
    }
    APPEALS {
        uuid id PK
        uuid alert_id FK
        uuid location_id FK
        json target_province_ids
        json category_ids
        datetime sent_at
    }
```

## 6. Trust and messages

`notifications` (one row per in-app message, with `data` for deep links) and `fraud_flags`
(rule code, severity, the entity it points at, evidence, review status). Flags are warnings only.

## Key rules the database supports

- **Only approved riders take jobs:** `rider_profiles.status = approved`.
- **Every status move is recorded** in `status_changes` (who, when, from, to).
- **A reassignment keeps history:** a new `jobs` row with `replaces_job_id`.
- **Web-search alerts start as `unconfirmed`;** appeals are always created by an admin (`appeals.created_by`).
- **Need levels are computed, not typed:** `need_levels` is rebuilt from `need_indicators`,
  `seasonal_rules`, alerts, point requests and deliveries, and keeps the `reasons` shown in the UI.
