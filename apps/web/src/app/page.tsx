import Image from "next/image";
import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-white px-6">
      <Image
        src="/spf-logo.png"
        alt="SkillPointe Foundation"
        width={320}
        height={87}
        priority
        className="mb-8 brightness-0"
      />
      <h1 className="text-4xl font-semibold tracking-tight text-zinc-900 text-center">
        SkillPointe Match
      </h1>
      <p className="mt-3 text-base text-zinc-500 text-center max-w-md">
        Find your best-fit skilled trades career. Get ranked recommendations,
        understand what makes you a strong candidate, and plan your next step.
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          href="/login"
          className="rounded-full bg-zinc-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 transition-colors"
        >
          Sign in
        </Link>
        <Link
          href="/signup"
          className="rounded-full border border-zinc-200 px-6 py-2.5 text-sm font-medium text-zinc-700 hover:border-zinc-400 hover:text-zinc-900 transition-colors"
        >
          Create account
        </Link>
      </div>
    </main>
  );
}
