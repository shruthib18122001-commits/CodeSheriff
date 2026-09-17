import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

// Chrome/Safari can restore a protected page from the back-forward cache
// (e.g. pressing Back after signing out) without re-running React's mount
// logic, so the `Protected` route guard in App.tsx never re-checks the
// token. Forcing a reload on a bfcache restore makes it re-run fresh.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    window.location.reload();
  }
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
