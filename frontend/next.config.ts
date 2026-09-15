import type { NextConfig } from "next";
import path from "node:path";

/**
 * Where the FastAPI backend lives. Overridable for prod deployments:
 * NEXT_PUBLIC_API_ORIGIN=https://api.example.com next start
 */
const API_ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://127.0.0.1:8000";

/**
 * Proxy every API path to the FastAPI backend so the frontend can keep using
 * relative fetches (no CORS, no API base URL scattered through client code).
 *
 * `async` + await-free body is fine — Next accepts either; we keep it async so
 * reading env vars later (e.g. from a loader) stays trivial.
 */
const nextConfig: NextConfig = {
  async rewrites() {
    // /chat, /conversations/x, /stats/summary, /improve, /sessions, /health, /docs …
    return [
      {
        source: "/:path(chat|conversations|stats|improve|sessions|prompts|health|docs|openapi.json)/:rest*",
        destination: `${API_ORIGIN}/:path/:rest*`,
      },
    ];
  },
  webpack: (config) => {
    // Resolve against THIS file's directory, not the process CWD — CI (Vercel)
    // and local dev may run the build from different working directories.
    // @splinetool/react-spline ships ESM-only ("import" condition) and webpack
    // fails to match it from a CJS-flavored project. Alias the subpath straight
    // to its file to bypass the exports map.
    config.resolve.alias["@splinetool/react-spline/next"] = path.resolve(
      __dirname,
      "node_modules/@splinetool/react-spline/dist/react-spline-next.js",
    );
    // @splinetool/runtime references boolean_wasm_bg.wasm via new URL(...) but
    // ships the file as boolean.wasm — map the name so the build resolves it.
    config.resolve.alias["boolean_wasm_bg.wasm"] = path.resolve(
      __dirname,
      "node_modules/@splinetool/runtime/build/boolean.wasm",
    );
    return config;
  },
};

export default nextConfig;
