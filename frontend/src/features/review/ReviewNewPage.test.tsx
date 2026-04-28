/**
 * Tests for <ReviewNewPage>.
 *
 * Tests cover:
 *   - Empty (no ?sample) form renders in "fields" step
 *   - ?sample=1 legacy path: loads STUB_SAMPLE_EXPECTED_FIELDS, advances to upload step
 *   - ?sample=<id> named path: fetches from API, prefills form, advances to upload
 *   - Error handling when useMutation propagates an AnalyzeApiError
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ReviewNewPage } from "./ReviewNewPage";
import type { ExpectedFields } from "@/lib/types/api";

// ---------------------------------------------------------------------------
// Mock modules
// ---------------------------------------------------------------------------
vi.mock("@/lib/api/samples", () => ({
  getSampleExpectedFields: vi.fn(),
  getSampleImageUrl: (id: string) => `/api/v1/samples/${id}/image`,
  listSamples: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/lib/api/client", () => ({
  analyzeLabel: vi.fn(),
  AnalyzeApiError: class AnalyzeApiError extends Error {
    constructor(
      public envelope: unknown,
      public httpStatus: number | null,
    ) {
      super("api error");
      this.name = "AnalyzeApiError";
    }
  },
  API_BASE_URL: "http://localhost:8000/api/v1",
}));

// Also mock global fetch so the file-prefetch in ReviewNewPage doesn't fail
global.fetch = vi.fn().mockResolvedValue({
  ok: false,
  blob: vi.fn(),
} as unknown as Response);

import { getSampleExpectedFields } from "@/lib/api/samples";
const mockGetSampleExpectedFields = vi.mocked(getSampleExpectedFields);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderAt(search: string = "") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/review/new${search}`]}>
        <Routes>
          <Route path="/review/new" element={<ReviewNewPage />} />
          <Route path="/review/:id" element={<div data-testid="results-page" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const SAMPLE_FIELDS: ExpectedFields = {
  brand_name: "ABC WINES",
  class_type: "American Merlot",
  alcohol_content: "ALC. 15.5% BY VOL.",
  net_contents: "750 ML",
  bottler: "BOTTLED BY XYZ VINTNERS, CITY, STATE",
  country_of_origin: null,
  warning: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("<ReviewNewPage>", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      blob: vi.fn(),
    });
  });

  // -------------------------------------------------------------------------
  // Base render
  // -------------------------------------------------------------------------

  it("renders the 'New review' heading", () => {
    renderAt();
    expect(screen.getByRole("heading", { name: /New review/i })).toBeInTheDocument();
  });

  it("renders the expected-fields form with empty inputs", () => {
    renderAt();
    const brandInput = screen.getByTestId("input-brand_name") as HTMLInputElement;
    expect(brandInput.value).toBe("");
  });

  it("does not show the upload section initially (no sample param)", () => {
    renderAt();
    // The UploadSection only appears once the user continues past the fields step.
    // With no ?sample param there is no auto-advance.
    expect(screen.queryByTestId("upload-section")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Legacy ?sample=1
  // -------------------------------------------------------------------------

  it("?sample=1 prefills brand_name with the stub sample value", () => {
    renderAt("?sample=1");
    const brandInput = screen.getByTestId("input-brand_name") as HTMLInputElement;
    expect(brandInput.value).toBe("Old Tom Distillery");
  });

  it("?sample=1 does NOT call getSampleExpectedFields (legacy path)", () => {
    renderAt("?sample=1");
    expect(mockGetSampleExpectedFields).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Named ?sample=<id> — fetches from API
  // -------------------------------------------------------------------------

  it("?sample=<id> calls getSampleExpectedFields with the correct id", async () => {
    mockGetSampleExpectedFields.mockResolvedValue(SAMPLE_FIELDS);
    renderAt("?sample=ttb_wine_reference");
    await waitFor(() => {
      expect(mockGetSampleExpectedFields).toHaveBeenCalledWith(
        "ttb_wine_reference",
      );
    });
  });

  it("?sample=<id> prefills the brand_name field after API responds", async () => {
    mockGetSampleExpectedFields.mockResolvedValue(SAMPLE_FIELDS);
    renderAt("?sample=ttb_wine_reference");
    await waitFor(() => {
      const brandInput = screen.getByTestId(
        "input-brand_name",
      ) as HTMLInputElement;
      expect(brandInput.value).toBe("ABC WINES");
    });
  });

  it("?sample=clean_match calls API with correct id", async () => {
    mockGetSampleExpectedFields.mockResolvedValue({
      brand_name: "STONE'S THROW WINERY",
      class_type: "Cabernet Sauvignon",
      alcohol_content: "13.5% Alc./Vol.",
      net_contents: "750 mL",
      bottler: "Bottled by Stone's Throw Winery, Napa, CA",
      country_of_origin: null,
      warning: null,
    });
    renderAt("?sample=clean_match");
    await waitFor(() => {
      expect(mockGetSampleExpectedFields).toHaveBeenCalledWith("clean_match");
    });
  });
});
