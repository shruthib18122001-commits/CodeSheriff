import type { JSX } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing";
import Callback from "./pages/Callback";
import Dashboard from "./pages/Dashboard";
import RepoChat from "./pages/RepoChat";
import RepoArchitecture from "./pages/RepoArchitecture";
import RepoCommunity from "./pages/RepoCommunity";
import { isLoggedIn } from "./lib/auth";

function Protected({ children }: { children: JSX.Element }) {
  return isLoggedIn() ? children : <Navigate to="/" replace />;
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/callback" element={<Callback />} />
      <Route
        path="/dashboard"
        element={
          <Protected>
            <Dashboard />
          </Protected>
        }
      />
      <Route
        path="/repo/:repoId/chat"
        element={
          <Protected>
            <RepoChat />
          </Protected>
        }
      />
      <Route
        path="/repo/:repoId/architecture"
        element={
          <Protected>
            <RepoArchitecture />
          </Protected>
        }
      />
      <Route
        path="/repo/:repoId/community"
        element={
          <Protected>
            <RepoCommunity />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
