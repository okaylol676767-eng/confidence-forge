#!/usr/bin/env node
/**
 * Restores files missing from the @splinetool/runtime npm tarball.
 *
 * Spline's published packages (2.0.40 through 2.0.50 at least) ship the
 * webpack chunk runtime-DRACOLoader-*.js, which imports
 * ../libs/draco/{draco_decoder.js,draco_decoder.wasm,draco_wasm_wrapper.js}
 * and ../libs/draco/gltf/* — but the tarball omits the libs/ directory
 * entirely. Any clean `npm ci` (CI, Vercel, a fresh clone) therefore produces
 * a package that cannot build:
 *   Module not found: Can't resolve '../libs/draco/draco_decoder.wasm'
 *
 * We vendor the five files in vendor/spline-runtime/ and copy them back after
 * every install via the "postinstall" hook in package.json. Idempotent,
 * version-tolerant, and fails soft: if Spline fixes the tarball, this is a
 * harmless no-op (or a warning if their paths change).
 */
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontend = dirname(here);
const runtimeRoot = join(frontend, "node_modules", "@splinetool", "runtime");
const vendor = join(frontend, "vendor", "spline-runtime", "draco");

// Spline not installed (e.g. dependency omitted) — nothing to restore.
if (!existsSync(runtimeRoot)) process.exit(0);

const files = [
  ["draco_decoder.js", "draco_decoder.js"],
  ["draco_decoder.wasm", "draco_decoder.wasm"],
  ["draco_wasm_wrapper.js", "draco_wasm_wrapper.js"],
  ["gltf/draco_decoder.wasm", "gltf/draco_decoder.wasm"],
  ["gltf/draco_wasm_wrapper.js", "gltf/draco_wasm_wrapper.js"],
];

let restored = 0;
for (const [fromRel, toRel] of files) {
  const from = join(vendor, fromRel);
  const to = join(runtimeRoot, "libs", "draco", toRel);
  if (!existsSync(from)) continue; // vendored file missing — skip quietly
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(from, to);
  restored += 1;
}
console.log(`[restore-spline-draco] restored ${restored}/5 libs/draco files`);
