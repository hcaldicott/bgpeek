"""Webhook notification models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WebhookEvent(StrEnum):
    """Events that can trigger a webhook."""

    QUERY = "query"
    DEVICE_CREATE = "device_create"
    DEVICE_UPDATE = "device_update"
    DEVICE_DELETE = "device_delete"
    LOGIN = "login"


class WebhookBase(BaseModel):
    """Shared fields for webhook creation and response."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=255)
    url: str = Field(max_length=2048)
    events: list[WebhookEvent] = Field(min_length=1)
    enabled: bool = True


class WebhookCreate(WebhookBase):
    """Payload for creating a new webhook."""

    secret: str | None = Field(default=None, max_length=255)


class WebhookUpdate(BaseModel):
    """Partial update payload — all fields optional."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=2048)
    events: list[WebhookEvent] | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    secret: str | None = Field(default=None, max_length=255)


class Webhook(WebhookBase):
    """Webhook as stored in PostgreSQL."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    secret: str | None = None
    created_at: datetime
    updated_at: datetime

    def mask_secret(self) -> Webhook:
        """Return a copy with the secret masked for API responses."""
        if self.secret is None:
            return self
        return self.model_copy(update={"secret": "****"})


class WebhookPayload(BaseModel):
    """Payload sent to webhook URL."""

    event: WebhookEvent
    timestamp: str
    data: dict[str, Any]
