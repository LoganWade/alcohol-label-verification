import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ErrorPanel } from "./ErrorPanel";

describe("<ErrorPanel>", () => {
  it("renders the AnalyzeError message and recovery_hint verbatim", () => {
    render(
      <ErrorPanel
        error={{
          code: "file_too_large",
          message: "This file is 14 MB. Please upload an image under 10 MB.",
          recovery_hint: "Resize the image to a smaller resolution and try again.",
        }}
      />,
    );

    expect(screen.getByTestId("error-message").textContent).toContain(
      "This file is 14 MB",
    );
    expect(screen.getByTestId("error-recovery-hint").textContent).toContain(
      "Resize the image to a smaller resolution and try again.",
    );
    expect(screen.getByTestId("error-code").textContent).toBe("file_too_large");
  });

  it("omits the recovery hint paragraph when absent", () => {
    render(
      <ErrorPanel
        error={{
          code: "unknown",
          message: "Something failed.",
          recovery_hint: null,
        }}
      />,
    );
    expect(screen.queryByTestId("error-recovery-hint")).toBeNull();
  });

  it("calls onRetry when retry button is clicked", () => {
    const onRetry = vi.fn();
    render(
      <ErrorPanel
        error={{ code: "x", message: "y", recovery_hint: null }}
        onRetry={onRetry}
      />,
    );
    fireEvent.click(screen.getByTestId("error-retry"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
