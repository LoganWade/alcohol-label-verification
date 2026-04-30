/**
 * Tests for <QueuePage>.
 *
 * The page composes listBatches + getBatch + bulkApproveBatch.
 * We mock api/batches so the network layer is fully stubbed.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueuePage } from "./QueuePage";
import type {
  Batch,
  BatchApplication,
  BatchDetail,
  BulkApproveResponse,
} from "@/lib/types/api";

vi.mock("@/lib/api/batches", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/batches")>(
    "@/lib/api/batches",
  );
  return {
    ...actual,
    listBatches: vi.fn(),
    getBatch: vi.fn(),
    bulkApproveBatch: vi.fn(),
  };
});

import { listBatches, getBatch, bulkApproveBatch } from "@/lib/api/batches";
const mockListBatches = vi.mocked(listBatches);
const mockGetBatch = vi.mocked(getBatch);
const mockBulkApprove = vi.mocked(bulkApproveBatch);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const BATCH_SUMMARY: Batch = {
  id: "batch_1",
  importer_name: "Janet's Imports",
  importer_email: "j@example.com",
  note: "peak season",
  counts: {
    total: 3,
    pending: 0,
    processing: 0,
    done: 3,
    failed: 0,
    approved: 1,
    rejected: 0,
    needs_correction: 0,
  },
  created_at: "2026-04-30T15:00:00Z",
};

function app(
  id: string,
  workflow: BatchApplication["workflow_status"],
  serial: string,
): BatchApplication {
  return {
    id,
    batch_id: "batch_1",
    fields: {
      serial_number: serial,
      brand_name: "Some Brand",
      fanciful_name: null,
      class_type: null,
      alcohol_content: null,
      net_contents: null,
      bottler: null,
      country_of_origin: null,
    },
    processing_status: "done",
    workflow_status: workflow,
    images: [],
    analyze: null,
    error: null,
    created_at: "2026-04-30T15:00:00Z",
    processed_at: "2026-04-30T15:00:30Z",
    decided_at: null,
    decided_note: null,
  };
}

const BATCH_DETAIL: BatchDetail = {
  ...BATCH_SUMMARY,
  applications: [
    app("a1", "approved", "TTB-001"),
    app("a2", "pending_review", "TTB-002"),
    app("a3", "rejected", "TTB-003"),
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function renderQueue(initial = "/queue") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/batches/new" element={<div>new batch page</div>} />
          <Route
            path="/queue/applications/:id"
            element={<div>app detail</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("<QueuePage>", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the batch list and auto-selects the first one", async () => {
    mockListBatches.mockResolvedValue([BATCH_SUMMARY]);
    mockGetBatch.mockResolvedValue(BATCH_DETAIL);
    renderQueue();

    await waitFor(() =>
      expect(
        screen.getByTestId(`batch-list-item-${BATCH_SUMMARY.id}`),
      ).toBeInTheDocument(),
    );
    // Right pane fills in once detail loads
    await waitFor(() =>
      expect(screen.getByTestId("applications-table")).toBeInTheDocument(),
    );
    expect(screen.getByText("TTB-001")).toBeInTheDocument();
    expect(screen.getByText("TTB-002")).toBeInTheDocument();
  });

  it("shows the empty state when no batches exist", async () => {
    mockListBatches.mockResolvedValue([]);
    renderQueue();
    await waitFor(() =>
      expect(screen.getByText(/No batches yet/i)).toBeInTheDocument(),
    );
  });

  it("filters applications by workflow status", async () => {
    mockListBatches.mockResolvedValue([BATCH_SUMMARY]);
    mockGetBatch.mockResolvedValue(BATCH_DETAIL);
    const user = userEvent.setup();
    renderQueue();

    await waitFor(() =>
      expect(screen.getByTestId("applications-table")).toBeInTheDocument(),
    );

    await user.click(screen.getByTestId("filter-approved"));
    expect(screen.getByText("TTB-001")).toBeInTheDocument();
    expect(screen.queryByText("TTB-002")).not.toBeInTheDocument();
    expect(screen.queryByText("TTB-003")).not.toBeInTheDocument();
  });

  it("calls bulk approve and renders the result counts", async () => {
    mockListBatches.mockResolvedValue([BATCH_SUMMARY]);
    mockGetBatch.mockResolvedValue(BATCH_DETAIL);
    const result: BulkApproveResponse = {
      approved_count: 2,
      skipped_count: 1,
      skipped_reasons: { not_clean_match: 1 },
    };
    mockBulkApprove.mockResolvedValue(result);

    const user = userEvent.setup();
    renderQueue();

    await waitFor(() =>
      expect(screen.getByTestId("bulk-approve")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("bulk-approve"));

    await waitFor(() =>
      expect(screen.getByTestId("bulk-approve-result")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Approved 2, skipped 1/i)).toBeInTheDocument();
  });
});
