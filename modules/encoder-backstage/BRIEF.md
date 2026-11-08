# encoder-backstage: the catalog as claims, in Backstage's own terms

**Built in kernel** (kernel D-100, `repos/kernel/modules/encoder-backstage`, with `map-drift` and the metrics
observer's call edges); substrate runs it with `scripts/map.sh` (S-33). This brief records what it was for.

**For:** teams already keep a map in `catalog-info.yaml`. Read it into kernel so the map is cited,
belief-scored and reviewable like everything else, and so Morphogen's verdicts and kernel's observations
attach to the same nodes (S-09). The substrate's own catalog is the first input.

**Vocabulary:** the catalog stays in Backstage's terms (owner, 2026-11-07: "left in its original form"): kernel's
`backstage` pack names its kinds, its well-known relations (`ownedBy`, `partOf`, `providesApi`, `consumesApi`,
`dependsOn`, `memberOf`, `childOf`) and its fields (`type`, `lifecycle`, `tag`, `annotation`). Kernel's mappings
pack relates them to kk-tosca (system structure) and ORG (groups) with SKOS, so a module that reasons in
kk-tosca, such as `map-drift`, reads a Backstage catalog through the mappings. Components and resources are
`urn:kk:node:<name>`, the node names other modules use.

**Checks (kernel):** every claim deterministic and citing its line; an unchanged file submits nothing, a changed one
supersedes or retracts; an unknown kind or a dangling ref is a finding, not a crash; and end to end, Substrate's
catalog (68 entities, 696 claims) with observed calls gives the first gap in the review lane, citing both sides.
