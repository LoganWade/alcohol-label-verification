/**
 * Tests for <BoundingBoxPreview>.
 *
 * The component reads natural image dimensions from a hidden <img>'s
 * onLoad event. jsdom doesn't decode images, so we simulate that by
 * stubbing `naturalWidth` / `naturalHeight` and firing the load event.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BoundingBoxPreview } from "./BoundingBoxPreview";
import type { BoundingBox } from "@/lib/types/api";

const BBOX: BoundingBox = { x0: 100, y0: 200, x1: 400, y1: 280 };

function setNaturalSizeAndFireLoad(width: number, height: number) {
  const img = document.querySelector("img.hidden") as HTMLImageElement | null;
  if (!img) throw new Error("hidden loader <img> not found");
  Object.defineProperty(img, "naturalWidth", { configurable: true, value: width });
  Object.defineProperty(img, "naturalHeight", { configurable: true, value: height });
  fireEvent.load(img);
}

describe("<BoundingBoxPreview>", () => {
  beforeEach(() => {
    // Each test renders fresh; nothing global to reset.
  });

  it("renders nothing when bbox is null", () => {
    const { container } = render(
      <BoundingBoxPreview
        bbox={null}
        imageUrl="/img.png"
        imageAlt="label"
      />,
    );
    expect(container.querySelector('[data-testid="bbox-preview"]')).toBeNull();
  });

  it("renders nothing when imageUrl is missing", () => {
    const { container } = render(
      <BoundingBoxPreview bbox={BBOX} imageUrl={null} imageAlt="label" />,
    );
    expect(container.querySelector('[data-testid="bbox-preview"]')).toBeNull();
  });

  it("renders the crop view by default once the image loads", async () => {
    render(
      <BoundingBoxPreview
        bbox={BBOX}
        imageUrl="/img.png"
        imageAlt="label region"
      />,
    );
    setNaturalSizeAndFireLoad(800, 600);
    await waitFor(() =>
      expect(screen.getByTestId("bbox-preview-crop")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("bbox-preview-full")).toBeNull();
  });

  it("toggles to the full image with overlay rectangle", async () => {
    render(
      <BoundingBoxPreview
        bbox={BBOX}
        imageUrl="/img.png"
        imageAlt="label region"
      />,
    );
    setNaturalSizeAndFireLoad(800, 600);
    await waitFor(() =>
      expect(screen.getByTestId("bbox-preview-crop")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByTestId("bbox-preview-toggle"));

    expect(screen.getByTestId("bbox-preview-full")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-preview-overlay")).toBeInTheDocument();
    expect(screen.queryByTestId("bbox-preview-crop")).toBeNull();
  });

  it("scales the crop background so the bbox fills the display area", async () => {
    // bbox is 300px wide; with maxCropWidth=300 the scale is 1.0,
    // so the backdrop equals the natural image size.
    render(
      <BoundingBoxPreview
        bbox={BBOX}
        imageUrl="/img.png"
        imageAlt="label region"
        maxCropWidth={300}
      />,
    );
    setNaturalSizeAndFireLoad(800, 600);
    await waitFor(() =>
      expect(screen.getByTestId("bbox-preview-crop")).toBeInTheDocument(),
    );
    const crop = screen.getByTestId("bbox-preview-crop");
    expect(crop.style.width).toBe("300px");
    expect(crop.style.height).toBe("80px");
    expect(crop.style.backgroundSize).toBe("800px 600px");
    // Backdrop offset = -bbox top-left
    expect(crop.style.backgroundPosition).toBe("-100px -200px");
  });

  it("renders an error fallback when the image fails to load", async () => {
    render(
      <BoundingBoxPreview
        bbox={BBOX}
        imageUrl="/missing.png"
        imageAlt="label region"
      />,
    );
    const img = document.querySelector("img.hidden") as HTMLImageElement;
    fireEvent.error(img);
    await waitFor(() =>
      expect(screen.getByTestId("bbox-preview-error")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("bbox-preview-crop")).toBeNull();
  });

  it("renders an empty-bbox notice when width or height is zero", async () => {
    render(
      <BoundingBoxPreview
        bbox={{ x0: 50, y0: 50, x1: 50, y1: 50 }}
        imageUrl="/img.png"
        imageAlt="label region"
      />,
    );
    setNaturalSizeAndFireLoad(800, 600);
    await waitFor(() =>
      expect(screen.getByTestId("bbox-preview-empty")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("bbox-preview-crop")).toBeNull();
  });

  it("uses the provided alt text on the cropped region for screen readers", async () => {
    render(
      <BoundingBoxPreview
        bbox={BBOX}
        imageUrl="/img.png"
        imageAlt="alcohol content field"
      />,
    );
    setNaturalSizeAndFireLoad(800, 600);
    await waitFor(() => {
      const crop = screen.getByTestId("bbox-preview-crop");
      expect(crop.getAttribute("aria-label")).toContain(
        "alcohol content field",
      );
    });
  });
});
