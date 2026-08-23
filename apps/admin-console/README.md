# Memory Admin Console

This React application is the control-plane UI. The first migration slice provides a runnable shell
and verifies connectivity to the Shared Memory API. Domain, schema, agent, approval, policy, and
audit workflows are added incrementally with the Admin API.

```bash
cd apps/admin-console
npm install
npm run dev
```

The Console never calls Vertex AI Memory Bank directly.
