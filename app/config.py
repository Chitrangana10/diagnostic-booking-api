from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://eve:eve@localhost:5432/eve"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "dev-secret-change-me-please-use-a-long-key"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # shared secret used to sign webhook bodies
    webhook_secret: str = "dev-webhook-secret"

    # chance that the fake payment succeeds when the caller doesn't force a result
    payment_success_rate: float = 0.8

    # pending bookings older than this get cancelled by the background job
    pending_booking_minutes: int = 30

    admin_email: str = "admin@eve.com"
    admin_password: str = "admin12345"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
