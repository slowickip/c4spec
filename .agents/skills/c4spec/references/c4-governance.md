# C4 modeling policy (initial, reviewable)

Sources: https://c4model.com/diagrams and
https://c4model.com/diagrams/checklist

## C4 levels of abstraction (zoom, not delivery phases)

| Level | Standard diagram | Scope and question | Typical content |
| --- | --- | --- | --- |
| **L1 — System Context** | System context | **One software system:** who uses it and which external systems does it interact with? | The system as a single box, people, external software systems, and their relationships. No internal applications or databases. |
| **L2 — Container** | Container diagram | **Inside that software system:** which independently runnable/deployable applications and data stores collaborate? | APIs, workers, frontends, databases and brokers, with their responsibilities, technologies and connections. *Container* does not mean Docker. |
| **L3 — Component** | Component diagram | **Inside one selected container:** what major logical components divide its responsibilities? | Significant modules/services/handlers and their dependencies; not every class, function or file. |

The C4 model also defines an optional **L4 — Code** zoom (e.g., classes or other implementation structures). Most teams need only L1 and L2. Add L3 only when a particular container's internals are important to an architectural decision.

**Levels describe the scope of a diagram, not a label attached to an element, a mandatory hierarchy of files, a maturity score or a C4Spec workflow stage.** A LikeC4 `system` element is not automatically a complete L1 context *diagram*; a view showing the system's containers is usually L2 even when it includes external actors. Focused, dynamic and deployment views can supplement these levels rather than forming additional numbered levels.

When reviewing an unfamiliar LikeC4 view, ask: **what boundary is zoomed into, and what details are intentionally hidden?** For structural L1/L2/L3 views, prefix the **human-visible LikeC4 `title`** with `L1 —`, `L2 —` or `L3 —`, then a meaningful subject (e.g. `L2 — Online Shop: container overview`). Keep the stable `view` identifier unchanged; it is used by export tooling and references. A focused view of interactions between L2 containers remains L2. Don't force L1/L2/L3 onto dynamic or deployment views that don't fit these three structural zoom levels.

## Terms that matter

- **Software system**: highest meaningful software boundary.
- **Container**: a separately runnable/deployable application or data store;
  it does *not* mean a Docker/Kubernetes container.
- **Message broker**: a separately running RabbitMQ/Kafka broker service can be a C4 container (application/data store). An individual named queue/topic/exchange managed by that service is typically configuration, not an independently running/deployable container; model it only when its distinct architectural significance justifies deeper detail.
- **Component**: a logical functional grouping *inside a container*.
  Do not use it as a synonym for independently deployed microservice.
- **Code**: classes/functions and implementation details, normally omitted from
  durable architecture models.
- **Dynamic view**: interaction sequence when order matters.
- **Deployment view**: meaningful execution environment mapping, *not* a dump
  of Kubernetes or Terraform configuration.

## Before adding an element

Ask whether it represents an independent architectural responsibility, an
important ownership/trust boundary, state ownership, failure/recovery domain
or externally meaningful contract. If not, keep it in code/configuration.

Default depth is context and container. Decompose a container only to answer
a concrete design question. Prefer a handful of focused views over one large
view. Twelve nodes is a **review warning**, not a hard C4 requirement.

## Review checklist

1. A view has a meaningful name, type/scope and clearly described purpose.
2. Each modeled element has a meaningful type, name and **responsibility**.
   Technology is present when it clarifies a container/component.
3. Each relationship has a direction and an intentional description; provide
   technology/protocol for cross-boundary integrations where known.
4. Use consistent notation and communicate non-obvious color/shape meanings
   through a legend. C4 terminology must be unambiguous.
5. The same architectural fact has one owner: model nodes/edges in LikeC4;
   APIs in OpenAPI/protobuf; deployment parameters in IaC; behavioral promises
   in contracts/tests. Prefer links over pasted configuration.
6. Omission does *not* prove access denial. Negative security properties and
   failure handling require explicit behavioral constraints with verification.
7. Do not silently update the approved architecture from code-derived diagrams;
   inferred structure is evidence for review, not approved design.

## What tooling can and cannot decide

LikeC4 validates syntax and references. `scripts/check.py` warns about missing
names/descriptions, relationships without labels, potentially too-detailed
names, overloaded views and absent optional technology. The human reviewer
decides whether each element belongs at that abstraction level. Treat the
scripts as **advisory**; don't use passing checks as proof of correctness.

New changes should be small and directed. Existing models should migrate
gradually; avoid mass churn simply to satisfy guidelines.
