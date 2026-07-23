// generate-issue.mjs — briefings + quick-hits, wider Black press coverage
//
// Structure:
//   2-3 briefings = the day's most significant stories: 50-70 word body,
//                    topic kicker, boxed "The takeaway," 2 sources
//   12-15 quick hits = 1 sentence, <=30 words, impact built in, 1 source
//   13-20 total      = hard floor and ceiling on the combined count
//   2 data desks   = Money Moves + Sports (no AI, free feeds)
//   1 closer       = short joy/community story or quote (AI)
//   + This Day in Legacy (standalone, no AI) + The Number (standalone, no AI)
//   + Green Book   = auto-curated real business + real opportunity, each
//     found via web_search and link-checked. Real paid entries in
//     green-book/listings.json override the automated pick.
//
// NEW: 6 Black press RSS feeds (BlackPressUSA, Capital B, AFRO News,
// Houston Defender, Washington Informer, NY Amsterdam News) are polled
// every run and handed to Claude as real, pre-verified, paywall-free
// leads — on top of its own web_search — to help hit the wider story
// count with genuinely free community-press coverage.
//
// Sports (P6) unchanged: HBCU Watch (RSS + live scores, capped at 8),
// Last Night / On Deck Tonight (WNBA/NBA capped at 5, others uncapped/
// summarized).

import { writeFile, readFile, mkdir } from "node:fs/promises";
import path from "node:path";

// ---------- CONFIG ----------
const SITE_NAME = "The Daily Drumbeat";
const SITE_URL = "https://thedailydrumbeat.com";
const MODEL = "claude-haiku-4-5-20251001";
const MIN_STORIES = 13;
const MAX_STORIES = 20; // hard ceiling — never more than this regardless of news volume
const MIN_BRIEFINGS = 2;
const MAX_BRIEFINGS = 3;
const BACKUP_COUNT = 3;

const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;
const FRED_API_KEY = process.env.FRED_API_KEY;
const FINNHUB_API_KEY = process.env.FINNHUB_API_KEY;
const BREVO_API_KEY = process.env.BREVO_API_KEY;
const BREVO_LIST_ID = process.env.BREVO_LIST_ID;
const BREVO_SENDER_EMAIL = process.env.BREVO_SENDER_EMAIL;
const BREVO_SENDER_NAME = process.env.BREVO_SENDER_NAME || SITE_NAME;

const STORY_SECTIONS = [
  { code: "P1", name: "Business & Enterprise", required: false },
  { code: "P2", name: "Policy & Justice", required: true }, // must run every day
  { code: "P3", name: "Economy & Work", required: false },
  { code: "P5", name: "HBCUs & Education", required: false },
  { code: "P8", name: "Tech & Innovation", required: false },
  { code: "P9", name: "Health Equity", required: false },
  { code: "P10", name: "Land & Legacy", required: false },
  { code: "P11", name: "Black Excellence", required: false }
];
// P7 (Culture & Community) is reserved for the Closer, not a regular story.

// Free, non-paywalled Black press RSS feeds - pre-verified leads for curation.
const PRESS_FEEDS = [
  { name: "BlackPressUSA", url: "https://blackpressusa.com/feed/" },
  { name: "Capital B", url: "https://capitalbnews.org/feed/" },
  { name: "AFRO News", url: "https://afro.com/feed/" },
  { name: "Houston Defender", url: "https://defendernetwork.com/feed/" },
  { name: "Washington Informer", url: "https://washingtoninformer.com/feed/" },
  { name: "NY Amsterdam News", url: "https://amsterdamnews.com/feed/" }
];

function todayParts(offsetDays = 0) {
  const now = new Date(Date.now() + offsetDays * 86400000);
  const iso = now.toISOString().slice(0, 10);
  const label = now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" }).toUpperCase();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return { iso, label, mm, dd, dayOfYear: Math.floor((now - new Date(now.getFullYear(), 0, 0)) / 86400000) };
}

