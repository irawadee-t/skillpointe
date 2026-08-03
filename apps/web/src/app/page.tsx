import Link from "next/link";
import { ArrowRight, Plus } from "lucide-react";

import { MarketingNav } from "@/components/marketing/MarketingNav";
import AuroraWater from "@/components/AuroraWater";
import { OrbMark } from "@/components/ui/Orb";
import { Reveal } from "@/components/ui";

/**
 * SKILLED Nation Match — marketing landing.
 *
 * Voice (from skilled-nation.org): short, declarative, confident. Concrete
 * numbers, never vague. Second person for workers, plain business case for
 * employers. No marketing-hedge words, no exclamation points — enthusiasm
 * lives in verbs. CTAs are verb-first with a trailing arrow.
 *
 * Layout: dark silk hero, then a light editorial page — left-aligned,
 * hairline-ruled, no centered card grids. The orb recurs once, quietly, in
 * the closing band so the page ends where it began.
 */

const PARTNERS = [
  "3M", "Ball", "DEWALT", "Ford", "GE Vernova",
  "The Home Depot", "Norfolk Southern", "PulteGroup",
  "Schneider Electric", "Southwire",
];

const STATS = [
  { value: "$10M", label: "in scholarships available in 2026" },
  { value: "3,000+", label: "SKILLED Scholars across all 50 states" },
  { value: "90%+", label: "employed within a year of training" },
];

const FEATURES = [
  {
    h: "Ranked, not guessed",
    b: "Every match is scored on trade fit, drive time, pay, and credentials. Nothing hidden. Every score explains itself.",
  },
  {
    h: "Credentials verified",
    b: "OSHA, CDL, NCCER, EPA 608, checked against national registries. Employers see a badge, not your word for it.",
  },
  {
    h: "Apply in one click",
    b: "Your profile and credentials go straight to the employer. No re-typing. No black-hole applications.",
  },
];

/**
 * Example-match preview — an honest, static render of a REAL posting from the
 * public demo catalog (Southwire's "Underground Lineman", Fort Worth TX),
 * scored the way an applicant sees it, for a stated sample profile. Clearly
 * labeled "Example match" so a cold visitor sees what "ranked matches" means
 * before the signup wall.
 */
const EXAMPLE_MATCH = {
  title: "Underground Lineman",
  employer: "Southwire",
  location: "Fort Worth, TX · On-site",
  score: 91,
  label: "Strong fit",
  dimensions: [
    { label: "Trade fit", score: 95 },
    { label: "Drive time", score: 88 },
    { label: "Credentials", score: 92 },
    { label: "Pay range", score: 78 },
    { label: "Timing", score: 90 },
  ],
  why: "Why it ranks: the trade matches the sample profile's lineworker program, the site is a 34-minute drive from Dallas, and the required CDL is already verified.",
};

const STEPS = [
  { n: "1", h: "Build your profile", b: "Trade, credentials, where you can work, when you can start." },
  { n: "2", h: "See matches ranked", b: "Real openings from real employers, ordered by fit. Each one explains its score." },
  { n: "3", h: "Apply on SKILLED", b: "Credentials go straight to the employer. Track every response in one place." },
];

