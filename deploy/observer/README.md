# Gateway metrics into kernel

Kernel's `observer-prometheus` already records Prometheus answers as observed claims, one per service,
property and window (kernel D-52). The substrate only gives it different queries.

1. Start the stack (`scripts/up.sh`; the queries need Prometheus, which is in it), send one request through Bifrost, and read
   `curl -s http://127.0.0.1:${BIFROST_PORT:-8090}/metrics | grep ^bifrost_` to confirm the metric names in
   `queries.yaml`.
2. Propose the four properties (`model-cost-usd`, `model-input-tokens`, `model-output-tokens`,
   `model-errors`) as `sosa:ObservableProperty` terms through kernel's review lane, next to
   `ontology/observables.ttl`'s existing ones.
3. Install the observer with these queries mounted in place of its own `queries.yaml`, as kernel's devops
   demo installs it: `kk module install repos/kernel/modules/observer-prometheus`, then its compose file
   from `repos/kernel/deploy/modules/`.

Not done yet: steps 2 and 3 need a running stack; the session that wrote this had none.
