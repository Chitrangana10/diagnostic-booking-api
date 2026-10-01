# Diagnostic Booking API

A backend for booking diagnostic tests (blood tests, scans, etc.) at labs and paying for them.
Payments are simulated, there is no real payment gateway.

Built with Python, FastAPI, PostgreSQL, Redis and Celery.

How the code is organised and how a request flows through it: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## What it does

- Sign up, log in, log out. Login uses JWT tokens (short access token + refresh token).
- Labs ("centres") offer tests, and each lab sets its own price for each test.
- A logged-in user books a test at a lab for a date and time.
- A fake payment endpoint pays for the booking (SUCCESS or FAILED) and updates the booking.
- A webhook endpoint takes payment updates from the "payment provider". Sending the same
  event twice does nothing the second time.

## Run it

You need Docker Desktop.

```bash
docker compose up --build -d
docker compose exec api python -m app.seed
```

- API docs (Swagger): http://localhost:8000/docs
- Admin login created by the seed: `admin@eve.com` / `admin12345` (demo values, change them for anything real)

`docker compose down` stops everything. Add `-v` to also delete the database.

The seed adds 3 labs, 4 tests with prices, and the admin user. It is safe to run twice.

### Run without Docker for the app

Only the database and Redis run in Docker. The app runs on your machine.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d db redis
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

## Run the tests

The tests use their own database (`eve_test`), so they never touch your real data.

```bash
docker compose up -d db redis
docker compose exec db psql -U eve -d postgres -c "CREATE DATABASE eve_test;"   # first time only
pytest
```

Useful variations:

```bash
pytest -v                                   # show every test name
pytest tests/test_webhook.py                # one file
pytest -k duplicate                         # tests with "duplicate" in the name
```

## Try it by hand

Open http://localhost:8000/docs. To call protected endpoints, log in first, copy the
`access_token`, click **Authorize** and paste it.

Or with curl (Git Bash):

```bash
# 1. sign up and log in
curl -X POST localhost:8000/auth/signup -H 'Content-Type: application/json' \
  -d '{"name":"Riya","email":"riya@example.com","password":"password123"}'

curl -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"riya@example.com","password":"password123"}'
# copy the access_token from the answer
TOKEN=paste_the_access_token_here

# 2. see the labs
curl localhost:8000/centres/

# 3. book test 1 at lab 1 (the time needs a timezone and must be in the future)
curl -X POST localhost:8000/bookings/ -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"test_id":1,"centre_id":1,"appointment_time":"2027-01-20T10:00:00+05:30"}'

# 4. pay for booking 1. "simulate" is optional, leave it out for a random result
curl -X POST localhost:8000/payments/ -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"booking_id":1,"simulate":"SUCCESS"}'
```

### Trying the webhook

The provider sends a JSON body and signs it. The signature goes in the `X-Signature` header:
an HMAC-SHA256 of the exact body, using `WEBHOOK_SECRET` as the key.

Take the `provider_ref` from the payment response in step 4 and use it here:

```bash
REF=paste_the_provider_ref_here
BODY='{"event_id":"evt_1","provider_ref":"'$REF'","status":"FAILED"}'
SIG=$(python -c "import hmac,hashlib,sys;print(hmac.new(b'change-me-webhook-secret',sys.argv[1].encode(),hashlib.sha256).hexdigest())" "$BODY")
curl -X POST localhost:8000/payments/webhook/ -H "X-Signature: $SIG" -d "$BODY"
```

What you get back:

| Answer | Meaning |
|---|---|
| `{"result":"processed"}` | the payment was waiting and has now been updated |
| `{"result":"duplicate"}` | this `event_id` was already received, nothing changed |
| `{"result":"ignored"}` | a new event, but the payment is already finished, nothing changed |

In step 4 the fake payment finishes straight away, so the first webhook for it comes back as
`ignored`. Run the last line again and you get `duplicate`. The case where a webhook finishes a
waiting payment is covered by the tests (`tests/test_webhook.py`).

## Endpoints

