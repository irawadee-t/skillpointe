"""
Pydantic schemas for GDPR/CCPA-style account deletion endpoints.

Deletion flow:
  1. POST /me/account/delete-request { password }  → mark pending_deletion_at
  2. POST /me/account/cancel-deletion              → clear pending_deletion_at
  3. DELETE /admin/account/{user_id}               → cascade delete (admin)
  4. Weekly worker sweep: users pending_deletion_at older than 7 days are
     hard-deleted (see app.worker.scheduler).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeleteAccountRequest(BaseModel):
    """User re-authenticates by password before we schedule their deletion."""
    password: str = Field(..., min_length=1, max_length=200)
    reason: Optional[str] = Field(default=None, max_length=2000)


class DeleteAccountResponse(BaseModel):
    status: str  # "pending"
    pending_deletion_at: datetime
    hard_delete_after: datetime
    message: str


class CancelDeletionResponse(BaseModel):
    status: str  # "cancelled"
    message: str


class HardDeleteResponse(BaseModel):
    """Admin-only response after cascade delete."""
    user_id: str
    tables_cleared: list[str]
    completed_at: datetime
