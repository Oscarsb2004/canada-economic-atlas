"""
atlas.readers — one module per publisher, for what only that publisher needs.

A reader turns the bytes an acquire shell fetched into this project's records:
the Major Projects Office's page markup, StatCan's cube CSV, Transport Canada's
register workbook, the Fiscal Reference Tables. What is general lives in
atlas/shells/; what is true of one publisher lives here.

(Was atlas/readers/ until step S8 of docs/REBUILD.md. It was renamed because
"sources" now means the source cards in registry/sources/, and one word for two
things is how a registry entry and a parser get confused.)
"""
