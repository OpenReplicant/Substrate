# The judge's cases

Cases a component's author never sees (docs/framework.md, "The judge is an interface"). Only the judge's
container mounts this folder (compose service `judge`); authors run elsewhere and read only the training slice of
the record (`env.training_turns`). Each file is one component's labelled set.

- `cases/voice_reply.jsonl`: what the owner might say aloud, and whether the voice head should hand it to the
  companion (`expect_handoff`): small talk and quick facts it answers itself; anything needing tools, files, the
  web, the machine, a schedule or a long answer it hands over.
