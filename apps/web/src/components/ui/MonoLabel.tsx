import { cn } from "@/lib/utils";

/** Uppercase technical / system marker label. */
export function MonoLabel({
  children,
  className,
  as: Tag = "span",
  id,
}: {
  children: React.ReactNode;
  className?: string;
  as?: "span" | "div" | "h2" | "h3" | "p";
  id?: string;
}) {
  return <Tag id={id} className={cn("mono-label", className)}>{children}</Tag>;
}
