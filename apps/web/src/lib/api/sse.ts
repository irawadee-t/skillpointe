/**
 * Shared SSE consumption for the chat surfaces (applicant planning chat,
 * employer analytics chat).
 *
 * Both talk to buffer-then-stream endpoints: the server runs its FULL
 * pipeline before the first byte, so every error the client can act on
 * arrives as a plain HTTP status BEFORE any SSE bytes — which is exactly
 * when a JSON re-POST is safe. Framing (identical on every endpoint):
 *
 *     event: chunk  data: {"delta": "..."}    (repeated)
 *     event: done   data: {<final payload>}   (terminal)
 */

/** Thrown when the stream endpoint couldn't start (non-2xx or network error
 *  BEFORE any bytes were consumed) — the only case where a JSON re-POST is
 *  safe, because the server hasn't persisted anything for this attempt that
 *  the JSON path would duplicate. */
export class StreamStartError extends Error {}

export interface SseEvent {
  event: string;
  data: Record<string, unknown>;
}

export function parseSseFrame(frame: string): SseEvent | null {
  let event: string | null = null;
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7).trim();
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!event || !data) return null;
  try {
    return { event, data: JSON.parse(data) as Record<string, unknown> };
  } catch {
    return null;
  }
}

/**
 * POST to an SSE endpoint and invoke `onEvent` for each parsed frame.
 *
 * Throws StreamStartError if the request fails before any bytes arrive
 * (network error or non-2xx) — callers fall back to their JSON endpoint on
 * that. A stream that breaks MID-flight resolves normally with whatever
 * frames were delivered: the server already stored the full reply, so the
 * caller keeps the accumulated partial rather than re-POSTing.
 */
export async function postSse(
  url: string,
  init: { token: string; body: unknown },
  onEvent: (ev: SseEvent) => void,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        Authorization: `Bearer ${init.token}`,
      },
      body: JSON.stringify(init.body),
    });
  } catch {
    throw new StreamStartError("network");
  }
  if (!res.ok) throw new StreamStartError(`API error ${res.status}`);

  const handle = (ev: SseEvent | null) => {
    if (ev) onEvent(ev);
  };

  if (res.body) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx: number;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          handle(parseSseFrame(buffer.slice(0, idx)));
          buffer = buffer.slice(idx + 2);
        }
      }
    } catch {
      // Stream broke mid-flight — keep whatever validated frames arrived.
    }
  } else {
    // No ReadableStream support — the response is still complete SSE text.
    const text = await res.text();
    for (const frame of text.split("\n\n")) handle(parseSseFrame(frame));
  }
}
