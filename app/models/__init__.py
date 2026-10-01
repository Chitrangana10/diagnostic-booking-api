# import everything here so Base.metadata knows about all tables (needed by alembic and tests)
from app.models.booking import Booking, BookingStatus  # noqa: F401
from app.models.centre import CentreTest, DiagnosticCentre, DiagnosticTest  # noqa: F401
from app.models.payment import Payment, PaymentStatus  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.webhook_event import WebhookEvent  # noqa: F401
