/**
 * Tests for <BatchUploadPage>.
 *
 * The form submits a multipart/form-data POST to /batches via createBatch.
 * We mock the entire api/batches module so the tests are deterministic.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { BatchUploadPage } from "./BatchUploadPage";
import type { Batch, ManifestError } from "@/lib/types/api";

// ---------------------------------------------------------------------------
// Mock api/batches
// ---------------------------------------------------------------------------
vi.mock("@/lib/api/batches", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/batches")>(
    "@/lib/api/batches",
  );
  return {
    ...actual,
    createBatch: vi.fn(),
  };
});

import { BatchApiError, createBatch } from "@/lib/api/batches";
const mockCreateBatch = vi.mocked(createBatch);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/batches/new"]}>
        <Routes>
          <Route path="/batches/new" element={<BatchUploadPage />} />
          <Route path="/queue" element={<div>queue page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const FAKE_BATCH: Batch = {
  id: "batch_abc",
  importer_name: "Importer Inc.",
  importer_email: "i@example.com",
  note: null,
  counts: {
    total: 1,
    pending: 1,
    processing: 0,
    done: 0,
    failed: 0,
    approved: 0,
    rejected: 0,
    needs_correction: 0,
  },
  created_at: "2026-04-30T15:00:00Z",
};

function csvFile() {
  return new File(["serial_number,brand_name,image_filename,is_primary\n"], "manifest.csv", {
    type: "text/csv",
  });
}

function imgFile(name = "front.png") {
  return new File([new Uint8Array([0])], name, { type: "image/png" });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("<BatchUploadPage>", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the importer fields and file pickers", () => {
    renderPage();
    expect(
      screen.getByRole("heading", { name: /Submit a batch of applications/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Importer name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Importer email/i)).toBeInTheDocument();
  });

  it("disables submit until name + email + manifest + images are selected", () => {
    renderPage();
    const submit = screen.getByTestId("submit-batch");
    expect(submit).toBeDisabled();
  });

  it("submits and navigates to queue on success", async () => {
    mockCreateBatch.mockResolvedValue(FAKE_BATCH);
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/Importer name/i), "Importer Inc.");
    await user.type(screen.getByLabelText(/Importer email/i), "i@example.com");

    const manifestInput = screen.getByTestId("input-manifest-file") as HTMLInputElement;
    await user.upload(manifestInput, csvFile());

    const imagesInput = screen.getByTestId("input-images") as HTMLInputElement;
    await user.upload(imagesInput, [imgFile("front.png")]);

    await user.click(screen.getByTestId("submit-batch"));

    await waitFor(() => {
      expect(mockCreateBatch).toHaveBeenCalledTimes(1);
    });
    await waitFor(() =>
      expect(screen.getByText("queue page")).toBeInTheDocument(),
    );
  });

  it("renders manifest errors row-by-row when the API returns 400", async () => {
    const errors: ManifestError[] = [
      {
        row_number: 2,
        column: "alcohol_content",
        code: "invalid_alcohol",
        message: "Could not parse alcohol_content '90 proof'",
      },
      {
        row_number: 3,
        column: "image_filename",
        code: "missing_file",
        message: "Manifest references file 'side.png' not in upload.",
      },
    ];
    mockCreateBatch.mockRejectedValue(
      new BatchApiError(
        {
          code: "manifest_invalid",
          message: "Manifest had errors",
          recovery_hint: "Fix and re-upload",
        },
        400,
        errors,
      ),
    );
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/Importer name/i), "Bad Importer");
    await user.type(screen.getByLabelText(/Importer email/i), "b@example.com");
    await user.upload(screen.getByTestId("input-manifest-file"), csvFile());
    await user.upload(screen.getByTestId("input-images"), [imgFile()]);
    await user.click(screen.getByTestId("submit-batch"));

    await waitFor(() =>
      expect(screen.getByTestId("manifest-errors")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Could not parse alcohol_content/)).toBeInTheDocument();
    expect(
      screen.getByText(/Manifest references file 'side\.png'/),
    ).toBeInTheDocument();
  });
});
