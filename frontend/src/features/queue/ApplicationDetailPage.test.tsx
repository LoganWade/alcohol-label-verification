/**
 * Tests for <ApplicationDetailPage>.
 *
 * Covers:
 *   - Reuses <ResultsView> when analyze is present.
 *   - Renders the error envelope via <ErrorPanel> on failure.
 *   - Workflow decision PUT updates the app.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ApplicationDetailPage } from "./ApplicationDetailPage";
import { FULL_FIXTURE } from "@/lib/__fixtures__/analyzeResponse";
import type { BatchApplication } from "@/lib/types/api";

vi.mock("@/lib/api/batches", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/batches")>(
    "@/lib/api/batches",
  );
  return {
    ...actual,
    getApplication: vi.fn(),
    setApplicationDecision: vi.fn(),
  };
});

import {
  getApplication,
  setApplicationDecision,
} from "@/lib/api/batches";
const mockGetApplication = vi.mocked(getApplication);
const mockSetDecision = vi.mocked(setApplicationDecision);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
function makeApp(overrides: Partial<BatchApplication> = {}): BatchApplication {
  return {
    id: "app_1",
    batch_id: "batch_1",
    fields: {
      serial_number: "TTB-001",
      brand_name: "Old Tom Distillery",
      fanciful_name: null,
      class_type: "Kentucky Straight Bourbon Whiskey",
      alcohol_content: "45% Alc./Vol.",
      net_contents: "750 mL",
      bottler: "Old Tom Co.",
      country_of_origin: "USA",
    },
    processing_status: "done",
    workflow_status: "pending_review",
    images: [
      {
        id: "img_1",
        filename: "front.png",
        attribution: "front",
        is_primary: true,
        byte_size: 1024,
        content_type: "image/png",
      },
    ],
    analyze: FULL_FIXTURE,
    error: null,
    created_at: "2026-04-30T15:00:00Z",
    processed_at: "2026-04-30T15:00:30Z",
    decided_at: null,
    decided_note: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function renderAt(id = "app_1") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/queue/applications/${id}?batch=batch_1`]}>
        <Routes>
          <Route
            path="/queue/applications/:id"
            element={<ApplicationDetailPage />}
          />
          <Route path="/queue" element={<div>queue page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("<ApplicationDetailPage>", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the application header with serial + workflow pill", async () => {
    mockGetApplication.mockResolvedValue(makeApp());
    renderAt();
    await waitFor(() =>
      expect(screen.getByTestId("application-header")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Application TTB-001/i)).toBeInTheDocument();
    expect(screen.getByTestId("workflow-pill")).toHaveTextContent(
      "Pending review",
    );
  });

  it("reuses <ResultsView> when the application has an analyze payload", async () => {
    mockGetApplication.mockResolvedValue(makeApp());
    renderAt();
    await waitFor(() =>
      expect(screen.getByTestId("results-view")).toBeInTheDocument(),
    );
  });

  it("renders <ErrorPanel> when processing failed", async () => {
    mockGetApplication.mockResolvedValue(
      makeApp({
        processing_status: "failed",
        analyze: null,
        error: {
          code: "ocr_no_text",
          message: "OCR returned no text.",
          recovery_hint: "Re-upload a higher resolution image.",
        },
      }),
    );
    renderAt();
    await waitFor(() =>
      expect(screen.getByTestId("error-panel")).toBeInTheDocument(),
    );
    expect(screen.getByText(/OCR returned no text/i)).toBeInTheDocument();
  });

  it("shows the waiting state while processing is still in flight", async () => {
    mockGetApplication.mockResolvedValue(
      makeApp({ processing_status: "processing", analyze: null }),
    );
    renderAt();
    await waitFor(() =>
      expect(screen.getByTestId("pipeline-waiting")).toBeInTheDocument(),
    );
  });

  it("calls setApplicationDecision on Approve click", async () => {
    mockGetApplication.mockResolvedValue(makeApp());
    mockSetDecision.mockResolvedValue(makeApp({ workflow_status: "approved" }));

    const user = userEvent.setup();
    renderAt();
    await waitFor(() =>
      expect(screen.getByTestId("decision-form")).toBeInTheDocument(),
    );

    await user.type(screen.getByTestId("decision-note"), "Looks good");
    await user.click(screen.getByTestId("decision-approved"));

    await waitFor(() => {
      expect(mockSetDecision).toHaveBeenCalledWith("app_1", {
        workflow_status: "approved",
        note: "Looks good",
      });
    });
    await waitFor(() =>
      expect(screen.getByTestId("decision-success")).toBeInTheDocument(),
    );
  });
});
