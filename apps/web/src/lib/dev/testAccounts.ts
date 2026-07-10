/**
 * Dev-only test account list — populates the quick-fill chips on the login page.
 *
 * IMPORTANT: This module is only ever imported behind a
 * `process.env.NODE_ENV === "development"` guard. In production builds the
 * import site becomes dead code and Next.js / the bundler strips both the
 * import and the strings below from the client bundle.
 *
 * If you add a real production login shortcut, do NOT put it here.
 */

export type DevAccount = {
  label: string;
  email: string;
  password: string;
};

export const DEV_ACCOUNTS: readonly DevAccount[] = [
  { label: "Admin",     email: "admin@test.local",     password: "Test1234!" },
  { label: "Applicant", email: "applicant@test.local", password: "Test1234!" },
  { label: "Employer",  email: "employer@test.local",  password: "Test1234!" },
] as const;
