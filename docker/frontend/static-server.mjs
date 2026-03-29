/**
 * Minimal static file server replacing nginx for the aiui frontend.
 * Files live at /app/static/; browser paths use the /static/ prefix.
 * Proxies /llm/* to the LLM server (http://qwen3vl-rocm:8000 by default).
 * Reads PORT env (default 8080).
 */
import { createServer } from "node:http";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { readFile } from "node:fs/promises";
import { extname, join, resolve } from "node:path";

const PORT = parseInt(process.env.PORT || "8080", 10);
const ROOT = resolve("/app/static");
const LLM_BACKEND = process.env.LLM_BACKEND_URL || "http://qwen3vl-rocm:8000";

console.log(`[aiui] using LLM backend: ${LLM_BACKEND}`);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".ico": "image/x-icon",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
};

// These are dynamic/generated — must never be cached.
const NO_CACHE = new Set([
  "/static/runtime-config.js",
  "/static/index.html",
  "/static/app.js",
  "/static/styles.css",
  "/index.html",
  "/",
]);

// Security headers applied to all responses (immutable, defined once).
const SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "SAMEORIGIN",
  "X-XSS-Protection": "1; mode=block",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
};

const server = createServer(async (req, res) => {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
  } catch {
    res.writeHead(400, { "Content-Type": "text/plain" });
    res.end("Bad Request");
    return;
  }

  // Proxy /llm/* requests to the LLM backend
  if (pathname.startsWith("/llm/")) {
    const backendPath = pathname.slice("/llm".length); // Strip /llm prefix
    const queryString = req.url.includes("?") ? "?" + req.url.split("?")[1] : "";
    const fullBackendUrl = `${LLM_BACKEND}${backendPath}${queryString}`;
    const backendUrl = new URL(fullBackendUrl);
    
    const requestor = backendUrl.protocol === "https:" ? httpsRequest : httpRequest;
    
    const proxyReq = requestor({
      hostname: backendUrl.hostname,
      port: backendUrl.port,
      path: backendUrl.pathname + (backendUrl.search || ""),
      method: req.method,
      headers: {
        ...req.headers,
        host: backendUrl.host,
      },
    }, (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 200, {
        ...Object.fromEntries(
          Object.entries(proxyRes.headers).filter(([k]) => 
            !["connection", "transfer-encoding"].includes(k.toLowerCase())
          )
        ),
        ...SECURITY_HEADERS,
      });
      proxyRes.pipe(res);
    });

    proxyReq.on("error", (err) => {
      console.error("[proxy] failed to reach", fullBackendUrl, ":", err.message);
      res.writeHead(502, { "Content-Type": "text/plain", ...SECURITY_HEADERS });
      res.end(`Bad Gateway: Failed to reach LLM server: ${err.message}`);
    });

    req.on("error", (err) => {
      console.error("[proxy] client error:", err.message);
      proxyReq.destroy();
    });

    req.pipe(proxyReq);
    return;
  }

  // Map /  → /static/index.html
  // Map /static/xyz → xyz within ROOT
  // All other paths → index.html (SPA fallback)
  let relPath;
  if (pathname === "/" || pathname === "") {
    relPath = "index.html";
  } else if (pathname.startsWith("/static/")) {
    relPath = pathname.slice("/static/".length);
  } else {
    relPath = "index.html";
  }

  // Normalise and guard against path traversal
  const filePath = resolve(join(ROOT, relPath));
  if (!filePath.startsWith(ROOT + "/") && filePath !== ROOT) {
    res.writeHead(403, {
      "Content-Type": "text/plain",
      ...SECURITY_HEADERS,
    });
    res.end("Forbidden");
    return;
  }

  try {
    const data = await readFile(filePath);
    const mime = MIME[extname(filePath)] || "application/octet-stream";
    const noCache = NO_CACHE.has(pathname);
    res.writeHead(200, {
      "Content-Type": mime,
      "Cache-Control": noCache ? "no-store" : "public, max-age=3600",
      ...SECURITY_HEADERS,
    });
    res.end(data);
  } catch {
    res.writeHead(404, {
      "Content-Type": "text/plain",
      ...SECURITY_HEADERS,
    });
    res.end("Not Found");
  }
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`aiui static server on :${PORT}  root=${ROOT}`);
});
