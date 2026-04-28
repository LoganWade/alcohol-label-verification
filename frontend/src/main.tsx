import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "@/app/App";
import "@/styles/index.css";

// Dev-only axe-core runtime accessibility checks. Logs violations to console
// per AGENTS.md "Run axe-core on each route in dev mode" rule.
if (import.meta.env.DEV) {
  void (async () => {
    const React = await import("react");
    const ReactDOM = await import("react-dom");
    const axe = (await import("@axe-core/react")).default;
    axe(React, ReactDOM, 1000);
  })();
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("#root element not found");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
