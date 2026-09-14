# Design

Visual system for the vMix Web Switcher. Source of truth is `public/css/style.css`; every value below lives there as a token.

## Overview

A broadcast control surface, not a web app. Dark, machined, high-contrast, built for a thumb on a phone and an arm's-length glance in a control room. Three modes share one token system but read as distinct surfaces:

- **Video Switcher**: dense, urgent, red-forward. Monitors pinned, sources as lit hardware keys.
- **Mic & Audio**: amber-forward mixer. Faders, mute states, VU meters.
- **Preview Wall**: black, edge-to-edge, green-forward monitoring wall. No card chrome, no dashboard feel.

Semantics are fixed everywhere: **red = live / program**, **green = next / preview**, **amber = attention / interactive audio**. Color is never the only signal: every tally state also carries a text label.

## Colors

OKLCH throughout. Cool near-black neutrals at hue 255 (deliberately not warm).

| Token | Value | Use |
|---|---|---|
| `--bg-0` | `oklch(15% 0.014 255)` | App background, inputs |
| `--bg-1` | `oklch(18% 0.016 255)` | Bars, panels, modals |
| `--bg-2` | `oklch(22% 0.018 255)` | Cards, controls |
| `--bg-3` | `oklch(27% 0.020 255)` | Hover, raised keys |
| `--bg-4` | `oklch(32% 0.022 255)` | Pressed / selected |
| `--line-1/2/3` | `32% / 40% / 50%` | Borders by emphasis |
| `--ink-1` | `oklch(97% 0.006 255)` | Primary text |
| `--ink-2` | `oklch(80% 0.012 255)` | Secondary text |
| `--ink-3` | `oklch(68% 0.014 255)` | Dim text, hints |
| `--live` / `--live-fill` | `oklch(58% 0.22 25)` / `50% 0.20 25` | Program, record |
| `--live-ink` | `oklch(72% 0.18 25)` | Red text on dark |
| `--next` / `--next-fill` | `oklch(62% 0.16 155)` / `48% 0.13 155` | Preview |
| `--next-ink` | `oklch(80% 0.14 155)` | Green text on dark |
| `--accent` / `--accent-fill` | `oklch(62% 0.17 250)` / `54% 0.17 250` | Primary actions, focus |
| `--warn` | `oklch(80% 0.15 80)` | Audio accent, badges |
| `--stream-fill` / `--external-fill` / `--fullscreen-fill` | `52% 0.15 230` / `46% 0.12 160` / `52% 0.16 300` | Output badges |

Verified WCAG AA (`/tmp` audit): body text 10:1+, white on live 4.8:1, white on next-fill 5.1:1, white on accent-fill 5.0:1, black on warn 11:1, ink-3 on bg-2 5.2:1. Never rely on red vs green alone.

### Per-mode identity

`--view-accent` is set by which `.view-panel` is visible (`:has()`), and each mode tab carries its own accent underline:

- Switcher: `--live`
- Audio: `--warn`
- Preview: `--next`

## Typography

One system stack, no web fonts (offline LAN tool). Numeric data uses the mono stack with tabular figures.

- `--font`: system UI stack
- `--mono`: `ui-monospace, SFMono-Regular, Menlo, ...`
- Body 15px, line-height 1.4.
- UI/labels: 0.72 to 0.98rem, weight 650 to 800.
- Numbers (tally, clock, counts): mono, weight 900.
- Uppercase reserved for short labels (tabs, tally tags, section headers), never body copy.

## Layout

Mobile-first. The phone is the primary target, not an afterthought.

- **Base (phones)**: the whole Switcher view scrolls so sources stay reachable. Top bar wraps into rows (brand + actions, tabs, output badges); tabs and badges scroll horizontally. Monitors stack full width.
- **≥640px**: Program and Preview sit side by side, transition center spans below them. Labels return.
- **≥1024px**: monitors pin in a 3-column grid (Program / transition / Preview), only the source grid scrolls.

Grids use `auto-fill` with `minmax`; no fixed column counts per breakpoint.

Spacing scale `--s-1..6` (4/8/12/16/20/24). Radius is hardware: `--r-1..3` (2/3/4px);
nothing structural exceeds 4px. Labels carry state, not chips: type legends, status
text, image-source state, the connection pill, and the mode indicator are plain
text, never tinted boxes. The only boxed labels are true tally signals
(ON AIR / NEXT) and the armed REC badge.

z-index is a named scale: `--z-sticky` 100, `--z-dropdown` 200, `--z-overlay` 900, `--z-modal` 1000, `--z-toast` 1100.

## Components

- **Buttons**: machined keys that press in (`inset` shadows only, never a floating
  drop shadow). The Direct / Preview+Take selector is a latched mechanical switch,
  not a glowing pill. Primary actions are flat fills with a dark machined foot,
  no white top highlight.
- **Source key** (`.source-card`): number, type pill, optional overlay/mute badges, thumbnail, title, tally status. Program and Preview are full solid fills with white text and an inset ring, never a gradient or glow.
- **Tally box**: solid tinted panel with a strong signal border and a labeled tag (`PROGRAM / LIVE`, `PREVIEW (NEXT)`).
- **Thumb pill** (`.thumb-mode-pill`): mono status chip. `is-live` green, `is-waiting` neutral, `is-off` dim.
- **Toggle**, **range fader**, **VU meter**, **table**, **modal**, **login**: one shared vocabulary. Every interactive control has hover, focus-visible, active, and disabled states.
- Focus is a single visible treatment: 2px `--accent-ink` outline, 2px offset.

## Motion

- Tokens: `--t-fast` 110ms, `--t-med` 170ms, `--t-slow` 260ms, all `--ease` (ease-out).
- Motion only conveys state: press depth, tally change, live pulse, FTB blink. No entrance choreography, no layout animation.
- Touch has no hover: the Preview wall's "Put Live" affordance is always visible under `@media (hover: none)`.
- `@media (prefers-reduced-motion: reduce)` disables pulses and blinks and flattens all transitions.

## Bans honored

No gradient buttons, no glassmorphism cards, no side-stripe accents, no ghost-card (1px border plus wide soft shadow), no over-rounded cards, no glow spam, no decorative stripes, no all-caps body copy.
