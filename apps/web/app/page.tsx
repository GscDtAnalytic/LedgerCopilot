const PIPELINE = [
  { step: "classify", note: "invoice · boleto · receipt" },
  { step: "extract", note: "fields + per-field confidence" },
  { step: "validate", note: "deterministic rules" },
  { step: "reconcile", note: "vs PO / payment / history" },
  { step: "apply policy", note: "+ risk" },
  { step: "decide", note: "auto · review · reject" },
] as const;

/**
 * Scaffold landing/overview. Server Component, semantic landmarks, calm layout
 *. The real surfaces
 * — inbox, case detail, exceptions, version compare, monitoring — land per phase.
 */
export default function Home() {
  return (
    <main id="main" className="mx-auto max-w-3xl px-6 py-20">
      <p className="text-sm font-medium uppercase tracking-widest text-muted">
        AI operations platform
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">LedgerCopilot</h1>
      <p className="mt-4 text-lg text-muted">
        Turns financial documents into traceable operational decisions — with a complete audit
        trail and selective human review.
      </p>

      <section aria-labelledby="pipeline-heading" className="mt-12">
        <h2 id="pipeline-heading" className="text-sm font-semibold uppercase tracking-wider">
          The pipeline
        </h2>
        <ol className="mt-4 grid gap-3 sm:grid-cols-2">
          {PIPELINE.map(({ step, note }, i) => (
            <li
              key={step}
              className="rounded-md border border-border bg-surface p-4 transition-colors duration-base ease-standard"
            >
              <span className="text-xs font-medium text-muted">{String(i + 1).padStart(2, "0")}</span>
              <p className="font-medium">{step}</p>
              <p className="text-sm text-muted">{note}</p>
            </li>
          ))}
        </ol>
      </section>

      <p className="mt-12 text-sm text-muted">
        Scaffold stage. See <code className="rounded bg-surface px-1.5 py-0.5"></code> for
        the project guide and roadmap.
      </p>
    </main>
  );
}
