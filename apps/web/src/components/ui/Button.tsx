import Link from "next/link";
import { cn } from "@/lib/utils";

type Variant = "primary" | "inverse" | "secondary" | "outline";

const VARIANT: Record<Variant, string> = {
  primary: "btn-primary",
  inverse: "btn-primary-inverse",
  secondary: "btn-secondary",
  outline: "btn-pill-outline",
};

type CommonProps = {
  variant?: Variant;
  className?: string;
  children: React.ReactNode;
};

/** Pill / text-link CTA. Renders an <a> when `href` is set, else a <button>. */
export function Button({
  variant = "primary",
  className,
  children,
  href,
  ...rest
}: CommonProps &
  ({ href: string } & React.ComponentProps<typeof Link>) ) {
  return (
    <Link href={href} className={cn(VARIANT[variant], className)} {...rest}>
      {children}
    </Link>
  );
}

export function ButtonAction({
  variant = "primary",
  className,
  children,
  ...rest
}: CommonProps & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={cn(VARIANT[variant], className)} {...rest}>
      {children}
    </button>
  );
}
