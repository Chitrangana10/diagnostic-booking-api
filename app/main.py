from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.errors import AppError
from app.limiter import limiter
from app.routers import auth, bookings, centres, tests

app = FastAPI(
    title="EVE Diagnostic Booking API",
    description="Book diagnostic tests at centres and pay for them (simulated payments).",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(auth.router)
app.include_router(bookings.router)
app.include_router(centres.router)
app.include_router(tests.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
