import Image from "next/image";
import Link from "next/link";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-neutral-50 flex flex-col items-center justify-center px-4 py-16">
      <Link href="/" className="mb-8">
        <Image
          src="/spf-logo.png"
          alt="SkillPointe Foundation"
          width={220}
          height={60}
          priority
        />
      </Link>
      {children}
    </div>
  );
}
