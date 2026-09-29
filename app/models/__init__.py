# import everything here so Base.metadata knows about all tables (needed by alembic and tests)
from app.models.booking import Booking, BookingStatus
from app.models.centre import CentreTest, DiagnosticCentre, DiagnosticTest
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.models.webhook_event import WebhookEvent
