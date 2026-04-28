import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ShieldCheck } from "lucide-react";

interface Props {
  children: ReactNode;
}

/**
 * Page chrome — header with brand, main landmark, and footer disclaimer.
 * Skip link satisfies WCAG 2.2 AA bypass-blocks.
 */
export function Layout({ children }: Props) {
  return (
    <div className="min-h-screen flex flex-col">
      <a
        href="#main"
        data-skip-link
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:bg-white focus:text-primary focus:px-3 focus:py-2 focus:rounded focus:shadow"
      >
        Skip to main content
      </a>

      <header className="bg-white border-b border-ink-200 no-print">
        <div className="max-w-6xl mx-auto px-u-3 py-u-2 flex items-center gap-u-2">
          <Link
            to="/"
            className="flex items-center gap-2 text-ink-800 font-semibold hover:text-primary"
            aria-label="Label Review home"
          >
            <ShieldCheck
              size={24}
              aria-hidden="true"
              className="text-primary"
            />
            <span>Label Review</span>
          </Link>
          <span className="text-xs text-ink-400 ml-2 hidden sm:inline">
            Reviewer-assist prototype
          </span>
        </div>
      </header>

      <main id="main" className="flex-1">
        {children}
      </main>

      <footer className="border-t border-ink-200 bg-white no-print">
        <div className="max-w-6xl mx-auto px-u-3 py-u-3 text-xs text-ink-500">
          <p>
            This tool assists review and does not replace reviewer judgment.
            Final compliance decisions remain with the reviewer.
          </p>
        </div>
      </footer>
    </div>
  );
}
