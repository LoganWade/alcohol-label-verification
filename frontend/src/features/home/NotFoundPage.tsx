import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="max-w-3xl mx-auto px-u-3 py-u-6">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-u-1 text-ink-500">
        The page you tried to open doesn’t exist.
      </p>
      <Link to="/" className="btn-primary mt-u-3">
        Go home
      </Link>
    </div>
  );
}
