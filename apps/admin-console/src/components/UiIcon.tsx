import type { ReactNode } from "react";

export type IconName = "home" | "sparkles" | "building" | "domain" | "scope" | "schema" | "catalog" | "agent" | "share" | "approval" | "policy" | "memory" | "audit" | "project" | "users" | "health" | "settings" | "budget" | "observe";

export function UiIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    home: <><path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10M9 20v-6h6v6"/></>,
    sparkles: <><path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2L12 3Z"/><path d="m5 14 .8 2.2L8 17l-2.2.8L5 20l-.8-2.2L2 17l2.2-.8L5 14Zm13-1 .8 2.2L21 16l-2.2.8L18 19l-.8-2.2L15 16l2.2-.8L18 13Z"/></>,
    building: <><path d="M4 21V8l8-4 8 4v13M2 21h20"/><path d="M8 10h2m4 0h2m-8 4h2m4 0h2m-8 4h2m4 0h2"/></>,
    domain: <><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/></>,
    scope: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 3v3m0 12v3m9-9h-3M6 12H3"/></>,
    schema: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/></>,
    catalog: <><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/></>,
    agent: <><rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8"/></>,
    share: <><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 10.5 6.8-4m-6.8 7 6.8 4"/></>,
    approval: <><path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6l-8-3Z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></>,
    policy: <><path d="M4 7h10M4 17h16M10 12h10"/><circle cx="17" cy="7" r="2"/><circle cx="7" cy="12" r="2"/><circle cx="9" cy="17" r="2"/></>,
    memory: <><path d="M8 4a3 3 0 0 0-3 3v1a3 3 0 0 0-1 5 3 3 0 0 0 3 5h1a4 4 0 0 0 8 0h1a3 3 0 0 0 3-5 3 3 0 0 0-1-5V7a3 3 0 0 0-3-3"/><path d="M12 3v18M8 9h4m0 6h4"/></>,
    audit: <><path d="M6 3h9l4 4v14H6zM15 3v5h5"/><path d="M9 13h6M9 17h6"/></>,
    project: <><path d="M3 7h7l2 2h9v11H3z"/><path d="M3 7V5h7l2 2"/></>,
    users: <><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v2"/></>,
    health: <><path d="M3 12h4l2-5 4 10 2-5h6"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2-.7-.7-1.7.9-1.9-2.1-2.1-1.9.9-1.7-.7L10.5 2h-3l-.7 2-1.7.7-1.9-.9-2.1 2.1.9 1.9-.7 1.7-2 .7v3l2 .7.7 1.7-.9 1.9 2.1 2.1 1.9-.9 1.7.7.7 2h3l.7-2 1.7-.7 1.9.9 2.1-2.1-.9-1.9.7-1.7 2-.7Z" transform="translate(1.5 0) scale(.88)"/></>,
    budget: <><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M16 15h2"/></>,
    observe: <><path d="M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6Z"/><circle cx="12" cy="12" r="3"/></>,
  };
  return <svg className="ui-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

