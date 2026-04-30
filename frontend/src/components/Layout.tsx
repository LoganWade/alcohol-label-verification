import type { ReactNode } from "react";
import { Sidebar } from "@/components/Sidebar";
import { Breadcrumbs } from "@/components/Breadcrumbs";

interface Props {
  children: ReactNode;
}

/**
 * App shell — persistent left sidebar nav + main pane with breadcrumbs.
 *
 * Desktop-first per the UX brief:
 *   - Sidebar is always visible at >= md and houses primary navigation.
 *   - Main pane is widened to ~1440px (max-w-screen-xl) so 2-column page
 *     interiors (e.g. the analyst queue) feel comfortable on a 1440px
 *     monitor without page interiors having to opt in individually.
 *   - Breadcrumbs render above the page content so the user always knows
 *     where they are. The skip link still satisfies WCAG 2.2 AA.
 *
 * Page interiors keep their own width containers; we don't override them
 * here. The intent of this round was "just the chrome".
 */
export function Layout({ children }: Props) {
  return (
    <div className="min-h-screen flex bg-ink-50">
      <a
        href="#main"
        data-skip-link
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:bg-white focus:text-primary focus:px-3 focus:py-2 focus:rounded focus:shadow"
      >
        Skip to main content
      </a>

      <Sidebar />

      <div className="flex-1 min-w-0 flex flex-col">
        <div className="bg-white border-b border-ink-200 no-print">
          <div className="px-u-3 py-u-2 pl-14 md:pl-u-3">
            {/* pl-14 on mobile gives the hamburger room to breathe */}
            <Breadcrumbs />
          </div>
        </div>

        <main id="main" className="flex-1 min-w-0">
          {children}
        </main>
      </div>
    </div>
  );
}
