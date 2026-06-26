# Dashboard UI Kit

A high-fidelity, interactive recreation of the **Surus Central Program Management** — the
internal Plotly Dash tool that reports voter-contact metrics to donors. Open
**`index.html`** for the full click-through.

## What it reproduces

The original app was **Bootstrap 5 + Bootswatch Flatly + Bootstrap Icons + Plotly
+ AG Grid (Alpine)**. It is **skinned to the Surus Illinois brand** (`il-theme.css`,
which pulls tokens from `themes/surus-illinois.css`): a light gray field, a bold
**red navbar**, heavy navy **Open Sans** headings, white cards with a red header
rule, red KPI icons and buttons, a red-header zebra-striped table, and an on-brand
donut palette (red / navy / slate / orange). Bootstrap supplies only the
grid/utilities; Bootstrap Icons + real Plotly are loaded for glyphs and charts.

## Flow

1. **Login** — Google OAuth gate, restricted to `@surusenterprises.com`. Click
   *Sign in with Google* to enter.
2. **Home** (`/`) — centered wordmark, one-line description, *View Contacts* CTA.
3. **Contacts** (`/analytics`) — State / Nation / Group / Date-Range filters → three
   KPI cards (Total / Unique Contacts, Total Events) → two **live Plotly donuts**
   (Contact Type Breakdown, Contacts by Frequency). All update from the filters.
4. **Contacts Detail** (`/contacts`) — same filters above an AG-Grid-styled weekly
   table with a pinned, bold **State** column and tabular numerals.

Everything is driven by deterministic mock data in `data.jsx` (mirrors the real
column set); no backend.

## Files

| File | Role |
|---|---|
| `index.html`      | App shell, routing, CDN/script loading, mounts `<App>` |
| `il-theme.css`    | Surus Illinois brand re-skin layered over Bootstrap |
| `data.jsx`        | Mock dataset + helpers (+ `IL_CAT_COLORS`) |
| `components.jsx`  | `Navbar`, `MultiSelect`, `KpiCard`, `DonutCard` |
| `pages.jsx`       | `LoginPage`, `HomePage`, `FilterBar`, `ContactsPage`, `ContactsDetailPage` |

## Notes / cut corners

- This is a **cosmetic** recreation — no Databricks queries, no real OAuth, no
  AG Grid library (the grid is a styled HTML table matching the Alpine theme).
- The **Debug** route is a stub (the real one shows cache/env diagnostics).
- KPI icons are all brand red `#C1272D`; numbers are heavy navy `#2A313C`.
