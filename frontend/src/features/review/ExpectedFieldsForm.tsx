import { useState, useId } from "react";
import { ClipboardPaste, ListChecks, Sparkles } from "lucide-react";
import type { ExpectedFields } from "@/lib/types/api";
import { TextField, TextArea } from "@/components/Field";
import { Button } from "@/components/Button";
import {
  STUB_SAMPLE_EXPECTED_FIELDS,
  DEFAULT_GOVERNMENT_WARNING,
} from "@/lib/sample";

import { expectedFieldsAreReady } from "@/features/review/expectedFieldsValidation";

type Mode = "form" | "json" | "sample";

interface Props {
  value: ExpectedFields;
  onChange: (next: ExpectedFields) => void;
  onContinue: () => void;
  /** When true, pre-load the stub sample on mount (from ?sample=1). */
  initialMode?: Mode;
}

// All-null EMPTY: blank optional fields ship as null on the wire so the
// backend's compare_field treats them as "not supplied" rather than
// comparing against an empty string. Required fields are still null when
// blank — `expectedFieldsAreReady` enforces non-empty values before submit.
const EMPTY: ExpectedFields = {
  brand_name: null,
  class_type: null,
  alcohol_content: null,
  net_contents: null,
  bottler: null,
  country_of_origin: null,
  warning: null,
};

