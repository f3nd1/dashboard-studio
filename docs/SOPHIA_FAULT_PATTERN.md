# The pattern behind the three findings

Written because three findings in a row turned out to be the same fault wearing
different clothes, and three remediation conversations would be two too many.

**No fixes here, nothing changed in either repo.** Read from source; the
positional binding is still unconfirmed on the live site pending Test B.

---

## The three instances

| # | Finding | What is joined to what | How the join is made |
|---|---|---|---|
| 1 | Positional binding | a chart ↔ its metric | **array index**, or a regex on the chart's *title* |
| 2 | Diagram/table unit split | a value ↔ its unit | **magnitude guess** (`max<=100`), or dropped entirely |
| 3 | Duplicate implementations | a metric ID ↔ its definition | **nothing** — two definitions coexist, unreconciled |

## The pattern

> **A value is joined to its meaning by convention, and the convention is not
> enforceable by anything in the system.**

In each case a rich object is flattened at an internal boundary into something
that has lost what it means, and the receiving code reconstructs the missing
part by inference. Inference is right most of the time, which is exactly why
these survive: they do not fail, they disagree.

`metricRows` (`:2399`) is the pattern in one function. It builds
`[label, value, metric]` — identity and unit *are* present at index 2 — and then:

```js
const start = (chartIndex * size) % metrics.length;   // chart ↔ metric by position
```

```js
if (/source availability|evidence readiness/.test(title))  // chart ↔ data by title text
```

and all fourteen diagram renderers consume `row[0]` and `row[1]` only, discarding
index 2. The metadata is carried to the boundary and dropped at it.

Two consequences that follow directly, without any new evidence:

- **Adding one metric to a `CONFIG` block re-points every chart on that tab.**
  `metrics.length` changes, so `start` changes for every chart index.
- **Renaming a chart's title can change which data it displays**, because the
  title string is a dispatch key.

Neither raises an error. Both produce a plausible dashboard.

## What structurally produces it

1. **Objects are flattened into tuples at every seam.** A metric enters
   `metricRows` whole and leaves as `[string, number]`. Once identity and unit
   are gone, every downstream consumer must re-derive them, and re-derivation is
   guessing with better manners.
2. **Cross-cutting rules are implemented per-site, not once.** "Apply the unit"
   must hold in fourteen renderers plus two KPI paths. A rule written sixteen
   times is a rule that holds in fifteen places. There is no shared formatter for
   it to live in.
3. **There is no single definition of a metric.** A declarative `CONFIG` engine
   and bespoke Python builders both produce metrics, into the same response, with
   no check that an ID appears once.
4. **Nothing can enforce anything.** No build step, no module system, no types,
   no tests; a 227 KB single file deployed by pasting into a Custom HTML Block,
   and eighteen Server Scripts edited in a browser textarea. Every invariant here
   rests on the memory of whoever edits next.
5. **Failure is silent by construction.** Wrong output is well-formed output.
   None of the three ever throws, logs, or renders an error state.

(4) is why the others persist. In an environment with no external enforcement,
any rule that depends on discipline decays; only rules a program can check about
itself survive.

## The uncomfortable corollary

All three were found the same way: **the same value was rendered twice by
different code, and the two copies disagreed on screen.** The redundancy that
causes the fault is also the only thing that made it detectable — Part 1 and
Part 1B both work by playing one path off against another.

Anything rendered by exactly one path cannot be checked this way at all. So
three is a **floor, not a measurement**, and single-path figures are the larger
unmeasured surface, not the safer one.

## What would have to be true for it to stop

Not fixes — conditions. A change that does not establish one of these buys one
fewer bug and no immunity.

1. **Identity travels with the value.** Charts bind by `metricId`. A chart whose
   metric is absent renders an error, never a neighbour's number. No index
   arithmetic, no title regex.
2. **Unit travels with the value, and is applied in one place.** One formatter,
   called by every renderer and every KPI path. Not "renderers made unit-aware"
   — one function, so the rule cannot hold in thirteen places out of fourteen.
3. **One definition per metric ID**, and the script asserts it about itself at
   runtime. Duplicate IDs between `CONFIG` and a bespoke builder is a set
   intersection — three lines, and it fails loudly on the next paste rather than
   in a board paper.
4. **Nothing is ever inferred from a value's magnitude or a chart's title.**
   Absent metadata means no output, not a plausible guess. This is the same rule
   as the parser's *flag, don't guess*, applied to rendering.
5. **Absence is loud.** Missing, blocked and unavailable each render distinctly.
   A number that is not there must not look like a number that is.

(2) and (3) are cheap. (1) is a real change to how charts are declared. (5) is
partly there already via `status`, and thrown away at the render boundary with
everything else.

## What it means for the three conversations

The two-line bar deletion is still worth shipping — it is harm reduction on the
loudest symptom and it is trivially reversible. But it fixes no cause, and
"unit-aware bar labels" would actively make things worse: one corner correct and
thirteen still dropping units is *harder* to detect than a uniform fault, because
the contradiction that Part 1B relies on disappears.

Ordering, if these become one conversation:

1. **Identity binding** — the only one of the three that puts a *wrong number*
   under a label rather than a wrong label on a right number.
2. **One formatter** — cheap, and it makes the whole unit class impossible
   rather than fixed.
3. **Duplicate-ID assertion** — cheapest of all, and it converts a silent
   divergence into a startup failure.

## And for Dashboard Studio

The same pressure exists on our side, and the decisions already taken push
against it: metric identity lives on the approved DS Metric, label format is
derived from `calculation_type` rather than set per chart, configuration goes in
fields rather than blobs, and the allowlist blocks by default. Those are the same
choices made in the other direction.

The one place we could reintroduce it is the publish contract. **Whatever
Dashboard Studio emits must carry the metric's ID with every chart, and its unit
with every value.** Publishing into a positional array would recreate finding #1
in a new file, correctly generated.