async function safeFetchJson(url, opts = {}, label = url) {
  try {
    const res = await fetch(url, { ...opts, signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new Error(`${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`[data] ${label} failed: ${err.message}`);
    return null;
  }
}

// Generic RSS reader - used for both HBCU Gameday and the 6 press feeds.
async function fetchRssHeadlines(url, sourceName, limit = 4) {
  try {
    const res = await fetch(url, {
      signal: AbortSignal.timeout(10000),
      headers: { "User-Agent": "Mozilla/5.0 (compatible; DailyDrumbeatBot/1.0; +https://thedailydrumbeat.com)" }
    });
    if (!res.ok) throw new Error(`${res.status}`);
    const xml = await res.text();
    const items = [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].slice(0, limit);
    return items.map(([, block]) => {
      const titleMatch = block.match(/<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/title>/s);
      const linkMatch = block.match(/<link>(.*?)<\/link>/s);
      return { title: (titleMatch?.[1] || "").trim(), url: (linkMatch?.[1] || "").trim(), source: sourceName };
    }).filter(h => h.title && h.url);
  } catch (err) {
    console.warn(`[data] RSS ${sourceName} failed: ${err.message}`);
    return [];
  }
}

async function fetchPressLeads() {
  const results = await Promise.all(PRESS_FEEDS.map(f => fetchRssHeadlines(f.url, f.name, 4)));
  return results.flat();
}

// =========================================================
// DATA BOXES — no AI cost
// =========================================================
async function fredWithChange(seriesId) {
  if (!FRED_API_KEY) return null;
  const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${seriesId}&api_key=${FRED_API_KEY}&file_type=json&sort_order=desc&limit=2`;
  const data = await safeFetchJson(url, {}, `FRED ${seriesId}`);
  const obs = (data?.observations || []).filter(o => o.value !== ".");
  if (!obs.length) return null;
  const latest = Number(obs[0].value);
  const prev = obs[1] ? Number(obs[1].value) : null;
  const changePct = prev ? ((latest - prev) / prev) * 100 : null;
  return { value: latest, date: obs[0].date, changePct };
}
async function fredLatest(seriesId, extraParams = "") {
  if (!FRED_API_KEY) return null;
  const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${seriesId}&api_key=${FRED_API_KEY}&file_type=json&sort_order=desc&limit=1${extraParams}`;
  const data = await safeFetchJson(url, {}, `FRED ${seriesId}`);
  const obs = data?.observations?.[0];
  return obs && obs.value !== "." ? { value: obs.value, date: obs.date } : null;
}

async function fetchFinnhubQuote(symbol) {
  if (!FINNHUB_API_KEY) return {};
  const data = await safeFetchJson(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${FINNHUB_API_KEY}`, {}, `Finnhub ${symbol}`);
  if (!data || data.c == null) return {};
  return { price: data.c, changePct: data.dp };
}

async function fetchMoneyMoves() {
  const [mortgage, sp500, dow, cpiYoy, unone, rlj, carv, crypto] = await Promise.all([
    fredLatest("MORTGAGE30US"), fredWithChange("SP500"), fredWithChange("DJIA"),
    fredLatest("CPIAUCSL", "&units=pc1"),
    fetchFinnhubQuote("UONE"), fetchFinnhubQuote("RLJ"), fetchFinnhubQuote("CARV"),
    safeFetchJson("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true", {}, "CoinGecko")
  ]);
  const fmtIdx = (v) => v?.value != null ? Number(v.value).toLocaleString(undefined, { maximumFractionDigits: 2 }) : null;
  return {
    mortgage30yr: mortgage?.value ? `${Number(mortgage.value).toFixed(2)}%` : null,
    sp500: fmtIdx(sp500), sp500Change: sp500?.changePct ?? null,
    dow: fmtIdx(dow), dowChange: dow?.changePct ?? null,
    cpiYoy: cpiYoy?.value ? `${Number(cpiYoy.value).toFixed(1)}%` : null,
    btc: crypto?.bitcoin?.usd ? `$${Math.round(crypto.bitcoin.usd).toLocaleString()}` : null,
    btcChange: crypto?.bitcoin?.usd_24h_change ?? null,
    eth: crypto?.ethereum?.usd ? `$${Math.round(crypto.ethereum.usd).toLocaleString()}` : null,
    ethChange: crypto?.ethereum?.usd_24h_change ?? null,
    tickers: [{ symbol: "UONE", ...unone }, { symbol: "RLJ", ...rlj }, { symbol: "CARV", ...carv }].filter(t => t.price != null),
    asOf: new Date().toLocaleString("en-US", { weekday: "long", hour: "numeric", minute: "2-digit", timeZoneName: "short" })
  };
}

// =========================================================
// SPORTS — HBCU Watch (RSS + live scores) + capped major leagues
// =========================================================
const HBCU_SCHOOLS = [
  "Alabama A&M", "Alabama State", "Alcorn State", "Arkansas-Pine Bluff", "Bethune-Cookman",
  "Bowie State", "Coppin State", "Delaware State", "Elizabeth City State", "Fayetteville State",
  "Florida A&M", "Grambling", "Hampton", "Howard", "Jackson State", "Johnson C. Smith",
  "Lincoln (PA)", "Livingstone", "Mississippi Valley State", "Morehouse", "Morgan State",
  "Norfolk State", "North Carolina A&T", "North Carolina Central", "Prairie View A&M",
  "Savannah State", "Shaw", "South Carolina State", "Southern University", "Southern",
  "Tennessee State", "Texas Southern", "Tuskegee", "Virginia State", "Virginia Union",
  "Winston-Salem State"
];
const HBCU_PATHS = [
  "football/college-football",
  "basketball/mens-college-basketball",
  "basketball/womens-college-basketball",
  "baseball/college-baseball"
];
const CAPPED_LEAGUES = [
  { path: "basketball/nba", label: "NBA" },
  { path: "basketball/wnba", label: "WNBA" }
];
const GENERAL_LEAGUES = [
  { path: "football/nfl", label: "NFL" },
  { path: "baseball/mlb", label: "MLB" },
  { path: "hockey/nhl", label: "NHL" },
  { path: "soccer/usa.1", label: "MLS" }
];

async function fetchEspnScoreboard(sportPath, dateIso) {
  const dateParam = dateIso ? `?dates=${dateIso.replace(/-/g, "")}&limit=200` : "?limit=200";
  const data = await safeFetchJson(`https://site.api.espn.com/apis/site/v2/sports/${sportPath}/scoreboard${dateParam}`, {}, `ESPN ${sportPath}`);
  return data?.events || [];
}
function summarizeGame(ev) {
  const comp = ev.competitions?.[0];
  const [a, b] = comp?.competitors || [];
  if (!a || !b) return null;
  const state = ev.status?.type?.state;
  const scoreStr = state === "pre" ? "" : ` ${a.score}-${b.score}`;
  const when = state === "pre" ? ` (${new Date(ev.date).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })} ET)` : state === "in" ? " (live)" : " (final)";
  return `${a.team.shortDisplayName} vs ${b.team.shortDisplayName}${scoreStr}${when}`;
}

async function fetchGeneralLeagueLines(league, todayIso, yestIso) {
  const [yestGames, todayGames] = await Promise.all([
    fetchEspnScoreboard(league.path, yestIso),
    fetchEspnScoreboard(league.path, todayIso)
  ]);
  const lastNight = yestGames.filter(ev => ev.status?.type?.state === "post")
    .map(summarizeGame).filter(Boolean).map(g => `${league.label}: ${g}`); // uncapped

  const scheduled = todayGames.filter(ev => ev.status?.type?.state === "pre");
  const onDeck = scheduled.length > 4
    ? [`${league.label}: full slate, ${scheduled.length} games`]
    : scheduled.map(summarizeGame).filter(Boolean).map(g => `${league.label}: ${g}`);
  return { lastNight, onDeck };
}
async function fetchCappedLeagueLines(league, todayIso, yestIso) {
  const [yestGames, todayGames] = await Promise.all([
    fetchEspnScoreboard(league.path, yestIso),
    fetchEspnScoreboard(league.path, todayIso)
  ]);
  const lastNight = yestGames.filter(ev => ev.status?.type?.state === "post")
    .map(summarizeGame).filter(Boolean).slice(0, 5).map(g => `${league.label}: ${g}`);
  const onDeck = todayGames.filter(ev => ev.status?.type?.state === "pre")
    .map(summarizeGame).filter(Boolean).slice(0, 5).map(g => `${league.label}: ${g}`);
  return { lastNight, onDeck };
}

async function fetchSportsBox() {
  const { iso: todayIso } = todayParts(0);
  const { iso: yestIso } = todayParts(-1);

  const [hbcuToday, hbcuYest, hbcuHeadlines, generalResults, cappedResults] = await Promise.all([
    Promise.all(HBCU_PATHS.map(p => fetchEspnScoreboard(p, todayIso))),
    Promise.all(HBCU_PATHS.map(p => fetchEspnScoreboard(p, yestIso))),
    fetchRssHeadlines("https://hbcugameday.com/feed", "HBCU Gameday", 2),
    Promise.all(GENERAL_LEAGUES.map(l => fetchGeneralLeagueLines(l, todayIso, yestIso))),
    Promise.all(CAPPED_LEAGUES.map(l => fetchCappedLeagueLines(l, todayIso, yestIso)))
  ]);

  const hbcuAll = [...hbcuToday.flat(), ...hbcuYest.flat()].filter(ev => {
    const names = ev.competitions?.[0]?.competitors?.map(c => c.team.displayName).join(" ") || "";
    return HBCU_SCHOOLS.some(school => names.includes(school));
  });
  const hbcuOnDeck = hbcuAll.filter(ev => ev.status?.type?.state === "pre").map(summarizeGame).filter(Boolean).slice(0, 8);
  const hbcuLastNight = hbcuAll.filter(ev => ev.status?.type?.state === "post").map(summarizeGame).filter(Boolean).slice(0, 8);

  return {
    hbcuHeadlines,
    hbcuGames: [...hbcuLastNight, ...hbcuOnDeck],
    lastNight: [...cappedResults.flatMap(r => r.lastNight), ...generalResults.flatMap(r => r.lastNight)],
    onDeck: [...cappedResults.flatMap(r => r.onDeck), ...generalResults.flatMap(r => r.onDeck)]
  };
}

const LEGACY_KEYWORDS = /african|black|slave|civil rights|jim crow|naacp|segregat|harlem renaissance|negro|colored|freedmen|apartheid|jamaica|haiti|caribbean|pan-african|reparations|underground railroad/i;
async function fetchThisDayInLegacy() {
  const { mm, dd } = todayParts(0);
  const data = await safeFetchJson(`https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/${mm}/${dd}`, { headers: { "User-Agent": `${SITE_NAME} (${SITE_URL})` } }, "Wikipedia On This Day");
  if (!data) return null;
  const hit = (data.events || []).find(e => LEGACY_KEYWORDS.test(e.text || "") || (e.pages || []).some(p => LEGACY_KEYWORDS.test(p.extract || p.description || "")));
  if (!hit) return null;
  const link = hit.pages?.[0]?.content_urls?.desktop?.page || "https://en.wikipedia.org/wiki/Portal:Black_history";
  return { year: hit.year, text: hit.text, url: link, sourceName: "Wikipedia · On This Day" };
}
async function fetchTheNumber(dayOfYear) {
  if (dayOfYear % 2 === 0) {
    const m = await fredLatest("MORTGAGE30US");
    return m ? { label: "30-year fixed mortgage, this week", value: `${Number(m.value).toFixed(2)}%`, source: "FRED", sourceUrl: "https://fred.stlouisfed.org/series/MORTGAGE30US" } : null;
  } else {
    const h = await fredLatest("BOAAAHORUSQ156N");
    return h ? { label: "Black homeownership rate", value: `${Number(h.value).toFixed(1)}%`, source: "Census via FRED", sourceUrl: "https://fred.stlouisfed.org/series/BOAAAHORUSQ156N" } : null;
  }
}

async function fetchManualGreenBook() {
  try {
    const raw = await readFile("green-book/listings.json", "utf-8");
    const data = JSON.parse(raw);
    return { business: data.businessOfTheDay?.[0] || null, opportunity: data.opportunities?.[0] || null };
  } catch {
    return { business: null, opportunity: null };
  }
}

// =========================================================
// EVERYTHING BELOW CALLS CLAUDE
// =========================================================
function buildCurationPrompt(pressLeads) {
  const leadsBlock = pressLeads.length
    ? `\nHere are real, freely-accessible headlines pulled just now from Black press RSS feeds - already confirmed real (not invented), no paywalls. Use these as strong leads where relevant; search further into any of them, or use your own web_search for anything else:\n${pressLeads.map(l => `- "${l.title}" — ${l.source} — ${l.url}`).join("\n")}\n`
    : "";

  return `You are the morning content curator for ${SITE_NAME}, a free daily newsletter
covering news that materially affects Black America.

Use the web_search tool. Never invent a URL — only cite URLs that actually appeared in your
own web_search results or in the press leads list below this run.
${leadsBlock}
PART 1 — Curate between ${MIN_STORIES} and ${MAX_STORIES} stories total, made up of two kinds:

BRIEFINGS (${MIN_BRIEFINGS}-${MAX_BRIEFINGS} of them): the day's most significant stories.
Mark each with "isBriefing": true. Each briefing gets:
- a short topic "kicker" label in all caps (e.g. "GOVERNMENT WATCH", "MARKET WATCH")
- a body: 50-70 words, 2-3 sentences
- a "takeaway": one sharp sentence on why this matters, for a boxed callout
- exactly 2 sources

QUICK HITS (fill the rest, roughly 12-15 of them, so the TOTAL lands between ${MIN_STORIES}
and ${MAX_STORIES}): exactly ONE sentence, **30 words or fewer**, with the impact or stakes
built directly into that sentence (not just a fact — say why it matters in the same breath).
Exactly 1 source each, freely accessible, no paywall.

Cover these core beats across your briefings + quick hits (Policy & Justice MUST appear at
least once, even on a slow news day):
${STORY_SECTIONS.map(s => `- ${s.code}: ${s.name}${s.required ? " (required every day)" : ""}`).join("\n")}
A beat can get multiple stories on a big day (e.g. 2-3 Black Excellence items). Never pad
with filler to hit the max, and never cut real coverage just to land under it.

IMPORTANT — every source, for every story, must be freely accessible with no paywall. Do not
cite outlets you know sit behind a hard paywall (e.g. WSJ subscriber-only pieces). If the only
coverage of something is paywalled, either find a freely-accessible outlet covering the same
story or skip that story.

PART 2 — Also write exactly ${BACKUP_COUNT} backup quick hits (any category, 1 source each,
never a briefing, freely accessible) to be used only if a primary story's source fails a
later link-check.

PART 3 — Curate exactly 1 "closer": a short uplifting Culture & Community or Health &
Wellness item, OR a brief attributed quote (under 15 words, from a real Black figure). 1 source
if it's a story, 0 if it's a quote.

PART 4 — Green Book: find ONE real, currently-operating Black-owned business worth
spotlighting, and ONE real, currently-open opportunity (scholarship, grant, fellowship,
program) for Black students/entrepreneurs. Both must come from an actual web_search result
with a real URL. Return null for either if you can't find a genuinely real, verifiable one.

Output ONLY valid JSON, no markdown fences, no commentary, exactly this shape:
{
  "stories": [
    { "section": "P2", "isBriefing": true, "headline": "...", "kicker": "GOVERNMENT WATCH",
      "body": "50-70 words...", "takeaway": "one sharp sentence",
      "sources": [{"name":"...","url":"..."},{"name":"...","url":"..."}] },
    { "section": "P1", "isBriefing": false, "headline": "...", "quickHit": "one sentence, <=30 words, impact built in",
      "sources": [{"name":"...","url":"..."}] }
  ],
  "backups": [
    { "section": "P3", "isBriefing": false, "headline": "...", "quickHit": "...",
      "sources": [{"name":"...","url":"..."}] }
  ],
  "closer": {
    "type": "story" or "quote", "headline": "only if type is story",
    "text": "the blurb (1-2 sentences) or the quote itself",
    "attribution": "only if type is quote", "sources": [{"name":"...","url":"..."}]
  },
  "greenBook": {
    "business": { "name":"...", "tagline":"...", "description":"25-50 words", "url":"...", "sourceName":"..." } or null,
    "opportunity": { "title":"...", "amount":"...", "deadline":"...", "description":"25-50 words", "url":"...", "sourceName":"..." } or null
  }
}

Rules:
- Between ${MIN_STORIES} and ${MAX_STORIES} stories total, ${MIN_BRIEFINGS}-${MAX_BRIEFINGS} with isBriefing true, exactly ${BACKUP_COUNT} backups.
- Briefings: exactly 2 sources. Quick hits and backups: exactly 1 source each.
- Every source is freely accessible — no paywalls, ever.
- All text is original wording, never a close paraphrase of source wording.
- No opinion pieces presented as news, no tabloid gossip, no fabricated businesses or grants.
- Headlines under 12 words. Quick hit sentences: 30 words maximum.`;
}

async function curateContent(pressLeads) {
  const { label } = todayParts(0);
  const prompt = buildCurationPrompt(pressLeads);
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "content-type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01" },
    body: JSON.stringify({
      model: MODEL, max_tokens: 9000, system: prompt,
      messages: [{ role: "user", content: `Today is ${label}. Curate today's ${MIN_STORIES}-${MAX_STORIES} stories (${MIN_BRIEFINGS}-${MAX_BRIEFINGS} briefings + quick hits), ${BACKUP_COUNT} backups, 1 closer, and the Green Book now.` }],
      tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 45 }]
    })
  });
  if (!res.ok) throw new Error(`Anthropic API error ${res.status}: ${await res.text()}`);
  const data = await res.json();
  const textBlocks = data.content.filter(b => b.type === "text").map(b => b.text);
  const raw = textBlocks[textBlocks.length - 1] || "";
  const jsonStart = raw.indexOf("{");
  const jsonEnd = raw.lastIndexOf("}");
  if (jsonStart === -1 || jsonEnd === -1) throw new Error(`No JSON object found in Claude's response: ${raw.slice(0, 300)}`);
  return JSON.parse(raw.slice(jsonStart, jsonEnd + 1));
}

