# Surus Central Program Management — User Guide

## Overview

The Surus Central Program Management is a voter contact analytics platform that lets campaign managers monitor outreach activity across states, organizations (Nations), and campaign groups. It tracks who was contacted, how often, by what method, and where — pulling from live data in Databricks.

---

## Getting Started

### Signing In

The dashboard uses Google OAuth for authentication. When you first visit the URL, you will be redirected to a Google sign-in page. Sign in with your authorized `@surusenterprises.com` Google account. After a successful login, you are redirected to the dashboard and a session cookie keeps you logged in.

If your session expires, you will be redirected to sign in again automatically.

---

## Navigation

The top navigation bar appears on every page:

| Link | URL | Purpose |
|------|-----|---------|
| **Surus Central Program Management** (logo) | `/` | Home page |
| **Home** | `/` | Home / landing page |
| **Contacts** | `/analytics` | Main KPI and summary dashboard |
| **Map** | `/map` | Geospatial map of voter contacts |
| **Debug** | `/debug` | Raw data table (internal/dev use) |

---

## Pages

### Home (`/`)

The landing page. Click **View Contacts** to jump directly to the Analytics dashboard.

---

### Contacts — Analytics Dashboard (`/analytics`)

The main overview page. It shows aggregate KPIs, contact method breakdowns, and a detailed summary grid.

#### Filters

All filters are optional. Leave them blank to see data for all states, nations, and groups.

| Filter | Description |
|--------|-------------|
| **State** | Multi-select. Filter to one or more US states (2-letter abbreviation). |
| **Nation** | Multi-select. Filter to one or more political organizations/nations. |
| **Group** | Multi-select. Filter to one or more campaign groups. |
| **Start Date / End Date** | Optional date range. Restricts data to contacts created within the selected window. |

The **status bar** at the bottom of the page shows a plain-English summary of the active filters (e.g., `All states · Democratic Party · All groups · 2025-01-01 → 2025-06-01`).

#### KPI Cards

Six summary cards appear at the top of the page:

| Card | What it shows |
|------|--------------|
| **Total Contacts** | Total number of contact interactions (counting repeats) |
| **Unique Contacts** | Number of distinct voters who were contacted at least once |
| **Total Events** | Number of outreach events that generated contacts |
| **Unreliable Conservatives (UC)** | Count of voters in the UC segment |
| **UC Total Contacts** | Total contacts made to UC-segment voters |
| **UC Unique Contacts** | Distinct UC-segment voters contacted |

> **What is an "Unreliable Conservative"?** The UC segment identifies voters classified as "Republican Turnout" in the voter segmentation system — people the campaign is specifically targeting for persuasion or turnout.

#### Charts

**Contact Type** (pie chart) — Shows the share of contacts made by each outreach method:
- Door Knock, Email, Phone, Text, Snail Mail, Face to Face, Other

**Contact Frequency** (pie chart) — Shows how many voters were contacted a given number of times:
- 1 Time, 2 Times, 3 Times, 4+ Times

Hover over any slice to see the exact count.

#### Summary Grid

The "Summary by State, Group & Nation" grid shows one row per (State, Group, Nation) combination. Columns:

| Column | Description |
|--------|-------------|
| State | 2-letter state abbreviation |
| Group | Campaign group |
| Nation | Political organization |
| Total Contacts | All contact interactions for this combination |
| Unique Contacts | Distinct voters contacted |
| Total Events | Outreach events |
| Contacts 4+ Times | Voters reached four or more times |
| Unreliable Conservatives | UC-segment voter count |
| UC Total Contacts | Total contacts to UC voters |
| UC Unique Contacts | Unique UC voters contacted |

Click any column header to sort ascending or descending. Drag column borders to resize. You can download the grid data using your browser's AG Grid export (right-click the grid on supported browsers, or use the built-in grid menu icon if visible).

---

### Map (`/map`)

The map page shows individual voter contacts plotted geographically, with an optional county-level heatmap.

#### Filters

| Filter | Description |
|--------|-------------|
| **State** | Multi-select. Focus the map on one or more states. |
| **Nation** | Multi-select. Filter by political organization. |
| **Group** | Multi-select. Filter by campaign group. |
| **Start Date / End Date** | Optional date range. Restricts which contact records appear. |
| **Boundary Layer** | Dropdown. Choose `None` (no overlays) or `County Boundaries` to show county polygons colored by voter density. |
| **Show Pins** | Toggle. Turn individual voter pins on or off. Useful when showing the choropleth alone, or when pin density makes the map hard to read. |

#### Map Layers

**Voter Pins** — Each dot represents a voter's registered address. Pin color indicates how many times that voter was contacted:

| Color | Meaning |
|-------|---------|
| Light blue | Contacted 1 time |
| Green | Contacted 2 times |
| Orange | Contacted 3 times |
| Red | Contacted 4 or more times |

**County Choropleth** (when Boundary Layer is set to "County Boundaries") — Counties are shaded from light orange to dark red based on how many unique voters were contacted within that county. Hover over a county to see a tooltip with the county name, state, unique voter count, and total contacts.

**Click a county** to open a detail card showing:
- Unique Voters contacted in the county
- Total Contacts made in the county
- Average contacts per voter
- Breakdown by frequency (1, 2, 3, 4+ times)

Use the zoom/pan controls or your mouse scroll wheel to navigate the map.

The status bar shows the number of pins currently displayed and the active filter summary.

---

### Debug (`/debug`)

An internal page showing a raw sample of data from the source table (`contact_analysis_dash`). Intended for developers and data team use to verify the underlying data. No filters are applied on this page.

---

## Common Workflows

### Checking statewide outreach progress

1. Go to **Contacts** (`/analytics`).
2. Select your state(s) in the **State** filter.
3. Review the KPI cards for total/unique contact counts and the frequency pie chart to see how well-saturated the voter file is.
4. Scroll to the summary grid to compare performance across groups and nations within the state.

### Identifying which contact method is driving reach

1. Go to **Contacts** (`/analytics`).
2. Apply any desired filters.
3. Look at the **Contact Type** pie chart. A dominant slice (e.g., Door Knock) indicates that method is generating most activity.

### Finding geographic coverage gaps

1. Go to **Map** (`/map`).
2. Select the target state and set **Boundary Layer** to **County Boundaries**.
3. Light-colored counties have fewer unique voters contacted; dark red counties have the most.
4. Click a pale county to see its raw numbers and assess whether it needs more outreach resources.

### Reviewing weekly contact detail

The weekly breakdown is accessible via the **Contacts** page. The underlying data is aggregated by week starting Sunday. Use the Date Range filter on the Analytics page to narrow to a specific campaign period.

---

## Tips

- **Filters compound**: State + Nation + Group all apply simultaneously. If you see 0 results, check whether your combination exists in the data.
- **Date range is optional**: Leave both date fields blank to include all historical data.
- **Pins can slow the map**: If you have a large dataset, turn off **Show Pins** and use the county choropleth for a faster overview.
- **The UC segment**: The "Unreliable Conservative" metrics are only relevant when your outreach targets Republican Turnout voters. If you're filtering to a nation that does not work that segment, UC counts will be zero.
- **Data refresh**: Query results are cached for up to 5 minutes. If you recently loaded data into Databricks, wait a few minutes and then reload the page to see updated numbers.
