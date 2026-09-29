from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=500)


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str


class CentreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    location: str = Field(min_length=1, max_length=255)


class CentreTestIn(BaseModel):
    test_id: int
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class PriceUpdate(BaseModel):
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class CentreTestOut(BaseModel):
    test_id: int
    name: str
    price: Decimal


class CentreOut(BaseModel):
    id: int
    name: str
    location: str
    tests: list[CentreTestOut]


def centre_to_out(centre) -> CentreOut:
    return CentreOut(
        id=centre.id,
        name=centre.name,
        location=centre.location,
        tests=[
            CentreTestOut(test_id=ct.test_id, name=ct.test.name, price=ct.price)
            for ct in centre.offered_tests
        ],
    )
