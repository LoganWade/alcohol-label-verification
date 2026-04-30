import { Fragment } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";

/**
 * Crumb derived from the URL path. We avoid coupling to react-router's
 * data-router (which our app doesn't use) by reading useLocation() and
 * mapping known segments to human labels.
 *
 * Unknown id-shaped segments (uuids, numbers) are dropped — we only render
 * crumbs for stable, named routes. This keeps the trail tidy and prevents
 * raw uuids from leaking into the chrome.
 */
interface Crumb {
  label: string;
  to?: string;
}

const ROOT: Crumb = { label: "Home", to: "/" };

const STATIC_LABELS: Record<string, string> = {
  review: "Reviews",
  new: "New",
  batches: "Batches",
  queue: "Queue",
  applications: "Application",
};

function looksLikeId(seg: string): boolean {
  // uuids, numeric ids, or anything that isn't in our label map and looks
  // opaque. We collapse these into a generic crumb to avoid surfacing them.
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(seg)) return true;
  if (/^\d+$/.test(seg)) return true;
  return false;
}

function buildCrumbs(pathname: string): Crumb[] {
  const segs = pathname.split("/").filter(Boolean);
  if (segs.length === 0) return [];

  const out: Crumb[] = [];
  let acc = "";

  for (let i = 0; i < segs.length; i++) {
    const seg = segs[i];
    acc += "/" + seg;

    if (looksLikeId(seg)) {
      // Show "Detail" rather than the raw id; previous crumb in the trail
      // already names the section.
      out.push({ label: "Detail" });
      continue;
    }

    const label = STATIC_LABELS[seg] ?? seg.charAt(0).toUpperCase() + seg.slice(1);
    const isLast = i === segs.length - 1;
    out.push(isLast ? { label } : { label, to: acc });
  }

  return out;
}

/**
 * Breadcrumbs rendered in the top bar of the app shell.
 *
 * Always starts with a Home crumb so the user can get back in one click,
 * which matters for the "65 year old mom" target — the brand link in the
 * sidebar already does this, but a redundant trail clarifies location.
 */
export function Breadcrumbs() {
  const { pathname } = useLocation();
  const trail = buildCrumbs(pathname);

  // On the home page itself, the trail is empty and we hide the chrome
  // line entirely — no point showing "Home" alone.
  if (trail.length === 0) {
    return null;
  }

  return (
    <nav
      aria-label="Breadcrumb"
      className="text-sm text-ink-500"
      data-testid="breadcrumbs"
    >
      <ol className="flex items-center gap-1 flex-wrap">
        <li className="flex items-center gap-1">
          <Link
            to={ROOT.to as string}
            className="inline-flex items-center gap-1 hover:text-primary"
          >
            <Home size={14} aria-hidden="true" />
            <span>{ROOT.label}</span>
          </Link>
        </li>
        {trail.map((c, i) => (
          <Fragment key={`${c.label}-${i}`}>
            <li aria-hidden="true" className="text-ink-300">
              <ChevronRight size={14} />
            </li>
            <li>
              {c.to ? (
                <Link to={c.to} className="hover:text-primary">
                  {c.label}
                </Link>
              ) : (
                <span className="text-ink-700" aria-current="page">
                  {c.label}
                </span>
              )}
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}
