# Architecture and flow

This explains how the project is put together and what happens to a request.

## The big picture

```
 Client (Swagger, curl, a future app)
        │  HTTP
        ▼
 ┌──────────────────────────── api container ────────────────────────────┐
 │  Uvicorn  →  FastAPI app (main.py)                                    │
 │                 │                                                     │
 │      rate limiter (Redis)                                             │
 │                 ▼                                                     │
 │   routers  →  services  →  models  →  PostgreSQL                     │
 │  (HTTP)      (rules)       (tables)                                   │
 │                 │                                                     │
 │            Redis cache                                                │
 └───────────────────────────────────────────────────────────────────────┘

 beat container   → every minute / 5 minutes puts a job message in Redis
 worker container → takes the message from Redis and runs the job (uses PostgreSQL)
```

Five containers: `api`, `worker`, `beat`, `db` (PostgreSQL), `redis`.

## Folder structure

```
app/
  main.py            creates the app, registers routers, error handler, rate limiter
  config.py          settings read from environment / .env
  database.py        database connection and the get_db session
  security.py        password hashing, creating and checking JWT tokens
  dependencies.py    get_current_user (login check) and require_admin
  errors.py          AppError, raised by services when a rule is broken
  limiter.py         rate limiting (counters in Redis)
  cache.py           small Redis helpers for the cache
  logging_config.py  JSON log format
  seed.py            sample data and the admin user

  models/            database tables
  schemas/           request and response shapes, input validation
  routers/           the HTTP endpoints, no business logic
  services/          the business rules
  tasks/             Celery jobs and their schedule

tests/               one test file per feature
alembic/             database migrations
docs/                this file
```

## The three layers

| Layer | Folder | Job | Must not |
|---|---|---|---|
| Router | `routers/` | read the request, check who is calling, call a service, return the answer | contain business rules |
| Service | `services/` | decide if something is allowed, change data | know about HTTP |
| Model | `models/` | describe the database tables | contain logic |

When a rule is broken, a service raises `AppError(status, message)`. `main.py` catches it and
sends the JSON error. That is why services never import anything from FastAPI.

If you need to change a rule (for example "who can cancel a booking"), the change goes in a
service. If you need a new endpoint, it is a router function that calls a service.

## Database tables

```
users               id, name, email (unique), password_hash, is_admin, token_version
diagnostic_centres  id, name, location
diagnostic_tests    id, name (unique), description
centre_tests        id, centre_id, test_id, price         unique (centre_id, test_id)
bookings            id, user_id, centre_id, test_id, appointment_time, amount, status
payments            id, booking_id, amount, status, provider_ref (unique)
webhook_events      id, event_id (unique), payload, processed, attempts, next_retry_at
```

Why some things are the way they are:

- The price is in `centre_tests` because each lab has its own price for the same test.
- `bookings.amount` copies the price at booking time, so later price changes do not touch old bookings.
- `provider_ref` is the id the payment provider knows a payment by. Webhooks use it to find the payment.
- `webhook_events.event_id` is unique. This is the first protection against duplicate webhooks.
- `users.token_version` is explained under "Logout" below.

## Booking status

```
          ┌──────────► CONFIRMED ──────► CANCELLED
PENDING ──┼──────────► FAILED
          └──────────► CANCELLED
```

FAILED and CANCELLED are final. The allowed moves are written once, in the `ALLOWED_TRANSITIONS`
dictionary in `services/booking_service.py`, and `change_status()` is the only function that
changes a booking's status.

## Flows

### Sign up, log in, refresh, log out

1. **Signup**: the email is lowercased, the password is hashed with bcrypt, a user row is saved.
2. **Login**: the password is checked, and the user gets two JWTs: an access token (15 minutes)
   and a refresh token (7 days). Each contains the user id, its type and the user's
   `token_version`.
3. **Every protected request**: `get_current_user` reads the access token, loads the user, and
   checks that the token's `token_version` equals the one in the database.
4. **Refresh**: send the refresh token, get a new pair. An access token is not accepted here and a
   refresh token is not accepted as an access token, because the token type is checked.
5. **Logout**: `token_version` goes up by one. Every token issued before now carries the old
   number, so all of them stop working immediately. This logs the user out on all devices.

### Booking and paying

1. `POST /bookings/` → the date must be in the future, the lab and test must exist, and the lab
   must offer that test. The price is copied into `amount`. Status starts as PENDING.
2. `POST /payments/` →
   - lock the booking row, so a double click cannot create two payments
   - the booking must belong to the caller and be PENDING (else 404 / 409)
   - create a payment row, then the fake provider picks SUCCESS or FAILED
   - `apply_result` updates the payment and moves the booking to CONFIRMED or FAILED
   - everything is saved in one transaction

### Payment webhook (the idempotent part)

`POST /payments/webhook/`

```
 request
   │
   ├─ signature wrong?            → 401
   ├─ body not valid?             → 422
   │
   ├─ save the event in webhook_events (event_id is unique)
   │     already there and processed?   → 200 "duplicate", stop
   │     already there, not processed?  → carry on (earlier try failed)
   │
   ├─ find the payment by provider_ref and lock its row
   │     not found?  → save when to retry, 404
   │
   └─ payment still PENDING?
         yes → update payment and booking → "processed"
         no  → change nothing           → "ignored"
```

Two protections work together:

1. the unique `event_id` stops the same event from being handled twice
2. only a PENDING payment can change, so a late or contradicting event can never undo a finished one

Because the payment row is locked while it is updated, two identical webhooks arriving at the
same moment are handled one after the other, and only one of them changes anything. There is a
test for exactly this, using several threads.

If a payment succeeded for a booking that was cancelled in the meantime, the payment is saved as
SUCCESS, the booking stays CANCELLED, and a warning is logged so someone can refund it.

### Retrying failed webhook events

A webhook can fail when the payment is not known yet. The event stays in `webhook_events` as not
processed, and `next_retry_at` is set. The Celery job `retry_failed_webhooks` runs every minute and
retries only events that are due. The wait doubles after every failed attempt:

| Attempt that failed | Wait before the next one |
|---|---|
| 1 | 30 seconds |
| 2 | 60 seconds |
| 3 | 120 seconds |
| 4 | 240 seconds |
| 5 | stop, the event stays unprocessed |

### Listing labs and the cache

`GET /centres/` → look in Redis for the key `centres:list:<page>:<size>:<location>`.
Found → return it. Not found → read PostgreSQL, store the answer in Redis for 60 seconds, return it.
Creating a lab, adding a test to a lab or changing a price deletes all `centres:*` keys.
If Redis is down the cache is skipped and the API still works.

### Rate limiting

Counters are kept in Redis (so they are shared if more than one api container runs). Signup and
login allow 5 per minute per IP, refresh 20, everything else 100. If Redis is unreachable the
limiter falls back to counting in memory.

### Background jobs

| Job | Runs | What it does |
|---|---|---|
| `retry_failed_webhooks` | every 60 s | retries events that are due |
| `expire_pending_bookings` | every 5 min | cancels bookings that stayed PENDING for 30 minutes, unless a payment for them is still waiting |

`beat` only schedules, `worker` does the work, and Redis passes the messages between them.

## Why these choices

- **FastAPI**: input validation and the Swagger page come for free.
- **PostgreSQL**: real transactions and row locks, which the payment and webhook code depends on.
- **Alembic**: the database structure is versioned, and the api container runs `alembic upgrade head` on start.
- **Sync SQLAlchemy** (not async): simpler to read, and speed is not the problem here.
- **Tests on PostgreSQL** (not SQLite): row locking and unique constraints behave differently on SQLite.
