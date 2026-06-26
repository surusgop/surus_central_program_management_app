---
name: surus-illinois-design
description: Use this skill to generate well-branded interfaces and assets for Surus (the Surus Central Program Management / Surus Illinois brand), either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the `README.md` file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy
assets out and create static HTML files for the user to view. If working on
production code, you can copy assets and read the rules here to become an expert
in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they
want to build or design, ask some questions, and act as an expert designer who
outputs HTML artifacts _or_ production code, depending on the need.

## Quick orientation

- **What this is:** the Surus Central Program Management — an internal Plotly Dash tool
  that reports voter-contact metrics (by State / Nation / Group / week) to donors,
  styled in the **Surus Illinois** brand.
- **One brand:** the light **Surus Illinois** look — light gray field, bold red
  chrome, heavy navy Open Sans headings, slate secondary text.
- **Tokens:** `themes/surus-illinois.css` (`--il-*`). Load it first.
- **Key colors:** brand red `#C1272D` (hover `#A11F24`), heading navy `#2A313C`,
  slate `#75859E`, gray band `#EEF0F3`, border `#E1E5EA`, white field.
- **Type:** Open Sans — headings Extrabold (800) navy; nav/labels 600/700
  uppercase; body 400.
- **Components:** copy from `ui_kits/dashboard/` (`components.jsx`, `pages.jsx`,
  `il-theme.css`). Specimens in `preview/il-*`.
- **Icons:** Bootstrap Icons (CDN), brand-red on KPI cards. No emoji, no custom SVG.
- **Voice:** terse, factual, Title/UPPER case, no emoji. See README CONTENT FUNDAMENTALS.

## Fastest path to an on-brand mock

Load these in your HTML, then build with Bootstrap classes + `--il-*` tokens:
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootswatch@5.3.3/dist/flatly/bootstrap.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
<link rel="stylesheet" href="themes/surus-illinois.css">
```
