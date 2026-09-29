from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models import DiagnosticTest
from app.schemas.centre import TestCreate, TestOut
from app.schemas.common import Page

router = APIRouter(prefix="/tests", tags=["tests"])


@router.get("/", response_model=Page[TestOut])
def list_tests(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count()).select_from(DiagnosticTest))
    tests = db.scalars(
        select(DiagnosticTest)
        .order_by(DiagnosticTest.id)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return Page(items=tests, total=total, page=page, size=size)


@router.post(
    "/",
    response_model=TestOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_test(data: TestCreate, db: Session = Depends(get_db)):
    test = DiagnosticTest(name=data.name, description=data.description)
    db.add(test)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A test with this name already exists")
    return test
