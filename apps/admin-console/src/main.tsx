import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { AuthenticationBoundary } from "./features/auth/auth";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthenticationBoundary>
      {(identity) => <App authenticatedIdentity={identity} />}
    </AuthenticationBoundary>
  </React.StrictMode>,
);
