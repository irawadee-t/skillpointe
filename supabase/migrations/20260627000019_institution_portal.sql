-- Institution partner portal: a self-serve role for colleges/training programs to
-- upload completions, see their roster, and review import history — the same
-- credential pipeline as the admin console, but scoped to one institution.

ALTER TABLE public.user_profiles DROP CONSTRAINT IF EXISTS user_profiles_role_check;
ALTER TABLE public.user_profiles
    ADD CONSTRAINT user_profiles_role_check
    CHECK (role = ANY (ARRAY['admin', 'applicant', 'employer', 'institution']));

CREATE TABLE IF NOT EXISTS public.institutions (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text NOT NULL,
    slug       text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.institution_contacts (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id uuid NOT NULL REFERENCES public.institutions(id) ON DELETE CASCADE,
    user_id        uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role           text NOT NULL DEFAULT 'admin',
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);
