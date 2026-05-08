from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, model_validator
from fastapi.middleware.cors import CORSMiddleware
import time
import logging
from fastapi import Request
app = FastAPI()

NAME_MAX_LEN = 120
DESCRIPTION_MAX_LEN = 2000
QUANTITY_MIN = 1
QUANTITY_MAX = 99_999

logger = logging.getLogger("app.request")
logging.basicConfig(level=logging.INFO)


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
    def at_least_one_field(self) -> ItemUpdate:
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


_items: list[ItemResponse] = []


def _parse_item_id(item_id: str) -> UUID:
    try:
        return UUID(item_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid item_id format. Expected UUID.",
        ) from exc


def _get_item_index(item_id: UUID) -> int:
    for index, item in enumerate(_items):
        if item.id == item_id:
            return index
    raise HTTPException(status_code=404, detail="Item not found.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items", response_model=list[ItemResponse], status_code=200)
def list_items(
    status: Literal["active", "inactive"] | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=100),
) -> list[ItemResponse]:
    filtered_items = list(_items)

    if status is not None:
        filtered_items = [item for item in filtered_items if item.status == status]

    if search is not None:
        keyword = search.casefold()
        filtered_items = [
            item
            for item in filtered_items
            if keyword in item.name.casefold()
            or (item.description is not None and keyword in item.description.casefold())
        ]

    return filtered_items


@app.post("/items", response_model=ItemResponse, status_code=201)
def create_item(payload: ItemCreate) -> ItemResponse:
    for existing in _items:
        if (
            existing.name == payload.name
            and existing.description == payload.description
            and existing.quantity == payload.quantity
            and existing.status == payload.status
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Duplicate item. An item with the same name, description, quantity, and "
                    "status already exists."
                ),
            )

    now = _utc_now()
    item = ItemResponse(
        id=uuid4(),
        name=payload.name,
        description=payload.description,
        quantity=payload.quantity,
        status=payload.status,
        created_at=now,
        updated_at=now,
    )
    _items.append(item)
    return item


@app.get("/items/{item_id}", response_model=ItemResponse, status_code=200)
def get_item(item_id: str) -> ItemResponse:
    parsed_id = _parse_item_id(item_id)
    return _items[_get_item_index(parsed_id)]


@app.put("/items/{item_id}", response_model=ItemResponse, status_code=200)
def replace_item(item_id: str, payload: ItemCreate) -> ItemResponse:
    parsed_id = _parse_item_id(item_id)
    index = _get_item_index(parsed_id)
    previous = _items[index]
    updated = ItemResponse(
        id=parsed_id,
        name=payload.name,
        description=payload.description,
        quantity=payload.quantity,
        status=payload.status,
        created_at=previous.created_at,
        updated_at=_utc_now(),
    )
    _items[index] = updated
    return updated


@app.patch("/items/{item_id}", response_model=ItemResponse, status_code=200)
def update_item(item_id: str, payload: ItemUpdate) -> ItemResponse:
    parsed_id = _parse_item_id(item_id)
    index = _get_item_index(parsed_id)
    current = _items[index]
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    merged = {**current.model_dump(), **changes}
    merged["updated_at"] = _utc_now()
    updated = ItemResponse(**merged)
    _items[index] = updated
    return updated


@app.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: str) -> Response:
    parsed_id = _parse_item_id(item_id)
    index = _get_item_index(parsed_id)
    _items.pop(index)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
