import { CheckCircle2, Clock, XCircle, Edit3, Send } from "lucide-react";

const MAP: Record<string, { label: string; Icon: typeof Clock; tone: string }> = {
  draft:     { label: "Draft",       Icon: Edit3,        tone: "text-slate bg-stone/60 border-hairline" },
  pending:   { label: "In review",   Icon: Clock,        tone: "text-cohere-blue bg-wash-blue border-cohere-blue/30" },
  approved:  { label: "Approved",    Icon: CheckCircle2, tone: "text-cohere-green bg-wash-green border-cohere-green/30" },
  published: { label: "Live",        Icon: Send,         tone: "text-cohere-green bg-wash-green border-cohere-green/30" },
  rejected:  { label: "Needs edits", Icon: XCircle,      tone: "text-studio-maroon bg-studio-maroon/[0.06] border-studio-maroon/30" },
};

export function StatusBadge({ status }: { status: string }) {
  const m = MAP[status] ?? MAP.draft;
  const { Icon } = m;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-micro font-medium ${m.tone}`}>
      <Icon className="h-3 w-3" strokeWidth={2} />
      {m.label}
    </span>
  );
}
