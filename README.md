# SBC Copilot Advisor — local alpha, revision 2

A free, MIT-licensed local advisor for EA FC Ultimate Team SBC decisions. The LLM sees all imported cards plus the full pasted challenge and any quoted market candidates, then reasons about what to use, buy instead, preserve, or skip. A deterministic checker guards exact card references, protections and quoted spending; the older numeric optimizer is secondary. Optional **official Sign in with ChatGPT** uses your ChatGPT plan (subject to account eligibility, consent, available models and plan limits), not an API key or an unofficial ChatGPT endpoint.

**This is a first planning prototype, not a game-validating or auto-submitting bot.** Demo players, scores and values are fictional. No EA account connection, scraping, purchases or submissions exist.

## Advisor workflow (the main experience)

1. Import your CSV/JSON club or load fictional demo cards. **Alpha bound: 1–150 cards**, 1 MB request and a **95,000-character complete advice prompt**. Over-limit data is rejected before any model call, never silently truncated. This does **not** yet handle arbitrary full-size clubs. Do not present a partial import as your complete club; mention omitted cards in the brief. A future inventory-query/tool approach can remove this limitation.
2. Protect favourites and starting XI. All imported cards and protection flags are included as context so the LLM understands what it must preserve, but protected selections are rejected locally.
3. Paste the **full SBC brief**: requirements, reward, expiry, relevant card versions, and your preferences. Choose the exact platform and a maximum **new-coin spending budget**.
4. Optionally paste a **manual market snapshot** of real candidate cards. This is not a search box, automatic scraper or live feed. Without quotes the advisor can recommend owned cards, identify what is missing, or suggest waiting—but cannot return invented market candidates.
5. Connect ChatGPT (instructions below), review the data-sharing preview, and explicitly consent to sharing **all imported club fields**, the brief, budget/platform and quote snapshot with OpenAI. Then click **Reason through my options**.
6. Receive one recommendation plus up to two distinct alternatives if supported by the data. Outcomes can also be **needs information** or **hold off** rather than forcing a squad. Card references and spending are recomputed from your data, not trusted from model prose. Review everything before manually acting in the game.

The numeric check is collapsed in the sidebar. Optionally include those fields as **additional hard checks** using the checkbox above the advisor button. They do not encode every rule in the pasted brief. Known failed structured constraints reject a recommendation; missing rule metadata is explicitly unverified. The standalone optimizer remains usable without an LLM.

### What the reasoning considers

- Using existing duplicates and untradeables versus buying supplied cheap substitutes.
- Preserving tradeable cards with higher estimated resale opportunity cost (estimates before fees, not guaranteed sale proceeds).
- Preserving valuable **untradeable utility/replacement value**: untradeable does not mean free. Historic acquisition cost is sunk cost, not a reason to consume a good card.
- Missing reward value, expiry, card versions, incomplete inventory or chemistry data; whether postponing the SBC is more sensible.
- Exact platform and snapshot freshness. Quotes older than one hour are flagged, but this heuristic is not a guarantee newer quotes remain available.

**LLM prose/confidence remains fallible.** Local checks validate references, quoted spend, protection and identity—not every statement or price claim embedded in prose, reward value, full game rules, or optimal strategy. There is no EA purchase, listing, submission or login action.

### Manual market snapshot shape

```json
{
  "source": "URL or clear label of where you manually checked this quote",
  "observedAt": "2026-10-25T20:00:00Z",
  "platform": "pc",
  "candidates": [
    {
      "id": "market-card-1",
      "playerId": "stable-footballer-id",
      "name": "Exact card name and version",
      "rating": 80,
      "nation": "Known nation",
      "league": "Known league",
      "club": "Known club",
      "position": "CM",
      "rare": true,
      "price": 700
    }
  ]
}
```

This is a **schema example**, not an actual player or current price. Update the timestamp to the actual observation, never pretend example values are real. Candidate IDs must be unique and distinct from owned-card IDs. Up to 40 candidates. `price` is a nonnegative quoted integer. `platform` must exactly match `pc`, `playstation`, `xbox` or `switch`; no unverified cross-platform mapping. Market cards cannot be marked untradeable, protected or starting XI. Version/eligibility information should be explicit in name/brief because there is no EA item database behind the app.

### Account linking and live prices: not implemented

There is **no working EA account link or automatic market feed in this release**. `ClubSnapshotAdapter` and `ManualSnapshotAdapter` define a read-only adapter boundary in `advisor.py`; they do not claim an external connection. Research found no verified permitted free machine feed for this build. FUT.GG advertises club sync but a permitted complete export/API path was not established; do not scrape it. FUT-DB offers a paid player-price API, but no signup, purchase, API key, redistribution clearance or integration was performed. Manual imports and quotes are the supported path. ChatGPT sign-in is separate from EA account linking.

