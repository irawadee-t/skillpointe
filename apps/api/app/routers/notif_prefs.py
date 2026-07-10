"""
Notification preferences — email/SMS opt-in and preferred_locale on user_profiles.

GET   /me/preferences
PATCH /me/preferences
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.db import get_db

router = APIRouter(prefix="/me", tags=["me"])


class Preferences(BaseModel):
    email_opt_in: bool = True
    sms_opt_in: bool = False
    preferred_locale: str = "en"     # 'en' | 'es'


class PreferencesPatch(BaseModel):
    email_opt_in: Optional[bool] = None
    sms_opt_in: Optional[bool] = None
    preferred_locale: Optional[str] = Field(default=None, pattern="^(en|es)$")


@router.get("/preferences", response_model=Preferences)
async def get_preferences(user: CurrentUser = Depends(get_current_user)):
    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT email_opt_in, sms_opt_in, preferred_locale FROM public.user_profiles WHERE user_id = $1",
            user.user_id,
        )
    if not row:
        return Preferences()
    return Preferences(
        email_opt_in=bool(row["email_opt_in"]),
        sms_opt_in=bool(row["sms_opt_in"]),
        preferred_locale=row["preferred_locale"] or "en",
    )


@router.patch("/preferences", response_model=Preferences)
async def patch_preferences(
    body: PreferencesPatch,
    user: CurrentUser = Depends(get_current_user),
):
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    set_clauses = []
    values: list = []
    idx = 1
    for k, v in updates.items():
        set_clauses.append(f"{k} = ${idx}")
        values.append(v)
        idx += 1
    values.append(user.user_id)
    async with get_db() as conn:
        await conn.execute(
            f"UPDATE public.user_profiles SET {', '.join(set_clauses)}, updated_at = NOW() WHERE user_id = ${idx}",
            *values,
        )
    return await get_preferences(user=user)  # type: ignore[arg-type]
