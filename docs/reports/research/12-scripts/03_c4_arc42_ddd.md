# Documentation shape for a multi-repo system (subagent research, 2026-09-08)

## C4 (c4model.com)
- Software System: highest abstraction; "Perhaps the code for that software system resides in a single source code repository"; boundary often = team boundary — https://c4model.com/abstractions/software-system
- Container: "Not Docker!" — an application or data store, "something that needs to be running"; "a runtime construct... whereas Java JAR files... modules... are used to organise the code" — https://c4model.com/abstractions/container
- Component: "grouping of related functionality encapsulated behind a well-defined interface"; "not separately deployable units" — https://c4model.com/abstractions/component
- Diagrams: System Context (scope: one system; audience everybody) https://c4model.com/diagrams/system-context ; Container https://c4model.com/diagrams/container ; Component ("consider automating their creation") https://c4model.com/diagrams/component ; System Landscape ("a system context diagram without a specific focus") https://c4model.com/diagrams/system-landscape ; Dynamic https://c4model.com/diagrams/dynamic ; Deployment https://c4model.com/diagrams/deployment
- Microservices: within one team, "Each microservice is modelled as a group of one or more containers"; when owned by separate teams, each is "promoted" to a software system — https://c4model.com/abstractions/microservices
- UNVERIFIED: any explicit c4model.com statement on "how many containers per repo".

## arc42 (docs.arc42.org)
- S3 Context & Scope: business context (partners, inputs/outputs) + technical context (channels, mapping table); "Show all (all!) external interfaces!" — https://docs.arc42.org/section-3/
- S5 Building Block View: level 1 whitebox overall + blackboxes; level 2/3 zoom; blackbox template: purpose, interfaces, location, open issues — https://docs.arc42.org/section-5/
- S7 Deployment View: infrastructure + mapping of building blocks to nodes — https://docs.arc42.org/section-7/
- S8 Cross-cutting concepts — https://docs.arc42.org/section-8/ ; S9 Architecture decisions (ADRs) — https://docs.arc42.org/section-9/

## DDD context mapping
| Pattern | Definition (Evans via ddd-crew) | CML | Static evidence? |
|---|---|---|---|
| Partnership | mutual delivery dependence of teams | `A [P]<->[P] B` | NO - human declaration |
| Shared Kernel | explicit shared subset of model, kept small | `A [SK]<->[SK] B` | PARTLY: shared library artifact consumed by both; "both teams commit" needs git history / CODEOWNERS |
| Customer/Supplier | downstream priorities factor into upstream planning | `Down [D,C]<-[U,S] Up` | NO - planning relationship; human |
| Conformist | downstream adheres to upstream model | `Down [D,CF]<-[U,OHS,PL] Up` | PARTLY: consumer imports producer DTO/model artifact directly |
| Anticorruption Layer | isolating translation layer in downstream | `Down [D,ACL]<-[U,OHS,PL] Up` | PARTLY: *Adapter/*Translator/acl packages (naming heuristic) |
| Open Host Service | protocol/API open for all integrators | `Up [U,OHS]->[D,ACL] Down` | YES (moderate): published API spec with high fan-in |
| Published Language | well-documented shared language (schema) | `[U,OHS,PL]` | YES (strong): contract repo/artifact (.proto/OpenAPI/Avro) consumed by >=2 repos |
| Separate Ways | no connection | not in CML | weak: absence of edges is not a decision |
| Big Ball of Mud | mixed models, inconsistent boundaries | not in CML | heuristic only |
Sources: https://github.com/ddd-crew/context-mapping ; https://contextmapper.org/docs/context-map/ ; https://contextmapper.org/docs/partnership/ ; https://contextmapper.org/docs/shared-kernel/ ; https://contextmapper.org/docs/customer-supplier/ ; https://contextmapper.org/docs/conformist/ ; https://contextmapper.org/docs/anticorruption-layer/ ; https://contextmapper.org/docs/open-host-service/ ; https://contextmapper.org/docs/published-language/ ; https://www.infoq.com/articles/ddd-contextmapping/
Context Mapper notes "A generic upstream-downstream relationship is not necessarily a customer-supplier relationship!" (https://contextmapper.org/docs/context-map/).
Context Mapper discovery library (https://github.com/ContextMapper/context-map-discovery): SpringBootBoundedContextDiscoveryStrategy (@SpringBootApplication, @RequestMapping -> aggregates), DockerComposeRelationshipDiscoveryStrategy reads only `depends_on` (depended-on = upstream). Emits generic U/D only; never OHS/PL/ACL/CF roles.

## Structurizr multi-repo
Workspace scope: one software system per workspace; landscape workspaces as "maps of their software systems"; linking so double-click on system A opens workspace 1 — https://docs.structurizr.com/workspaces/scope ; `workspace extends <local|https url>` — https://docs.structurizr.com/dsl/language ; `!include` — https://docs.structurizr.com/dsl/includes ; cookbook: system-landscape.dsl + per-system workspaces extending it with `!element` — https://docs.structurizr.com/dsl/cookbook/workspace-extension/ (the "one DSL fragment per team repo" phrasing is an inference).

## Backstage system model
Domain > System > Component/API/Resource; Component "typically intimately linked to the source code", "unit of software" — https://backstage.io/docs/features/software-catalog/system-model ; https://backstage.io/docs/features/software-catalog/descriptor-format . Repo ~= Component; System = grouping declared by spec.system.

## Architecture-as-code prior art (per-repo?)
| Tool | Scope | Source |
|---|---|---|
| Structurizr for Java component finder / DSL `!components` | per container/codebase | https://docs.structurizr.com/java/component |
| Structurizr for .NET | UNVERIFIED (404) | - |
| jQAssistant + C4 plugin | multiple artifacts into one Neo4j graph; artifact-based, not repo-federated | https://jqassistant.github.io/jqassistant/current/ ; https://github.com/jqassistant-plugin/jqassistant-c4-plugin |
| ArchUnit | per-repo | https://www.archunit.org/ |
| arch-go | per Go module | https://github.com/arch-go/arch-go |
| Diagrams (mingrammer) | hand-authored, not derived | https://diagrams.mingrammer.com/ |
| Context Mapper discovery | per project + docker-compose | https://github.com/ContextMapper/context-map-discovery |
Takeaway: none generates a cross-repo landscape from dependency metadata; composable mechanisms are Structurizr extends/!include and Backstage catalog relations.
