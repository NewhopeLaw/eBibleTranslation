# UI audit checklist

Before presenting any screen, component or front-end change, audit it against
these seven points as a Staff Product Designer and Design Systems Lead would.
Do not merely verify visual aesthetics: ask whether incomplete product thinking,
unstated assumptions or missing edge states are hiding behind a polished
surface. Present the work together with the audit.

## 1. Unstated assumptions and default scenarios

- Identify what user, business or device context was assumed without being
  specified: a single user rather than a group, a signed-in user, an ideal
  network or device, a phone in portrait, one language at a time.
- Surface every unverified assumption explicitly and say how the design holds
  up if it changes.

## 2. Complete state coverage, beyond the happy path

Does the screen only show the ideal, populated state? Define and handle:

- Empty / zero state — the first open, nothing translated in the chosen
  language, a search with no hits, a chapter with no notes.
- Loading / skeleton / async state.
- Error / offline / validation-failure state.
- Extreme data — huge numbers, zeros, the longest chapter, pagination limits,
  200 % zoom.

## 3. Visual hierarchy and decision bottlenecks

- Name the single primary call to action on the screen.
- Check whether competing cards, badges or secondary buttons dilute it.
- Destructive or irreversible actions are clearly separated and de-emphasised.

## 4. Flow continuity and reversibility

- Say how the user arrived at this screen and exactly where they go next, both
  on completing and on abandoning the action.
- Verify the escape hatches: cancel, back, close, undo — without losing unsaved
  progress or the reading position.

## 5. Content stress-testing and data realism

Test layouts against realistic, messy data rather than sanitised placeholders:

- Long localised strings (German or Finnish expansion; here also Hebrew and
  Aramaic right to left, Thai without word spaces, Japanese with ruby).
- Truncation versus multi-line wrapping in cards and headers — decided, not
  accidental.
- Missing optional fields: no gloss, no translation, no built layer.

## 6. Accessibility and usability (WCAG 2.1 AA)

- Text contrast of at least 4.5 : 1 against its background; no low-contrast
  grey on white.
- Every tappable or clickable control has an effective target of at least
  44 × 44 px.
- Status is never conveyed by colour alone: add shape, weight, an icon or text.

## 7. Component feasibility and design-system conventions

- Prefer standard platform or design-system primitives (native select, dialog,
  disclosure) to bespoke, over-complex components; justify each custom one.
- Responsive behaviour is structurally sound: breakpoint collapse, sticky bars,
  scroll containment, no layout shift, no horizontal overflow.

## Output

1. **The screen / implementation** — the proposed structure or code.
2. **The 7-point self-audit report** — concise: where trade-offs were made,
   which edge states still need a visual, and which assumptions need a human
   product decision.
