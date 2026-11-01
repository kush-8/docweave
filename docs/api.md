# API guide

The application uses `/api/v1`, GitHub-only sessions and direct owner/project authorization. The checked contract is [backend/openapi.yaml](../backend/openapi.yaml); the running service exposes `/docs` and `/openapi.json`. No retired application/contract copy is kept in tests.

Browser mutations require exact Origin and session-bound CSRF. Cookie credentials are HttpOnly/SameSite and secure except the explicit loopback-development setting. Private resource reads recheck ownership and upstream repository authority. Safe errors must not disclose source content, paths, secrets or existence to unauthorized callers. Public profiles/catalog expose safe metadata only.

## Current route inventory

| Method | Path | Operation |
| --- | --- | --- |
| GET | `/auth/login` | startLogin |
| GET | `/auth/callback` | finishLogin |
| GET | `/me` | getCurrentUser |
| POST | `/auth/logout` | logout |
| GET | `/connections/github` | getGitHubConnection |
| GET | `/connections/github/repositories` | listGitHubRepositories |
| GET | `/connections/github/repositories/{repository_id}/branches` | listGitHubBranches |
| GET | `/projects` | list_projects_api_v1_projects_get |
| POST | `/projects` | create_project_api_v1_projects_post |
| GET | `/projects/{project_id}` | get_project_api_v1_projects__project_id__get |
| POST | `/projects/{project_id}/repository` | link_repository_api_v1_projects__project_id__repository_post |
| GET | `/catalog` | catalog_api_v1_catalog_get |
| GET | `/projects/{project_id}/documentation` | documentation_api_v1_projects__project_id__documentation_get |
| PUT | `/projects/{project_id}/documentation/{dependency_id}` | choose_documentation_api_v1_projects__project_id__documentation__dependency_id__put |
| GET | `/projects/{project_id}/processing-policy` | processing_policy_api_v1_projects__project_id__processing_policy_get |
| PUT | `/projects/{project_id}/processing-policy` | replace_processing_policy_api_v1_projects__project_id__processing_policy_put |
| GET | `/documents/{document_id}/assessment` | document_assessment_api_v1_documents__document_id__assessment_get |
| GET | `/documents/{document_id}/review` | review_content_api_v1_documents__document_id__review_get |
| POST | `/documents/{document_id}/review` | review_document_api_v1_documents__document_id__review_post |
| GET | `/projects/{project_id}/conversations` | conversations_api_v1_projects__project_id__conversations_get |
| POST | `/projects/{project_id}/conversations` | create_conversation_api_v1_projects__project_id__conversations_post |
| GET | `/conversations/{conversation_id}` | conversation_api_v1_conversations__conversation_id__get |
| POST | `/conversations/{conversation_id}/sync-retry` | retry_sync_api_v1_conversations__conversation_id__sync_retry_post |
| DELETE | `/conversations/{conversation_id}` | delete_conversation_api_v1_conversations__conversation_id__delete |
| GET | `/conversations/{conversation_id}/turns` | turns_api_v1_conversations__conversation_id__turns_get |
| POST | `/conversations/{conversation_id}/turns` | append_turn_api_v1_conversations__conversation_id__turns_post |
| GET | `/turns/{turn_id}` | turn_api_v1_turns__turn_id__get |
| GET | `/turns/{turn_id}/citations/{citation_id}` | citation_api_v1_turns__turn_id__citations__citation_id__get |
| POST | `/collections/{collection_id}/documents` | uploadDocument |
| GET | `/collections/{collection_id}/documents` | listDocuments |
| GET | `/documents/{document_id}` | getDocument |
| DELETE | `/documents/{document_id}` | deleteDocument |
| GET | `/documents/{document_id}/versions` | listDocumentVersions |
| POST | `/documents/{document_id}/versions` | replaceDocument |
| GET | `/jobs/{job_id}` | getJob |
| GET | `/projects/{project_id}/jobs` | listProjectJobs |
| POST | `/projects/{project_id}/sources` | importSource |
| GET | `/projects/{project_id}/sources` | listSources |
| POST | `/sources/{source_id}/refresh` | refreshSource |
| DELETE | `/sources/{source_id}` | deleteSource |
| GET | `/providers` | listProviderProfiles |
| GET | `/health/live` | getLiveness |
| GET | `/health/ready` | getReadiness |

## Runtime semantics

Project creation requires a repository and short goal; branch/root default from repository metadata. Existing bindings cannot be changed; preserved unbound projects link once. New conversations initialize through a durable commit check. Turns use request idempotency and one-active-turn constraints; identified source waits retain the original durable intent. Evidence and retained history are reauthorized on read. Processing-policy mutation records explicit project consent and applies it to its private collections; it does not authorize shared catalog publication.

A blocked conversation exposes a safe `progress` explanation. `POST /conversations/{conversation_id}/sync-retry` requires current owner/upstream access, Origin and CSRF, and returns HTTP 202 with the same conversation in `initializing` state. It atomically queues metadata synchronization; concurrent/repeated requests while initializing reuse that work. A ready conversation returns a revision conflict. The worker resolves HEAD after the project lock, retains good memory on incomplete scans and clears progress on success. Retry never recreates a chat or replays an answer/provider call.

Documentation coverage lists actual version ranges, source attribution and distinct missing/review/capacity/failure/active-work states. Owner selection requires the current context revision; broader versions need explicit acceptance bound to the dependency target and immutable revision. Omitting the revision removes a selection without deleting shared work. Source publication/review remains operator-only. See the [catalog runbook](runbooks/catalog.md) for request semantics, review commands and remaining catalog/discovery limits.

Private uploads/imports currently accept bounded TXT/Markdown with isolated parsing. Review is bound to the exact assessment/version/hash/rules; credentials cannot be approved. Source-fetch restrictions apply regardless of a URL being public. Workspace/member/invitation/grant/allowance endpoints are absent. Remaining installation/catalog/recovery gaps are in [tasks](tasks.md). Readiness remains 503; liveness does not establish dependency or release readiness.
