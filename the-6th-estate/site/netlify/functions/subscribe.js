// The 6th Estate — Netlify Function backing POST /api/subscribe in production.
// Reuses the SHARED subscribe logic (../../lib/subscribe.js) that also powers the
// local dev server, so validation / honeypot / consent / success / error behavior
// can never drift between environments.
//
// Adds a consenting contact to the production "Daily Readers" Brevo list (11) with
// updateEnabled:true — never sends unlinkListIds (so no contact is ever removed
// from another list) and never references the test list (#12).
//
// Configuration (set in the Netlify UI, never committed):
//   BREVO_API_KEY   -> Brevo v3 API key, sent as the "api-key" header. REQUIRED in production.
//   BREVO_LIST_ID   -> optional override of the target list id (defaults to 11).
//   BREVO_API_BASE  -> optional override of the Brevo base URL (used by tests only;
//                      defaults to https://api.brevo.com).
const { subscribe } = require("../../lib/subscribe");

exports.handler = async (event) => {
  if (event.httpMethod && event.httpMethod !== "POST") {
    return { statusCode: 405, headers: { allow: "POST" }, body: "" };
  }

  let input;
  try {
    input = JSON.parse(event.body || "{}");
  } catch (e) {
    return {
      statusCode: 500,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ok: false, error: "Something went wrong — please try again." }),
    };
  }

  const result = await subscribe(input, {
    token: process.env.BREVO_API_KEY,
    base: process.env.BREVO_API_BASE || "https://api.brevo.com",
    listId: Number(process.env.BREVO_LIST_ID) || 11,
  });

  return {
    statusCode: result.status,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(result.body),
  };
};
