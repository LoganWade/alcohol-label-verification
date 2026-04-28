/**
 * <StatusChip> — the only place the app renders a status.
 *
 * Per AGENTS.md, every status must be conveyed via three redundant channels:
 * text label + icon + color. Color alone is never used. The icon carries
 * `aria-hidden="true"` so screen readers only announce the text.
 *
 * Accepts the union of FieldStatus and ReviewStatus. The "Pass" review
 * summary status reuses Match styling — same green semantics.
 */

import {
  Check,
  X,
  AlertTriangle,
  Eye,
  HelpCircle,
  type LucideIcon,
} from "lucide-react";
import type { FieldStatus, ReviewStatus } from "@/lib/types/api";

export type AnyStatus = FieldStatus | ReviewStatus;

type Variant = "match" | "mismatch" | "missing" | "review" | "uncertain";

interface ChipStyle {
  variant: Variant;
  Icon: LucideIcon;
  classes: string;
}

const STYLES: Record<Variant, Omit<ChipStyle, "variant">> = {
  match: {
    Icon: Check,
    classes:
      "bg-status-match-bg text-status-match-text border-status-match-border",
  },
  mismatch: {
    Icon: X,
    classes:
      "bg-status-mismatch-bg text-status-mismatch-text border-status-mismatch-border",
  },
  missing: {
    Icon: AlertTriangle,
    classes:
      "bg-status-missing-bg text-status-missing-text border-status-missing-border",
  },
  review: {
    Icon: Eye,
    classes:
      "bg-status-review-bg text-status-review-text border-status-review-border",
  },
  uncertain: {
    Icon: HelpCircle,
    classes:
      "bg-status-uncertain-bg text-status-uncertain-text border-status-uncertain-border",
  },
};

function variantFor(status: AnyStatus): Variant {
  switch (status) {
    case "Match":
    case "Pass":
      return "match";
    case "Mismatch":
      return "mismatch";
    case "Missing":
      return "missing";
    case "Needs Review":
      return "review";
    case "Uncertain":
      return "uncertain";
  }
}

export interface StatusChipProps {
  status: AnyStatus;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function StatusChip({
  status,
  size = "md",
  className = "",
}: StatusChipProps) {
  const variant = variantFor(status);
  const { Icon, classes } = STYLES[variant];

  const sizeClasses =
    size === "sm"
      ? "text-xs px-2 py-0.5 gap-1"
      : size === "lg"
      ? "text-base px-4 py-2 gap-2"
      : "text-sm px-3 py-1 gap-1.5";

  const iconSize = size === "sm" ? 14 : size === "lg" ? 20 : 16;

  return (
    <span
      className={`inline-flex items-center rounded-full border font-medium ${classes} ${sizeClasses} ${className}`}
      data-status={status}
      data-variant={variant}
    >
      <Icon
        size={iconSize}
        aria-hidden="true"
        focusable="false"
        strokeWidth={2.25}
      />
      <span>{status}</span>
    </span>
  );
}
