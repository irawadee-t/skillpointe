-- =============================================================
-- Migration: enums and extensions
-- Phase 3 — Core Data Model
--
-- All shared enum types and required extensions for SkillPointe Match.
-- These must be created before any table that references them.
-- =============================================================

-- pgvector: required for semantic scoring (Phase 7+).
-- Adding now so extracted_signals tables can carry the vector column from the start.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;


-- ---------------------------------------------------------------
-- Eligibility status (Stage 1 hard gates output)
-- ---------------------------------------------------------------
CREATE TYPE public.eligibility_status_enum AS ENUM (
  'eligible',   -- no critical hard failures
  'near_fit',   -- important gaps, still worth surfacing
  'ineligible'  -- critical mismatch; do not rank prominently
);


-- ---------------------------------------------------------------
-- Confidence tiers (extraction and match confidence)
-- ---------------------------------------------------------------
CREATE TYPE public.confidence_level_enum AS ENUM (
  'high',
  'medium',
  'low'
);


-- ---------------------------------------------------------------
-- Review status (for extraction, match, and queue items)
-- ---------------------------------------------------------------
CREATE TYPE public.review_status_enum AS ENUM (
  'pending',    -- not yet reviewed by admin
  'reviewed',   -- reviewed and approved as-is
  'overridden', -- admin manually changed the value
  'dismissed'   -- flagged item dismissed without action
);


-- ---------------------------------------------------------------
-- Match label (UI-facing label derived from eligibility + score)
-- ---------------------------------------------------------------
CREATE TYPE public.match_label_enum AS ENUM (
  'strong_match',
  'good_match',
  'near_fit',
  'low_fit',
  'ineligible'
);


-- ---------------------------------------------------------------
-- Work setting
-- ---------------------------------------------------------------
CREATE TYPE public.work_setting_enum AS ENUM (
  'remote',
  'hybrid',
  'on_site',
  'flexible'
);


-- ---------------------------------------------------------------
-- Document type (for applicant_documents)
-- ---------------------------------------------------------------
CREATE TYPE public.document_type_enum AS ENUM (
  'resume',
  'essay',
  'transcript',
  'certification',
  'other'
);


-- ---------------------------------------------------------------
-- Import status (for import_runs)
-- ---------------------------------------------------------------
CREATE TYPE public.import_status_enum AS ENUM (
  'pending',
  'processing',
  'complete',
  'failed',
  'partial'  -- completed with some row errors
);


-- ---------------------------------------------------------------
-- Review queue item type (what kind of thing is being reviewed)
-- ---------------------------------------------------------------
CREATE TYPE public.review_queue_item_type_enum AS ENUM (
  'extraction_confidence',    -- LLM extraction needs human check
  'taxonomy_mismatch',        -- normalization mapping uncertain
  'borderline_match',         -- match score near threshold
  'geography_ambiguity',      -- location interpretation unclear
  'credential_ambiguity',     -- credential present but uncertain
  'suspicious_import',        -- import row looks malformed or suspicious
  'low_confidence_verifier',  -- LLM verifier returned low-confidence verdict
  'admin_override_review'     -- item flagged because admin override was applied
);


-- ---------------------------------------------------------------
-- Chat role (for chat_messages)
-- ---------------------------------------------------------------
CREATE TYPE public.chat_role_enum AS ENUM (
  'user',
  'assistant',
  'system'
);
