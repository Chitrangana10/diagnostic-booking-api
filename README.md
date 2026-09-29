# EVE Diagnostic Booking API

A backend service where patients book diagnostic tests at labs and pay for them. Payments are
simulated (no real gateway). Built with **FastAPI, PostgreSQL, SQLAlchemy, Redis and Celery**.

## Run it

### With Docker (easiest)

```bash
docker compose up --build
docker compose exec api python -m app.seed     # sample centres, tests and an admin user
```

- API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs (click **Authorize** and paste the token from `/auth/login`)
- Admin login created by the seed: `admin@eve.com` / `admin12345`

Docker starts five containers: `api`, `worker` and `beat` (Celery), `db` (Postgres), `redis`.
The api container runs the Alembic migrations on start.

### Locally (without Docker for the app)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d db redis                          # just the database and redis
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

Optional, for the background jobs: `celery -A app.tasks.celery_app worker --beat --loglevel=info`

### Tests

Tests use a separate Postgres database called `eve_test`, so they never touch real data.

```bash
docker compose up -d db redis
docker compose exec db psql -U eve -d postgres -c "CREATE DATABASE eve_test;"   # only once
pytest
```

## How the code is organised

```
app/
  routers/    HTTP only: read the request, call a service, return the response
  services/   business rules (booking state machine, payments, webhook)
  models/     database tables
  schemas/    request / response shapes and validation (pydantic)
  tasks/      Celery jobs
  security.py, dependencies.py   password hashing, JWT, "who is the current user"
  cache.py, limiter.py, logging_config.py
tests/
alembic/      database migrations
```

Routers never contain business logic. Services raise `AppError(status, message)` when a rule is
broken, and `main.py` turns that into the HTTP response.

## API

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/auth/signup` | anyone | create an account |
| POST | `/auth/login` | anyone | get a JWT |
| GET | `/centres/` | anyone | list centres with their tests and prices (`page`, `size`, `location`) |
| GET | `/centres/{id}` | anyone | one centre |
| POST | `/centres/` | admin | create a centre |
| POST | `/centres/{id}/tests` | admin | make a centre offer a test at a price |
| PUT | `/centres/{id}/tests/{test_id}` | admin | change that price |
| GET | `/tests/` | anyone | list tests |
| POST | `/tests/` | admin | create a test |
| POST | `/bookings/` | user | book a test |
| GET | `/bookings/` | user | my bookings (`status`, `page`, `size`) |
| GET | `/bookings/{id}` | user | one of my bookings |
| POST | `/bookings/{id}/cancel` | user | cancel my booking |
| POST | `/payments/` | user | pay for a booking (simulated) |
| POST | `/payments/webhook/` | payment provider | payment status update, signed |

### Example requests

```bash
# sign up and log in
curl -X POST localhost:8000/auth/signup -H 'Content-Type: application/json' \
  -d '{"name":"Riya","email":"riya@example.com","password":"password123"}'
curl -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"riya@example.com","password":"password123"}'
# -> {"access_token":"<TOKEN>","token_type":"bearer"}

# see centres
curl localhost:8000/centres/

# book test 1 at centre 1 (time must include a timezone and be in the future)
curl -X POST localhost:8000/bookings/ -H "Authorization: Bearer <TOKEN>" \
  -H 'Content-Type: application/json' \
  -d '{"test_id":1,"centre_id":1,"appointment_time":"2027-01-20T10:00:00+05:30"}'

# pay. "simulate" is optional: leave it out for a random result (80% success)
curl -X POST localhost:8000/payments/ -H "Authorization: Bearer <TOKEN>" \
  -H 'Content-Type: application/json' -d '{"booking_id":1,"simulate":"SUCCESS"}'
```

### The webhook

The provider sends `{"event_id": "...", "provider_ref": "...", "status": "SUCCESS" | "FAILED"}`.
`provider_ref` is the id returned when the payment was created. The body must be signed:
header `X-Signature` = hex HMAC-SHA256 of the raw body using `WEBHOOK_SECRET`.

```bash
BODY='{"event_id":"evt_1","provider_ref":"<PROVIDER_REF>","status":"SUCCESS"}'
SIG=$(python -c "import hmac,hashlib,sys;print(hmac.new(b'change-me-webhook-secret',sys.argv[1].encode(),hashlib.sha256).hexdigest())" "$BODY")
curl -X POST localhost:8000/payments/webhook/ -H "X-Signature: $SIG" -d "$BODY"
```

Response is `{"result": "processed"}` the first time, `"duplicate"` if the same `event_id` comes
again, and `"ignored"` if it is a new event for a payment that is already finished.

## Database design

```
users ──< bookings >── diagnostic_centres ──< centre_tests >── diagnostic_tests
             │
             └──< payments          webhook_events (standalone)
