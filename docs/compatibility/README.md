# What Substrate can talk to

Substrate doesn't replace the runtime a system already uses. It describes the system as a map in the Knowledge
Kernel, and a **decoder** writes that map out in the runtime's own format; an **encoder** reads the runtime's state
and history back in (S-174). So a business that already runs Kubernetes, Camunda or Step Functions keeps it: the
map is the same, and only the decoder changes. Compose is the first runtime Substrate decodes to, because Substrate
itself runs on it.

A licence decides only whether a part can be one of Substrate's **defaults** (rule 7: open licences; GPL only in
its own container, S-146). Any runtime below can be a **target** for a business that already runs it.

The facts (formats, APIs, licences) were read from each project's docs and GitHub on 2026-11-22;
`runtimes.json` holds them with their sources, as entries for the kernel. The agent harnesses surveyed the same day
are in `scripts/trials/harness/candidates.json`.

## Services and processes

| Runtime | Native format | Read back | Licence | Default? |
| --- | --- | --- | --- | --- |
| Docker Compose / Podman | `compose.yaml` (Compose Specification, JSON schema) | `compose ps --format json` | Apache-2.0 | **yes (now)** |
| Podman Quadlet / `kube play` | Quadlet units; Kubernetes YAML (a subset) | Libpod REST API | Apache-2.0 | yes |
| process-compose | `process-compose.yaml` | REST (OpenAPI) | Apache-2.0 | lead candidate for processes |
| systemd | unit files | `systemctl show` | LGPL-2.1+ | yes |
| Kubernetes, k3s | YAML manifests (OpenAPI schema) | the API server | Apache-2.0 | yes |
| Docker Swarm | Compose files as stacks | `docker service ls` | Apache-2.0 | yes |
| s6, supervisord | service directories; INI | `s6-svstat`; XML-RPC | ISC; BSD-style | yes (check supervisord's clause) |
| Nomad | HCL jobspec | HTTP API | BUSL-1.1 | target only |

## Workflow orchestrators

| Orchestrator | How a workflow is defined | Interchange | Licence | Default? |
| --- | --- | --- | --- | --- |
| Flowable | BPMN 2.0 XML | **BPMN** | Apache-2.0 | yes |
| Kestra | YAML flows | | Apache-2.0 | yes |
| Argo Workflows | Kubernetes YAML | | Apache-2.0 | yes |
| Conductor | JSON definitions | | Apache-2.0 | yes |
| Node-RED | flow JSON | | Apache-2.0 | yes |
| Apache Airflow, Prefect, Dagster | Python | | Apache-2.0 | yes (code, not files) |
| Temporal, Hatchet | code (several languages) | | MIT | yes (code, not files) |
| Windmill | code | | AGPL-3.0 + proprietary EE | owner's call |
| Camunda 8 | BPMN 2.0 | **BPMN** | Camunda License | target only |
| n8n | visual, JSON | | Sustainable Use License | target only |
| Restate, Inngest | code | | BUSL-1.1, SSPL | target only |

Where a workflow is code, not a file, Substrate can read its runs (encode) but writes it only through generated code
or the orchestrator's API; the file-defined ones (BPMN, YAML, JSON) are decoded directly.

## Cloud services (targets)

| Service | Format |
| --- | --- |
| AWS Step Functions | Amazon States Language (JSON) |
| Azure Logic Apps | Workflow Definition Language (JSON schema) |
| Google Cloud Workflows | YAML or JSON |
| AWS ECS; Google Cloud Run | task definitions (JSON); Knative Service YAML |
| Cloudflare Workflows; Azure Durable Functions | code |

## Interchange standards

| Standard | Describes | Note |
| --- | --- | --- |
| BPMN 2.0 (OMG) | processes | the kernel reads it (`encoder-bpmn`, the BBO pack); Camunda and Flowable run it |
| CNCF Serverless Workflow 1.1 | workflows | no orchestrator above confirmed as an adopter |
| Compose Specification | deployments | Substrate's own |
| OASIS TOSCA 2.0 | deployments | the kernel's `kk-tosca` mirror |
| CWL 1.2 | workflows | |
| W3C WoT Thing Description 1.1 | interfaces: affordances and protocol forms | blocks follow its shape (S-164) |
| OpenAPI 3.2, AsyncAPI 3.1 | HTTP and message APIs | AsyncAPI describes a queue link |
| CloudEvents 1.0 | event envelopes | |
| OpenTelemetry (GenAI conventions) | telemetry | |
| Model Context Protocol | agent tools | |
| W3C PROV-O | provenance | the kernel's |
| P-Plan | plans | **CC BY-NC-SA 2.0**: the owner decides how plans refer to it |
