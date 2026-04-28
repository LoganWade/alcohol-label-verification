import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ResultsPage } from "./ResultsPage";
import { FULL_FIXTURE } from "@/lib/__fixtures__/analyzeResponse";

function renderAt(initial: { pathname: string; state?: unknown }) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/review/:id" element={<ResultsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("<ResultsPage>", () => {
  it("renders results when router state carries the response", () => {
    renderAt({
      pathname: "/review/rev_test_001",
      state: { response: FULL_FIXTURE },
    });
    expect(screen.getByTestId("results-headline")).toBeInTheDocument();
    expect(screen.getByTestId("button-export-json")).toBeInTheDocument();
    expect(screen.getByTestId("button-print")).toBeInTheDocument();
    expect(screen.getByTestId("button-run-another")).toBeInTheDocument();
  });

  it("shows 'No review loaded' fallback when state is missing", () => {
    renderAt({ pathname: "/review/rev_no_state" });
    expect(screen.getByText(/No review loaded/i)).toBeInTheDocument();
  });

  it("matches a snapshot of the headline + table for the full fixture", () => {
    const { container } = renderAt({
      pathname: "/review/rev_test_001",
      state: { response: FULL_FIXTURE },
    });
    // Snapshot just the results-view region — the buttons are stable but
    // the snapshot stays small and meaningful.
    const view = container.querySelector("[data-testid='results-view']");
    expect(view).not.toBeNull();
    expect(view!.textContent).toMatchSnapshot();
  });
});
