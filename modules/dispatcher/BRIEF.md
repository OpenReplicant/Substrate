# dispatcher: coordination

**For:** with triggers waking modules and skills on their own, something has to keep changes attributable
and stop agents colliding or looping. In the Viable System Model this is System 2, and it is the thinnest
part of the substrate today.

**Shape:** a reactor on kernel's detectors (M6-T0, D-86): it reads detector events in order, under its own
role, and submits a task claim or nothing.

## Rules

1. One open task per scope (a system or cell). A second trigger on the same scope waits or merges into it.
2. Tasks are ordered by the goals they cite; a task that cites none is not started.
3. A scope's model budget (from the gateway's cost claims, S-05) caps how many tasks start in a window.
4. A change that re-triggers its own scope more than N times in a window stops and asks a person.
5. Doing nothing is a recorded decision, with its reason.

## Tests first

- two triggers on one scope give one task;
- a task with no goal is not started and says why;
- a loop on one scope stops at N and raises a question;
- over budget, nothing starts and the reason cites the cost claims.

## Depends on

Kernel M6-T0 (detectors and the applied cursor) and goal claims (no vocabulary yet; propose one through
kernel's review lane).
