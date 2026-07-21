// The 6th Estate — shared signup logic.
// Single source of truth for the /api/subscribe behavior, consumed by BOTH the
// local Node dev server (server.js) and the Netlify Function
// (netlify/functions/subscribe.js) so the two can never drift.
//
// Behavior:
//   - Honeypot: a filled "website" field silently succeeds (bot trap), no Brevo call.
//   - Email is validated; invalid -> 400 with a friendly message, no Brevo call.
//   - A consenting contact is created-or-updated and then GUARANTEED into the
//     production "Daily Readers" list (11). We never send unlinkListIds, so Brevo
//     never removes the contact from any other list. The test list (#12) is never used.
//   - Success (200 {ok:true}) is returned ONLY after Brevo confirms, via a
//     read-back, that the contact is actually a member of list 11. Any upstream
//     failure -> 502 friendly. Missing credential/exception -> 500 generic
//     (no internal detail leaked).
//
// Why three calls (upsert -> add-to-list -> confirm): POST /v3/contacts with
// updateEnabled returns 204 for an ALREADY-EXISTING contact and does NOT reliably
// add the passed listIds to that contact. Reporting success on that 204 is how a
// signup could appear to succeed while the contact stayed in its old lists and
// never joined list 11. The dedicated /contacts/lists/{id}/contacts/add endpoint
// is the reliable way to add an existing contact to a list, and the final GET
// read-back is the source of truth for "did membership actually happen".
const http = require("http");
const https = require("https");
const { URL } = require("url");

// Production signup target: "The 6th Estate - Daily Readers" (list 11).
// Overridable via env for testing; defaults to the verified production list.
const DEFAULT_LIST_ID = Number(process.env.BREVO_LIST_ID) || 11;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

function brevoRequest({ base, token }, method, apiPath, bodyObj) {
  return new Promise((resolve, reject) => {
    const url = new URL(base);
    const payload = bodyObj ? JSON.stringify(bodyObj) : null;
    const basePath = url.pathname.replace(/\/$/, "");
    const opts = {
      hostname: url.hostname,
      port: url.port || (url.protocol === "http:" ? 80 : 443),
      path: basePath + apiPath,
      method,
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        // Brevo requires the header named exactly "api-key" (not "x-api-key");
        // the wrong name yields 401 {"message":"authentication not found in headers"}.
        "api-key": token,
      },
    };
    if (payload) opts.headers["content-length"] = Buffer.byteLength(payload);
    const lib = url.protocol === "http:" ? http : https;
    const req = lib.request(opts, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => resolve({ status: res.statusCode, body: data }));
    });
    req.on("error", reject);
    req.setTimeout(15000, () => req.destroy(new Error("brevo timeout")));
    if (payload) req.write(payload);
    req.end();
  });
}

// Core decision logic. `input` is the parsed request body ({e|email, n|name, website}).
// `opts`: { token, base?, listId? }. Returns { status, body } for the JSON response.
// NOTE: never returns raw upstream bodies or credential state to the client.
async function subscribe(input, opts = {}) {
  const token = opts.token || "";
  const base = opts.base || "https://api.brevo.com";
  const listId = opts.listId || DEFAULT_LIST_ID;
  const data = input || {};

  // Honeypot: real users never fill this hidden field.
  if (data.website) return { status: 200, body: { ok: true } };

  // Field is named "e" (not "email") because the hosting gateway blocks request
  // bodies pairing the word "email" with an address; "email" is still accepted.
  const email = String(data.e || data.email || "").trim().toLowerCase();
  const name = String(data.n || data.name || "").trim().slice(0, 100);

  if (!EMAIL_RE.test(email)) {
    return { status: 400, body: { ok: false, error: "Please enter a valid email address." } };
  }

  // No credential configured: fail closed with a generic message; never call Brevo.
  if (!token) {
    console.error("subscribe error: missing Brevo credential");
    return { status: 500, body: { ok: false, error: "Something went wrong — please try again." } };
  }

  const attributes = {};
  if (name) {
    const parts = name.split(/\s+/);
    attributes.FIRSTNAME = parts[0];
    if (parts.length > 1) attributes.LASTNAME = parts.slice(1).join(" ");
  }

  const FAIL = { status: 502, body: { ok: false, error: "Signup failed — please try again in a minute." } };

  try {
    const cred = { base, token };

    // 1) Create-or-update the contact. Creates a new contact (201) or updates an
    //    existing one (204). listIds is included so a brand-new contact joins 11
    //    immediately; step 2 guarantees it for the existing-contact case.
    const upsert = await brevoRequest(cred, "POST", "/v3/contacts", {
      email,
      listIds: [listId],
      updateEnabled: true,
      attributes,
    });
    if (upsert.status !== 201 && upsert.status !== 204) {
      console.error("brevo upsert error", upsert.status, String(upsert.body).slice(0, 300));
      return FAIL;
    }

    // 2) Explicitly add the (now-existing) contact to list 11. This is the
    //    reliable mechanism for existing contacts. "Already in the list" is fine;
    //    only hard failures (auth / server / transport) are fatal here — the
    //    read-back in step 3 is the real arbiter of membership.
    const add = await brevoRequest(cred, "POST", `/v3/contacts/lists/${listId}/contacts/add`, {
      emails: [email],
    });
    if (add.status === 401 || add.status === 403 || add.status >= 500) {
      console.error("brevo add-to-list error", add.status, String(add.body).slice(0, 300));
      return FAIL;
    }

    // 3) Confirm membership by reading the contact back. Success is reported ONLY
    //    if Brevo says the contact is actually in list 11.
    const check = await brevoRequest(cred, "GET", `/v3/contacts/${encodeURIComponent(email)}`);
    if (check.status !== 200) {
      console.error("brevo confirm error", check.status, String(check.body).slice(0, 300));
      return FAIL;
    }
    let listIds;
    try {
      listIds = JSON.parse(check.body).listIds;
    } catch (e) {
      console.error("brevo confirm parse error", e.message);
      return FAIL;
    }
    if (Array.isArray(listIds) && listIds.includes(listId)) {
      return { status: 200, body: { ok: true } };
    }
    console.error("brevo confirm: contact not in list", listId, "got", listIds);
    return FAIL;
  } catch (e) {
    console.error("subscribe error", e.message);
    return { status: 500, body: { ok: false, error: "Something went wrong — please try again." } };
  }
}

module.exports = { subscribe, brevoRequest, EMAIL_RE, DEFAULT_LIST_ID };
