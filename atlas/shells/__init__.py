"""
atlas.shells — the operations the pipeline is built from (docs/REBUILD.md §2.3).

A shell does one thing, has a card in registry/shells/ naming its contract,
invariants, refusals and benchmark, and knows nothing about which dataset it
serves. Three kinds, one folder each:

  acquire/    source -> bytes on disk or in memory; the only code that touches the network
  transform/  frame(s) -> frame; pure
  check/      frame -> pass or a named refusal

Project-specific code (the MPO page parser, the province page) stays in
atlas/readers/ until it moves to atlas/project/.
"""
