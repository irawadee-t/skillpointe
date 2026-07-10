import { Fragment } from "react";

/**
 * Minimal, dependency-free markdown renderer for AI chat output.
 * Supports: **bold**, bullet lists ("- "), numbered context, and
 * blank-line paragraphs. Builds React nodes from text (no HTML injection).
 */

function inline(text: string, keyBase: string): React.ReactNode[] {
  // Split on **bold** spans.
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return (
        <strong key={`${keyBase}-b${i}`} className="font-semibold text-cohere-ink">
          {p.slice(2, -2)}
        </strong>
      );
    }
    return <Fragment key={`${keyBase}-t${i}`}>{p}</Fragment>;
  });
}

export function Markdown({ content, className }: { content: string; className?: string }) {
  const blocks = content.trim().split(/\n{2,}/);

  const isBullet = (l: string) => /^\s*[-•*]\s+/.test(l);

  return (
    <div className={className}>
      {blocks.map((block, bi) => {
        // Split a block into runs of bullet lines vs. plain text lines, so a
        // "Header:" line directly above a list still renders the list properly.
        const lines = block.split("\n");
        const runs: { type: "ul" | "p"; lines: string[] }[] = [];
        for (const l of lines) {
          const t = isBullet(l) ? "ul" : "p";
          const last = runs[runs.length - 1];
          if (last && last.type === t) last.lines.push(l);
          else runs.push({ type: t, lines: [l] });
        }

        return (
          <div key={bi} className="my-2 first:mt-0 last:mb-0">
            {runs.map((run, ri) =>
              run.type === "ul" ? (
                <ul key={ri} className="my-1.5 space-y-1.5">
                  {run.lines.map((l, li) => (
                    <li key={li} className="flex gap-2.5">
                      <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-cohere-green" />
                      <span>{inline(l.replace(/^\s*[-•*]\s+/, ""), `${bi}-${ri}-${li}`)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p key={ri} className="leading-relaxed">
                  {run.lines.map((l, li) => (
                    <Fragment key={li}>
                      {inline(l, `${bi}-${ri}-${li}`)}
                      {li < run.lines.length - 1 && <br />}
                    </Fragment>
                  ))}
                </p>
              ),
            )}
          </div>
        );
      })}
    </div>
  );
}
