import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { ResultsView } from "./ResultsView";
import {
  ALL_STATUSES_FIXTURE,
  FULL_FIXTURE,
  withWarning,
} from "@/lib/__fixtures__/analyzeResponse";

describe("<ResultsView>", () => {
  it("renders the summary headline and a large status chip", () => {
    render(<ResultsView response={FULL_FIXTURE} />);
    expect(screen.getByTestId("results-headline").textContent).toContain(
      "5 of 6 fields match",
    );
    // Summary status chip — Needs Review.
    expect(screen.getAllByText("Needs Review").length).toBeGreaterThan(0);
  });

  it("renders the elapsed time as a trust signal", () => {
    render(<ResultsView response={FULL_FIXTURE} />);
    expect(screen.getByTestId("results-elapsed").textContent).toContain(
      "Reviewed in 3.4s",
    );
  });

  it("renders all five field statuses in the comparison table", () => {
    render(<ResultsView response={ALL_STATUSES_FIXTURE} />);
    // Each chip should be present at least once.
    expect(screen.getAllByText("Match").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Mismatch").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Missing").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Needs Review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Uncertain").length).toBeGreaterThan(0);
  });

  it("expands a field row and shows raw OCR text + bbox", () => {
    render(<ResultsView response={FULL_FIXTURE} />);
    const toggle = screen.getByTestId("toggle-brand_name");
    fireEvent.click(toggle);

    const evidence = screen.getByTestId("evidence-brand_name");
    // Raw OCR text rendered verbatim (preserves original case).
    expect(evidence.textContent).toContain("OLD TOM DISTILLERY");
    // Bbox rendered as text.
    expect(evidence.textContent).toMatch(/x0:\s*10/);
  });

  it("shows 'No bounding box available' when the bbox is null", () => {
    render(<ResultsView response={FULL_FIXTURE} />);
    fireEvent.click(screen.getByTestId("toggle-country_of_origin"));
    const evidence = screen.getByTestId("evidence-country_of_origin");
    expect(evidence.textContent).toContain("No bounding box available");
  });

  describe("Government Warning row", () => {
    it("renders both sub-flags when header fails and wording matches", () => {
      render(<ResultsView response={FULL_FIXTURE} />);
      const row = screen.getByTestId("row-warning");
      expect(within(row).getByTestId("warning-header-caps").textContent).toContain("No");
      expect(within(row).getByTestId("warning-wording-match").textContent).toContain("Yes");
      expect(within(row).getByTestId("warning-reason").textContent).toContain(
        "not in all caps",
      );
    });

    it("renders Yes/Yes for a fully matching warning", () => {
      const fixture = withWarning({
        status: "Match",
        header_caps_ok: true,
        wording_match: true,
        reason: "All checks passed.",
      });
      render(<ResultsView response={fixture} />);
      const row = screen.getByTestId("row-warning");
      expect(within(row).getByTestId("warning-header-caps").textContent).toContain("Yes");
      expect(within(row).getByTestId("warning-wording-match").textContent).toContain("Yes");
      // Reason hidden when both sub-flags pass.
      expect(within(row).queryByTestId("warning-reason")).toBeNull();
    });

    it("renders the reason inline when wording fails", () => {
      const fixture = withWarning({
        status: "Mismatch",
        header_caps_ok: true,
        wording_match: false,
        reason: "Wording differs from the statutory text.",
      });
      render(<ResultsView response={fixture} />);
      const row = screen.getByTestId("row-warning");
      expect(within(row).getByTestId("warning-header-caps").textContent).toContain("Yes");
      expect(within(row).getByTestId("warning-wording-match").textContent).toContain("No");
      expect(within(row).getByTestId("warning-reason").textContent).toContain(
        "Wording differs",
      );
    });

    it("renders Missing status without exploding when raw_text is null", () => {
      const fixture = withWarning({
        status: "Missing",
        header_caps_ok: false,
        wording_match: false,
        raw_text: null,
        reason: "Government Warning not detected on the label.",
      });
      render(<ResultsView response={fixture} />);
      const row = screen.getByTestId("row-warning");
      expect(within(row).getByText("Missing")).toBeInTheDocument();
      expect(row.textContent).toContain("not detected");
    });

    it("renders Uncertain status when image quality is poor", () => {
      const fixture = withWarning({
        status: "Uncertain",
        header_caps_ok: false,
        wording_match: false,
        reason: "Warning region OCR confidence too low to assert format.",
      });
      render(<ResultsView response={fixture} />);
      const row = screen.getByTestId("row-warning");
      expect(within(row).getByText("Uncertain")).toBeInTheDocument();
    });

    it("expansion shows expected_text panel", () => {
      render(<ResultsView response={FULL_FIXTURE} />);
      fireEvent.click(screen.getByTestId("toggle-warning"));
      const evidence = screen.getByTestId("evidence-warning");
      expect(evidence.textContent).toContain("GOVERNMENT WARNING:");
    });
  });

  it("renders the limitations footer", () => {
    render(<ResultsView response={FULL_FIXTURE} />);
    const lim = screen.getByTestId("limitations");
    expect(lim.textContent).toContain(
      "This tool assists review and does not replace reviewer judgment.",
    );
  });

  describe("bounding-box preview", () => {
    it("renders the bbox preview when an imageUrl is provided", () => {
      render(<ResultsView response={FULL_FIXTURE} imageUrl="/label.png" />);
      fireEvent.click(screen.getByTestId("toggle-brand_name"));
      const evidence = screen.getByTestId("evidence-brand_name");
      expect(
        within(evidence).getByTestId("bbox-preview"),
      ).toBeInTheDocument();
    });

    it("shows the unavailable note when imageUrl is omitted", () => {
      render(<ResultsView response={FULL_FIXTURE} />);
      fireEvent.click(screen.getByTestId("toggle-brand_name"));
      const evidence = screen.getByTestId("evidence-brand_name");
      expect(evidence.textContent).toContain("Image preview unavailable");
      expect(
        within(evidence).queryByTestId("bbox-preview"),
      ).not.toBeInTheDocument();
    });

    it("does not render the preview when bbox is null even if imageUrl is given", () => {
      render(<ResultsView response={FULL_FIXTURE} imageUrl="/label.png" />);
      fireEvent.click(screen.getByTestId("toggle-country_of_origin"));
      const evidence = screen.getByTestId("evidence-country_of_origin");
      expect(evidence.textContent).toContain("No bounding box available");
      expect(
        within(evidence).queryByTestId("bbox-preview"),
      ).not.toBeInTheDocument();
    });
  });
});
