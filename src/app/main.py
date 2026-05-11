from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import time
from typing import Literal, Self
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import ItemRow

NAME_MAX_LEN = 120
DESCRIPTION_MAX_LEN = 2000
QUANTITY_MIN = 1
QUANTITY_MAX = 99_999

logger = logging.getLogger("app.request")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "%s %s %s %.2fms",
            request.method,
            request.url.path,
            500,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "%s %s %s %.2fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ItemCreate(BaseModel):
    """Request body for POST (create) and PUT (full replace)."""

    name: str = Field(..., min_length=1, max_length=NAME_MAX_LEN)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LEN)
    quantity: int = Field(default=1, ge=QUANTITY_MIN, le=QUANTITY_MAX)
    status: Literal["active", "inactive"] = "active"


class ItemUpdate(BaseModel):
    """Request body for PATCH (partial update). Omitted fields stay unchanged."""

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LEN)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LEN)
    quantity: int | None = Field(default=None, ge=QUANTITY_MIN, le=QUANTITY_MAX)
    status: Literal["active", "inactive"] | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        patch = self.model_dump(exclude_unset=True, exclude_none=True)
        if not patch:
            raise ValueError("At least one field must be provided for a partial update.")
        return self


class ItemResponse(BaseModel):
    """API response: id, fields, and audit timestamps."""

    id: UUID
    name: str
    description: str | None = None
    quantity: int = Field(ge=QUANTITY_MIN, le=QUANTITY_MAX)
    status: Literal["active", "inactive"] = "active"
    created_at: datetime
    updated_at: datetime


def _row_to_response(row: ItemRow) -> ItemResponse:
    st: Literal["active", "inactive"] = "active" if row.status == "active" else "inactive"
    return ItemResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        quantity=row.quantity,
        status=st,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _parse_item_id(item_id: str) -> UUID:
    try:
        return UUID(item_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid item_id format. Expected UUID.",
        ) from exc


def _duplicate_stmt(payload: ItemCreate):
    stmt = select(ItemRow).where(
        ItemRow.name == payload.name,
        ItemRow.quantity == payload.quantity,
        ItemRow.status == payload.status,
    )
    if payload.description is None:
        stmt = stmt.where(ItemRow.description.is_(None))
    else:
        stmt = stmt.where(ItemRow.description == payload.description)
    return stmt


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items", response_model=list[ItemResponse], status_code=200)
def list_items(
    db: Session = Depends(get_db),
    status: Literal["active", "inactive"] | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=100),
) -> list[ItemResponse]:
    stmt = select(ItemRow)
    if status is not None:
        stmt = stmt.where(ItemRow.status == status)
    rows = list(db.scalars(stmt).all())

    if search is not None:
        keyword = search.casefold()
        rows = [
            r
            for r in rows
            if keyword in r.name.casefold()
            or (r.description is not None and keyword in r.description.casefold())
        ]

    return [_row_to_response(r) for r in rows]


@app.post("/items", response_model=ItemResponse, status_code=201)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)) -> ItemResponse:
    if db.scalars(_duplicate_stmt(payload).limit(1)).first() is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Duplicate item. An item with the same name, description, quantity, and "
                "status already exists."
            ),
        )

    now = _utc_now()
    row = ItemRow(
        id=uuid4(),
        name=payload.name,
        description=payload.description,
        quantity=payload.quantity,
        status=payload.status,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_response(row)


@app.get("/items/{item_id}", response_model=ItemResponse, status_code=200)
def get_item(item_id: str, db: Session = Depends(get_db)) -> ItemResponse:
    parsed_id = _parse_item_id(item_id)
    row = db.get(ItemRow, parsed_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    return _row_to_response(row)


@app.put("/items/{item_id}", response_model=ItemResponse, status_code=200)
def replace_item(
    item_id: str, payload: ItemCreate, db: Session = Depends(get_db)
) -> ItemResponse:
    parsed_id = _parse_item_id(item_id)
    row = db.get(ItemRow, parsed_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found.")

    row.name = payload.name
    row.description = payload.description
    row.quantity = payload.quantity
    row.status = payload.status
    row.updated_at = _utc_now()
    db.commit()
    db.refresh(row)
    return _row_to_response(row)


@app.patch("/items/{item_id}", response_model=ItemResponse, status_code=200)
def update_item(
    item_id: str, payload: ItemUpdate, db: Session = Depends(get_db)
) -> ItemResponse:
    parsed_id = _parse_item_id(item_id)
    row = db.get(ItemRow, parsed_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found.")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(row, key, value)
    row.updated_at = _utc_now()
    db.commit()
    db.refresh(row)
    return _row_to_response(row)


@app.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: str, db: Session = Depends(get_db)) -> Response:
    parsed_id = _parse_item_id(item_id)
    row = db.get(ItemRow, parsed_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
