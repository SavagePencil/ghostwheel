# Graph validation report

**Summary:** 2 errors · 2 warnings · 1 info
**Graph:** 2 nodes (Blade: 1, Herb: 1), 0 edges, 1 placeholder nodes

## Dangling references (2)

| Severity | File | Location | Detail |
| --- | --- | --- | --- |
| error | data/herbs.csv | row 3 | Nightbell names a Region 'Mistfen' that no row defines |
| warning | data/blades.csv | row 1 | Falchion cites a Smith nobody forged |

## Unparsed cells (kept verbatim) (1)

| Severity | File | Location | Detail |
| --- | --- | --- | --- |
| warning | data/herbs.csv | row 5 col hue | kept verbatim: 'pale \| ash' |

## Ontology problems (1)

| Severity | File | Location | Detail |
| --- | --- | --- | --- |
| info | graph/ontology.yaml | concepts.Herb | no lens declared |

## sky-colour (1)

| Severity | File | Location | Detail |
| --- | --- | --- | --- |
| error | notes.md | - | an unknown category lands in its own section |
