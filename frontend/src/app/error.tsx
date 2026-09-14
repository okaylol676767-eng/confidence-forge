"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // Never surface technical details to the user.
  void error;

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 bg-forge-bg px-6 text-center">
      <div className="relative">
        <div className="absolute inset-0 -z-10 rounded-full bg-forge-red/30 blur-3xl" />
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-3xl">
          ⚠️
        </div>
      </div>
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-white">
          Something went sideways
        </h1>
        <p className="max-w-md text-sm text-forge-muted/60">
          SPIRAL AI hit an unexpected snag. Your conversation is safe —
          try picking up right where you left off.
        </p>
      </div>
      <button
        onClick={reset}
        className="ring-focus rounded-full bg-forge-lime px-6 py-2.5 text-sm font-semibold text-forge-bg shadow-[0_0_24px_rgba(198,255,77,0.35)] transition hover:brightness-110 active:scale-[0.98]"
      >
        Try again
      </button>
    </main>
  );
}
