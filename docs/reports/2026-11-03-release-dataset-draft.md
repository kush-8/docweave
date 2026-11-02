# Release benchmark draft

Created 2026-11-03: [release-draft-v1.json](../../backend/eval/fixtures/release-draft-v1.json). This is a proposed question/label artifact, not an executed benchmark. `human_label_review` remains `pending`. It does not authorize provider calls or claim release quality.

The draft has 150 distinct questions: 100 development and 50 held-out candidates, with 34 disjoint families. Five questions represent each of the [29 catalog technologies](../../backend/catalog/required-sources.json); five additional cases cover independent access, missing-evidence, version and instruction-spoofing conditions. The first 20 technology families, Python through S3 in registry order, are development-only. IAM through Playwright and the five independent policy families are held-out candidates. Technology variants never cross splits. This is a proposed technology-disjoint split, not proof against every semantic similarity across technologies.

| Split | Answerable | No evidence | Version | Denied | Guardrail | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Development | 94 | 3 | 1 | 1 | 1 | 100 |
| Held-out candidate | 45 | 2 | 1 | 1 | 1 | 50 |
| Total | 139 | 5 | 2 | 2 | 2 | 150 |

Development boundary cases cover unmeasured service capacity, unknown browser performance, missing backend configuration, an unaccepted exact-version target, another owner's private notes and a direct instruction-injection query. Held-out controls use separate safety families. Their empty factual labels do not assert that an undocumented feature is impossible. Expected refusal/clarification is a policy expectation; actual HTTP denial versus a turn-level blocked outcome still needs harness mapping.

## Primary evidence opened

Every answerable case has short paraphrased factual labels and an HTTPS official source. Only representative page topics were examined; the registry's 85 pages were not all re-read. These references support general documentation questions, not exact installed-package compatibility or an assertion that DocWeave already indexed the pages.

| Technology | Primary page and covered topic |
| --- | --- |
| Python | [Tutorial introduction](https://docs.python.org/3/tutorial/introduction.html): arithmetic, sequences and assignment. |
| TypeScript | [Everyday types](https://www.typescriptlang.org/docs/handbook/2/everyday-types.html): arrays, unions and assertions. |
| React | [useState](https://react.dev/reference/react/useState): state updates and initialization. |
| Next.js | [Server and Client Components](https://nextjs.org/docs/app/getting-started/server-and-client-components): component boundaries. |
| Tailwind CSS | [Responsive design](https://tailwindcss.com/docs/responsive-design): breakpoints and containers. |
| FastAPI | [Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/): injection and declarations. |
| Pydantic | [Models](https://pydantic.dev/docs/validation/latest/concepts/models/): parsing and serialization. |
| SQLAlchemy | [Session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html): transactions and session lifetime. |
| LangChain | [Structured output](https://docs.langchain.com/oss/python/langchain/structured-output): schemas and strategies. |
| LangGraph | [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence): checkpointers and stores. |
| Hugging Face | [Pipeline](https://huggingface.co/docs/transformers/main/en/pipeline_tutorial): inference configuration. |
| vLLM | [Online serving](https://docs.vllm.ai/en/latest/serving/online_serving/): interfaces and operations. |
| PostgreSQL | [Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html): atomic operations. |
| pgvector | [Official README](https://github.com/pgvector/pgvector): exact and approximate search. |
| Qdrant | [Collections](https://qdrant.tech/documentation/manage-data/collections/): vector configuration. |
| Redis | [Data types](https://redis.io/docs/latest/develop/data-types/): choosing record/sequence structures. |
| Docker | [Dockerfile](https://docs.docker.com/build/concepts/dockerfile/): build instructions. |
| GitHub Actions | [Workflow authentication](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token): token permissions. |
| Terraform | [State](https://developer.hashicorp.com/terraform/language/state): resource bindings and storage. |
| S3 | [Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html): object recovery. |
| IAM | [Security practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html): credentials and access. |
| ECS | [Services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_services.html): scheduler behavior. |
| RDS | [Backup introduction](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.html): snapshot and recovery boundaries. |
| OpenTelemetry | [Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/): spans and attributes. |
| Prometheus | [Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/): query types and time selection. |
| Grafana | [Data sources](https://grafana.com/docs/grafana/latest/datasources/): connections and query configuration. |
| Langfuse | [Masking](https://langfuse.com/docs/observability/features/masking): export-stage filtering. |
| pytest | [Fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html): scope and teardown. |
| Playwright | [Assertions](https://playwright.dev/docs/test-assertions): retries and failure collection. |

The pinned raw SQLAlchemy and Playwright page fetches failed; their official rendered documentation was used instead. The RDS registry overview linked to the backup-introduction page used for labels. Those three alternatives are explicit evidence references, not new approved catalog URLs. Source allowlisting, publisher permissions and actual ingestion remain separate gates. All other references are enumerated registry pages. No Google billing or pricing pages were inspected.

## Validation and remaining limits

The current `load_release_dataset` accepted the draft. Independent assertions checked exactly 150 unique IDs and normalized questions, the 100/50 counts, family separation, all 29 technology IDs, and nonempty sources/facts for answerable cases. SHA-256: `a380a6a0ad2baaecc57260bae6ae6a6c36d433f178d51a57d2c5c8f7a4a6db9e`. The original pilot fixture was not modified.

Before execution, a person must review question realism, factual labels, version targets, boundary outcomes, split composition and the small control denominators. The nine held-out technology families differ from the development distribution; report that limitation when interpreting comparisons. The draft is visible to the builder and can still change; it is not a sealed or independently administered held-out test.

The schema stores one question per case, source URLs and concise factual labels. It does not yet contain executable multi-turn sequences, frozen source-body hashes/exact support spans, project/selection provisioning, real access/consent transitions, retrieval captures or observed outputs. Those are required follow-on artifacts; none is implied by reaching a count of 150. Source pages can change and must be frozen through the accepted source workflow before a reproducible run. Any re-labeling requires a new reviewed artifact hash.

No answers were generated, no metrics measured, no human review completed, no provider inference or DB action performed, and no commit created. Separate 30-output development and release review packets can only be populated after actual authorized captures exist. Readiness remains governed by the unfinished release gates in [tasks](../tasks.md).
