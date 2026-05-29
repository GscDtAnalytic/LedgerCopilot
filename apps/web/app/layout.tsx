import type { Metadata } from "next";

import "./globals.css";
import { TopBar } from "@/components/TopBar";

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
        <TopBar />
        {children}
      </body>
    </html>
  );
}
