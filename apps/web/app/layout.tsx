import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "LedgerCopilot",
  description: "AI operations platform for financial document workflows.",
};

/**
 * Root layout. Server Component by default.
 * The skip link and landmark roles are baseline accessibility, not an add-on
 *.
 */
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:text-foreground"
        >
          Skip to content
        </a>
        <header className="border-b border-border bg-surface">
          <nav
            className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-3"
            aria-label="Main navigation"
          >
            <a href="/inbox" className="text-sm font-semibold tracking-tight">
              LedgerCopilot
            </a>
            <div className="flex gap-4 text-sm text-muted">
              <a href="/inbox" className="transition-colors hover:text-foreground">Inbox</a>
              <a href="/monitoring" className="transition-colors hover:text-foreground">Monitoring</a>
              <a href="/prompts" className="transition-colors hover:text-foreground">Prompts</a>
            </div>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