async function urlIsAlive(url) {
  try {
    const res = await fetch(url, {
      method: "GET", redirect: "follow", signal: AbortSignal.timeout(8000),
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36" }
    });
    return res.status < 400;
  } catch { return false; }
}

async function validateStories(stories) {
  const kept = [];
  for (const s of stories || []) {
    const minSources = s.isBriefing ? 2 : 1;
    if (!s.sources || s.sources.length < minSources) continue;
    const checks = await Promise.all(s.sources.map(src => urlIsAlive(src.url)));
    if (checks.every(Boolean)) kept.push(s); else console.warn(`Dropped "${s.headline}" - a source link failed`);
  }
  return kept;
}

function assembleStories(validPrimaries, validBackups) {
  const usedHeadlines = new Set();
  const final = [];

  // Keep all validated briefings (target 2-3, but take whatever survived).
  const briefings = validPrimaries.filter(s => s.isBriefing).slice(0, MAX_BRIEFINGS);
  for (const b of briefings) { final.push(b); usedHeadlines.add(b.headline); }

  // Add remaining valid primaries (quick hits).
  for (const s of validPrimaries) {
    if (usedHeadlines.has(s.headline)) continue;
    final.push(s); usedHeadlines.add(s.headline);
  }

  // Top up from backups only if we're below the minimum - never pad
  // just to reach the max.
  for (const s of validBackups) {
    if (final.length >= MIN_STORIES) break;
    if (usedHeadlines.has(s.headline)) continue;
    final.push(s); usedHeadlines.add(s.headline);
  }

  // If no briefing survived validation at all, promote the strongest
  // remaining story so the edition always has at least one.
  if (!final.some(s => s.isBriefing) && final.length) {
    final[0] = { ...final[0], isBriefing: true, kicker: final[0].kicker || "TODAY'S TOP STORY", body: final[0].body || final[0].quickHit, takeaway: final[0].takeaway || null };
  }

  return final.slice(0, MAX_STORIES); // hard ceiling, regardless of how much validated
}

