"use client";

/**
 * ChatStartButton — creates a new chat session and navigates to it.
 */
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Loader2 } from "lucide-react";

interface ChatStartButtonProps {
  token: string;
}

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function ChatStartButton({ token }: ChatStartButtonProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleStart() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/applicant/me/chat/sessions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error("Failed to create session");
      const data = await res.json();
      router.push(`/applicant/chat/${data.session_id}`);
    } catch {
      setError("Could not start chat. Please try again.");
      setLoading(false);
    }
  }

  return (
    <div>
      <button
        onClick={handleStart}
        disabled={loading}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-white bg-spf-navy rounded-md px-3 py-1.5 hover:bg-spf-navy/90 disabled:opacity-50 transition-colors"
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Plus className="w-4 h-4" />
        )}
        {loading ? "Starting…" : "New chat"}
      </button>
      {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
    </div>
  );
}
