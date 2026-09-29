from fastapi import FastAPI

app = FastAPI(
    title="EVE Diagnostic Booking API",
    description="Book diagnostic tests at centres and pay for them (simulated payments).",
)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
