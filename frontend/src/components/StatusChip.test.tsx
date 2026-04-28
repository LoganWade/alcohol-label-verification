import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusChip } from "./StatusChip";
import type { FieldStatus, ReviewStatus } from "@/lib/types/api";

describe("<StatusChip>", () => {
  const fieldStatuses: FieldStatus[] = [
    "Match",
    "Mismatch",
    "Missing",
    "Needs Review",
    "Uncertain",
  ];

  it.each(fieldStatuses)(
    "renders text and an icon for the %s field status",
    (status) => {
      const { container } = render(<StatusChip status={status} />);
      // Text is present (regardless of color).
      expect(screen.getByText(status)).toBeInTheDocument();
      // Icon is present and hidden from assistive tech.
      const svg = container.querySelector("svg");
      expect(svg).not.toBeNull();
      expect(svg!.getAttribute("aria-hidden")).toBe("true");
    },
  );

  const reviewStatuses: ReviewStatus[] = ["Pass", "Mismatch", "Needs Review"];

  it.each(reviewStatuses)(
    "renders text + icon for the %s review summary status",
    (status) => {
      const { container } = render(<StatusChip status={status} />);
      expect(screen.getByText(status)).toBeInTheDocument();
      expect(container.querySelector("svg")).not.toBeNull();
    },
  );

  it("uses the same green variant for Match and Pass", () => {
    const { container: matchC } = render(<StatusChip status="Match" />);
    const { container: passC } = render(<StatusChip status="Pass" />);
    const matchVariant = matchC.querySelector("[data-variant]")?.getAttribute("data-variant");
    const passVariant = passC.querySelector("[data-variant]")?.getAttribute("data-variant");
    expect(matchVariant).toBe("match");
    expect(passVariant).toBe("match");
  });

  it("does not rely on color alone — text content is always present", () => {
    // Render every status; the textContent must contain the verbatim status string.
    for (const status of [...fieldStatuses, ...reviewStatuses] as const) {
      const { container, unmount } = render(<StatusChip status={status} />);
      expect(container.textContent).toContain(status);
      unmount();
    }
  });
});
