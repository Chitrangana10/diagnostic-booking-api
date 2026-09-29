class AppError(Exception):
    """Raised by services when a business rule is broken. main.py turns it into an HTTP response."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
