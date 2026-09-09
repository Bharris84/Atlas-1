# @atlas/shared-types

TypeScript types shared between the Atlas API and the web app.

Two conventions encoded here are worth knowing before using them:

**Money and ratios are strings.** The backend computes in `Decimal`. Parsing
`"150000.00"` into a JavaScript float on the way in would reintroduce exactly
the imprecision the financial engine exists to avoid. Convert to a number only
at the point of display.

**`null` means unknown, never zero.** A null DSCR is a property with no debt.
A null cash-on-cash is a deal with no cash left in it. The UI renders these as
"—", and must never substitute a `0`.
