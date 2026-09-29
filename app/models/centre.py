from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DiagnosticCentre(Base):
    __tablename__ = "diagnostic_centres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    location: Mapped[str] = mapped_column(String(255))

    offered_tests: Mapped[list["CentreTest"]] = relationship(
        back_populates="centre", cascade="all, delete-orphan"
    )


class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[str] = mapped_column(String(500), default="")


class CentreTest(Base):
    """A test offered by a centre. The price is per centre, so it lives here."""

    __tablename__ = "centre_tests"
    __table_args__ = (UniqueConstraint("centre_id", "test_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    centre_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_centres.id"))
    test_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_tests.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    centre: Mapped[DiagnosticCentre] = relationship(back_populates="offered_tests")
    test: Mapped[DiagnosticTest] = relationship()