const FAQS: Array<{ q: string; a: React.ReactNode }> = [
  {
    q: "Is it free?",
    a: "Yes, for workers. Always. Employers pay a modest platform fee. SKILLED Nation scholarships also cover training tuition, tools, and certifications.",
  },
  {
    q: "Who can join?",
    a: "Any US-based worker in a skilled trade: electrical, welding, HVAC, automotive, construction, manufacturing, logistics, aviation, healthcare. If you don't need a four-year degree to do it, it belongs here.",
  },
  {
    q: "How do you find matches?",
    a: "We score every job against your profile on nine things: trade, credentials, location, drive time, pay range, work setting, experience, availability, and employer preferences. Every match tells you why. No black boxes.",
  },
  {
    q: "What credentials count?",
    a: "OSHA 10 / 30, CDL classes, NCCER cards, EPA 608, welding certs, state licenses, apprenticeship hours, and program completion certificates. We verify them against national registries so you show up with a badge, not a promise.",
  },
  {
    q: "Do I have to leave SKILLED to apply?",
    a: "No. Most jobs let you apply in-platform: one click, credentials attached, no re-typing. Some employers still route to their own careers page; when that happens, we tell you before you leave.",
  },
  {
    q: "Who's behind this?",
    a: (
      <>
        SKILLED Nation, the nonprofit that has funded 3,000+ scholarships across all 50 states. Backed by 3M, Ball, DEWALT, Ford Philanthropy, GE Vernova, The Home Depot Foundation, Norfolk Southern, PulteGroup, Schneider Electric, and Southwire.{" "}
        <Link href="/about" className="text-studio-maroon underline decoration-studio-maroon/40 underline-offset-2 hover:decoration-studio-maroon">
          More about the mission
        </Link>
        .
      </>
    ),
  },
];

