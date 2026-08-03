import type { Metadata } from "next";

import { VerifyDocClient } from "./VerifyDocClient";

export const metadata: Metadata = {
  title: "Verify your document · SKILLED",
  robots: { index: false, follow: false },
};

/**
 * Public phone-upload page (QR handoff target). Deliberately unauthenticated —
 * the single-use token in the URL is the credential; the phone has no session.
 * Middleware only protects /applicant, /employer, /admin, so this passes through.
 */
export default async function VerifyDocPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <VerifyDocClient token={token} />;
}
