import Link from "next/link";

import AuroraWater from "@/components/AuroraWater";
import { Reveal } from "@/components/ui";
import { SkilledNationLogo } from "@/components/ui/Logo";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Brand panel — same light-ribbon scene as the landing hero, no intro
          (it's simply there), scrimmed for copy legibility. */}
      <aside className="relative hidden flex-col justify-between overflow-hidden p-12 text-studio-cream lg:flex">
        {/* Static red-sphere fallback — always present so the panel never
            renders flat black if WebGL is slow or unavailable. */}
        <div
          aria-hidden
          className="absolute inset-0 bg-[#0b0b0c]"
          style={{
            backgroundImage:
              "radial-gradient(58% 74% at 34% 26%, rgba(157,34,53,0.85), rgba(92,16,30,0.55) 45%, rgba(11,11,12,0) 72%)",
          }}
        />
        <AuroraWater
          className="absolute inset-0"
          intro={false}
          orb={{ x: 0.3, y: 0.2, r: 0.62 }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/55 via-black/15 to-black/25"
        />

        <Link href="/" className="relative z-10">
          <SkilledNationLogo width={170} invert />
        </Link>

        <div className="relative z-10 max-w-md">
          <h2 className="font-display text-card leading-[1.1] text-studio-cream sm:text-heading drop-shadow-[0_1px_10px_rgba(0,0,0,0.4)]">
            The right trade.
            <br />
            The right place.
          </h2>
          <p className="mt-5 text-body-lg text-studio-cream/85 drop-shadow-[0_1px_8px_rgba(0,0,0,0.4)]">
            Ranked matches, verified credentials, and a clear next step
            for SKILLED Scholars, employers, and the staff between them.
          </p>
        </div>

        <p className="relative z-10 text-micro text-studio-cream/50">
          © {new Date().getFullYear()} SKILLED Nation
        </p>
      </aside>

      {/* Form area */}
      <main className="flex min-h-screen flex-col items-center justify-center bg-canvas px-5 py-12">
        <Link href="/" className="mb-10 lg:hidden">
          <SkilledNationLogo width={160} />
        </Link>
        <Reveal className="w-full max-w-md">{children}</Reveal>
      </main>
    </div>
  );
}
