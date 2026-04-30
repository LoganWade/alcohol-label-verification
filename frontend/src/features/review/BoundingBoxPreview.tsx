/**
 * Renders a cropped preview of an OCR bounding box over a label image.
 *
 * Two modes:
 *   - "crop"  (default) — shows just the cropped region. The crop is done
 *                         purely in CSS using `background-image` +
 *                         `background-size` + `background-position`, so
 *                         no canvas, no extra fetch, no Pillow. The image
 *                         is loaded once via a hidden <img> so we can read
 *                         its natural pixel dimensions and scale the
 *                         backdrop correctly.
 *   - "full" (toggled)  — shows the entire image with a thin highlighted
 *                         rectangle drawn over the bbox region.
 *
 * Coordinates from the backend are in *image pixel space* (matching the
 * image natural size). All scaling lives in this component.
 *
 * If the image fails to load or no bbox/imageUrl is given, the component
 * renders a small fallback line and never throws.
 */
import { useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import type { BoundingBox } from "@/lib/types/api";

interface Props {
  bbox: BoundingBox | null;
  imageUrl: string | null | undefined;
  imageAlt: string;
  /** Maximum displayed width of the crop preview, in CSS pixels. */
  maxCropWidth?: number;
  /** Maximum displayed width of the expanded full image, in CSS pixels. */
  maxFullWidth?: number;
}

interface NaturalSize {
  width: number;
  height: number;
}

export function BoundingBoxPreview({
  bbox,
  imageUrl,
  imageAlt,
  maxCropWidth = 360,
  maxFullWidth = 480,
}: Props) {
  const [natural, setNatural] = useState<NaturalSize | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [expanded, setExpanded] = useState(false);

  // Nothing to render — parent already shows the bbox text or "no bbox" line.
  if (!bbox || !imageUrl) {
    return null;
  }

  if (loadError) {
    return (
      <p
        className="text-xs text-ink-500 italic"
        data-testid="bbox-preview-error"
      >
        Could not load the label image to render the crop preview.
      </p>
    );
  }

  const bboxWidth = Math.max(0, bbox.x1 - bbox.x0);
  const bboxHeight = Math.max(0, bbox.y1 - bbox.y0);

  return (
    <div className="space-y-u-1" data-testid="bbox-preview">
      {/* Hidden loader: lets us read the natural image dimensions
          before doing any CSS math. We render the visible preview only
          after the dimensions are known. */}
      {!natural && (
        <img
          src={imageUrl}
          alt=""
          aria-hidden="true"
          className="hidden"
          // Stable hook for tests that need to fire onLoad with mocked
          // natural dimensions. Querying by Tailwind class couples tests
          // to styling; a data-testid is the right contract.
          data-testid="bbox-preview-loader"
          onLoad={(e) => {
            const img = e.currentTarget;
            setNatural({
              width: img.naturalWidth,
              height: img.naturalHeight,
            });
          }}
          onError={() => setLoadError(true)}
        />
      )}

      {natural && bboxWidth > 0 && bboxHeight > 0 && (
        <>
          {!expanded && (
            <CropView
              imageUrl={imageUrl}
              imageAlt={imageAlt}
              bbox={bbox}
              natural={natural}
              maxCropWidth={maxCropWidth}
            />
          )}
          {expanded && (
            <FullView
              imageUrl={imageUrl}
              imageAlt={imageAlt}
              bbox={bbox}
              natural={natural}
              maxFullWidth={maxFullWidth}
            />
          )}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
            data-testid="bbox-preview-toggle"
            aria-pressed={expanded}
          >
            {expanded ? (
              <>
                <Minimize2 size={12} aria-hidden="true" />
                Show crop only
              </>
            ) : (
              <>
                <Maximize2 size={12} aria-hidden="true" />
                Show full image
              </>
            )}
          </button>
        </>
      )}

      {natural && (bboxWidth === 0 || bboxHeight === 0) && (
        <p
          className="text-xs text-ink-500 italic"
          data-testid="bbox-preview-empty"
        >
          Bounding box has zero area; nothing to preview.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CropView — CSS-only crop using background-image
// ---------------------------------------------------------------------------
interface ViewProps {
  imageUrl: string;
  imageAlt: string;
  bbox: BoundingBox;
  natural: NaturalSize;
}

function CropView({
  imageUrl,
  imageAlt,
  bbox,
  natural,
  maxCropWidth,
}: ViewProps & { maxCropWidth: number }) {
  const bboxW = bbox.x1 - bbox.x0;
  const bboxH = bbox.y1 - bbox.y0;
  // Scale so the bbox fills `maxCropWidth` (capped to actual size).
  const displayW = Math.min(bboxW, maxCropWidth);
  const scale = displayW / bboxW;
  const displayH = bboxH * scale;
  // The full image, scaled by the same factor, becomes our backdrop.
  const bgW = natural.width * scale;
  const bgH = natural.height * scale;
  // Slide the backdrop so the bbox aligns with (0, 0) of our viewport.
  const bgX = -bbox.x0 * scale;
  const bgY = -bbox.y0 * scale;

  return (
    <div
      role="img"
      aria-label={`Cropped region of ${imageAlt} showing the matched OCR text.`}
      className="border border-ink-200 rounded bg-ink-50"
      data-testid="bbox-preview-crop"
      style={{
        width: `${displayW}px`,
        height: `${displayH}px`,
        backgroundImage: `url("${imageUrl}")`,
        backgroundRepeat: "no-repeat",
        backgroundSize: `${bgW}px ${bgH}px`,
        backgroundPosition: `${bgX}px ${bgY}px`,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// FullView — full image with overlay rectangle
// ---------------------------------------------------------------------------
function FullView({
  imageUrl,
  imageAlt,
  bbox,
  natural,
  maxFullWidth,
}: ViewProps & { maxFullWidth: number }) {
  const displayW = Math.min(natural.width, maxFullWidth);
  const scale = displayW / natural.width;
  const displayH = natural.height * scale;

  const left = bbox.x0 * scale;
  const top = bbox.y0 * scale;
  const width = (bbox.x1 - bbox.x0) * scale;
  const height = (bbox.y1 - bbox.y0) * scale;

  return (
    <div
      className="relative inline-block border border-ink-200 rounded overflow-hidden"
      data-testid="bbox-preview-full"
      style={{ width: `${displayW}px`, height: `${displayH}px` }}
    >
      <img
        src={imageUrl}
        alt={imageAlt}
        width={displayW}
        height={displayH}
        className="block"
        draggable={false}
      />
      <div
        aria-hidden="true"
        className="absolute pointer-events-none border-2 border-primary shadow-[0_0_0_2px_rgba(255,255,255,0.6)]"
        data-testid="bbox-preview-overlay"
        style={{
          left: `${left}px`,
          top: `${top}px`,
          width: `${width}px`,
          height: `${height}px`,
        }}
      />
    </div>
  );
}