Research references (not bundled integrations):
- https://fut-db.com/
- https://api.fut-db.com/api/doc/v1/swagger.json
- https://fut-db.com/terms
- https://stormstrike.gg/terms

## Run in two minutes

Install Python **3.10 or newer** if needed. Extract this whole folder, then open a terminal in it:

```sh
python3 server.py
```

On Windows use `py -3 server.py` (or double-click `start.bat`). On macOS `start.command` runs the same command. Both launchers prefer this folder’s `.venv` Python when present. Open **http://127.0.0.1:8765**. Stop with Ctrl+C. If occupied: `python3 server.py --port 8766`, and use that port in the browser. Do not expose the server through a proxy or public tunnel.

For the standalone numeric example, open **Optional numeric check**, then **Try demo club → Find my squad**. For advisor testing, load the fictional brief and connect ChatGPT; no offline advice is fabricated. The demo includes fictional per-card item scores and sets a 700-point total target. Lock any card using 🔒 or XI and solve again. Your inventory and protection edits are held in browser memory; **Export club** to keep them. Refreshing or navigating away clears your club. No local database setup is required.

### Optional ChatGPT plan connection

The local solver needs **no dependencies**. For ChatGPT, install the maintained JWT signature-verification dependency, preferably in a virtual environment:

```sh
python3 -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-chatgpt.txt
python server.py
```

1. Read the on-screen local credential-storage notice and check consent if acceptable.
2. Click **Connect ChatGPT**, then the explicit **Continue to OpenAI sign-in** link. You review and approve the OpenAI grant yourself. No sign-in is performed by this project’s tests.
3. Return to the app. It discovers models available to your account. Identity-only sign-in without plan sharing is not treated as usable inference.
4. For the main experience use **Reason through my options** with the separate whole-club consent. For the optional numeric result, **Explain with ChatGPT**; this sends the selected card fields, constraints and result to OpenAI. To change constraints, type a request, **Preview adjustment**, review its numeric proposal, then **Apply & find squad**. The LLM does not choose or override protected cards: the deterministic solver runs again.
5. **Disconnect** removes local tokens and active account identity, then attempts remote revocation. Non-secret previous registration IDs, account subject IDs and issuer mappings plus the random persistent installation/host ID remain in `.local` so account-bound registrations are not accidentally reused; email is removed. Delete the `.local` folder after stopping the app if you want to erase those mappings too (only after any necessary remote revocation). If remote revocation cannot be confirmed, review connected apps in ChatGPT.

Tokens are stored **unencrypted** in `.local/chatgpt.json` inside this project after explicit consent. POSIX files use mode 0600 and directory 0700; Windows access control depends on your user folder. Do not use a shared computer, sync this folder, commit `.local`, or send it to anyone. `.gitignore` excludes it. The app does not collect EA credentials. No account email/identifier is sent in recommendation prompts. The local solver itself makes no external requests. Copying a plan only shares it when you paste it elsewhere.

Auth implementation: dynamic public-client registration, loopback callback, PKCE S256, state, nonce, discovery/JWKS signature verification, issuer/audience/expiry checks, scope checks, refresh rotation, model discovery, Responses API streaming with `store:false`, and completion-event verification. Unsupported/dead streams fail rather than claiming success. No custom authentication endpoints or reverse-engineered browser sessions.

**Live OAuth login and live ChatGPT inference have not been tested** with a user account. Protocol and error paths are unit-tested with mocks; real signature and claim validation are tested using local test keys. Availability and account eligibility must be established by your own grant. This is not a promise of unlimited usage.

Official protocol documentation verified 2026-10-25:
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference

## Import format

CSV with a header or JSON array. Maximum **150 cards**, **1 MB** request. Every card must have a unique card `id`. Use `demo-club.json` as a complete template. Example CSV:

```csv
id,playerId,name,rating,nation,league,club,position,rare,untradeable,duplicate,protected,startingXI,value,itemScore
card-1,footballer-1,Example Player,80,Example Nation,Example League,Example Club,CM,true,true,true,false,false,700,60
```

