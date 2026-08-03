/**
 * applyReturn.ts — the "finish your application" return-trip contract.
 *
 * When the ApplySheet blocks on a missing credential, it stores a pending
 * return here and sends the user to /applicant/credentials?return=<jobId>.
 * The page that mounts the sheet (jobs browse, match detail, matches list)
 * consumes the pending return on mount and reopens the sheet on that job.
 * The ApplySheet itself also self-opens when it is mounted for the matching
 * job (covers parents that keep the sheet mounted with open=false).
 *
 * sessionStorage (not query params) so browser Back works and the state
 * survives the credentials detour without leaking into shareable URLs.
 */

export interface ApplyReturn {
  jobId: string;
  /** Path (+search) of the page the user applied from — used for the "Back to your application" link. */
  href: string;
  title?: string;
}

const KEY = "skilled:applyReturn";

export function setApplyReturn(r: ApplyReturn): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(r));
  } catch {
    /* storage unavailable — the user just loses the auto-reopen, nothing breaks */
  }
}

/** Read without clearing — for the credentials page banner. */
export function peekApplyReturn(): ApplyReturn | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ApplyReturn;
    return parsed && typeof parsed.jobId === "string" && typeof parsed.href === "string"
      ? parsed
      : null;
  } catch {
    return null;
  }
}

/**
 * Read AND clear the pending return. Pass a jobId to consume only a matching
 * pending return (returns null and leaves storage untouched otherwise).
 */
export function consumeApplyReturn(jobId?: string): ApplyReturn | null {
  const pending = peekApplyReturn();
  if (!pending) return null;
  if (jobId && pending.jobId !== jobId) return null;
  clearApplyReturn();
  return pending;
}

export function clearApplyReturn(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
