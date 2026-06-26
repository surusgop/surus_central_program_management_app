# Installing this as a Claude Code skill

This folder is a self-contained **Agent Skill**. Drop it into your repo (or your
user skills dir) and Claude Code will be able to design on-brand
Surus Central Program Management interfaces.

## Install

Copy the whole folder into one of these locations, renaming it to match the skill:

```bash
# Project-scoped (committed to your repo, shared with the team)
mkdir -p .claude/skills
cp -R surus-central-design-system .claude/skills/surus-central-design

# — or — user-scoped (available in every project on your machine)
mkdir -p ~/.claude/skills
cp -R surus-central-design-system ~/.claude/skills/surus-central-design
```

The skill's entry point is **`SKILL.md`** at the root of this folder — Claude Code
reads its front-matter (`name: surus-central-design`) to discover and invoke it.

## Use

In Claude Code, just describe what you want, e.g.:

> "Add a new 'Events' summary page to the outreach dashboard, matching the
> existing Contacts page."

Claude will load the skill, read `README.md` + `colors_and_type.css`, and either
produce HTML mocks or write production code against the Flatly/Bootstrap stack.

## What's inside

| Path | Purpose |
|---|---|
| `SKILL.md` | Skill manifest + quick orientation (entry point) |
| `README.md` | Full brand guide: product context, content & visual foundations, iconography, manifest |
| `colors_and_type.css` | Color + type tokens (base + semantic) — load first |
| `fonts.css` | Lato (`@import`) + Bootstrap Icons CDN note |
| `assets/app-global-overrides.css` | The product's verbatim global CSS overrides |
| `preview/` | Specimen cards (palette, type, spacing, components) |
| `ui_kits/dashboard/` | Interactive recreation + reusable JSX components |

## Source

Built from `surusgop/surus_central_program_management_app` @ `dev`
(https://github.com/surusgop/surus_central_program_management_app/tree/dev). The live app is
Plotly Dash + Bootstrap 5 + Bootswatch Flatly + Bootstrap Icons + Plotly +
AG Grid (Alpine). Recreate against that stack for highest fidelity.
