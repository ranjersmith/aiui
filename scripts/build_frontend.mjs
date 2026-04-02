import { build } from "esbuild";
import { cpSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(scriptDir, "..");
const staticDir = resolve(rootDir, "static");

const katexDistDir = resolve(rootDir, "node_modules", "katex", "dist");
const katexVendorDir = resolve(staticDir, "vendor", "katex");
mkdirSync(katexVendorDir, { recursive: true });
cpSync(katexDistDir, katexVendorDir, { recursive: true });

const hlStylesDir = resolve(rootDir, "node_modules", "highlight.js", "styles");
const hlVendorDir = resolve(staticDir, "vendor", "highlight");
mkdirSync(hlVendorDir, { recursive: true });
cpSync(resolve(hlStylesDir, "vs2015.min.css"), resolve(hlVendorDir, "vs2015.min.css"));

await build({
  entryPoints: [resolve(rootDir, "frontend", "app.ts")],
  bundle: true,
  format: "esm",
  target: ["es2020"],
  outfile: resolve(staticDir, "app.js"),
  minify: true,
  sourcemap: true,
  logLevel: "info",
});

console.log("Frontend build complete: static/app.js");