| Method | Path | Who can call it | What it does |
|---|---|---|---|
| POST | `/auth/signup` | anyone | create an account |
| POST | `/auth/login` | anyone | get an access token and a refresh token |
| POST | `/auth/refresh` | anyone with a refresh token | get a new pair of tokens |
| POST | `/auth/logout` | logged in | invalidate all of the user's tokens |
| GET | `/centres/` | anyone | list labs with their tests and prices (`page`, `size`, `location`) |
| GET | `/centres/{id}` | anyone | one lab |
| POST | `/centres/` | admin | add a lab |
| POST | `/centres/{id}/tests` | admin | make a lab offer a test at a price |
| PUT | `/centres/{id}/tests/{test_id}` | admin | change that price |
| GET | `/tests/` | anyone | list tests |
| POST | `/tests/` | admin | add a test |
| POST | `/bookings/` | logged in | book a test |
| GET | `/bookings/` | logged in | my bookings (`status`, `page`, `size`) |
| GET | `/bookings/{id}` | logged in | one of my bookings |
| POST | `/bookings/{id}/cancel` | logged in | cancel my booking |
| POST | `/payments/` | logged in | pay for a booking (simulated) |
| POST | `/payments/webhook/` | the payment provider | payment update, signed |

## Database

```
users ──< bookings >── diagnostic_centres ──< centre_tests >── diagnostic_tests
              │
              └──< payments            webhook_events (separate)
```

- **centre_tests** holds the price, because every lab charges its own price for a test.
- **bookings.amount** is a copy of the price taken when the booking was made, so changing a
  price later does not change old bookings.
- **webhook_events.event_id** is unique. That is what stops the same event being applied twice.
- Money is stored as `Numeric(10,2)`, not as a float.

Booking status can only move like this:

```
PENDING   -> CONFIRMED, FAILED or CANCELLED
CONFIRMED -> CANCELLED
FAILED and CANCELLED are final
```

The full table list and more detail are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Extras included

| Extra | How it is used |
|---|---|
| Redis cache | `GET /centres/` is cached for 60 seconds and cleared when a lab or price changes |
| Celery | one job retries failed webhook events, another cancels bookings left PENDING for 30 minutes |
| Webhook retry | failed events are retried up to 5 times, waiting 30s, 60s, 120s, 240s between tries |
| Rate limiting | 5 per minute on signup and login, 20 on refresh, 100 for everything else. Counters are in Redis |
| Logout / refresh tokens | access token lasts 15 minutes, refresh token 7 days, logout invalidates both straight away |
| Docker | `Dockerfile` and `docker-compose.yml` (api, worker, beat, database, redis) |
| Swagger | `/docs` |
| Structured logging | JSON log lines with `booking_id`, `payment_id`, `event_id` |
| Pagination | `page` and `size` on every list |
| Tests | 71 tests, run on a real PostgreSQL database |

## How errors are handled

| Situation | Answer |
|---|---|
| Wrong or missing fields, bad email, short password | 422 |
| Missing, wrong, expired or logged-out token | 401 |
| A normal user calls an admin endpoint | 403 |
| Someone else's booking | 404 (same as "not found", so ids cannot be guessed) |
| Unknown booking, lab or test id | 404 |
| Appointment in the past, or the lab does not offer the test | 400 |
| Email already registered | 409 |
| Paying twice, paying a cancelled or failed booking, cancelling twice | 409 |
| Webhook with a wrong signature | 401 |
| Same webhook sent again | 200 `duplicate`, nothing changes |
| New webhook for a payment that is already finished | 200 `ignored`, nothing changes |
| Webhook for a payment we do not know | 404, the event is kept and retried later |

## Assumptions

- A failed payment makes the booking FAILED right away, and the user books again.
- Cancelling a confirmed booking is allowed. Refunds are not handled.
- If a payment succeeds for a booking that was cancelled in the meantime, the payment is saved as
  SUCCESS, the booking stays CANCELLED, and a warning is logged so it can be refunded.
- Only admins can create labs and tests. Admins come from the seed script, never from signup.
- Appointment times must include a timezone and are stored in UTC.
- Logout logs the user out everywhere (all devices), not just one.
- The `simulate` field on `POST /payments/` exists only so the fake provider can be forced to a
  result in demos and tests.

## What I would do with more time

- Slots: opening hours and capacity, so two people cannot take the same slot at a lab.
- Log out of a single device instead of all devices.
- Refunds, and a payment history endpoint.
- Sign a timestamp together with the webhook body, so an old webhook cannot be replayed.
- A CI workflow that runs the tests on every push.