async function resolveGreenBook(aiGreenBook) {
  const manual = await fetchManualGreenBook();
  let business = manual.business ? { ...manual.business, sponsored: true } : null;
  let opportunity = manual.opportunity ? { ...manual.opportunity, sponsored: true } : null;

  if (!business && aiGreenBook?.business?.url) {
    if (await urlIsAlive(aiGreenBook.business.url)) business = { ...aiGreenBook.business, sponsored: false };
    else console.warn("Dropped AI-picked Green Book business - source link failed");
  }
  if (!opportunity && aiGreenBook?.opportunity?.url) {
    if (await urlIsAlive(aiGreenBook.opportunity.url)) opportunity = { ...aiGreenBook.opportunity, sponsored: false };
    else console.warn("Dropped AI-picked Green Book opportunity - source link failed");
  }
  return { business, opportunity };
}

// =========================================================
// HTML BUILDING
// =========================================================
function sectionLabel(code) { return STORY_SECTIONS.find(s => s.code === code)?.name || code; }

function pageHead(title, ogPath = "") {
  const ogUrl = `${SITE_URL}/${ogPath}`;
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${title} — ${SITE_NAME}</title>
<meta property="og:type" content="website">
<meta property="og:site_name" content="${SITE_NAME}">
<meta property="og:title" content="${SITE_NAME}">
<meta property="og:description" content="News about us. For us. By the beat of the drum. Curated stories, Money Moves, HBCU sports, and the Green Book — every weekday morning.">
<meta property="og:image" content="${SITE_URL}/assets/og-image.png">
<meta property="og:url" content="${ogUrl}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${SITE_NAME}">
<meta name="twitter:description" content="News about us. For us. By the beat of the drum.">
<meta name="twitter:image" content="${SITE_URL}/assets/og-image.png">
<link rel="stylesheet" href="assets/drumbeat.css"></head>
<body>`;
}
function header(active) {
  const items = [["index.html", "Landing"], ["today.html", "Today's Edition"], ["archive.html", "Archive"], ["manifesto.html", "About"], ["advertise.html", "Advertise"]];
  return `<div class="site-header">
    <a href="index.html" class="logo">THE DAILY <span class="D">D</span>RUMBEAT</a>
    <div class="nav">${items.map(([href, label]) => `<a href="${href}"${href === active ? ' class="active"' : ""}>${label}</a>`).join("")}</div>
  </div>`;
}
function footer() {
  return `<div class="site-footer">
    <div class="logo2">THE DAILY <span class="D">D</span>RUMBEAT</div>
    <div class="fine">News about us. For us. By the beat of the drum.<br>
      <a href="corrections.html">Corrections: corrections@thedailydrumbeat.com</a>
      &nbsp;|&nbsp; All sources free to access &nbsp;|&nbsp; A Pitre Media publication</div>
  </div>`;
}

function briefingBlock(s, issueUrl) {
  const sources = s.sources.map(src => `<a href="${src.url}" target="_blank" rel="noopener" class="pill">[${src.name}]</a>`).join(" ");
  const shareText = `${s.headline} — via thedailydrumbeat.com ${issueUrl}`.replace(/'/g, "&#39;");
  return `<div class="story anchor-story">
    <div class="tag">[ ${s.section} &middot; ${sectionLabel(s.section).toUpperCase()} &middot; BRIEFING ]</div>
    <h2>${s.headline}</h2>
    <p>${s.kicker ? `<b>${s.kicker} &mdash; </b>` : ""}${s.body}</p>
    ${s.takeaway ? `<div class="takeaway"><div class="takeaway-label">The takeaway</div>${s.takeaway}</div>` : ""}
    <div class="story-footer">
      <div class="sources"><span class="label">Sources</span> ${sources}</div>
      <button class="copy-link" onclick="navigator.clipboard.writeText('${shareText}'); this.textContent='Copied';">Copy Link</button>
    </div>
  </div>`;
}
function quickHitBlock(s, issueUrl) {
  const source = `<a href="${s.sources[0].url}" target="_blank" rel="noopener" class="pill">[${s.sources[0].name}]</a>`;
  const shareText = `${s.headline} — via thedailydrumbeat.com ${issueUrl}`.replace(/'/g, "&#39;");
  return `<div class="quick-hit">
    <div class="tag">[ ${s.section} &middot; ${sectionLabel(s.section).toUpperCase()} ]</div>
    <p>${s.quickHit || s.body}</p>
    <div class="story-footer">
      <div class="sources">${source}</div>
      <button class="copy-link" onclick="navigator.clipboard.writeText('${shareText}'); this.textContent='Copied';">Copy Link</button>
    </div>
  </div>`;
}

function moneyMovesBox(m) {
  const chg = (v) => v == null ? "" : `<span class="${v >= 0 ? "change-up" : "change-down"}">${v >= 0 ? "+" : ""}${v.toFixed(1)}%</span>`;
  const rows = [];
  if (m.sp500) rows.push(["S&P 500", `${m.sp500} ${chg(m.sp500Change)}`, ""]);
  if (m.dow) rows.push(["Dow Jones", `${m.dow} ${chg(m.dowChange)}`, ""]);
  if (m.mortgage30yr) rows.push(["30-Yr Mortgage", m.mortgage30yr, "FRED / Freddie Mac"]);
  if (m.cpiYoy) rows.push(["CPI (YoY)", m.cpiYoy, "BLS via FRED"]);
  if (m.btc) rows.push(["Bitcoin", `${m.btc} ${chg(m.btcChange)}`, "CoinGecko"]);
  if (m.eth) rows.push(["Ethereum", `${m.eth} ${chg(m.ethChange)}`, "CoinGecko"]);
  if (!rows.length && !m.tickers.length) return "";
  const tickerRows = m.tickers.map(t => {
    const dir = t.changePct >= 0 ? "change-up" : "change-down";
    return `<tr><td class="asset">${t.symbol}</td><td>$${t.price.toFixed(2)}</td><td class="${dir}">${t.changePct >= 0 ? "+" : ""}${t.changePct.toFixed(1)}%</td></tr>`;
  }).join("");
  return `<div class="box">
    <div class="box-head">
      <div class="tag">[ P4 &middot; MONEY MOVES ]</div>
    </div>
    <table>${rows.map(([a, v, s]) => `<tr><td class="asset">${a}</td><td>${v}</td><td class="source-note">${s}</td></tr>`).join("")}</table>
    ${m.tickers.length ? `<div style="margin-top:14px; font-size:11px; letter-spacing:1px; text-transform:uppercase; color:var(--muted);">Black Wall Street Watch</div><table style="margin-top:6px;">${tickerRows}</table>` : ""}
    <div class="sponsor-note">As of ${m.asOf} &middot; Finnhub, FRED, CoinGecko (all free) &middot; <a href="advertise.html">Sponsor this box</a></div>
  </div>`;
}

function sportsBox(s) {
  const hasAny = s.hbcuHeadlines.length || s.hbcuGames.length || s.lastNight.length || s.onDeck.length;
  if (!hasAny) return "";
  const list = (arr) => arr.map(g => `<div style="padding:6px 0; border-bottom:1px solid var(--border); font-size:14px;">${g}</div>`).join("");
  const headlineList = s.hbcuHeadlines.map(h => `<div style="padding:6px 0; border-bottom:1px solid var(--border); font-size:14px;">${h.title} <a href="${h.url}" style="color:var(--red); font-size:12px;">[HBCU Gameday]</a></div>`).join("");
  return `<div class="box">
    <div class="box-head">
      <div class="tag">[ P6 &middot; SPORTS ]</div>
    </div>
    <div style="font-size:11px; letter-spacing:1px; text-transform:uppercase; color:var(--muted); margin-bottom:4px;">HBCU Watch</div>
    ${headlineList}
    ${s.hbcuGames.length ? list(s.hbcuGames) : (s.hbcuHeadlines.length ? "" : `<div style="font-size:13px; color:var(--muted); padding:6px 0;">No HBCU news found today.</div>`)}
    ${s.lastNight.length ? `<div style="margin-top:14px; font-size:11px; letter-spacing:1px; text-transform:uppercase; color:var(--muted);">Last Night</div>${list(s.lastNight)}` : ""}
    ${s.onDeck.length ? `<div style="margin-top:14px; font-size:11px; letter-spacing:1px; text-transform:uppercase; color:var(--muted);">On Deck Tonight</div>${list(s.onDeck)}` : ""}
  </div>`;
}

function legacyBox(legacy) {
  if (!legacy) return "";
  return `<div class="box">
    <div class="box-head"><div class="tag">[ P10 &middot; THIS DAY IN LEGACY ]</div></div>
    <div style="font-size:14px; line-height:1.7;"><b>${legacy.year}</b> &mdash; ${legacy.text}</div>
    <div class="sponsor-note">From: <a href="${legacy.url}">${legacy.sourceName}</a></div>
  </div>`;
}

function numberBox(theNumber) {
  if (!theNumber) return "";
  return `<div class="drumroll">
    <div class="drumroll-head"><div class="dot">D</div><h3>The Drum Roll</h3></div>
    <div style="padding:22px 24px;">
      <div class="kicker">The Number</div>
      <div class="big">${theNumber.value}</div>
      <div class="note">${theNumber.label} &middot; <a href="${theNumber.sourceUrl}" style="color:var(--red);">${theNumber.source}</a></div>
    </div>
  </div>`;
}

function greenBookBox(gb) {
  if (!gb.business && !gb.opportunity) return "";
  const anySponsored = gb.business?.sponsored || gb.opportunity?.sponsored;
  return `<div class="box">
    <div class="box-head">
      <div class="tag">[ GB &middot; THE GREEN BOOK ]</div>
      ${anySponsored ? `<span class="badge">Sponsored</span>` : ""}
    </div>
    ${gb.business ? `
    <div class="tag" style="font-size:11px;">${gb.business.sponsored ? "Business of the Day" : "Business Spotlight"}</div>
    <h3 style="margin:6px 0 4px; font-size:17px;">${gb.business.name}</h3>
    <div style="font-size:13px; color:var(--muted); margin-bottom:8px;">${gb.business.tagline || ""}</div>
    <p style="font-size:14px; line-height:1.6;">${gb.business.description || ""}</p>
    ${gb.business.discountCode ? `<p style="font-size:13px; font-style:italic;">${gb.business.discountCode}</p>` : ""}
    <a href="${gb.business.url}" style="font-size:12px; font-weight:700; letter-spacing:1px; text-transform:uppercase; text-decoration:underline;">${gb.business.cta || "Visit Business"} &rarr;</a>
    ` : ""}
    ${gb.opportunity ? `
    <div style="border-top:1px solid var(--border); margin-top:18px; padding-top:16px;">
      <div class="tag" style="font-size:11px;">Opportunity</div>
      <h3 style="margin:6px 0 4px; font-size:17px;">${gb.opportunity.title} &mdash; ${gb.opportunity.amount || ""}${gb.opportunity.deadline ? ` &mdash; Deadline ${gb.opportunity.deadline}` : ""}</h3>
      <p style="font-size:14px; line-height:1.6;">${gb.opportunity.description || ""}</p>
      <a href="${gb.opportunity.url}" style="font-size:12px; font-weight:700; letter-spacing:1px; text-transform:uppercase; text-decoration:underline;">${gb.opportunity.cta || "Apply"} &rarr;</a>
    </div>` : ""}
    <div class="sponsor-note">Want your business featured here? <a href="advertise.html">Advertise</a></div>
  </div>
  <div class="box" style="text-align:center; border-style:dashed; color:var(--muted); font-size:12px; letter-spacing:1px; text-transform:uppercase;">Ad Slot — Money Moves Sponsor &middot; 300x100 &middot; <a href="advertise.html" style="color:var(--red);">Available</a></div>`;
}

function closerBlock(closer, issueUrl) {
  if (!closer) return "";
  const shareText = `via Drumbeat: ${closer.type === "quote" ? `"${closer.text}" — ${closer.attribution}` : closer.text} ${issueUrl}`.replace(/'/g, "&#39;");
  const body = closer.type === "quote"
    ? `<div class="serif" style="font-style:italic; font-size:22px;">&ldquo;${closer.text}&rdquo;</div><div style="font-size:14px; color:var(--muted); margin-top:8px;">&mdash; ${closer.attribution}</div>`
    : `<h3 style="margin:0;">${closer.headline}</h3><p style="margin-top:8px;">${closer.text}</p>`;
  return `<div class="box" style="text-align:center;">
    <div class="tag" style="margin-bottom:10px;">[ THE CLOSER &middot; P7 &middot; CULTURE & COMMUNITY ]</div>
    ${body}
    <button class="copy-link" style="margin-top:14px;" onclick="navigator.clipboard.writeText('${shareText}'); this.textContent='Copied';">Share the Daily Drumbeat</button>
  </div>`;
}

function todayEditionHtml({ dateLabel, volume, stories, closer, moneyMoves, sports, legacy, theNumber, greenBook, issueUrl }) {
  const briefings = stories.filter(s => s.isBriefing);
  const quickHits = stories.filter(s => !s.isBriefing);
  return `${pageHead(dateLabel, "today.html")}
  ${header("today.html")}
  <div class="wrap" style="padding-top:40px;">
    <div class="hero" style="padding-top:0;">
      <div class="maintitle" style="font-size:40px;">THE DAILY <span class="D">D</span>RUMBEAT</div>
      <div class="hero .volbar" style="max-width:760px; margin:20px auto 0; border-top:1px solid var(--ink); border-bottom:1px solid var(--ink); padding:10px 0; font-size:13px; letter-spacing:2px; text-transform:uppercase; color:var(--muted);">TODAY'S EDITION &mdash; ${volume} &mdash; ${dateLabel}</div>
    </div>

    <div class="two-col" style="margin-top:40px;">
      <div>
        ${briefings.map(s => briefingBlock(s, issueUrl)).join("\n        ")}
        <div class="quick-hits-label">The quick ${quickHits.length}</div>
        ${quickHits.map(s => quickHitBlock(s, issueUrl)).join("\n        ")}
      </div>
      <div>
        ${moneyMovesBox(moneyMoves)}
        ${sportsBox(sports)}
        ${legacyBox(legacy)}
        ${greenBookBox(greenBook)}
      </div>
    </div>

    ${numberBox(theNumber)}
    <div style="margin-top:18px;">${closerBlock(closer, issueUrl)}</div>
  </div>
  ${footer()}
</body></html>`;
}

function landingHtml({ dateLabel, volume, stories, issueUrl }) {
  const briefings = stories.filter(s => s.isBriefing);
  const summary = [...briefings, ...stories.filter(s => !s.isBriefing)].slice(0, 4).map(s => s.headline).join(", ");
  const sectionCards = [
    ...stories.map(s => [s.section, sectionLabel(s.section), s.headline]),
    ["P4", "Money Moves", "Markets &middot; Mortgage &middot; Crypto"],
    ["P6", "Sports", "HBCU sports coverage"],
    ["P10", "This Day in Legacy", "A Black-history fact for today"],
    ["GB", "The Green Book", "Auto-spotlighted business + opportunity"]
  ];
  return `${pageHead("Landing", "index.html")}
  ${header("index.html")}
  <div class="hero">
    <div class="maintitle">THE DAILY <span class="D">D</span>RUMBEAT</div>
    <div class="tagline">News about us. For us. By the beat of the drum.</div>
    <div class="volbar">${volume} &mdash; ${dateLabel}</div>
    <div class="summary">In today&rsquo;s Drumbeat: ${summary}.</div>
    <a href="today.html" class="btn-primary">Read Today's Edition &rarr;</a>
  </div>

  <div class="inside-today wrap">
    <h3>Inside Today</h3>
    <div class="sub">All sections</div>
    <div class="section-grid">
      ${sectionCards.map(([code, name, preview]) => `<a href="today.html"><div class="stag">[ ${code} &middot; ${name.toUpperCase()} ]</div><div class="stitle">${preview}</div></a>`).join("\n      ")}
    </div>
  </div>

  <div class="subscribe-box">
    <div>
      <h4>Get the Drumbeat in your inbox</h4>
      <p>Five minutes every weekday. No spam. Unsubscribe anytime.</p>
    </div>
    <a href="https://1a3e105b.sibforms.com/serve/MUIFAIJL5UKBuRKB0t2SMRcCN7dPVIDPS3wraCIqU8bOsCk_66TFY1aS5ovPumAlVJoBIkt2Zlz4Sm1ZQHNhm0siu2bk2mg_JfqsMDb_ZUUMDQ6FFiG9mkYwawb9VGtIkRyftpMI051EtSZvYQxGINXN6a53vz039oP4Oq6JE5YbUko_1Wj8VK1818z-wNjiClOYANVT1k7fwNKYyw==" class="btn-primary" style="margin-top:0;">Subscribe free &rarr;</a>
  </div>
  ${footer()}
</body></html>`;
}

function archiveHtml(manifest) {
  const rows = manifest.map(e => `<a href="${e.file}" class="archive-row">
      <span class="d">${e.dateLabel}</span><span class="v">${e.volume}</span><span class="c">${e.storyCount} stories &rarr;</span>
      <div class="s">${e.summary}</div>
    </a>`).join("\n    ");
  return `${pageHead("Archive", "archive.html")}
  ${header("archive.html")}
  <div class="wrap" style="max-width:900px; padding-top:56px;">
    <h1 style="font-size:40px;">The Archive</h1>
    <div class="sub" style="font-size:13px; letter-spacing:3px; text-transform:uppercase; color:var(--muted); margin:8px 0 24px;">${manifest.length} editions</div>
    <div>${rows}</div>
  </div>
  ${footer()}
</body></html>`;
}

// =========================================================
// EMAIL
// =========================================================
async function sendBrevoCampaign({ dateLabel, issueUrl, stories, closer }) {
  if (!BREVO_API_KEY || !BREVO_LIST_ID || !BREVO_SENDER_EMAIL) { console.warn("Brevo env vars missing - skipping email send."); return; }
  const briefings = stories.filter(s => s.isBriefing);
  const quickHits = stories.filter(s => !s.isBriefing);
  const htmlContent = `<div style="font-family:Georgia,serif; max-width:600px; margin:0 auto;">
    <h1 style="color:#8E2A2B;">The Daily Drumbeat — ${dateLabel}</h1>
    ${briefings.map(anchor => `<div style="margin-bottom:24px;">
      <div style="font-size:12px; color:#8E2A2B; text-transform:uppercase; letter-spacing:1px;">${sectionLabel(anchor.section)} &middot; Briefing</div>
      <h2 style="font-family:Georgia,serif; margin:6px 0;">${anchor.headline}</h2>
      <p style="font-family:Helvetica,Arial,sans-serif; font-size:15px; line-height:1.6;">${anchor.kicker ? `<b>${anchor.kicker} — </b>` : ""}${anchor.body}</p>
      ${anchor.takeaway ? `<p style="background:#F7F3EC; padding:10px 14px; font-size:14px;"><b>The takeaway:</b> ${anchor.takeaway}</p>` : ""}
      <p style="font-size:13px; color:#6E6A60;">Sources: ${anchor.sources.map(src => `<a href="${src.url}">${src.name}</a>`).join(" &middot; ")}</p>
    </div>`).join("")}
    ${quickHits.map(s => `<div style="margin-bottom:14px;">
      <div style="font-size:11px; color:#8E2A2B; text-transform:uppercase; letter-spacing:1px;">${sectionLabel(s.section)}</div>
      <p style="font-family:Helvetica,Arial,sans-serif; font-size:14px; line-height:1.5;">${s.quickHit || s.body} <a href="${s.sources[0].url}" style="font-size:12px;">[${s.sources[0].name}]</a></p>
    </div>`).join("")}
    ${closer ? `<p style="font-style:italic;">${closer.type === "quote" ? `&ldquo;${closer.text}&rdquo; — ${closer.attribution}` : closer.text}</p>` : ""}
    <p><a href="${issueUrl}" style="background:#8E2A2B; color:#fff; padding:12px 24px; text-decoration:none;">Read online</a></p>
    <p style="font-size:12px; color:#6E6A60;">The Daily Drumbeat &middot; ${SITE_URL}</p>
  </div>`;
  const createRes = await fetch("https://api.brevo.com/v3/emailCampaigns", {
    method: "POST", headers: { "content-type": "application/json", "api-key": BREVO_API_KEY },
    body: JSON.stringify({ name: `Drumbeat ${dateLabel}`, subject: `The Daily Drumbeat — ${dateLabel}`, sender: { name: BREVO_SENDER_NAME, email: BREVO_SENDER_EMAIL }, type: "classic", htmlContent, recipients: { listIds: [Number(BREVO_LIST_ID)] } })
  });
  if (!createRes.ok) { console.error("Brevo campaign create failed:", await createRes.text()); return; }
  const { id } = await createRes.json();
  const sendRes = await fetch(`https://api.brevo.com/v3/emailCampaigns/${id}/sendNow`, { method: "POST", headers: { "api-key": BREVO_API_KEY } });
  if (!sendRes.ok) console.error("Brevo send failed:", await sendRes.text()); else console.log("Brevo campaign sent.");
}

