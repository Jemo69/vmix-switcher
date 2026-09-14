# Product

## Register

product

## Users

Live video production operators and crew: a director running the show, plus camera and audio crew sharing control from the same network. They use phones, tablets, and touchscreens on the same LAN as the vMix machine, often standing, often one-handed, often in a dark control room or a noisy on-location setup. They are mid-show: the operator needs to find a source and cut to it in under a second, without looking away from the output.

The job to be done: control a vMix live production from any device on the local network as fast and as unambiguously as a hardware switcher panel, without touching the vMix PC itself.

## Product Purpose

A web switcher for vMix that runs on any device on the LAN. It mirrors live Program and Preview, lets the operator switch sources (direct or preview/take), drive transitions, control mic and audio levels, and watch a full multiviewer, all synced in real time across every connected device. Success looks like: an operator never hesitates about what is live, never mis-cuts because a control was ambiguous, and never has to walk to the vMix machine.

## Brand Personality

Tactile, urgent, game-day. The voice of a broadcast control surface: direct, operator-to-operator, zero filler. The interface should feel like well-machined hardware under your hand, not a web page. Energy comes from contrast, weight, and instantaneous state feedback, never from glow or decoration.

## Anti-references

- Generic SaaS dashboards: gradient buttons, glassy floating cards, blue-purple blobs, metric-hero templates, decorative glassmorphism.
- Gamer / RGB aesthetics: neon glow spam, rainbow accents, gratuitous gradients, animated chrome.
- Legacy broadcast software: skeuomorphic grey bevels, cramped dense panels, tiny unlabeled controls.
- Anything where the state (live / next / muted / recording) is ambiguous at arm's length.

## Design Principles

1. **State is the design.** What is live, what is next, what is muted, what is recording must be readable in a glance at arm's length. Color means exactly one thing and is never used decoratively.
2. **Built for the cut.** Every primary action is reachable one-handed with a large touch target and gives instant, unmistakable feedback. No destructive action without confirmation.
3. **Hardware, not web page.** Tactility comes from press depth, crisp edges, and tight typography, not from glow, gradients, or glass.
4. **One system, distinct modes.** Switcher, Audio, and Preview share one token set, one component vocabulary, and one motion language, but each mode has its own identity: Video Switcher is a dense, urgent control panel; Preview is a calm, immersive monitoring wall. An operator should know which mode they are in from a single glance, not just from the tab bar.
5. **Mobile first, not mobile tolerated.** Crew switch from phones as often as desktops. Layouts, touch targets, and control order are designed for a thumb on a phone in portrait, then scaled up, not the reverse.
6. **Never ambiguous, never color-only.** Tally and mute states are always carried by a label or shape as well as color, so a color-blind operator loses nothing.

## Accessibility & Inclusion

Target WCAG 2.1 AA. Body and label text must meet 4.5:1 against its surface. Tally and mute states must never be conveyed by red/green alone: pair every color state with a text label or icon. All interactive controls need a visible focus state, touch targets of at least 44px on primary actions, and `prefers-reduced-motion` alternatives for every animation. The UI must stay usable at tablet and phone widths in portrait and landscape.
