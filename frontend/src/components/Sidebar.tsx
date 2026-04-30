import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  ClipboardList,
  Home,
  Menu,
  PackagePlus,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";

/**
 * Persistent left sidebar — primary navigation for the app shell.
 *
 * Active route is highlighted via NavLink's aria-current="page" so the
 * current section is always visible. Targets are deliberately limited to
 * the four real top-level destinations; deeper pages (Application detail,
 * Results) are reached from inside those sections and never need their
 * own sidebar entry.
 *
 * Mobile: sidebar is hidden behind a hamburger button. The desktop case is
 * the priority per the UX brief, but the mobile fallback keeps the app
 * navigable on a phone if a reviewer ever needs to glance from one.
 */
const NAV: Array<{ to: string; label: string; icon: typeof Home; end?: boolean }> = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/review/new", label: "New review", icon: Upload },
  { to: "/batches/new", label: "New batch", icon: PackagePlus },
  { to: "/queue", label: "Analyst queue", icon: ClipboardList },
];

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <ul className="space-y-1" data-testid="sidebar-nav">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <li key={to}>
          <NavLink
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              [
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                "hover:bg-ink-50 hover:text-primary",
                isActive
                  ? "bg-primary-lighter text-primary font-semibold"
                  : "text-ink-700",
              ].join(" ")
            }
            data-testid={`sidebar-link-${to}`}
          >
            <Icon size={18} aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

function Brand() {
  return (
    <NavLink
      to="/"
      end
      className="flex items-center gap-2 text-ink-800 font-semibold hover:text-primary"
      aria-label="Label Review home"
    >
      <ShieldCheck size={22} aria-hidden="true" className="text-primary" />
      <span>Label Review</span>
    </NavLink>
  );
}

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Mobile hamburger — visible only below md */}
      <button
        type="button"
        className="md:hidden fixed top-3 left-3 z-40 rounded-md border border-ink-200 bg-white p-2 shadow-sm"
        aria-label={mobileOpen ? "Close menu" : "Open menu"}
        aria-expanded={mobileOpen}
        onClick={() => setMobileOpen((v) => !v)}
        data-testid="sidebar-mobile-toggle"
      >
        {mobileOpen ? <X size={18} /> : <Menu size={18} />}
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-30 bg-ink-800/40"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={[
          "bg-white border-r border-ink-200 flex flex-col",
          // Desktop: sticky column inside the flex shell
          "md:w-[220px] md:shrink-0 md:sticky md:top-0 md:h-screen",
          // Mobile: slides in from the left
          "fixed md:static inset-y-0 left-0 z-30 w-[260px] transition-transform",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        ].join(" ")}
        aria-label="Primary"
        data-testid="sidebar"
      >
        <div className="px-4 py-4 border-b border-ink-200">
          <Brand />
          <p className="text-xs text-ink-400 mt-1">Reviewer-assist prototype</p>
        </div>
        <nav className="px-2 py-3 flex-1 overflow-y-auto">
          <NavItems onNavigate={() => setMobileOpen(false)} />
        </nav>
        <div className="px-4 py-3 border-t border-ink-200 text-xs text-ink-500">
          <p>
            This tool assists review and does not replace reviewer judgment.
          </p>
        </div>
      </aside>
    </>
  );
}
