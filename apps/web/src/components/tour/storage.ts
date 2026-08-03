/**
 * Tour persistence — localStorage, namespaced per user id so shared browsers
 * behave. Everything is best-effort: storage failures never break the app.
 */

const VERSION = "v1";

/** Old CoachMarkTour key — counts as "applicant welcome already dismissed". */
export const LEGACY_COACHMARK_KEY = "skillpointe:coachmark-tour:v1";

const ns = (userId: string) => `sn:tours:${VERSION}:${userId}`;

export type TourProgress = { tourId: string; stepIx: number };

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable — tours simply don't persist */
  }
}

export function hasSeenTour(userId: string, tourId: string): boolean {
  return read(`${ns(userId)}:seen:${tourId}`) !== null;
}

export function markTourSeen(userId: string, tourId: string) {
  write(`${ns(userId)}:seen:${tourId}`, new Date().toISOString());
}

export function isOfferDismissed(userId: string, role: string): boolean {
  if (role === "applicant" && read(LEGACY_COACHMARK_KEY) !== null) return true;
  return read(`${ns(userId)}:offer-dismissed:${role}`) !== null;
}

export function dismissOffer(userId: string, role: string) {
  write(`${ns(userId)}:offer-dismissed:${role}`, new Date().toISOString());
}

export function readProgress(userId: string): TourProgress | null {
  const raw = read(`${ns(userId)}:active`);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as TourProgress;
    if (typeof parsed.tourId === "string" && typeof parsed.stepIx === "number") {
      return parsed;
    }
  } catch {
    /* corrupted — treat as absent */
  }
  return null;
}

export function writeProgress(userId: string, progress: TourProgress | null) {
  write(
    `${ns(userId)}:active`,
    progress === null ? null : JSON.stringify(progress),
  );
}
