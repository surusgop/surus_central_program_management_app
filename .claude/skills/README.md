# Surus Central Program Management — Design System

An internal **voter-contact analytics dashboard**. It reads pre-aggregated
contact metrics from a Databricks SQL warehouse and presents them as KPI cards,
donut charts, and a detailed weekly grid — broken down by **State, Nation, and
Group** — so the team can **report outreach activity to donors**.

Under the hood the app is a **Plotly Dash** application (Bootstrap 5 grid +
**Bootstrap Icons** + **Plotly** + **AG Grid "Alpine"**), gated by **Google
OAuth** restricted to a single Google Workspace domain.

## Brand — Surus Illinois

**This system has one brand: the light "Surus Illinois" look**, taken from the
public Surus Illinois campaign site. Every surface — dashboard, components,
specimens — uses it. Tokens live in **`themes/surus-illinois.css`** (`--il-*`).

The look in one line: a **light gray field**, a bold **red `#C1272D`** navbar and
accents, heavy **navy `#2A313C` Open Sans** headings, **white cards with a red
header rule**, and a **red-header zebra-striped** data grid.

The live recreation is **`ui_kits/dashboard/`** — open
`ui_kits/dashboard/index.html`. It keeps Bootstrap only for its grid/utilities;
all theming is repainted by `ui_kits/dashboard/il-theme.css`.

## Source

- **GitHub:** `surusgop/surus_central_program_management_app` @ `dev`
  — https://github.com/surusgop/surus_central_program_management_app/tree/dev
- **Brand reference:** the public **Surus Illinois** website (red/white campaign
  look) — captured from a screenshot; sampled colors recorded in
  `themes/surus-illinois.css`.
- Related Surus repos (broader context, not used here):
  - `surusgop/contact_app` — "Import contacts into Nationbuilder"
  - `surusgop/surus_central_program_management_app` — "Reporting App for CLP and BP Programs"
  - `surusgop/surus-program-analytics` — "Chatbot for BP and CLP analytics"

The reader is encouraged to explore the `surus_central_program_management_app` repo directly
to build higher-fidelity designs — especially `pages/analytics.py`,
`pages/contacts_detail.py`, and `components/navbar.py`, the primary sources for
the dashboard's structure.

### What the product tracks

The core dataset (`universal.bitables.contact_analysis_dash`) is summarized per
**week / state / nation / group** with these measures:

- **Totals:** `total_contacts`, `unique_contacts`, `total_events`
- **Contact types:** Door Knock, Email, Phone, Text, Snail Mail, Face to Face, Other
- **Contact frequency:** contacted 1 / 2 / 3 / 4+ times

The three product surfaces:

1. **Home** (`/`) — a centered wordmark, one-line description, and a primary CTA.
2. **Contacts** (`/analytics`) — State/Nation/Group/Date-Range filters, three KPI
   cards, and two donut charts (Contact Type Breakdown, Contacts by Frequency).
3. **Contacts Detail** (`/contacts`) — the same filters above a full grid of
   weekly rows with a pinned State column.

---

## CONTENT FUNDAMENTALS

The voice is **plain, terse, and operational** — this is an internal reporting
tool. There is no persuasion, no exclamation, no emoji.

- **Tone:** Neutral and factual. Labels name the thing and stop. The longest
  sentence in the UI is the home subtitle: *"Voter contact data by state and
  nation. Use the navigation above to explore."*
- **Casing:** **Title Case** for nav items, page titles, card headers, KPI labels,
  filter labels, and table columns ("Contact Summary", "Total Contacts",
  "Door Knock"). Sentence case for the one descriptive paragraph.
- **Person:** Effectively **none** — the copy addresses tasks, not a reader. The
  rare instruction uses an implied imperative *you* ("Use the navigation above").
- **Placeholders:** lowercase with a trailing ellipsis — `All states…`,
  `All nations…`, `All groups…`.
- **Empty / status states:** quiet and literal — *"No contact data for this
  selection."* The status line echoes the active filters:
  `All states · All nations · All groups`.
- **Numbers:** always **thousands-separated** (`1,234`), tabular figures; a
  missing/null value renders as an em dash `—`.
- **Brand name:** written in full — **"Surus Central Program Management"** — set in heavy
  Open Sans (white in the red navbar, navy on light).
- **Emoji:** never. **Icons** carry visual shorthand (see ICONOGRAPHY).

---

## VISUAL FOUNDATIONS (Surus Illinois)

Bold, high-energy, **red-and-white campaign** styling on a clean light field.

