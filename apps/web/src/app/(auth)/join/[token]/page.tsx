/**
 * /join/{token} — accept a team invite (public, token-authenticated).
 *
 * Server component: resolves the invite (valid / expired / revoked / used /
 * unknown) so dead links render an honest state with no client fetch, then
 * hands the live form to JoinClient. Lives in the (auth) route group for the
 * split-screen brand shell.
 */
import { getJoinInfo, type JoinInfo } from "@/lib/api/team";
import { ApiError } from "@/lib/api/client";
import { JoinClient } from "./JoinClient";

export const dynamic = "force-dynamic";

export default async function JoinPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  let info: JoinInfo | null = null;
  let unknown = false;
  try {
    info = await getJoinInfo(token);
  } catch (e: unknown) {
    if (e instanceof ApiError && e.status === 404) {
      unknown = true;
    } else {
      throw e;
    }
  }

  return <JoinClient joinToken={token} info={info} unknown={unknown} />;
}
