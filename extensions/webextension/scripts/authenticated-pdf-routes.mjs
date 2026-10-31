// Deterministic local-only authentication fixture for browser PDF smoke tests.
// The session value is generated in memory for each run, never read from a
// user profile, environment variable, secret store or real website.
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";

const COOKIE_NAME = "pdfmagic_test_session";
const PDF_ROUTE = "/auth/private.pdf";
const LOGIN_ROUTE = "/auth/sign-in";
const FAILURE_TEXT = "Authentication required";

export function createAuthenticatedPdfRoutes(pdf) {
  assert.ok(Buffer.isBuffer(pdf) && pdf.subarray(0, 5).toString() === "%PDF-",
    "The local fixture requires a generated PDF");
  const token = randomBytes(24).toString("hex");
  const exactCookie = COOKIE_NAME + "=" + token;
  let denied = 0;
  let granted = 0;
  let signedIn = 0;

  function respond(response, code, type, body, other = {}) {
    response.writeHead(code, {
      "Content-Type": type,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...other
    });
    response.end(body);
  }

  function handle(request, response) {
    const path = request.url;
    if (typeof path !== "string" || !path.startsWith("/auth/")) return false;
    if (request.method !== "GET") {
      respond(response, 405, "text/plain; charset=utf-8", "Method not allowed",
        { "Allow": "GET" });
      return true;
    }
    if (path === LOGIN_ROUTE) {
      signedIn++;
      respond(response, 200, "text/html; charset=utf-8",
        "<!doctype html><title>Local sign-in</title><p>Signed in</p>", {
          "Set-Cookie": exactCookie + "; HttpOnly; SameSite=Lax; Path=/auth"
        });
      return true;
    }
    if (path === PDF_ROUTE) {
      const cookies = request.headers.cookie?.split(";").map(x => x.trim()) ?? [];
      if (!cookies.includes(exactCookie)) {
        denied++;
        respond(response, 401, "text/plain; charset=utf-8", FAILURE_TEXT);
        return true;
      }
      granted++;
      respond(response, 200, "application/pdf", pdf, {
        "Content-Disposition": "inline", "Content-Length": pdf.length
      });
      return true;
    }
    respond(response, 404, "text/plain; charset=utf-8", "Not found");
    return true;
  }

  return Object.freeze({
    handle,
    snapshot: () => Object.freeze({ denied, granted, signedIn }),
    pdfRoute: PDF_ROUTE,
    loginRoute: LOGIN_ROUTE
  });
}
