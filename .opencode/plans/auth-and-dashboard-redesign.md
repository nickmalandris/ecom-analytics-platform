# Plan: Social Auth + Dashboard Redesign

## Epic A: Google + Facebook Social Login

### Context
- Currently using **fastapi-users v15.0.4** with `CookieTransport` (JWT in `analytics_auth` cookie).
- fastapi-users has built-in OAuth via `httpx-oauth`. We already have `httpx` installed.
- Login is email/password via `POST /auth/jwt/login` (form-urlencoded).
- We need Google and Facebook/Meta OAuth providers.
- **Auto-link by email:** If a social login email matches an existing account, link them (no duplicates).

### A1: Backend — OAuth Database Model

**New file:** `src/auth/oauth.py`

- Install `httpx-oauth` (fastapi-users' recommended OAuth companion).
- Create `OAuthAccount` SQLAlchemy model (fastapi-users provides `SQLAlchemyBaseOAuthAccountTable`).
  - Fields: `id`, `user_id` (FK to users), `oauth_name` (e.g. "google"), `access_token`, `expires_at`, `refresh_token`, `account_id`, `account_email`.
- Update the `User` model in `src/auth/db.py` to include the `oauth_accounts` relationship.
- Generate an Alembic migration for the `oauth_account` table.

### A2: Backend — OAuth Clients + Routes

**Modify:** `src/auth/manager.py`, `src/api/users.py`

- Create `GoogleOAuth2` and `FacebookOAuth2` clients from `httpx-oauth`.
  - Google: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` env vars. Scopes: `openid email profile`.
  - Facebook: Reuse existing `META_APP_ID` / `META_APP_SECRET` from `.env`. Scopes: `email public_profile`.
- Register fastapi-users OAuth routers:
  - `GET /auth/google/authorize` — redirects to Google consent screen.
  - `GET /auth/google/callback` — handles callback, creates/links user, sets cookie.
  - Same for `/auth/facebook/authorize` and `/auth/facebook/callback`.
- **Auto-link logic:** fastapi-users' `on_after_login` hook + custom `UserManager.oauth_callback` override. If an OAuth email matches an existing user, associate the OAuth account with that user instead of creating a new one.
- Redirect URI after successful OAuth: `http://localhost:5173/` (Dashboard).

### A3: Frontend — Login Page Redesign

**Modify:** `frontend/src/pages/Login.tsx`, `frontend/src/pages/Register.tsx`

- Add "Continue with Google" and "Continue with Facebook" buttons above the email/password form.
- Google button: White bg, Google "G" logo SVG, `text-gray-700`. Standard Google branding guidelines.
- Facebook button: Facebook blue (`#1877f2`), white Facebook "f" logo SVG.
- Divider: "or" text between social buttons and email form.
- Both buttons simply redirect to `/auth/google/authorize` or `/auth/facebook/authorize` (full page redirect, not popup).
- Register page also gets social buttons (same flow — OAuth creates account if needed).

### A4: Backend — Environment Variables

Add to `.env`:
```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```
Facebook reuses existing `META_APP_ID` / `META_APP_SECRET`.

### A5: Vite Proxy Update

Add proxy rule for `/auth/google` and `/auth/facebook` (already covered by existing `/auth` prefix proxy rule — no change needed).

---

## Epic B: Dashboard Redesign (Layout + Visual Overhaul)

### Context
- Adopting **shadcn/ui** (Tailwind + Radix primitives, Lucide icons).
- Visual direction: **Modern SaaS with dark sidebar** (think Linear, Vercel, Stripe).
- Scope: Rethink layout of KPIs/targets/insights/charts, not just skin.

### B1: Install shadcn/ui + Dependencies

- Install shadcn/ui CLI and initialize: `npx shadcn-ui@latest init`.
  - This creates `components/ui/` directory with base components.
  - Adds `tailwind.config.ts` CSS variables for theming (background, foreground, primary, secondary, accent, muted, destructive, etc.).
  - Installs `@radix-ui/react-*` primitives, `lucide-react` icons, `class-variance-authority`, `clsx`, `tailwind-merge`.
- Install specific shadcn/ui components we'll use:
  - `card`, `button`, `badge`, `tooltip`, `separator`, `skeleton`, `avatar`, `dropdown-menu`, `tabs`.

### B2: Design System — Theme + Tokens

**Modify:** `tailwind.config.ts`, `frontend/src/index.css`

Define CSS variables for the dark sidebar + light content dual-tone:

- **Sidebar:** Dark charcoal/navy (`#0f172a` slate-900 or `#1e1b4b` indigo-950). White text. Indigo accent for active items.
- **Content area:** `#fafbfc` (very light gray). White cards with subtle shadows.
- **Primary accent:** Indigo-500 (`#6366f1`).
- **Typography:** Install Inter font via Google Fonts (or use `@fontsource/inter`). Set as default sans.
- **Card style:** `rounded-xl`, subtle `shadow-sm` + `ring-1 ring-gray-950/5` (Tailwind v3 subtle border trick).

### B3: Sidebar Redesign

**Rewrite:** `frontend/src/components/Sidebar.tsx`

- Dark background (`bg-slate-900` or `bg-indigo-950`).
- **Logo:** Proper brand mark at top (text "Analytics" in white with a subtle indigo icon, or a geometric logo).
- **Nav items:** Use Lucide icons instead of emoji. White text, rounded hover state with `bg-white/10`. Active item: `bg-white/15` with indigo left border accent or indigo bg.
- **Items:**
  - Dashboard (LayoutDashboard icon)
  - Assistant (MessageSquare icon)
  - Connectors (Plug icon)
- **User section at bottom:** Avatar circle with user initials + email, dropdown with "Sign out".
- **Subtle details:** 1px right border in `white/5`, logo area has bottom separator.

### B4: Layout Redesign

**Rewrite:** `frontend/src/components/Layout.tsx`

- Same flex structure but sidebar gets the dark treatment.
- Content area keeps `bg-gray-50` or moves to `bg-muted` (from shadcn theme).
- Consider adding a thin top bar inside content area for breadcrumbs / page title (optional).

### B5: KPI Cards — Merged with Targets

**Rewrite:** `frontend/src/components/KpiCard.tsx`

This is the key layout rethink. Instead of having separate "KPI Cards" and a "Targets Panel", **merge them**:

Each KPI card shows:
- Metric name + current value (large).
- Period-over-period change % (green/red badge).
- A **mini progress bar** toward the target (if target exists for that metric).
- Target value as small text below the progress bar (e.g., "Target: $87.74").
- Confidence indicator as a subtle dot (green/amber/red).

This eliminates the TargetsPanel as a separate section — the target data is embedded directly into each KPI card.

**Fetch:** Dashboard fetches both `/api/analytics/kpis` and `/api/analytics/targets`, then joins them client-side by metric name.

**Grid:** 2x4 on desktop (8 cards). Each card uses the shadcn `Card` component with consistent styling.

### B6: Dashboard Layout Rethink

**Rewrite:** `frontend/src/pages/Dashboard.tsx`

New vertical ordering:

1. **Page header** — "Dashboard" title + period selector (use shadcn `Tabs` component for periods instead of custom pills).
2. **KPI Cards with targets** — 2x4 grid (B5 above).
3. **Two-column layout:**
   - **Left (2/3 width):** Charts (Revenue + Orders stacked, or tabbed).
   - **Right (1/3 width):** AI Insights panel (slimmer, sidebar-like card).
4. **Full-width section:** Campaign table (if campaigns exist).

This is more space-efficient than the current full-width-everything stack.

### B7: Chart Styling Refresh

**Modify:** `frontend/src/components/MetricChart.tsx`

- Match the new design system (use Inter font for axes/tooltips).
- Slightly darker grid lines to fit the refined aesthetic.
- Consider using shadcn `Tabs` to allow switching between metrics in a single chart area (Revenue / Orders / Ad Spend / ROAS tabs on one chart card) instead of 4 separate charts.

### B8: Login/Register Pages Styling

**Rewrite:** `frontend/src/pages/Login.tsx`, `frontend/src/pages/Register.tsx`

- Split layout: Left side is a dark branded panel (dark bg + logo + tagline). Right side is the form.
- Use shadcn `Button`, `Input`, `Label`, `Separator` components.
- Social login buttons (from Epic A) styled per brand guidelines.
- Cleaner form validation UX.

### B9: Clean Up Dead Code

- Remove `frontend/src/App.tsx` and `frontend/src/App.css` (unused Vite boilerplate).
- Remove emoji usage from Sidebar (replaced by Lucide icons).
- Remove `_EMPTY_KPIS` dict reference if still lingering.

---

## Execution Order

**Phase 1 — Foundation (do first):**
1. B1: Install shadcn/ui + dependencies
2. B2: Design system / theme tokens
3. B9: Clean up dead code

**Phase 2 — Core UI (dark sidebar + layout):**
4. B3: Sidebar redesign
5. B4: Layout redesign

**Phase 3 — Dashboard content:**
6. B5: KPI cards merged with targets
7. B6: Dashboard layout rethink
8. B7: Chart styling refresh

**Phase 4 — Auth:**
9. A1: OAuth database model
10. A2: OAuth clients + routes
11. A4: Env vars
12. A3 + B8: Login/Register pages (social buttons + visual redesign together)

**Phase 5 — Polish:**
13. End-to-end testing
14. Final visual QA

---

## Out of Scope (for now)
- Dark mode toggle (full app dark mode)
- Collapsible sidebar
- Drag-and-drop widget customization
- Email % Revenue / Subscription Retention metrics (no data source)
- Mobile responsive optimization (beyond basic Tailwind responsive)