Required: `id` (text), `name` (text), `rating` (integer 1–99).
Optional:
- `playerId`: stable identity shared by all cards of the same footballer. Strongly recommended. If either compared card lacks an ID, normalized names are compared; aliases may evade that fallback and namesakes may be incorrectly excluded.
- `nation`, `league`, `club`, `position`: text. Missing league/nation/club cannot satisfy active constraints on those fields.
- `rare`, `untradeable`, `duplicate`, `protected`, `startingXI`: JSON booleans; CSV `true/false` or `1/0`.
- `value`: integer estimated value, defaults to 0. **Supply realistic estimates to make value optimization meaningful.** These are not live prices, purchase costs, or financial advice.
- `itemScore`: nonnegative integer copied by you from the relevant challenge; not inferred from rating. Required on every eligible card if the score target is positive.

Unknown fields, malformed records, duplicate IDs/JSON keys, out-of-range numbers, and ambiguous booleans are rejected. Import failure does not replace your current club. JSON export preserves all normalized fields, protections and known scores.

## Exactly what is supported

UI: squad size 1–11, minimum **arithmetic average** rating, minimum rare count, minimum league count, maximum estimated value, minimum sum of known item scores. Engine/API additionally supports maximum leagues, minimum/maximum nations, maximum cards from one club and explicit protected IDs. Protection and starting XI exclusions are always hard rules. Known same-footballer identities cannot appear twice.

**Not supported:** EA’s actual squad-rating formula, chemistry, position/formation requirements, card rarity categories beyond a user-supplied rare boolean, item eligibility/version rules, multi-squad sequencing, progress already submitted, reward valuation, live market prices or automatic club inventory sync. A score total is a useful sum of user-entered values, **not full Simplified SBC rule validation**. Unknown constraint keys fail explicitly rather than being silently ignored. Do not enter an in-game rating requirement and interpret this arithmetic planner as proving it passed.

### Optimization and honest outcomes

Minimize the sum of this transparent heuristic per card:

```
value × (15 if duplicate, else 65 if untradeable, else 100)
+ 10000 × max(rating − 75, 0)²
```

Thus duplicates/untradeables are preferred when other properties match, while high-rated cards are strongly conserved. It is **not** guaranteed to use every duplicate or select the lowest raw coin-value squad. Search has a two-second budget. `optimal` proves the best heuristic score under supported constraints, `feasible` is a found valid plan without proven optimum, `infeasible` means exhausted search, and `timeout` means no plan found yet—not impossibility. Always inspect the plan and verify the full challenge in-game before manual submission.

## Tests

```sh
python -m unittest discover -v
node --check static/app.js   # optional JS syntax check; needs Node
node test_ui.js              # isolated actual UI-handler/state regressions
```

Advisor tests additionally cover all-imported-card context, explicit consent, referenced-only cards/prices, stale and mismatched-platform snapshots, hard protection and spend limits, unknown/duplicated card IDs, same-player collisions, owned-only/mixed alternatives, needs-information/hold, prompt size preflight and structured-rule checks.

Tests cover strict CSV/JSON import, protections, identity exclusion, score totals, unsupported constraints, brute-force optimum comparisons, deterministic repeats, infeasible versus timeout outcomes, loopback/Host/Origin/CSRF and private-file boundaries, mocked OAuth/refresh/inference errors, real signature/claim checks when optional dependencies are installed, and HTTP import → solve plus LLM proposal → review payload → solve. No external account is used.

Browser automation was attempted but **not completed** in the build environment: headless Chromium’s local socket was sandbox-blocked; one elevated attempt failed environment setup; the supported existing cloud browser could not reach the loopback server. No screenshot or visual/browser-flow pass is claimed. HTML/JavaScript were inspected, JS syntax checked, and selected actual UI handlers (including repeated-click guard, changed-input discard, sharing consent and freshness) exercised in an isolated Node VM (not a browser or visual-layout pass). Repeated requests and malformed inputs are covered at the HTTP layer; mobile layout, clipboard/download and live OAuth navigation remain manual-QA items.

## Files and trust boundaries

- `advisor.py`: whole-import context, strict structured advice validation, manual read-only snapshot boundary.
- `core.py`: deterministic validation/optimizer, no network access.
- `server.py`: loopback-only HTTP server, bounded bodies, strict JSON, origin/host checks and session token for mutation routes; static file allowlist.
- `chatgpt.py`: explicit OpenAI-only integration; credentials remain server-side.
- `static/`: plain browser UI, no CDN, third-party scripts, analytics or build tooling.
- `demo-club.json`: fictional data.
- `test_*.py`: tests.

The UI treats imported text and LLM output as text, not HTML. LLM proposals must match the supported numeric constraint schema and cannot change protections; they require a separate apply action. OpenAI responses remain advisory. This alpha is designed for one local user, not a hosted multi-user service.
