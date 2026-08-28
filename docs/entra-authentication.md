# Microsoft Entra Authentication Setup

## Target model

The Admin Console and Control Plane Admin API use Microsoft Entra ID for interactive users. Agent
runtime authentication remains separately configurable through the existing workload identity path.

Use two single-tenant app registrations:

| Registration | Purpose | Secret required |
|---|---|---|
| `geap-admin-console-spa` | Browser sign-in and delegated token acquisition | No |
| `geap-control-plane-api` | API audience, delegated scope, and platform app roles | No for user-delegated calls |

The UI uses token roles only to enable or hide controls. The API independently validates the token
and enforces authorization; UI behavior is never the security boundary.

## 1. Create security groups

Create two security groups. Use your naming convention; these examples are placeholders:

- `GEAP-Platform-Admins`
- `GEAP-Platform-Users`

Prefer direct membership. Nested group membership is not expanded for enterprise application
assignment. Group-based application assignment requires suitable Entra licensing; direct user
assignments can be used in a development tenant.

## 2. Register the Control Plane API

In **Microsoft Entra admin center → Identity → Applications → App registrations**:

1. Create `geap-control-plane-api` as **Accounts in this organizational directory only**.
2. Record its **Application (client) ID** and the **Directory (tenant) ID**.
3. In the manifest, set `api.requestedAccessTokenVersion` to `2` so the API receives the
   tenant-specific v2 issuer validated by the implementation.
4. Under **Expose an API**, use `api://<API_APPLICATION_CLIENT_ID>` as the Application ID URI.
5. Add administrator-consented delegated scope `access_as_user` with display name
   `Access GEAP Control Plane as the signed-in user`.
6. Under **App roles**, create these enabled roles with **Users/Groups** allowed member type:

| Display name | Value in token | Purpose |
|---|---|---|
| Platform Administrator | `Platform.Admin` | Global platform administration |
| Platform User | `Platform.User` | Read-only access plus persisted organization/project membership |

Use generated immutable GUIDs for the app-role IDs. In **Enterprise applications →
geap-control-plane-api → Properties**, set **Assignment required?** to **Yes**, then assign:

- `GEAP-Platform-Admins` → `Platform Administrator`
- `GEAP-Platform-Users` → `Platform User`

Do not configure group claims. App roles provide a smaller, application-specific `roles` claim and
avoid group-overage handling.

## 3. Register the Admin Console SPA

1. Create single-tenant app `geap-admin-console-spa`.
2. Under **Authentication → Add a platform → Single-page application**, add:
   - development: `http://localhost:3000`
   - deployed: `https://<ADMIN_CONSOLE_HOST>`
3. Do not create a client secret; a browser SPA cannot safely hold one.
4. Under **API permissions → My APIs**, select `geap-control-plane-api`, add delegated permission
   `access_as_user`, and grant tenant admin consent.
5. In its Enterprise Application, set **Assignment required?** to **Yes** and assign both GEAP groups.

The API registration remains the source of the `Platform.Admin` and `Platform.User` roles. Redirect
URIs are exact matches and must use HTTPS outside localhost.

## 4. Configure local development

Authentication is disabled by default. Local persona headers work only while Entra is disabled:

```dotenv
AUTH_ENABLED=false
ENTRA_AUTH_ENABLED=false
VITE_ENTRA_AUTH_ENABLED=false
VITE_LOCAL_ADMIN_USER=platform-admin@example.com
VITE_LOCAL_ADMIN_ROLE=PLATFORM_ADMIN
VITE_LOCAL_ADMIN_DOMAINS=grocery,customer
```

The former on-screen user/role/domain switcher has been removed. When Entra is disabled, change the
development identity through these environment values and restart or rebuild the UI.

Enable Entra for the Admin Console and Admin API while leaving reference-agent authentication local:

```dotenv
AUTH_ENABLED=false
ENTRA_AUTH_ENABLED=true
VITE_ENTRA_AUTH_ENABLED=true

ENTRA_TENANT_ID=<DIRECTORY_TENANT_ID>
ENTRA_API_AUDIENCE=<API_APPLICATION_CLIENT_ID>
ENTRA_REQUIRED_SCOPE=access_as_user
ENTRA_PLATFORM_ADMIN_ROLE=Platform.Admin
ENTRA_PLATFORM_USER_ROLE=Platform.User

VITE_ENTRA_TENANT_ID=<DIRECTORY_TENANT_ID>
VITE_ENTRA_SPA_CLIENT_ID=<SPA_APPLICATION_CLIENT_ID>
VITE_ENTRA_API_SCOPE=api://<API_APPLICATION_CLIENT_ID>/access_as_user
VITE_ENTRA_REDIRECT_URI=http://localhost:3000
VITE_ENTRA_PLATFORM_ADMIN_ROLE=Platform.Admin
VITE_ENTRA_PLATFORM_USER_ROLE=Platform.User
```

Rebuild after changing a `VITE_` value because Vite embeds it in the browser bundle:

```bash
docker compose up --build
```

Set both Entra flags to `false` and rebuild to return to local personas. Never deploy with Entra
disabled unless another reviewed identity-aware proxy protects both routes.

## 5. Validation performed by the API

Every admin request validates Bearer presence, RS256 signature from tenant signing keys, tenant v2
issuer, API audience, lifetime claims, exact tenant ID, delegated `access_as_user` scope, and at
least one supported `roles` claim. Entra object ID is the immutable subject; preferred username is
the display principal. `Platform.Admin` maps to `PLATFORM_ADMIN`; `Platform.User` maps to
`PLATFORM_USER`.

## 6. Deployment placeholders

API environment:

```text
ENTRA_AUTH_ENABLED=true
ENTRA_TENANT_ID=<TENANT_GUID>
ENTRA_API_AUDIENCE=<API_CLIENT_GUID>
ENTRA_REQUIRED_SCOPE=access_as_user
ENTRA_PLATFORM_ADMIN_ROLE=Platform.Admin
ENTRA_PLATFORM_USER_ROLE=Platform.User
```

Supply `VITE_ENTRA_*` values as Admin Console image build arguments. These identifiers are public,
not secrets. The API needs outbound HTTPS access to the tenant signing-key endpoint under
`login.microsoftonline.com`.

The current GCP Terraform path also enables Google Cloud IAP on the external load balancer. IAP and
application-level Entra are separate interactive identity gates; leaving both enabled requires users
to satisfy both providers and is normally undesirable. Before deploying the Entra path, choose and
review one edge pattern:

- expose the Entra-protected services through a load balancer without Google IAP, while retaining
  Cloud Run ingress restrictions and API-side Entra validation; or
- retain IAP as the enterprise edge identity provider and leave `ENTRA_AUTH_ENABLED=false`.

Do not simply make Cloud Run publicly invokable to bypass IAP. The Terraform edge change, Cloud Run
invoker policy, ingress policy, and load-balancer access controls must be reviewed together.

## 7. Validation checklist

1. An unassigned account cannot sign in.
2. Platform User can read but global create/edit/approval controls are disabled.
3. Platform Administrator can perform global administration.
4. Removing an assignment removes its role after existing tokens expire or refresh.
5. Another tenant/audience or a token without `access_as_user` receives HTTP 401.
6. A valid token without either supported role receives HTTP 401.
7. `X-Admin-Roles` cannot elevate a request while Entra is enabled.
8. Apply enterprise Conditional Access, MFA, sign-in logging, access reviews, and emergency access
   policies.

## Role behavior

| Capability | Platform Admin | Platform User |
|---|---:|---:|
| View platform resources | Yes | Yes |
| Global create/edit/approve | Yes | No |
| Manage assigned organization/project resources | Yes | Subject to persisted membership role |
| Configure platform-wide settings | Yes | No |

## Microsoft references

- [Add app roles and receive them in tokens](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps)
- [Assign users or groups to an enterprise application](https://learn.microsoft.com/en-us/azure/active-directory/manage-apps/assign-user-or-group-access-portal)
- [Configure group claims and app roles](https://learn.microsoft.com/en-us/security/zero-trust/develop/configure-tokens-group-claims-app-roles)
- [Access token claims reference](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference)