```

| Table | Important columns |
|---|---|
| users | email (unique), password_hash, is_admin |
| diagnostic_centres | name, location |
| diagnostic_tests | name (unique) |
| centre_tests | centre_id, test_id, **price**. Unique on (centre_id, test_id) |
| bookings | user_id, centre_id, test_id, appointment_time, **amount**, status |
| payments | booking_id, amount, status, provider_ref (unique) |
| webhook_events | **event_id (unique)**, payload, processed, attempts |

Why it looks like this:

- **Price is on `centre_tests`**, not on the test, because every centre charges its own price.
- **`bookings.amount` is a copy** of the price at booking time, so changing a price later does not
  change old bookings.
- **`webhook_events.event_id` is unique.** That constraint is what makes the webhook idempotent.
- Money uses `Numeric(10,2)`, never floats.
- Indexes on the columns we filter by: `bookings.user_id`, `bookings.status`, `payments.booking_id`, `users.email`.

### Booking states

```
PENDING   -> CONFIRMED | FAILED | CANCELLED
CONFIRMED -> CANCELLED
FAILED, CANCELLED -> (final)
```

The allowed moves are one dict (`ALLOWED_TRANSITIONS`) in `services/booking_service.py`, and
`change_status()` is the only function that changes a booking's status.

## How the webhook stays idempotent

1. Verify the signature (401 if wrong).
2. Insert the event into `webhook_events`. If `event_id` already exists the database rejects it,
   so we know it is a repeat and change nothing.
3. Lock the payment row (`SELECT ... FOR UPDATE`) and only update it **if it is still PENDING**.
   A late or contradicting event can never overwrite a finished payment.
4. Payment and booking are updated in one transaction.

So there are two layers: the unique `event_id`, and the "only PENDING payments can change" check.
`tests/test_webhook.py` includes a test that fires the same event from 6 threads at once.

If processing fails (for example the payment is not known yet), the event stays stored as
unprocessed and a Celery job retries it every minute, up to 5 attempts.

## Bonus features

| Feature | Where |
|---|---|
| Redis cache | `GET /centres/` is cached for 60s, cleared when a centre or price changes. If Redis is down the API still works. |
| Celery | `retry_failed_webhooks` (every minute) and `expire_pending_bookings` (cancels bookings pending more than 30 min) |
| Docker | `Dockerfile`, `docker-compose.yml` |
| Swagger | `/docs` |
| Tests | `pytest`, 59 tests |
| Structured logging | JSON logs with `booking_id`, `payment_id`, `event_id` |
| Pagination | `page` and `size` on all list endpoints |
| Rate limiting | 5/min on signup and login, 100/min per IP for everything else |
| Webhook retry | described above |

## Edge cases handled

| Case | Response |
|---|---|
| Bad JSON / missing fields / bad email / short password | 422 |
| Missing or invalid token | 401 |
| Normal user calling an admin endpoint | 403 |
| Someone else's booking | 404 (same as "not found", so ids can't be guessed) |
| Unknown booking / centre / test id | 404 |
| Appointment in the past, or centre doesn't offer the test | 400 |
| Duplicate signup email | 409 |
| Paying twice, paying a cancelled or failed booking, cancelling twice | 409 |
| Webhook with a bad signature | 401 |
| Same webhook event repeated | 200 `duplicate`, nothing changes |
| Contradicting webhook after payment finished | 200 `ignored`, nothing changes |
| Webhook for a payment we don't know | 404, event kept and retried by the job |

## Assumptions

- A failed payment fails the booking straight away, and the user books again. There is one payment
  attempt per booking.
- Cancelling a confirmed booking is allowed. Refunds are out of scope.
- If a payment succeeds for a booking that was cancelled meanwhile, the payment is recorded as
  SUCCESS but the booking stays CANCELLED, and a warning is logged so it can be refunded.
- Only admins create centres and tests. Admins are created by the seed script, never by signup.
- Appointment times must include a timezone. All times are stored in UTC.
- `simulate` on `POST /payments/` exists only so the fake provider can be forced in demos and tests.

## What I would improve with more time

- Real slot management: opening hours, capacity per slot, no double booking of the same slot.
- Refresh tokens and logout. Right now a JWT is valid until it expires.
- Retry with exponential backoff (right now it is a fixed one minute), and a dead-letter view for
  events that gave up.
- Rate limit storage in Redis, so limits are shared if the API runs as several containers.
- A payments history endpoint, and refunds for cancelled paid bookings.
- Include the `X-Signature` timestamp in the signed data to stop replay of old webhooks.
- CI pipeline that runs the tests on every push.
