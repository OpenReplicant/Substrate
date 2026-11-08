# Gateway metrics into kernel

Kernel's `observer-prometheus` already records Prometheus answers as observed claims, one per service,
property and window (kernel D-52). The substrate only gives it different queries.

1. Start the stack (`scripts/up.sh`; the queries need Prometheus, which is in it), send one request through Bifrost, and read
   `curl -s http://127.0.0.1:${BIFROST_PORT:-8090}/metrics | grep ^bifrost_` to confirm the metric names in
   `queries.yaml`.
2. Propose the four properties (`model-cost-usd`, `model-input-tokens`, `model-output-tokens`,
   `model-errors`) as `sosa:ObservableProperty` terms through kernel's review lane, next to
   `ontology/observables.ttl`'s existing ones.
3. Uncomment the four gateway queries at the end of `queries.yaml`. The observer already runs in the kernel
   container with this file (`kk serve` part `observer`, `KK_QUERIES=/observer/queries.yaml`, S-33), where it
   records the collector's call graph for map drift; restart the kernel service to pick up the change.

Not done yet: steps 1 and 2 need a running stack.
