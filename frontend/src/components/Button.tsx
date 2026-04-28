import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

/**
 * Button with three visual variants. Always 44px+ tall (WCAG 2.2 AA).
 * Disabled state is non-interactive but readable; never relies on color alone.
 */
export function Button({
  variant = "primary",
  className = "",
  children,
  type,
  ...rest
}: Props) {
  const cls =
    variant === "primary"
      ? "btn-primary"
      : variant === "secondary"
      ? "btn-secondary"
      : "btn-ghost";
  return (
    <button type={type ?? "button"} className={`${cls} ${className}`} {...rest}>
      {children}
    </button>
  );
}
