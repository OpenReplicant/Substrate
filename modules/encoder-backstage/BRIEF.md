# encoder-backstage: the catalog as system-structure claims

**For:** teams already keep a map in `catalog-info.yaml`. Read it into kernel so the map is cited,
belief-scored and reviewable like everything else, and so Morphogen's verdicts and kernel's observations
attach to the same nodes (S-09). The substrate's own catalog is the first input.

**Pattern:** kernel's `self-encoder` (D-26, D-68): a command that reads files and submits one change set
per file; re-reading a changed file supersedes what it said.

## Mapping (to kernel's kk-tosca profile, D-07)

| Backstage | Claims |
| --- | --- |
| Domain, System, Component, Resource | an entity typed `kkt:NodeTemplate`, its kind as the node type |
| `system`, `domain`, `subcomponentOf` | containment, as the profile's sub-topology terms |
| API, `providesApis`, `consumesApis` | `kkt:CapabilityDefinition` and `kkt:RequirementDefinition`, fulfilled by `kkt:fulfills` |
| `dependsOn` | `kkt:dependsOn` |
| owner, lifecycle | ORG and lifecycle claims; owner links to the person or group entity |
| `substrate.dev/*` annotations | intent and fill as qualifiers; candidates as claims about the software |

Every claim cites the file and the entity's line as its reference (artifact plus quote), evidence type
`deterministic`.

## Tests first

- the substrate's own `catalog-info.yaml` gives the expected node count (30 components, 5 resources, 5 systems, 1 domain, 10 APIs) and
  every relation, each citing its line;
- re-reading an unchanged file submits nothing; removing an entity supersedes its claims, deleting none;
- an unknown kind or a dangling ref becomes a finding, not a crash;
- `kk explain` on any node shows the file and line it came from.

## Check before building

Read `ontology/kk-tosca.ttl` for the exact containment and fulfilment terms; the table above names them
from the term list, not from their definitions.
