import { InteractionRequiredAuthError, PublicClientApplication } from "@azure/msal-browser";
import { MsalProvider, useMsal } from "@azure/msal-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import type { AdminIdentity, AdminRole } from "../../types";

const entraEnabled = import.meta.env.VITE_ENTRA_AUTH_ENABLED === "true";
const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID ?? "";
const clientId = import.meta.env.VITE_ENTRA_SPA_CLIENT_ID ?? "";
const apiScope = import.meta.env.VITE_ENTRA_API_SCOPE ?? "";
const redirectUri = import.meta.env.VITE_ENTRA_REDIRECT_URI || window.location.origin;
const adminRoleValue = import.meta.env.VITE_ENTRA_PLATFORM_ADMIN_ROLE || "Platform.Admin";
const userRoleValue = import.meta.env.VITE_ENTRA_PLATFORM_USER_ROLE || "Platform.User";

function requiredConfiguration(): string[] {
  return [
    ["VITE_ENTRA_TENANT_ID", tenantId],
    ["VITE_ENTRA_SPA_CLIENT_ID", clientId],
    ["VITE_ENTRA_API_SCOPE", apiScope],
  ].filter(([, value]) => !value).map(([name]) => name);
}

const msal = entraEnabled && requiredConfiguration().length === 0
  ? new PublicClientApplication({
      auth: {
        clientId,
        authority: `https://login.microsoftonline.com/${tenantId}`,
        redirectUri,
        postLogoutRedirectUri: redirectUri,
      },
      cache: { cacheLocation: "sessionStorage" },
    })
  : null;

function accessTokenClaims(token: string): Record<string, unknown> {
  const encoded = token.split(".")[1];
  if (!encoded) return {};
  try {
    const normalized = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(atob(padded)) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function EntraSession({ children }: { children: (identity: AdminIdentity) => ReactNode }) {
  const { instance, accounts } = useMsal();
  const [identity, setIdentity] = useState<AdminIdentity | null>(null);
  const [error, setError] = useState("");
  const account = accounts[0];

  useEffect(() => {
    if (!account) {
      void instance.loginRedirect({ scopes: [apiScope] });
      return;
    }
    void instance.acquireTokenSilent({ account, scopes: [apiScope] })
      .then((result) => {
        const claims = accessTokenClaims(result.accessToken);
        const tokenRoles = Array.isArray(claims.roles) ? claims.roles.map(String) : [];
        const roles: AdminRole[] = [];
        if (tokenRoles.includes(adminRoleValue)) roles.push("PLATFORM_ADMIN");
        if (tokenRoles.includes(userRoleValue)) roles.push("PLATFORM_USER");
        if (!roles.length) throw new Error("Your account has no supported GEAP platform role.");
        setIdentity({
          user: account.username || String(claims.preferred_username || claims.oid || "Entra user"),
          roles,
          domains: [],
          accessToken: result.accessToken,
        });
      })
      .catch((caught: unknown) => {
        if (caught instanceof InteractionRequiredAuthError) {
          void instance.acquireTokenRedirect({ account, scopes: [apiScope] });
          return;
        }
        setError(caught instanceof Error ? caught.message : "Microsoft Entra sign-in failed");
      });
  }, [account, instance]);

  if (error) return <main className="auth-state"><h1>Access unavailable</h1><p>{error}</p><button type="button" onClick={() => void instance.loginRedirect({ scopes: [apiScope] })}>Try again</button></main>;
  if (!identity) return <main className="auth-state"><h1>Signing you in…</h1><p>Connecting to Microsoft Entra ID.</p></main>;
  return <><button className="entra-signout" type="button" onClick={() => void instance.logoutRedirect({ account })}>Sign out</button>{children(identity)}</>;
}

export function AuthenticationBoundary({ children }: { children: (identity?: AdminIdentity) => ReactNode }) {
  const missing = useMemo(requiredConfiguration, []);
  if (!entraEnabled) return <>{children(undefined)}</>;
  if (!msal || missing.length) return <main className="auth-state"><h1>Entra configuration required</h1><p>Set: {missing.join(", ")}</p></main>;
  return <MsalProvider instance={msal}><EntraSession>{children}</EntraSession></MsalProvider>;
}
