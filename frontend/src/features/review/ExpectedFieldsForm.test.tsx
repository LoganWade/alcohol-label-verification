import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useState } from "react";
import { ExpectedFieldsForm } from "./ExpectedFieldsForm";
import { expectedFieldsAreReady } from "./expectedFieldsValidation";
import type { ExpectedFields } from "@/lib/types/api";

const EMPTY: ExpectedFields = {
  brand_name: "",
  class_type: "",
  alcohol_content: "",
  net_contents: "",
  bottler: "",
  country_of_origin: null,
  warning: null,
};

function Harness({ onContinue }: { onContinue?: () => void }) {
  const [v, setV] = useState<ExpectedFields>(EMPTY);
  return (
    <ExpectedFieldsForm
      value={v}
      onChange={setV}
      onContinue={onContinue ?? (() => undefined)}
    />
  );
}

describe("<ExpectedFieldsForm>", () => {
  it("disables Continue until brand_name AND alcohol_content are filled", () => {
    render(<Harness />);
    const cont = screen.getByTestId("button-continue-to-upload") as HTMLButtonElement;
    expect(cont.disabled).toBe(true);

    fireEvent.change(screen.getByTestId("input-brand_name"), {
      target: { value: "Old Tom Distillery" },
    });
    expect(cont.disabled).toBe(true); // still missing alcohol_content

    fireEvent.change(screen.getByTestId("input-alcohol_content"), {
      target: { value: "45% Alc./Vol." },
    });
    expect(cont.disabled).toBe(false);
  });

  it("calls onContinue when the button is clicked and form is ready", () => {
    const onContinue = vi.fn();
    render(<Harness onContinue={onContinue} />);
    fireEvent.change(screen.getByTestId("input-brand_name"), {
      target: { value: "Old Tom Distillery" },
    });
    fireEvent.change(screen.getByTestId("input-alcohol_content"), {
      target: { value: "45%" },
    });
    fireEvent.click(screen.getByTestId("button-continue-to-upload"));
    expect(onContinue).toHaveBeenCalled();
  });

  it("loads the stub sample and enables Continue", () => {
    render(<Harness />);
    fireEvent.click(screen.getByTestId("tab-sample"));
    const cont = screen.getByTestId("button-continue-to-upload") as HTMLButtonElement;
    expect(cont.disabled).toBe(false);
    const brand = screen.getByTestId("input-brand_name") as HTMLInputElement;
    expect(brand.value).toBe("Old Tom Distillery");
  });

  it("toggles the standard TTB warning text via the toggle", () => {
    render(<Harness />);
    const toggle = screen.getByTestId("toggle-default-warning") as HTMLInputElement;
    const warning = screen.getByTestId("input-warning") as HTMLTextAreaElement;
    expect(warning.value).toBe("");

    fireEvent.click(toggle);
    expect(warning.value).toContain("GOVERNMENT WARNING");

    fireEvent.click(toggle);
    expect(warning.value).toBe("");
  });

  it("expectedFieldsAreReady mirrors the disabled-state logic", () => {
    expect(expectedFieldsAreReady(EMPTY)).toBe(false);
    expect(
      expectedFieldsAreReady({ ...EMPTY, brand_name: "x" }),
    ).toBe(false);
    expect(
      expectedFieldsAreReady({
        ...EMPTY,
        brand_name: "x",
        alcohol_content: "y",
      }),
    ).toBe(true);
  });
});
