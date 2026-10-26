"""Envelope de paginação usado por todas as listas: {items, total, page, page_size}."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int
    page: int
    page_size: int


class Message(BaseModel):
    detail: str
