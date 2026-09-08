# Prior art: deterministic cross-repository relation detection (subagent research, 2026-09-08)

Legend: S = static (source/config/catalog), R = runtime, H = history (VCS). SM = self-hosted / GitLab self-managed.

## 1. Backstage software catalog
| Aspect | Finding | Source |
|---|---|---|
| Kinds | Domain, System, Component, API, Resource, Group, User, Template, Location | https://backstage.io/docs/features/software-catalog/descriptor-format |
| Component spec | spec.owner -> ownedBy/ownerOf; spec.system -> partOf/hasPart; spec.subcomponentOf -> partOf/hasPart; spec.providesApis -> providesApi/apiProvidedBy; spec.consumesApis -> consumesApi/apiConsumedBy; spec.dependsOn -> dependsOn/dependencyOf; spec.dependencyOf | same |
| Well-known relations | ownedBy/ownerOf; providesApi/apiProvidedBy; consumesApi/apiConsumedBy; dependsOn/dependencyOf; parentOf/childOf; memberOf/hasMember; partOf/hasPart | https://backstage.io/docs/features/software-catalog/well-known-relations |
| System model | System = "collection of resources and components that exposes one or several public APIs"; Domain groups systems | https://backstage.io/docs/features/software-catalog/system-model |
| GitLab discovery | provider config host/group/branch/entityFilename (catalog-info.yaml)/schedule/projectPattern/groupPattern; useSearch needs Premium/Ultimate; SM via host | https://backstage.io/docs/integrations/gitlab/discovery |
| GitLab org data | orgEnabled ingests User/Group hierarchy; SM supported | https://backstage.io/docs/integrations/gitlab/org |
| TechDocs | Markdown + MkDocs per entity | https://backstage.io/docs/features/techdocs/ |

## 2. GitLab self-managed
| Feature | Signals | Tier | Output | Source |
|---|---|---|---|---|
| Dependency List | from dependency/container scanning or uploaded CycloneDX 1.4-1.6; project+group level; export JSON/CSV/CycloneDX | Ultimate | package inventory (not service graph) | https://docs.gitlab.com/user/application_security/dependency_list/ |
| Dependency scanning (SBOM) | CycloneDX per lockfile/manifest dir; Maven needs `mvn dependency:tree -DoutputType=json` (maven.graph.json), Gradle `gradle dependencies` (gradle.graph.txt) | Ultimate | CycloneDX | https://docs.gitlab.com/user/application_security/dependency_scanning/dependency_scanning_sbom/ |
| artifacts:reports:cyclonedx | SBOM report | Ultimate | CycloneDX | https://docs.gitlab.com/ci/yaml/artifacts_reports/ |
| Multi-project pipelines `trigger: project:` | explicit cross-project CI edge | Free | edge | https://docs.gitlab.com/ci/pipelines/downstream_pipelines/ |
| `needs: project:` | cross-project artifacts (job-token allowlist) | Premium | edge | same |
| `include: project:/remote/template` | CI config reuse | Free | edge | https://docs.gitlab.com/ci/yaml/includes/ |
| `include: component:` | CI/CD catalog `$CI_SERVER_FQDN/org/proj/component@1.0.0` | Free | versioned edge | https://docs.gitlab.com/ci/components/ |
| Groups/subgroups | up to 20 levels | Free | hierarchy | https://docs.gitlab.com/user/group/subgroups/ |
| CODEOWNERS | ./CODEOWNERS, docs/, .gitlab/; sections, @group/subgroup | Premium | path->owner | https://docs.gitlab.com/user/project/codeowners/ |
None of these yields a service dependency graph; CI keywords are the only explicit repo->repo edges.

## 3. Renovate / Dependabot / GitHub dependency graph
| Tool | Cross-repo graph? | Source |
|---|---|---|
| Renovate dashboard | per-repo | https://docs.renovatebot.com/key-concepts/dashboard/ |
| Dependabot | per-repo dependabot.yml | https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/about-dependabot-version-updates |
| GitHub dependency graph | manifests/lockfiles + submission API; Dependents only for public repos | https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/about-the-dependency-graph |
| GHES 3.14 | no dependents calculation | https://docs.github.com/en/enterprise-server@3.14/code-security/supply-chain-security/understanding-your-software-supply-chain/about-the-dependency-graph |
| SBOM API | GET /repos/{o}/{r}/dependency-graph/sbom (SPDX); deprecation after 2026-11-13 | https://docs.github.com/en/rest/dependency-graph/sboms |