- **Colors:** **red `#C1272D` is the brand** — it owns the navbar, buttons, card
  header rules, table headers, KPI icons, and active states. Headings and body
  text are heavy **navy `#2A313C`**; secondary/muted text and nav links are
  **slate `#75859E`**. Section bands and zebra rows use **`#EEF0F3`**; hairline
  borders are `#E1E5EA`. Hover darkens red to `#A11F24`.
- **Type:** **Open Sans** throughout. Display/headings are **Extrabold (800)** in
  navy; nav and field labels are **600/700 uppercase** with light tracking; body
  is 400 at 16px; grid cells 13px tabular.
- **Backgrounds:** flat color only — light gray app field `#F4F6F8`, white cards,
  solid red bands. **No gradients, images, textures, or patterns.** Donut charts
  sit on a transparent (light) background.
- **Spacing:** Bootstrap's spacer scale (4px base). 12-column grid with `g-*`
  gutters; pages use `px-4` side padding, cards `py-4` interior. KPI cards are
  centered; filters align to the bottom.
- **Cards:** white, **4px radius**, hairline `#E1E5EA` border + a soft shadow
  (`0 1px 3px rgba(42,49,60,.12)`). Headers carry a **2px red bottom rule** and
  navy uppercase bold text. KPI cards add a red top rule.
- **Buttons:** solid **red**, white bold label, 4px radius; hover → `#A11F24`.
  Secondary is a red outline on white.
- **Table:** **red header bar** with white uppercase labels, **zebra rows** on
  `#EEF0F3`, a bold navy pinned **State** column, red-tint row hover.
- **Shadows:** one soft elevation (the card shadow above). No deep/colored shadows.
- **Corner radii:** **4px** is universal — buttons, cards, inputs, dropdowns.
- **Hover / press:** red elements darken to `#A11F24`; nav links go white-bold
  (active link carries a white underline). No scale/transform animation.
- **Animation:** minimal — Plotly's default chart transitions only. No entrance
  animations, parallax, or decorative motion.
- **Transparency / blur:** none. Everything is opaque.
- **Imagery / illustration:** the marketing site uses a small **red elephant
  logo** above a "SURUS / ILLINOIS" wordmark — **the logo asset is not in any
  repo**, so the kit uses the text wordmark as a stand-in (drop the real file in
  `assets/` to finish it). Data viz (donuts, grid) is the only other "imagery."
- **Layout rules:** the red navbar is the single top chrome element, full-width.
  Content is a fluid container; the home view centers a 6-of-12 column.

---

## ICONOGRAPHY

- **Icon system:** **Bootstrap Icons** — a webfont; icons are `<i class="bi bi-…">`
  elements colored with inline CSS (brand red on KPI cards).
- **Observed usage** (KPI cards, ~30px):
  - `bi-telephone-fill` → Total Contacts
  - `bi-people-fill` → Unique Contacts
  - `bi-calendar-event-fill` → Total Events
  - Social row uses `bi-facebook` / `bi-twitter` / `bi-linkedin` / `bi-instagram`
    / `bi-envelope-fill`.
- Icons are used **sparingly** — KPI glyphs, share/social, and inside Bootstrap
  controls (dropdown carets). **Filled** variants are preferred.
- **No emoji, no Unicode pictographs, no custom SVG icons.** The only non-text
  glyph used as content is the em dash `—` for null/empty values.
- **How to use here:** load Bootstrap Icons from CDN (`bootstrap-icons@1.11.3`)
  and reference by class. Do not hand-draw SVG icons.

---

## INDEX (manifest)

- **`themes/surus-illinois.css`** — the single brand-token file (`--il-*`):
  colors, Open Sans type scale, spacing, radius. **Start here.**
- **`preview/`** — small specimen cards shown in the Design System tab
  (palette, type, spacing, components, site header) — all `il-*`.
- **`ui_kits/dashboard/`** — the interactive recreation (Login → Home → Contacts →
  Contacts Detail). Open `ui_kits/dashboard/index.html`. `il-theme.css` is the
  brand re-skin; `components.jsx` / `pages.jsx` / `data.jsx` hold the kit.
- **`assets/`** — drop the real elephant logo / brand fonts here.
- **`SKILL.md`** — Agent-Skill manifest so this folder can be used directly by
  Claude Code.

### Notable caveats
- **Elephant logo missing** — the navbar uses the "Surus Central Program Management"
  text wordmark; add the real logo to `assets/` and place it in the navbar.
- **Open Sans Extrabold** is a best-guess match for the marketing-site display
  face. Send the real font if it differs and it'll be swapped in.
- The kit is a **cosmetic** recreation — no Databricks queries, no real OAuth, and
  the grid is a styled HTML table (not the AG Grid library).
