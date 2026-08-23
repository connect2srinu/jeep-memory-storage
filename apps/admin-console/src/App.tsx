import { useEffect, useState } from "react";

const sections = [
  "Dashboard",
  "Domains",
  "Schemas",
  "Preference Catalog",
  "Agents",
  "Access Requests",
  "Approvals",
  "Resolution Policies",
  "Dynamic Memory Policies",
  "Audit",
];

export default function App() {
  const [status, setStatus] = useState("checking");

  useEffect(() => {
    const baseUrl = import.meta.env.VITE_MEMORY_API_URL ?? "/memory-api";
    fetch(`${baseUrl}/healthz`)
      .then((response) => {
        if (!response.ok) throw new Error("unavailable");
        return response.json();
      })
      .then(() => setStatus("connected"))
      .catch(() => setStatus("unavailable"));
  }, []);

  return (
    <main>
      <header>
        <p className="eyebrow">Gemini Enterprise Agent Platform</p>
        <h1>Memory Admin Console</h1>
        <p>Control-plane shell for governed domains, schemas, agents, access, and policies.</p>
        <span className={`status ${status}`}>Memory API: {status}</span>
      </header>
      <section className="grid" aria-label="Administration areas">
        {sections.map((section) => (
          <article key={section}>
            <h2>{section}</h2>
            <p>Configuration will be managed through the Shared Memory Admin API.</p>
          </article>
        ))}
      </section>
    </main>
  );
}
