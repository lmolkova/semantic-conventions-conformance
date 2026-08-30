# UI mockups

Throwaway prototypes for the conformance site. Not wired into the build or the
published Pages site.

## conformance-site.html

Verdict-first navigation over the report. Open the file directly in a browser -
it is self-contained, with a snapshot of `data/conformance.json` inlined, so it
needs no server.

The verdict rule it demonstrates: a run is **red** when a whole signal (spans or
metrics) is missing, **yellow** when any violation is found on the signals it
does emit, **green** otherwise. `missing_attribute` findings never affect the
verdict; they appear as blanks in the parity grid instead.

Views:

- **Overview** - counts, a tile per domain, a strip per signal, and every run as
  either a card wall or a sortable scoreboard.
- **Domain** - the same board scoped to one domain, plus the signal parity grid
  over that domain's runs.
- **Library** - verdict per instrumentation with its violation breakdown, plus
  the parity grid with one column per instrumentation of that library.
- **Signal** - one signal, every run that emits it across all domains, filterable
  by language.
- **Detail panel** - per signal, every attribute the registry declares, grouped
  by requirement level, marking what was emitted and what never arrived.
