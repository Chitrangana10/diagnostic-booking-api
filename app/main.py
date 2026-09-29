from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.limiter import limiter
from app.routers import auth

app = FastAPI(
    title="EVE Diagnostic Booking API",
    description="Book diagnostic tests at centres and pay for them (simulated payments).",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(auth.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
