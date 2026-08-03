-- Chat guardrails: admin review-queue visibility for tripped guardrails.
--
-- The applicant planning chat now runs every LLM reply through a guardrail
-- pipeline (input moderation → grounded generation → output validation). When
-- a guardrail trips (harmful content, fabricated claims, discouraging tone),
-- the reply is replaced/regenerated AND the event is queued here so admins can
-- audit what the model tried to say. Additive change only.

ALTER TYPE public.review_queue_item_type_enum ADD VALUE IF NOT EXISTS 'chat_guardrail';

-- Guardrail metadata on the stored assistant message: which checks ran and
-- whether the content was replaced (fallback) or regenerated.
ALTER TABLE public.chat_messages
  ADD COLUMN IF NOT EXISTS guardrail_meta JSONB;

COMMENT ON COLUMN public.chat_messages.guardrail_meta IS
  'NULL for user messages / clean replies. Otherwise {version, checks_failed: [..], action: passed|regenerated|fallback|refused}.';
