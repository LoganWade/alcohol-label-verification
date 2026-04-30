/**
 * Tests for <UploadSection>'s file validation.
 *
 * `validateFile` is module-private by design, so we drive it through the
 * public file-picker surface and assert on the rendered error message.
 * That keeps tests honest about the contract a reviewer actually sees.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { UploadSection } from "./UploadSection";

function renderWithFile(handlers?: { onFileChange?: (f: File | null) => void }) {
  const onFileChange = handlers?.onFileChange ?? vi.fn();
  const onRun = vi.fn();
  render(
    <UploadSection file={null} onFileChange={onFileChange} onRun={onRun} />,
  );
  return { onFileChange, onRun };
}

function makeFile(name: string, type: string, size: number): File {
  const f = new File([new Uint8Array(8)], name, { type });
  // jsdom honors the constructor's blob bytes for `size`; override for the
  // oversize test instead of allocating an actual 11 MB Uint8Array.
  Object.defineProperty(f, "size", { configurable: true, value: size });
  return f;
}

function pickFile(file: File) {
  const input = screen.getByTestId("input-file") as HTMLInputElement;
  // jsdom requires defineProperty to seed `files` on a file input.
  Object.defineProperty(input, "files", { configurable: true, value: [file] });
  fireEvent.change(input);
}

describe("<UploadSection> validateFile", () => {
  it("rejects an unsupported MIME type with a clear error", () => {
    const { onFileChange } = renderWithFile();
    pickFile(makeFile("notes.pdf", "application/pdf", 1024));

    const err = screen.getByTestId("text-upload-error");
    expect(err.textContent).toMatch(/not supported/i);
    expect(err.textContent).toMatch(/PNG or JPG/i);
    // The picker should clear the file slot when validation fails so the
    // reviewer doesn't see an inconsistent "file selected + error" state.
    expect(onFileChange).toHaveBeenLastCalledWith(null);
  });

  it("rejects a file larger than the 10 MB limit", () => {
    const { onFileChange } = renderWithFile();
    const elevenMb = 11 * 1024 * 1024;
    pickFile(makeFile("huge.png", "image/png", elevenMb));

    const err = screen.getByTestId("text-upload-error");
    expect(err.textContent).toMatch(/10 MB/i);
    expect(err.textContent).toMatch(/11\.0 MB/);
    expect(onFileChange).toHaveBeenLastCalledWith(null);
  });

  it("accepts a valid PNG under the size cap", () => {
    const { onFileChange } = renderWithFile();
    const file = makeFile("label.png", "image/png", 256 * 1024);
    pickFile(file);

    expect(screen.queryByTestId("text-upload-error")).toBeNull();
    expect(onFileChange).toHaveBeenLastCalledWith(file);
  });

  it("accepts a valid JPEG under the size cap", () => {
    const { onFileChange } = renderWithFile();
    const file = makeFile("label.jpg", "image/jpeg", 512 * 1024);
    pickFile(file);

    expect(screen.queryByTestId("text-upload-error")).toBeNull();
    expect(onFileChange).toHaveBeenLastCalledWith(file);
  });
});