export default function Home() {
  return (
    <main className="bg-canvas">
      <MarketingNav />

      {/* ── 1. Hero ─────────────────────────────────────────────────────── */}
      {/* min-h-[100svh]: the scene owns the full first viewport on any screen
          (svh so mobile browser chrome doesn't cause overflow). */}
      <section className="relative isolate flex min-h-[100svh] items-center overflow-hidden">
        {/* Out-of-focus light ribbons + glass orb fill the hero — amber and
            crimson light drifting through dark water, rippling under the
            cursor. Scene is dark, so hero copy below stays cream-tinted. */}
        <AuroraWater className="absolute inset-0" />
        {/* Legibility scrim: darkens behind the copy on the left, fades out
            before the orb so the glass stays untouched. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-gradient-to-r from-black/45 via-black/15 to-transparent"
        />

        <div className="container-cohere relative z-10 pb-24 pt-40 sm:pt-48 lg:pb-32 lg:pt-56">
          <Reveal>
            <p className="text-caption font-medium uppercase tracking-[0.14em] text-studio-cream/80 drop-shadow-[0_1px_8px_rgba(0,0,0,0.4)]">
              SKILLED Nation
            </p>
          </Reveal>
          <Reveal delay={0.05}>
            <h1 className="mt-6 max-w-[10ch] font-display text-[2.5rem] leading-[0.98] tracking-[-0.02em] text-studio-cream xs:text-[3rem] sm:text-[5rem] lg:text-[7rem] drop-shadow-[0_2px_16px_rgba(0,0,0,0.3)]">
              Real jobs.
              <br />
              Right fit.
            </h1>
          </Reveal>
          <Reveal delay={0.1}>
            <p className="mt-8 max-w-[42ch] text-body-lg text-studio-cream/90 drop-shadow-[0_1px_8px_rgba(0,0,0,0.35)]">
              A platform where skilled trades workers find real jobs, and employers find real workers. Built by the nonprofit funding their training.
            </p>
          </Reveal>
          <Reveal delay={0.15}>
            <div className="mt-10 flex flex-wrap items-center gap-6">
              <Link
                href="/signup"
                className="inline-flex items-center gap-2 rounded-[8px] bg-studio-cream px-6 py-3 text-[16px] font-medium text-studio-black transition-colors hover:bg-studio-sienna hover:text-studio-cream"
              >
                See your matches <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/login"
                className="inline-flex items-center gap-1.5 text-[15px] font-medium text-studio-cream underline decoration-studio-cream/40 underline-offset-4 transition-colors hover:decoration-studio-cream"
              >
                I already have an account
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── 2. Proof — the numbers behind the platform ──────────────────── */}
      {/* Their homepage leads with these three stats; ours inherits them.
          Left-aligned, hairline-ruled columns — a ledger, not a billboard. */}
      <section className="border-b border-hairline">
        <div className="container-cohere py-16 sm:py-20">
          <Reveal>
            <p className="max-w-[52ch] text-body-lg text-slate">
              The nonprofit behind 3,000+ trade scholarships now connects its
              scholars, and every skilled worker, to the employers who fund
              the training.
            </p>
          </Reveal>
          <div className="mt-12 grid gap-10 sm:grid-cols-3 sm:gap-0 sm:divide-x sm:divide-hairline">
            {STATS.map((s, i) => (
              <Reveal key={s.value} delay={i * 0.06}>
                <div className={i > 0 ? "sm:pl-10" : ""}>
                  <p className="font-display text-[3.25rem] leading-none tracking-[-0.02em] text-cohere-ink sm:text-[3.75rem]">
                    {s.value}
                  </p>
                  <p className="mt-3 max-w-[24ch] text-body text-slate-muted">{s.label}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── 3. Partners ─────────────────────────────────────────────────── */}
      <section className="border-b border-hairline bg-parchment/50">
        <div className="container-cohere py-10">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:gap-12">
            <p className="shrink-0 text-caption text-slate-muted">
              Hiring alongside SKILLED Nation
            </p>
            <ul className="flex flex-wrap items-center gap-x-8 gap-y-3">
              {PARTNERS.map((name) => (
                <li key={name} className="text-caption font-medium text-slate/70">
                  {name}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ── 4. What it does — heading left, ruled rows right ───────────── */}
      <section className="container-cohere py-24 sm:py-28">
        <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-20">
          <div>
            <Reveal>
              <h2 className="max-w-[16ch] font-display text-[2.1rem] leading-[1.08] tracking-[-0.015em] text-cohere-ink sm:text-[2.6rem]">
                Matching you can read like a ledger.
              </h2>
            </Reveal>
            <Reveal delay={0.08}>
              <p className="mt-6 max-w-[44ch] text-body text-slate">
                No résumé roulette. The engine that ranks every job is
                deterministic. The same inputs give the same answer, and every
                answer shows its work.
              </p>
            </Reveal>
          </div>

          <div>
            {FEATURES.map((f, i) => (
              <Reveal key={f.h} delay={i * 0.06}>
                <div className={`grid gap-2 py-7 sm:grid-cols-[minmax(0,4fr)_minmax(0,7fr)] sm:gap-8 ${i > 0 ? "border-t border-hairline" : "border-t border-hairline lg:border-t-0 lg:pt-2"}`}>
                  <h3 className="text-subhead font-semibold text-cohere-ink">{f.h}</h3>
                  <p className="text-body text-slate">{f.b}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── 4b. Example match — real value preview before the signup wall ── */}
      <section className="border-t border-hairline">
        <div className="container-cohere py-24 sm:py-28">
          <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-20">
            <div>
              <Reveal>
                <p className="text-caption font-medium text-studio-maroon">Example match</p>
                <h2 className="mt-3 max-w-[16ch] font-display text-[2.1rem] leading-[1.08] tracking-[-0.015em] text-cohere-ink sm:text-[2.6rem]">
                  This is what a ranked match looks like.
                </h2>
              </Reveal>
              <Reveal delay={0.08}>
                <p className="mt-6 max-w-[44ch] text-body text-slate">
                  A real posting from our catalog, scored the way you&rsquo;d
                  see it, here for a sample profile: a lineworker program
                  graduate in Dallas, Texas. Sign up and every job is ranked
                  like this against your own profile.
                </p>
              </Reveal>
            </div>

            <Reveal delay={0.1}>
              <div className="rounded-[14px] border border-hairline bg-white p-6 sm:p-8">
                <div className="flex items-start justify-between gap-6">
                  <div className="min-w-0">
                    <span className="rounded-full border border-hairline bg-parchment px-2.5 py-0.5 text-[11px] font-medium text-slate">
                      Example match
                    </span>
                    <h3 className="mt-3 text-[1.25rem] font-semibold text-cohere-ink">
                      {EXAMPLE_MATCH.title}
                    </h3>
                    <p className="mt-1 text-body text-slate">
                      {EXAMPLE_MATCH.employer} · {EXAMPLE_MATCH.location}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="font-display text-[2.6rem] leading-none tabular-nums text-cohere-ink">
                      {EXAMPLE_MATCH.score}
                    </p>
                    <p className="mt-1 text-caption text-slate-muted">{EXAMPLE_MATCH.label}</p>
                  </div>
                </div>

                <dl className="mt-6 space-y-3 border-t border-hairline pt-5">
                  {EXAMPLE_MATCH.dimensions.map((d) => (
                    <div key={d.label} className="grid grid-cols-[7.5rem_1fr_2.5rem] items-center gap-3">
                      <dt className="text-caption text-slate">{d.label}</dt>
                      <dd>
                        <div className="h-1 rounded-full bg-stone">
                          <div
                            className="h-1 rounded-full bg-studio-maroon"
                            style={{ width: `${d.score}%` }}
                          />
                        </div>
                      </dd>
                      <dd className="text-right text-caption tabular-nums text-slate">{d.score}</dd>
                    </div>
                  ))}
                </dl>

                <p className="mt-5 border-t border-hairline pt-4 text-caption text-slate">
                  {EXAMPLE_MATCH.why}
                </p>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ── 5. Two doors — workers and employers ────────────────────────── */}
      <section className="border-y border-hairline bg-parchment/50">
        <div className="container-cohere grid gap-y-14 py-20 sm:py-24 lg:grid-cols-2 lg:divide-x lg:divide-hairline">
          <Reveal className="lg:pr-16">
            <p className="text-caption font-medium text-studio-maroon">For workers</p>
            <h3 className="mt-3 max-w-[18ch] font-display text-[1.9rem] leading-[1.1] tracking-[-0.01em] text-cohere-ink">
              You&rsquo;re the one employers are looking for.
            </h3>
            <ul className="mt-6 space-y-2.5 text-body text-slate">
              <li>Free, always. Built by the nonprofit funding your training.</li>
              <li>Matches ranked and explained, not a wall of listings.</li>
              <li>Verified credentials that travel with every application.</li>
            </ul>
            <Link
              href="/signup"
              className="btn-md mt-8 inline-flex"
            >
              Create your profile <ArrowRight className="h-4 w-4" />
            </Link>
          </Reveal>

          <Reveal delay={0.08} className="lg:pl-16">
            <p className="text-caption font-medium text-studio-maroon">For employers</p>
            <h3 className="mt-3 max-w-[18ch] font-display text-[1.9rem] leading-[1.1] tracking-[-0.01em] text-cohere-ink">
              Candidates who can already do the work.
            </h3>
            <ul className="mt-6 space-y-2.5 text-body text-slate">
              <li>Ranked candidates with verified credentials, per opening.</li>
              <li>Every ranking explains itself. Defensible hiring, on paper.</li>
              <li>Reach the 3,000+ scholars your industry helped train.</li>
            </ul>
            <a
              href="mailto:partnerships@skilled-nation.org"
              className="btn-ghost mt-8 inline-flex"
            >
              Talk to the team <ArrowRight className="h-4 w-4" />
            </a>
            <p className="mt-3 text-caption text-slate-muted">
              Employer accounts are set up by invitation. We reply within two business days.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ── 6. How it works — an honest sequence, so honest numerals ────── */}
      <section className="container-cohere py-24 sm:py-28">
        <Reveal>
          <h2 className="max-w-[24ch] font-display text-[2.1rem] leading-[1.08] tracking-[-0.015em] text-cohere-ink sm:text-[2.6rem]">
            Five minutes to set up. Matches the same day.
          </h2>
        </Reveal>
        {/* Reveal renders AS the <li> so the <ol> only directly contains list
            items (axe: list/listitem). */}
        <ol className="mt-14 grid gap-10 sm:grid-cols-3 sm:gap-8">
          {STEPS.map((s, i) => (
            <Reveal key={s.n} as="li" delay={i * 0.06} className="border-t border-hairline pt-6">
              <div className="flex items-baseline gap-3">
                <span className="font-display text-[1.6rem] leading-none text-studio-maroon">{s.n}</span>
                <h3 className="text-subhead font-semibold text-cohere-ink">{s.h}</h3>
              </div>
              <p className="mt-3 text-body text-slate">{s.b}</p>
            </Reveal>
          ))}
        </ol>
      </section>

      {/* ── 7. One scholar, in their words ──────────────────────────────── */}
      <section className="border-y border-hairline bg-parchment/50">
        <div className="container-cohere py-20 sm:py-24">
          <Reveal>
            <figure className="mx-auto max-w-[46ch] text-center">
              <blockquote className="font-display text-[1.7rem] leading-[1.25] tracking-[-0.01em] text-cohere-ink sm:text-[2rem]">
                &ldquo;The scholarship paid for the certification. The match is
                how an employer actually saw it.&rdquo;
              </blockquote>
              <figcaption className="mt-6 text-caption text-slate-muted">
                Marcus T., welder in Birmingham, Alabama
              </figcaption>
            </figure>
          </Reveal>
        </div>
      </section>

      {/* ── 8. FAQ — a quiet list, not a stack of cards ─────────────────── */}
      <section className="container-cohere py-24 sm:py-28">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] lg:gap-20">
          <Reveal>
            <h2 className="max-w-[14ch] font-display text-[2.1rem] leading-[1.08] tracking-[-0.015em] text-cohere-ink sm:text-[2.6rem]">
              Worth knowing.
            </h2>
          </Reveal>
          <div>
            {FAQS.map((item, i) => (
              <details key={i} className="group border-b border-hairline">
                <summary className="flex cursor-pointer items-center justify-between gap-4 py-5 text-body-lg font-medium text-cohere-ink transition-colors hover:text-studio-maroon [&::-webkit-details-marker]:hidden">
                  <span>{item.q}</span>
                  <Plus
                    className="h-4 w-4 shrink-0 text-slate-muted transition-transform group-open:rotate-45 group-open:text-studio-maroon"
                    strokeWidth={2}
                  />
                </summary>
                <div className="pb-6 pr-8 text-body text-slate">{item.a}</div>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ── 9. Close — the orb again, where the page ends ───────────────── */}
      <section className="bg-studio-black">
        <div className="container-cohere relative overflow-hidden py-20 sm:py-24">
          <OrbMark
            size={280}
            className="pointer-events-none absolute -right-16 top-1/2 hidden -translate-y-1/2 opacity-90 lg:block"
          />
          <div className="relative max-w-[46ch]">
            <h2 className="font-display text-[2rem] leading-[1.08] tracking-[-0.015em] text-studio-cream sm:text-[2.6rem]">
              Show us what you do. We&rsquo;ll show you where it fits.
            </h2>
            <div className="mt-10 flex flex-wrap items-center gap-6">
              <Link
                href="/signup"
                className="inline-flex items-center gap-2 rounded-[8px] bg-studio-cream px-6 py-3 text-[16px] font-medium text-studio-black transition-colors hover:bg-studio-sienna hover:text-studio-cream"
              >
                See your matches <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/login"
                className="text-[15px] font-medium text-studio-cream underline decoration-studio-cream/40 underline-offset-4 transition-colors hover:decoration-studio-cream"
              >
                Sign in
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── 10. Footer ──────────────────────────────────────────────────── */}
      <footer className="border-t border-hairline bg-white">
        <div className="container-cohere flex flex-col gap-6 py-12 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-md">
            <p className="text-caption font-semibold text-studio-maroon">SKILLED Nation</p>
            <p className="mt-3 text-body text-slate">
              Scholarships for skilled careers, and the platform that connects
              them to real jobs.
            </p>
          </div>
          <div className="text-caption text-slate-muted sm:text-right">
            <p>© {new Date().getFullYear()} SKILLED Nation.</p>
            <p className="mt-1">Employer &amp; admin accounts by invitation.</p>
          </div>
        </div>
      </footer>
    </main>
  );
}
