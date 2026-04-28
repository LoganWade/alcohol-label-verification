/**
 * Tests for <HomePage>.
 *
 * The component fetches samples via react-query + listSamples().  All network
 * calls are mocked so the tests are fully deterministic.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { HomePage } from "./HomePage";
import type { SampleSummary } from "@/lib/types/api";

// ---------------------------------------------------------------------------
// Mock the samples API module
// ---------------------------------------------------------------------------
vi.mock("@/lib/api/samples", () => ({
  listSamples: vi.fn(),
  getSampleImageUrl: (id: string) => `/api/v1/samples/${id}/image`,
  getSampleExpectedFields: vi.fn(),
}));

import { listSamples } from "@/lib/api/samples";
const mockListSamples = vi.mocked(listSamples);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const SYNTHETIC_SAMPLES: SampleSummary[] = [
  {
    id: "clean_match",
    title: "Clean match",
    description: "All fields match exactly.",
    expected_outcome: "All fields Match",
    provenance: "synthetic",
  },
  {
    id: "abv_mismatch",
    title: "ABV mismatch",
    description: "Label shows wrong ABV.",
    expected_outcome: "ABV Mismatch",
    provenance: "synthetic",
  },
];

const TTB_SAMPLES: SampleSummary[] = [
  {
    id: "ttb_wine_reference",
    title: "TTB reference — Merlot wine label",
    description: "ABC WINES / AMERICAN MERLOT from Wine BAM.",
    expected_outcome: "Pipeline runs and returns a structured result",
    provenance: "public_ttb_reference",
  },
  {
    id: "ttb_beer_reference",
    title: "TTB reference — Beer front label",
    description: "Example / Golden Ale from TTB Boot Camp.",
    expected_outcome: "Pipeline runs and returns a structured result",
    provenance: "public_ttb_reference",
  },
];

const ALL_SAMPLES = [...SYNTHETIC_SAMPLES, ...TTB_SAMPLES];

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------
function renderHomePage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("<HomePage>", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the primary start-review link", () => {
    mockListSamples.mockResolvedValue([]);
    renderHomePage();
    expect(screen.getByTestId("link-start-review")).toBeInTheDocument();
  });

  it("shows the page headline", () => {
    mockListSamples.mockResolvedValue([]);
    renderHomePage();
    expect(
      screen.getByText(/Verify a label against the application data/i),
    ).toBeInTheDocument();
  });

  it("renders the synthetic section heading after samples load", async () => {
    mockListSamples.mockResolvedValue(ALL_SAMPLES);
    renderHomePage();
    await waitFor(() =>
      expect(
        screen.getByText(/Synthetic test scenarios/i),
      ).toBeInTheDocument(),
    );
  });

  it("renders the TTB reference section heading after samples load", async () => {
    mockListSamples.mockResolvedValue(ALL_SAMPLES);
    renderHomePage();
    await waitFor(() =>
      expect(screen.getByText(/TTB reference labels/i)).toBeInTheDocument(),
    );
  });

  it("renders cards for each synthetic sample", async () => {
    mockListSamples.mockResolvedValue(ALL_SAMPLES);
    renderHomePage();
    await waitFor(() => {
      for (const s of SYNTHETIC_SAMPLES) {
        expect(
          screen.getByTestId(`link-try-sample-${s.id}`),
        ).toBeInTheDocument();
      }
    });
  });

  it("renders cards for each TTB reference sample", async () => {
    mockListSamples.mockResolvedValue(ALL_SAMPLES);
    renderHomePage();
    await waitFor(() => {
      for (const s of TTB_SAMPLES) {
        expect(
          screen.getByTestId(`link-try-sample-${s.id}`),
        ).toBeInTheDocument();
      }
    });
  });

  it("synthetic and TTB samples are in separate grid containers", async () => {
    mockListSamples.mockResolvedValue(ALL_SAMPLES);
    renderHomePage();
    await waitFor(() => {
      expect(screen.getByTestId("sample-group-synthetic")).toBeInTheDocument();
      expect(screen.getByTestId("sample-group-ttb")).toBeInTheDocument();
    });
  });

  it("does not render sample sections when list is empty", async () => {
    mockListSamples.mockResolvedValue([]);
    renderHomePage();
    // Give time for query to settle
    await waitFor(() =>
      expect(
        screen.queryByTestId("sample-group-synthetic"),
      ).not.toBeInTheDocument(),
    );
  });

  it("does not render TTB section when only synthetic samples exist", async () => {
    mockListSamples.mockResolvedValue(SYNTHETIC_SAMPLES);
    renderHomePage();
    await waitFor(() => {
      expect(screen.getByTestId("sample-group-synthetic")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("sample-group-ttb")).not.toBeInTheDocument();
  });

  it("shows a loading state while samples are fetching", () => {
    // Make the query hang indefinitely
    mockListSamples.mockReturnValue(new Promise(() => {}));
    renderHomePage();
    expect(screen.getByLabelText(/Loading samples/i)).toBeInTheDocument();
  });
});