export function ExpectedFieldsForm({
  value,
  onChange,
  onContinue,
  initialMode = "form",
}: Props) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [jsonText, setJsonText] = useState<string>(() =>
    JSON.stringify(value, null, 2),
  );
  const [jsonError, setJsonError] = useState<string | undefined>();
  const [warningEnabled, setWarningEnabled] = useState<boolean>(
    value.warning !== null,
  );
  const warningToggleId = useId();

  const update = <K extends keyof ExpectedFields>(
    key: K,
    next: ExpectedFields[K],
  ) => onChange({ ...value, [key]: next });

  const tryParseJson = (text: string) => {
    setJsonText(text);
    if (!text.trim()) {
      setJsonError("Paste a JSON object with the expected fields.");
      return;
    }
    try {
      const parsed = JSON.parse(text);
      const next: ExpectedFields = { ...EMPTY, ...parsed };
      onChange(next);
      setJsonError(undefined);
    } catch (e) {
      setJsonError(
        `Could not parse JSON: ${(e as Error).message}. Check syntax and retry.`,
      );
    }
  };

  const loadSample = () => {
    onChange({ ...STUB_SAMPLE_EXPECTED_FIELDS });
    setJsonText(JSON.stringify(STUB_SAMPLE_EXPECTED_FIELDS, null, 2));
    setWarningEnabled(STUB_SAMPLE_EXPECTED_FIELDS.warning !== null);
    setMode("form");
  };

  const ready = expectedFieldsAreReady(value);

  return (
    <section
      aria-labelledby="expected-fields-heading"
      className="card p-u-3 space-y-u-3"
    >
      <header className="flex items-start justify-between flex-wrap gap-u-2">
        <div>
          <h2
            id="expected-fields-heading"
            className="text-xl font-semibold"
          >
            Step 1 — Expected fields
          </h2>
          <p className="text-sm text-ink-500 mt-1">
            Enter the values from the application that should appear on the
            label.
          </p>
        </div>
        <div
          role="tablist"
          aria-label="Input mode"
          className="inline-flex rounded border border-ink-200 bg-ink-50 p-0.5"
        >
          {(
            [
              { id: "form" as Mode, label: "Form", Icon: ListChecks },
              { id: "json" as Mode, label: "Paste JSON", Icon: ClipboardPaste },
              { id: "sample" as Mode, label: "Load sample", Icon: Sparkles },
            ]
          ).map(({ id, label, Icon }) => {
            const active = mode === id;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => {
                  if (id === "sample") {
                    loadSample();
                  } else {
                    setMode(id);
                  }
                }}
                className={`inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded transition-colors min-h-[36px] ${
                  active
                    ? "bg-white text-primary shadow-sm font-medium"
                    : "text-ink-600 hover:text-ink-800"
                }`}
                data-testid={`tab-${id}`}
              >
                <Icon size={14} aria-hidden="true" />
                {label}
              </button>
            );
          })}
        </div>
      </header>

      {mode === "json" ? (
        <TextArea
          label="Expected fields JSON"
          hint="Paste a JSON object. Keys: brand_name, class_type, alcohol_content, net_contents, bottler, country_of_origin, warning."
          error={jsonError}
          value={jsonText}
          onChange={(e) => tryParseJson(e.target.value)}
          spellCheck={false}
          data-testid="input-json"
        />
      ) : (
        <div className="grid gap-u-2 md:grid-cols-2">
          <TextField
            label="Brand name"
            placeholder="e.g. Old Tom Distillery"
            value={value.brand_name ?? ""}
            onChange={(e) => update("brand_name", e.target.value || null)}
            data-testid="input-brand_name"
            required
          />
          <TextField
            label="Class / type"
            placeholder="e.g. Kentucky Straight Bourbon Whiskey"
            value={value.class_type ?? ""}
            onChange={(e) => update("class_type", e.target.value || null)}
            data-testid="input-class_type"
          />
          <TextField
            label="Alcohol content"
            placeholder="e.g. 45% Alc./Vol."
            value={value.alcohol_content ?? ""}
            onChange={(e) => update("alcohol_content", e.target.value || null)}
            data-testid="input-alcohol_content"
            required
          />
          <TextField
            label="Net contents"
            placeholder="e.g. 750 mL"
            value={value.net_contents ?? ""}
            onChange={(e) => update("net_contents", e.target.value || null)}
            data-testid="input-net_contents"
          />
          <TextField
            label="Bottler / producer"
            placeholder="e.g. Bottled by Old Tom Co., Frankfort, KY"
            value={value.bottler ?? ""}
            onChange={(e) => update("bottler", e.target.value || null)}
            data-testid="input-bottler"
          />
          <TextField
            label="Country of origin"
            placeholder="e.g. United States"
            optional
            value={value.country_of_origin ?? ""}
            onChange={(e) =>
              update("country_of_origin", e.target.value || null)
            }
            data-testid="input-country_of_origin"
          />

          <div className="md:col-span-2 space-y-u-1">
            <div className="flex items-center justify-between">
              <span className="label-base !mb-0">
                Government warning{" "}
                <span className="text-ink-400 font-normal">(optional)</span>
              </span>
              <label
                htmlFor={warningToggleId}
                className="inline-flex items-center gap-2 text-sm text-ink-600 cursor-pointer"
              >
                <input
                  id={warningToggleId}
                  type="checkbox"
                  className="h-4 w-4 accent-primary"
                  checked={warningEnabled}
                  onChange={(e) => {
                    const checked = e.target.checked;
                    setWarningEnabled(checked);
                    update(
                      "warning",
                      checked ? DEFAULT_GOVERNMENT_WARNING : null,
                    );
                  }}
                  data-testid="toggle-default-warning"
                />
                Use standard TTB warning
              </label>
            </div>
            <textarea
              aria-label="Government warning text"
              className="input-base font-mono text-sm min-h-[6rem]"
              placeholder="Leave blank to use the default TTB warning text."
              value={value.warning ?? ""}
              onChange={(e) => update("warning", e.target.value || null)}
              data-testid="input-warning"
            />
            <p className="text-xs text-ink-500">
              When left blank, the validator compares against the standard
              statutory text.
            </p>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between flex-wrap gap-u-2 pt-u-1 border-t border-ink-100">
        <p className="text-xs text-ink-500">
          Brand name and alcohol content are required to continue.
        </p>
        <Button
          onClick={onContinue}
          disabled={!ready}
          data-testid="button-continue-to-upload"
        >
          Continue to upload
        </Button>
      </div>
    </section>
  );
}
