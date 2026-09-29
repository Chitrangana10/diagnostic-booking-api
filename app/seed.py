"""Puts starting data in an empty database:  python -m app.seed

Safe to run more than once, it skips anything that already exists.
"""
from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest, User
from app.security import hash_password

TESTS = ["Complete Blood Count", "Lipid Profile", "Thyroid Panel", "HbA1c"]

# centre name -> (location, {test name: price})
CENTRES = {
    "City Diagnostics": (
        "Connaught Place, Delhi",
        {"Complete Blood Count": "350", "Lipid Profile": "600", "HbA1c": "450"},
    ),
    "HealthFirst Labs": (
        "Bandra, Mumbai",
        {"Complete Blood Count": "400", "Thyroid Panel": "700", "HbA1c": "500"},
    ),
    "Green Cross Lab": (
        "Koramangala, Bengaluru",
        {"Lipid Profile": "550", "Thyroid Panel": "650"},
    ),
}


def seed() -> None:
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email == settings.admin_email)):
            db.add(
                User(
                    name="Admin",
                    email=settings.admin_email,
                    password_hash=hash_password(settings.admin_password),
                    is_admin=True,
                )
            )

        tests = {}
        for name in TESTS:
            test = db.scalar(select(DiagnosticTest).where(DiagnosticTest.name == name))
            if test is None:
                test = DiagnosticTest(name=name)
                db.add(test)
            tests[name] = test

        for name, (location, prices) in CENTRES.items():
            centre = db.scalar(select(DiagnosticCentre).where(DiagnosticCentre.name == name))
            if centre is not None:
                continue
            centre = DiagnosticCentre(name=name, location=location)
            db.add(centre)
            db.flush()
            for test_name, price in prices.items():
                db.flush()
                db.add(
                    CentreTest(
                        centre_id=centre.id, test_id=tests[test_name].id, price=Decimal(price)
                    )
                )

        db.commit()
    print(f"Seeded. Admin login: {settings.admin_email} / {settings.admin_password}")


if __name__ == "__main__":
    seed()
