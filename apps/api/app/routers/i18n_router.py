"""
On-demand LLM translation with caching.

POST /i18n/translate  — translate arbitrary text (returns cached if seen before)
GET  /i18n/job/{job_id}  — return translated {description, requirements, ...} for a job

Cache table: translated_content(entity_type, entity_id, field, locale, text).
Only 'es' is supported today; 'en' is a passthrough.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.util.rate_limit import rate_limit_llm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/i18n", tags=["i18n"])

SUPPORTED_LOCALES = {"en", "es"}


class TranslateIn(BaseModel):
    text: str = Field(max_length=10000)
    target: str = Field(default="es", pattern="^(en|es)$")
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    field: Optional[str] = None


class TranslateOut(BaseModel):
    text: str
    locale: str
    cached: bool = False


class TranslatedJob(BaseModel):
    job_id: UUID
    locale: str
    fields: dict[str, str]


@router.post(
    "/translate",
    response_model=TranslateOut,
    dependencies=[Depends(rate_limit_llm("i18n_translate"))],
)
async def translate(body: TranslateIn, _: CurrentUser = Depends(get_current_user)):
    if body.target == "en":
        return TranslateOut(text=body.text, locale="en", cached=True)

    async with get_db() as conn:
        if body.entity_type and body.entity_id and body.field:
            row = await conn.fetchrow(
                """
                SELECT text FROM public.translated_content
                 WHERE entity_type = $1 AND entity_id = $2 AND field = $3 AND locale = $4
                """,
                body.entity_type, body.entity_id, body.field, body.target,
            )
            if row:
                return TranslateOut(text=row["text"], locale=body.target, cached=True)

        translated = await _llm_translate(body.text, body.target)

        if body.entity_type and body.entity_id and body.field:
            await conn.execute(
                """
                INSERT INTO public.translated_content
                  (entity_type, entity_id, field, locale, text)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (entity_type, entity_id, field, locale) DO UPDATE SET text = EXCLUDED.text
                """,
                body.entity_type, body.entity_id, body.field, body.target, translated,
            )

    return TranslateOut(text=translated, locale=body.target, cached=False)


@router.get(
    "/job/{job_id}",
    response_model=TranslatedJob,
    dependencies=[Depends(rate_limit_llm("i18n_translate"))],
)
async def translate_job(
    job_id: UUID,
    target: str = "es",
    _: CurrentUser = Depends(get_current_user),
):
    if target not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=400, detail=f"Locale not supported: {target}")

    async with get_db() as conn:
        job = await conn.fetchrow(
            """
            SELECT id, title_raw, description_raw, responsibilities_raw,
                   requirements_raw, preferred_qualifications_raw
              FROM public.jobs WHERE id = $1
            """,
            job_id,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")

        if target == "en":
            return TranslatedJob(
                job_id=job_id,
                locale="en",
                fields={k: (job[k] or "") for k in (
                    "title_raw", "description_raw", "responsibilities_raw",
                    "requirements_raw", "preferred_qualifications_raw",
                )},
            )

        cached_rows = await conn.fetch(
            """
            SELECT field, text FROM public.translated_content
             WHERE entity_type = 'job' AND entity_id = $1 AND locale = $2
            """,
            job_id, target,
        )
        cache = {r["field"]: r["text"] for r in cached_rows}

        out: dict[str, str] = {}
        for field in ("title_raw", "description_raw", "responsibilities_raw",
                      "requirements_raw", "preferred_qualifications_raw"):
            original = job[field] or ""
            if not original.strip():
                out[field] = ""
                continue
            if field in cache:
                out[field] = cache[field]
                continue
            translated = await _llm_translate(original, target)
            out[field] = translated
            await conn.execute(
                """
                INSERT INTO public.translated_content
                  (entity_type, entity_id, field, locale, text)
                VALUES ('job', $1, $2, $3, $4)
                ON CONFLICT (entity_type, entity_id, field, locale) DO UPDATE SET text = EXCLUDED.text
                """,
                job_id, field, target, translated,
            )

    return TranslatedJob(job_id=job_id, locale=target, fields=out)


_SYS_ES = (
    "You are translating trades-industry job descriptions from English to natural, plain-spoken "
    "Latin-American Spanish suitable for skilled tradesworkers (welders, electricians, mechanics, "
    "HVAC techs, CDL drivers). Keep certification and license names in their canonical English form "
    "(OSHA 30, AWS D1.1, EPA 608, CDL Class A) — do not translate those. Return ONLY the translated "
    "text, no preamble."
)


async def _llm_translate(text: str, target: str) -> str:
    if not text.strip():
        return ""
    if target != "es":
        return text
    settings = get_settings()
    from app.util.openai_client import get_openai_client
    client = get_openai_client()
    if client is None:
        return text
    # Degrade gracefully: an OpenAI outage/timeout returns the original English
    # text rather than 500-ing the request.
    try:
        resp = client.chat.completions.create(
            model=settings.llm_extraction_model,
            messages=[
                {"role": "system", "content": _SYS_ES},
                {"role": "user",   "content": text[:8_000]},
            ],
            temperature=0.2,
            max_tokens=2_000,
        )
        return (resp.choices[0].message.content or "").strip() or text
    except Exception as exc:
        logger.warning("Translation degraded to source text (OpenAI error): %s", exc)
        return text