// =========================================================
// MAIN
// =========================================================
async function main() {
  const { iso, label, dayOfYear } = todayParts(0);

  const pressLeads = await fetchPressLeads();
  const [content, moneyMoves, sports, legacy, theNumber] = await Promise.all([
    curateContent(pressLeads), fetchMoneyMoves(), fetchSportsBox(), fetchThisDayInLegacy(), fetchTheNumber(dayOfYear)
  ]);

  const validPrimaries = await validateStories(content.stories);
  const validBackups = await validateStories(content.backups);
  const stories = assembleStories(validPrimaries, validBackups);
  if (stories.length === 0) throw new Error("No stories passed validation today - not publishing.");

  const greenBook = await resolveGreenBook(content.greenBook);

  const manifestPath = path.join("issues", "manifest.json");
  let manifest = [];
  try { manifest = JSON.parse(await readFile(manifestPath, "utf-8")); } catch { /* first run */ }

  const volume = `VOL 1 NO ${manifest.length + 1}`;
  const issueFile = `issues/${iso}.html`;
  const issueUrl = `${SITE_URL}/${issueFile}`;

  await mkdir("issues", { recursive: true });
  const html = todayEditionHtml({ dateLabel: label, volume, stories, closer: content.closer, moneyMoves, sports, legacy, theNumber, greenBook, issueUrl });
  await writeFile(issueFile, html);
  await writeFile("today.html", html);
  await writeFile("index.html", landingHtml({ dateLabel: label, volume, stories, issueUrl }));

  manifest.unshift({ date: iso, dateLabel: label, volume, file: issueFile, storyCount: stories.length, summary: stories.map(s => s.headline).join(", ") });
  manifest = manifest.slice(0, 90);
  await writeFile(manifestPath, JSON.stringify(manifest, null, 2));
  await writeFile("archive.html", archiveHtml(manifest));

  await sendBrevoCampaign({ dateLabel: label, issueUrl, stories, closer: content.closer });

  const briefingCount = stories.filter(s => s.isBriefing).length;
  console.log(`Published ${issueFile} with ${stories.length} stories (target ${MIN_STORIES}-${MAX_STORIES}), ${briefingCount} briefings, + closer + Green Book. ${pressLeads.length} press leads fetched.`);
}

export { todayEditionHtml, landingHtml, archiveHtml };

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(err => { console.error(err); process.exit(1); });
}
