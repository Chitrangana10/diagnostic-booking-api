from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import cache
from app.database import get_db
from app.dependencies import require_admin
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest
from app.schemas.centre import (
    CentreCreate,
    CentreOut,
    CentreTestIn,
    PriceUpdate,
    centre_to_out,
)
from app.schemas.common import Page

router = APIRouter(prefix="/centres", tags=["centres"])

CACHE_PREFIX = "centres:"


def _load_centre(db: Session, centre_id: int) -> DiagnosticCentre:
    centre = db.scalar(
        select(DiagnosticCentre)
        .where(DiagnosticCentre.id == centre_id)
        .options(selectinload(DiagnosticCentre.offered_tests).selectinload(CentreTest.test))
    )
    if centre is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centre not found")
    return centre


@router.get("/", response_model=Page[CentreOut])
def list_centres(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    location: str | None = Query(None, description="filter by part of the location"),
    db: Session = Depends(get_db),
):
    cache_key = f"{CACHE_PREFIX}list:{page}:{size}:{location or ''}"
    cached = cache.get_json(cache_key)
    if cached is not None:
        return cached

    query = select(DiagnosticCentre)
    if location:
        query = query.where(DiagnosticCentre.location.ilike(f"%{location}%"))

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    centres = db.scalars(
        query.options(selectinload(DiagnosticCentre.offered_tests).selectinload(CentreTest.test))
        .order_by(DiagnosticCentre.id)
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    result = Page(
        items=[centre_to_out(c) for c in centres], total=total, page=page, size=size
    ).model_dump(mode="json")
    cache.set_json(cache_key, result)
    return result


@router.get("/{centre_id}", response_model=CentreOut)
def get_centre(centre_id: int, db: Session = Depends(get_db)):
    return centre_to_out(_load_centre(db, centre_id))


@router.post(
    "/",
    response_model=CentreOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_centre(data: CentreCreate, db: Session = Depends(get_db)):
    centre = DiagnosticCentre(name=data.name, location=data.location)
    db.add(centre)
    db.commit()
    cache.delete_prefix(CACHE_PREFIX)
    return centre_to_out(_load_centre(db, centre.id))


@router.post(
    "/{centre_id}/tests",
    response_model=CentreOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def add_test_to_centre(centre_id: int, data: CentreTestIn, db: Session = Depends(get_db)):
    centre = _load_centre(db, centre_id)
    if db.get(DiagnosticTest, data.test_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test not found")

    db.add(CentreTest(centre_id=centre.id, test_id=data.test_id, price=data.price))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Centre already offers this test")

    cache.delete_prefix(CACHE_PREFIX)
    db.expire_all()
    return centre_to_out(_load_centre(db, centre_id))


@router.put(
    "/{centre_id}/tests/{test_id}",
    response_model=CentreOut,
    dependencies=[Depends(require_admin)],
)
def update_test_price(
    centre_id: int, test_id: int, data: PriceUpdate, db: Session = Depends(get_db)
):
    offer = db.scalar(
        select(CentreTest).where(
            CentreTest.centre_id == centre_id, CentreTest.test_id == test_id
        )
    )
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centre does not offer this test")

    # old bookings keep the price they were made at, so only the offer changes
    offer.price = data.price
    db.commit()
    cache.delete_prefix(CACHE_PREFIX)
    db.expire_all()
    return centre_to_out(_load_centre(db, centre_id))
