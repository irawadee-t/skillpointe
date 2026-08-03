-- Per-request attempt counter for account-change confirmations.
--
-- Adds a lockout so a 6-digit confirmation code cannot be brute-forced: each
-- wrong guess increments `attempts`, and the confirm endpoint invalidates the
-- request once a small threshold is exceeded (see routers/account.py). This is
-- defense-in-depth alongside the per-user rate limiter.

ALTER TABLE account_change_requests
  ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0;
