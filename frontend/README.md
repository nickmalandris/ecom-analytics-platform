# Frontend (Vite + React)

This directory contains the dashboard UI, connectors wizard, and analytics assistant chat client.

## Development

```bash
cd frontend
npm install
cp .env.example .env
# Optionally set VITE_BACKEND_HOST to a remote backend; leave blank to use the proxy
npm run dev
```

Vite proxies API/auth requests to `http://localhost:8000` when `VITE_BACKEND_HOST` is empty (see `vite.config.ts`).

## Production build

```bash
cd frontend
npm install
VITE_BACKEND_HOST="https://backend.example.com" npm run build
```

The resulting static files in `dist/` are copied into the nginx container defined in `Dockerfile.frontend`. Set `VITE_BACKEND_HOST` to the public FastAPI URL (no trailing slash) so that the generated bundle calls the correct origin instead of the frontend domain.

## Environment variables

| Variable | Description |
|----------|-------------|
| `VITE_BACKEND_HOST` | Base URL for API calls. Leave blank locally to use Vite's proxy to `http://localhost:8000`. For deployments, set to your backend host, e.g. `https://api.yourapp.com`. |

## Linting & formatting

```bash
npm run lint
```

## Testing the production bundle locally

```bash
npm run build
npm run preview
```

`npm run preview` respects the same `VITE_BACKEND_HOST` value, so it's a good way to verify cross-origin calls before shipping.
