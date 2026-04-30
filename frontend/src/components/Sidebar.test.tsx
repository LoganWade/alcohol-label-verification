import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Breadcrumbs } from "./Breadcrumbs";

function renderSidebarAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar />
      <Routes>
        <Route path="*" element={<div>page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderBreadcrumbsAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Breadcrumbs />
      <Routes>
        <Route path="*" element={<div>page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("<Sidebar>", () => {
  it("renders all four primary nav links", () => {
    renderSidebarAt("/");
    expect(screen.getByRole("link", { name: /^Home$/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^New review$/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^New batch$/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Analyst queue$/ })).toBeInTheDocument();
  });

  it("highlights the current section via aria-current", () => {
    renderSidebarAt("/queue");
    const queueLink = screen.getByRole("link", { name: /Analyst queue/ });
    expect(queueLink.getAttribute("aria-current")).toBe("page");
    // Home should not be the active page when we're at /queue.
    const homeLink = screen.getByRole("link", { name: /^Home$/ });
    expect(homeLink.getAttribute("aria-current")).not.toBe("page");
  });

  it("uses end-matching for Home so it isn't active on every nested route", () => {
    renderSidebarAt("/review/new");
    const homeLink = screen.getByRole("link", { name: /^Home$/ });
    expect(homeLink.getAttribute("aria-current")).not.toBe("page");
    const reviewLink = screen.getByRole("link", { name: /New review/ });
    expect(reviewLink.getAttribute("aria-current")).toBe("page");
  });
});

describe("<Breadcrumbs>", () => {
  it("renders nothing on the home page", () => {
    renderBreadcrumbsAt("/");
    expect(screen.queryByTestId("breadcrumbs")).toBeNull();
  });

  it("renders a Home → Reviews → New trail on /review/new", () => {
    renderBreadcrumbsAt("/review/new");
    const crumbs = screen.getByTestId("breadcrumbs");
    expect(crumbs).toBeInTheDocument();
    expect(crumbs.textContent).toContain("Home");
    expect(crumbs.textContent).toContain("Reviews");
    expect(crumbs.textContent).toContain("New");
  });

  it("collapses uuid segments to a generic 'Detail' crumb", () => {
    renderBreadcrumbsAt("/queue/applications/123e4567-e89b-12d3-a456-426614174000");
    const crumbs = screen.getByTestId("breadcrumbs");
    expect(crumbs.textContent).toContain("Queue");
    expect(crumbs.textContent).toContain("Application");
    expect(crumbs.textContent).toContain("Detail");
    expect(crumbs.textContent).not.toContain("123e4567");
  });

  it("marks the last crumb as the current page", () => {
    renderBreadcrumbsAt("/queue");
    const current = screen.getByText("Queue");
    expect(current.getAttribute("aria-current")).toBe("page");
  });
});