## 4. Sourcegraph
repo: filters, repo:has.file/path/commit.after/description/meta (https://sourcegraph.com/docs/code-search/queries/language); structural search = Comby (https://sourcegraph.com/docs/code-search/types/structural); precise nav via SCIP, Enterprise (https://sourcegraph.com/docs/code-search/code-navigation/precise_code_navigation); Code Insights (https://sourcegraph.com/docs/code_insights); self-hosted Helm/Compose (https://sourcegraph.com/docs/admin/deploy). Output is search results / symbol graph, not a service graph. `repo:deps(...)` UNVERIFIED.

## 5. CodeScene
Change coupling = same commit / same author window / same ticket ID (https://codescene.io/docs/guides/technical/change-coupling.html); architectural components by glob; "automatically creates a new component for each Github repository included in the project" (https://codescene.io/docs/guides/architectural/architectural-analyses.html); on-prem plans (https://codescene.com/pricing). History-based, not source-deterministic. A page literally named "change coupling across repositories": UNVERIFIED.

## 6. Structurizr DSL & Kroki
`workspace extends <file|url>` (https://docs.structurizr.com/dsl/language); `!include <file|dir|url>` inlined (https://docs.structurizr.com/dsl/includes); `!docs`, `!adrs`; workspace-extension cookbook with `!element` (https://docs.structurizr.com/dsl/cookbook/workspace-extension/). Kroki renders C4-PlantUML, D2, GraphViz, Mermaid, PlantUML, Structurizr, ... (https://kroki.io/); self-host yuzutech/kroki + kroki-mermaid companion (https://docs.kroki.io/kroki/setup/install/). Nothing inferred: DSL must be authored/generated.

## 7. Service-graph derivation tools
| Tool | Mode | Signals | Output | Source |
|---|---|---|---|---|
| Code2DFD (TUHH) | S | Java/Spring: Feign, RabbitMQ, Kafka, Eureka, Spring Cloud Config, docker-compose | DFD PlantUML/JSON + traceability | https://github.com/tuhh-softsec/code2DFD ; https://doi.org/10.1016/j.jss.2023.111722 |
| MicroDepGraph | S | docker-compose/Docker | Neo4j/GraphML/SVG | https://github.com/clowee/MicroDepGraph |
| Prophet / prophet-utils (Cloud Hubs, Baylor) | S | Java enterprise code -> context map, bounded contexts | Neo4j + web | https://github.com/cloudhubs/prophet ; https://github.com/cloudhubs/prophet-utils ; https://doi.org/10.1109/ase51524.2021.9678749 (ANTLR use UNVERIFIED) |
| MicroART | S+R | source + Dockerfiles + runtime logs | model | https://github.com/microart/microART-Tool |
| Bilt | S | npm package.json, monorepo only | build order | https://github.com/giltayar/bilt |
| Oxeye | R (UNVERIFIED) | acquired by GitLab (2024) | - | https://about.gitlab.com/press/releases/ |
| Cortex.io | S declared | cortex.yaml x-cortex-dependency; GitLab SM supported | graph | https://docs.cortex.io/ingesting-data-into-cortex/entities-overview/entities/adding-entities/dependencies.md ; https://docs.cortex.io/ingesting-data-into-cortex/integrations/gitlab.md |
| OpsLevel | S declared | opslevel.yml dependencies | graph | https://docs.opslevel.com/docs/opslevel-yml ; https://docs.opslevel.com/docs/service-dependencies ; https://docs.opslevel.com/docs/gitlab-self-hosted-opslevel |
| Port.io | S mapped | GitLab projects/groups/files via mapping | blueprint relations | https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/git/gitlab/ |
| Atlassian Compass | S declared | compass.yml relationships DEPENDS_ON; GitLab.com only | graph | https://developer.atlassian.com/cloud/compass/config-as-code/structure-and-contents-of-a-compass-yml-file/ |
| Confluent Stream Lineage | R | producer/consumer activity | topic lineage | https://docs.confluent.io/cloud/current/stream-governance/stream-lineage.html |
| Conduktor stream lineage | S (ACLs) | Kafka ACLs per service account | topic<->account | https://docs.conduktor.io/guide/conduktor-concepts/stream-lineage.md |
| Airflow lineage | S decl + R | inlets/outlets, experimental | assets | https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/lineage.html |

## 8. Maven / Gradle parsing rules
Maven: groupId/version inherited from parent, artifactId not (https://maven.apache.org/pom.html); relativePath default ../pom.xml (https://maven.apache.org/guides/introduction/introduction-to-the-pom.html); `${project.version}` etc.; BOM import scope=import type=pom (https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html); dependency:tree outputType text|dot|graphml|tgf|json (https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html). GitLab itself requires dependency:tree JSON for Maven graphs.
Gradle: rootProject.name in settings (https://docs.gradle.org/current/userguide/settings_file_basics.html); group defaults to path (https://docs.gradle.org/current/dsl/org.gradle.api.Project.html); publication coords from group/name/version (https://docs.gradle.org/current/userguide/publishing_maven.html); includeBuild substitution by `${project.group}:${project.name}` (https://docs.gradle.org/current/userguide/composite_builds.html); libs.versions.toml (https://docs.gradle.org/current/userguide/version_catalogs.html). Static parse of build scripts is heuristic.

## 9. Protobuf / buf / OpenAPI / AsyncAPI
proto package/import/import public/java_package/go_package (https://protobuf.dev/programming-guides/proto3/); buf.yaml v2 modules/deps, buf.lock (https://buf.build/docs/configuration/v2/buf-yaml ; https://buf.build/docs/bsr/module/dependency-management); OpenAPI 3.1 $ref relative resolution (https://spec.openapis.org/oas/v3.1.0.html#reference-object); AsyncAPI 3.0 channel address = topic name (https://www.asyncapi.com/docs/reference/specification/v3.0.0).

## Takeaways
Deterministic cross-repo edges from committed files come from: (a) catalog descriptors (declared); (b) build/CI config (coordinates, CI triggers/includes, buf deps, proto imports, OpenAPI $ref, AsyncAPI channels); (c) academic static extractors (Code2DFD, MicroDepGraph, Prophet), Java/Spring/Docker-centric. Backstage is the only one with a GitLab SM discovery provider and a typed relation model. Kafka/Airflow lineage products are runtime or ACL-derived.
