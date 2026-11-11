# Business: a Workbench plugin for an organisation's parts, with adopted terms

A plugin for any Workbench, written so it can leave with Workbench: nothing in it names the plugin or system that
uses it. It holds a business's map (who, what, how work runs, what it is for) as items in one domain per business,
with terms adopted from published models instead of invented ones, and moves processes in and out as BPMN 2.0.

## The types and their terms

Each type's class comes from the model that defines it best (the choice and its candidates:
`docs/choices/business-vocabulary.yaml` in the repository that uses this plugin, S-86 there). Every type has
`domain` (the business it belongs to) and `description`.

| Type | Term | Model | Other fields |
| --- | --- | --- | --- |
| `organisation` | `org:Organization` | W3C ORG (PDDL) | legal_name, identifier, site |
| `unit` | `org:OrganizationalUnit` | W3C ORG | |
| `role` | `org:Role` | W3C ORG | responsibilities |
| `person` | `foaf:Person` | FOAF 0.99 (CC BY 1.0), which ORG builds on | |
| `resource` | `vf:EconomicResource` | Valueflows 1.0.0, REA in OWL (CC BY-SA 4.0) | kind, quantity |
| `process` | `bpmn:Process` | BPMN 2.0.2 | trigger, outcome, bpmn (what BPMN XML needs: ids, lanes, data, the diagram's ids) |
| `activity` | `bpmn:Activity` | BPMN 2.0.2 | kind (the BPMN element), bpmn_id, shape, outgoing (flows), data (associations), minutes, bpmn |
| `event` | `ocel:Event` | OCEL 2.0 (CC BY 4.0) | activity, time, attributes, objects (qualified, OCEL's E2O) |
| `decision` | `dmn:Decision` | DMN 1.5 | question, answers, logic, dmn_id |
| `document` | `foaf:Document` | FOAF 0.99 | kind, format |
| `measure` | `schema:StatisticalVariable` | schema.org V30.1 (CC BY-SA 3.0) | definition, unit, better, stat |
| `goal` | `bmm:Goal` | BMM 1.3, as the BMMOntology OWL (MIT) | statement, target, due |

BPMN, DMN and OCEL publish XML or JSON schemas, not RDF: their terms are their metamodels' names under their
namespaces (`ocel:` is written that way here; OCEL publishes no namespace). Relations between items are
`unitOf`, `memberOf` (ORG's), and `holds`, `roleIn`, `partOf`, `flowsTo`, `performedBy`, `uses`, `produces`,
`makes`, `ownedBy`, `occurrenceOf`, `concerns`, `measures`, `serves`, `goalOf` (`biz:`, each said in
`vocabulary.yaml` in terms of the models). `mappings.sssom.tsv` maps every type's term, and a few relations, to
the terms of the models not picked (schema.org, Valueflows, BPMN, OCEL, BMM), loaded into `wb.mapping`.

## A business's map

One YAML file per business: its `domain`, then its items by type, each under a local name, with its fields and
its relations (a relation is a key naming its predicate, its value one local name or a list):

```yaml
domain: harbour-bakery
items:
  unit:
    bakehouse: {title: Bakehouse, unitOf: harbour-bakery}
```

`business:map` writes it as items (slug `<domain>.<name>`, every value a claim citing the file), and
`export-map` writes the domain back in the same form, so a map makes the round trip. An import speaks for its own
domain only: an item gone from the file is retracted there and nowhere else.

## BPMN 2.0

`business:bpmn` reads a BPMN 2.0 XML file into a domain: each process is a `process`, each flow node (task, event,
gateway) an `activity` with its sequence flows, each lane a `role` (the same role as the map's, by name), each
data object reference a `document`, and the diagram's shapes and edges kept. `export-bpmn` writes the process back
with its diagram; a process mapped without one is laid out left to right. The subset kept is flow nodes,
sequence flows (names, conditions, defaults), lanes, data objects and their associations, event definitions, a
pool per process and the diagram; anything else in a file is named in the run's log and left out.

```
python3 business_plugin.py export-map DOMAIN           # WORKBENCH_ADMIN_URL set
python3 business_plugin.py export-bpmn PROCESS-SLUG
```

## Check

`tests/test_business.py`: every type's term is a picked model's and loaded, with its mappings; the demo
business (`demo/harbour-bakery.yaml`) imports, exports to the same map, re-imports changing nothing, and makes
the same entities in an empty Workbench; another domain's import leaves it alone; the demo process
(`demo/wholesale-order.bpmn`) imports and exports with the same nodes, flows, lanes, data, defaults, event
definitions and diagram, and re-imports changing nothing. That a BPMN tool opens the files is checked with
bpmn-moddle, the parser bpmn.io's modeler reads with (in the using repository: `scripts/trials/bpmn-opens`).
