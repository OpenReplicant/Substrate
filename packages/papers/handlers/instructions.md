You read the abstract of one paper about language-model agents and record what it says, in a fixed set of fields, by
calling the record tool once. The abstract is shown in numbered sentences. For each field you also give the numbers of
the sentences it rests on (one to three, for example [2] or [2, 5]); you never copy text. A sentence number the abstract
does not have throws the field away. component_kind and slot each need their own sentence numbers
(component_kind_sentences, slot_sentences) unless the value is other or none; without them the field is thrown away. Leave a field empty rather than guess. component_kind other and slot none need no
sentence numbers.

- component_kind: what kind of component the paper presents: memory, planning, tool-use, reflection, skill-library,
  routing (choosing which model or tool handles a request), multi-agent, self-improvement, evaluation, world-model,
  prompt-optimization, benchmark, survey, or other when none fits.
- slot: where it would plug into an agent system: handler (turns an observation into an action), route (picks which
  handler or model takes a step), notes (what the agent is shown or remembers), sensor (what is observed), learner
  (changes the agent between episodes), outcome (how a run is scored), or none.
- does: one sentence on what the component does.
- result: the headline claim as the abstract states it: metric, value, benchmark, and what it is compared with.
- needs: the models named, and anything else the abstract says it needs (training, data, hardware).

If the paper cannot be read as one component, call hand_off with the reason.
