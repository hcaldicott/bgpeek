"""SSH credential model for device authentication."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CredentialBase(BaseModel):
    """Fields shared by create / read variants."""

    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    auth_type: str = Field(default="key", pattern=r"^(key|password|key\+password)$")
    username: str = Field(min_length=1, max_length=255)
    key_name: str | None = None
    password: str | None = None


class CredentialCreate(CredentialBase):
    """Payload for creating a credential."""


class CredentialUpdate(BaseModel):
    """Partial update payload. All fields optional."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    auth_type: str | None = Field(default=None, pattern=r"^(key|password|key\+password)$")
    username: str | None = Field(default=None, min_length=1, max_length=255)
    key_name: str | None = None
    password: str | None = None


class Credential(CredentialBase):
    """Credential as stored in PostgreSQL (password masked in API responses)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    password: str | None = None
    created_at: datetime
    updated_at: datetime


class CredentialWithUsage(Credential):
    """Credential with count of devices referencing it."""

    device_count: int = 0
