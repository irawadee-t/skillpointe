export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <h1 className="text-4xl font-bold">SkillPointe Match</h1>
      <p className="mt-4 text-lg text-gray-600">
        Ranked job recommendations and planning platform.
      </p>
      <div className="mt-8 flex gap-4">
        <a
          href="/login"
          className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          Sign in
        </a>
      </div>
      <div className="mt-8 text-sm text-gray-400">
        API status:{" "}
        <a
          href="http://localhost:8000/health"
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
        >
          localhost:8000/health
        </a>
      </div>
    </main>
  );
}
