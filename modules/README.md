# Substrate's modules

The glue between kernel, Morphogen and the gateway. Each is a kernel module (kernel's
`modules/_template`, a `module.yaml` valid against `vendor/kernel/kernel/schemas/module.schema.json`,
its own `kkm_*` role, writes only by `submit_change_set`). Each starts as a brief; tests come next, then a
builder makes them pass, then Morphogen judges it (Morphogen's demos rule).

| Module | Fills | Brief |
| --- | --- | --- |
| `encoder-morphogen` | Morphogen's verdicts as claims (S-08) | [BRIEF](encoder-morphogen/BRIEF.md) |
| `encoder-backstage` | `catalog-info.yaml` as system-structure claims (S-09) | [BRIEF](encoder-backstage/BRIEF.md) |
| `resolver` | entity resolution: kernel M6-T9, judged by Morphogen (S-07) | [BRIEF](resolver/BRIEF.md) |
| `dispatcher` | coordination: one task per scope, ordered, within budget | [BRIEF](dispatcher/BRIEF.md) |

A module that turns out general enough moves to kernel's `modules/` by pull request there; the substrate
then uses it from `vendor/kernel`.
