# DocWeave — Frontend Design and App Flow

Status: Direction and GitHub extension confirmed and reconciled 2026-10-28. Frontend implementation is unstarted.
Confirmed document scope: frontend design, screens, navigation, interactions, and user-facing app flows.
Product requirements: [PRD.md](PRD.md). Backend workflows, security enforcement, limits, and evaluation: [architecture.md](architecture.md).

This file records the confirmed frontend direction and explicit visual defaults, not a rendered UI or a runtime accessibility audit. Numerical backend limits and API/state contracts remain authoritative in architecture.

## Experience principles

- Keep the active workspace, project, selected technologies, and source coverage visible.
- Make evidence inspectable beside an answer, with source date/version labels and direct access to captured spans.
- Use real source/job state. Explain missing coverage, permission restrictions, and failures with a next action.
- Make provider selection and external processing understandable before a paid or private-data operation.
- Keep the engineer's main path short: create project, add knowledge, ask, inspect evidence.

## Visual direction

Direction: a documentation workbench built around **claim and evidence together**. Give the answer a quiet reading surface; selecting an inline citation highlights the matching source number and exact excerpt in the adjacent inspector. This relationship is the distinctive visual feature. Keep navigation, source lists, and settings restrained so the engineer can judge the answer's evidence quickly.

Use rows and section dividers for source/job lists; reserve cards for project summaries. Align headings, fields, and prose left. Use the same column rhythm for source titles, status, snapshot dates, and actions. Avoid decorative gradients, repeated floating cards, oversized statistics, and a chat-avatar treatment that pushes evidence down the page.

| Core token | Light | Dark | Use |
| --- | --- | --- | --- |
| Canvas | `#F7F9FC` | `#0B1220` | Page background |
| Surface | `#FFFFFF` | `#111C2E` | Reading/input surfaces |
| Ink | `#172B4D` | `#E5EDF7` | Primary text/headings |
| Secondary ink | `#475569` | `#A8B8CC` | Supporting text |
| Accent | `#1D4ED8` | `#8CB4FF` | Actions, links, active citation, focus |
| Control boundary | `#64748B` | `#71839B` | Meaningful control outlines |

Pale slate `#D8E1EC` is a light-theme decorative divider, not an input's sole boundary. On white, semantic text colors are success `#166534`, warning `#92400E`, and error/destructive `#B91C1C`. In dark mode, use ink plus status icons/labels until semantic-color variants are contrast-verified; never reuse dark red/green text from the light palette. Selected navigation has a marker and `aria-current`; status/selection never relies on color alone.

Calculated contrast on white: primary text 14.10:1, secondary text 7.58:1, accent text/white button text 6.70:1, and control boundary 4.76:1. Accent focus on the canvas is 6.35:1. Dark-surface ratios: ink 14.47:1, secondary ink 8.45:1, accent 8.21:1, control boundary 4.41:1. Dark accent buttons use canvas-colored labels (8.99:1), not white labels (2.08:1). These calculations cover specified solid-color pairs, not rendered components, transparency, hover variants, or a complete accessibility audit.

### Typography, spacing, and components

- Use `Segoe UI Variable`, `Segoe UI`, then system sans-serif fallbacks. Use `ui-monospace`/Consolas/monospace for code. These OS-provided families keep the technical workspace clear without a font download.
- Body and answer prose: 16px with 1.6 line height. Page title: 28px/1.25, weight 600; section heading: 20px/1.35, weight 600; navigation/metadata: 14px/1.5. Use a readable text column of 65–75 characters. Preserve browser text scaling.
- Use a 4px spacing unit: 8px within related controls, 16px within sections, 24px between sections, and 32px at major boundaries. Page padding is 24px on desktop and 16px on mobile.
- Controls and compact panels use 6px corners. Establish hierarchy with spacing, type weight, and surface boundaries; use shadows only for overlay elevation. Primary controls and icon hit areas are at least 44 by 44px.
- Use one filled primary action per active form/section. Secondary actions are outlined or text buttons. Keep delete/revoke actions separated from ordinary actions; hover/pressed/focus states increase emphasis without moving layout.
- Inputs have persistent labels, visible boundaries, helper text, and an inline error slot. Provider choices show the provider and model label; unavailable profiles have an adjacent reason. Do not rely on a tooltip to explain an unavailable action.
- Status badges show a short label plus a stable icon: Queued, Processing, Ready, Partial, Failed, or Awaiting approval. Numeric usage/date columns align consistently and use tabular numerals.
- Code blocks have a language label and **Copy code** action; confirmation is **Copied**, announced politely. Code tokens remain verbatim, even when surrounding prose follows sentence case.

Support light and dark themes throughout sign-in entry, navigation, forms, conversations, code, citations, dialogs, and status views. A visible, labeled light/dark toggle remembers a non-sensitive per-device override. Without an override, follow live OS preference. Apply it before first paint, set native `color-scheme`/page chrome consistently, and tolerate unavailable browser storage. Identity-provider-hosted pages may use their configured theme; do not promise application-toggle synchronization across that external boundary. Custom font downloads, illustrations, and a marketing site are outside scope. Motion is limited to interruptible 120–180ms opacity/transform transitions after a user action; reduced-motion preferences remove nonessential transitions. Avoid `transition: all` and layout-property animation.

## Navigation and screen map

The application opens into workspace/project selection, then a project workspace. Workspace-level member management is separate from project settings.

| Screen | Purpose and primary action |
| --- | --- |
| Sign in | **Continue with Google**, **Continue with GitHub**, or **Continue with email**; email uses the identity provider's password, verification, and reset flows |
| Workspaces and projects | Select an authorized workspace/project; create a workspace as owner or accept a recipient-bound invitation |
| New project | Choose GitHub detection or manual setup; enter goal, review stack/versions and coverage; **Create project and import docs** |
| GitHub connections | Account-level **Connect GitHub**/**Disconnect**; separate from login and owned by the current user |
| Repository scan/review | Select repository/branch/application, inspect commit-pinned dependency facts, correct versions, and confirm stack |
| Documentation review | Inspect publisher-linked origin/path/version coverage; approve new sources or explicit fallbacks before import |
| Project overview | Show stack, ready/partial sources, private-document readiness, recent activity; **Add sources** or **Ask a question** |
| Ask | Create/resume a private project conversation, select its provider once, send contextual follow-ups, inspect validated replies/citations |
| Sources | Browse catalog selections, indexed coverage, snapshot dates, import status, refresh results; **Import docs** or **Refresh** |
| Documents | Browse collections/files and version history; **Upload documents**, **Replace**, **Re-index**, or **Delete** where permitted |
| Activity | Inspect imports/jobs, safe failures, and request IDs; **Retry** eligible failed jobs |
| Project settings | Edit goal/stack/context, grants, and owner-approved processing policy; show own-workspace usage/allowance without global spend |
| Workspace members | Owners manage membership and roles; other users see only permitted membership information |

The project rail contains Overview, Ask, Sources, Documents, Activity, and Settings. Keep member management/invitations in the workspace menu. GitHub connections live under the signed-in account, not a tenant-wide shared credential screen; project settings link to the actor's own connection/scan state. Ask includes a paginated recent-conversations picker/list and **New conversation**; only the author sees its titles and messages. Provider selection is editable when creating a conversation and read-only afterward. Provider credentials are configured outside the browser; the UI shows configured profiles without key-entry fields.

Use real links for navigation and buttons for actions. Project pages, private conversations, saved turns, and citations have stable URLs. URL state includes page/tab, public-catalog search, source/job status filters, cursor, conversation/turn IDs, and selected citation ID. Back/forward restores that view; opening a result/citation in a new tab works. Draft questions, private document search text, prompts, filenames, private repository paths/names, credentials, and content stay out of URLs. Connection/scan/source routes use opaque identifiers; original GitHub links are shown only to currently eligible viewers.

Enforce visibility through server responses; hiding a navigation item is only a usability measure. Scope in-memory data to identity/workspace/project; clear protected views on logout or a reported access change. Never flash a previous project's result while the next project loads.

## Layout and responsive behavior

Use CSS grid/flex layout rather than measuring panels in JavaScript. At 1,200px and wider, use a 224px project rail and a 56px top bar. The remaining Ask workspace can show a main column of at least 480px and a 360px evidence inspector; let discussion fill the space when the inspector is closed. Recent conversations use a collapsible list/picker inside Ask, not another permanent 240px rail: the project rail, discussion, evidence, 48px padding, and 24px gap fit in 1,136px; a permanent history rail would need about 1,400px. The top bar holds project identity and a compact coverage link; avoid repeating the full technology list above every answer.

```text
Project rail   | Project name / coverage              | Account
               | Conversation picker / New conversation
Overview       |-----------------------------------------------
Ask            | Discussion + inline citations [1]   | Source [1]
Sources        |                                    | Exact excerpt
Documents      | Suggested steps / code              | Heading / page
Activity       |                                    | Snapshot / link
Settings       | Composer / fixed provider / details | Close
```

From 768px through 1,199px, collapse the rail into a menu and open evidence as a modal side sheet. Below 768px, use a single-column flow and a full-height evidence sheet. Keep the question, provider choice, and current knowledge selection reachable without horizontal page scrolling. Below the title, source/job tables become labeled row groups on narrow screens rather than hiding status or actions.

The desktop inspector is a nonmodal, labeled region: selecting a citation moves focus to its heading without trapping navigation. Compact evidence sheets are dialogs with contained focus, a visible close button, Escape dismissal, and focus restoration to the triggering citation. Their internal scrolling stays contained; background content is inert while modal. Respect safe-area insets and the on-screen keyboard; sticky headers/actions must not obscure focused controls.

Long source names, filenames, and URLs wrap inside shrinking flex/grid children. Code blocks scroll horizontally inside their own container. Full filenames remain available on focus/open; truncation never removes an action's accessible name. Render only the selected excerpt initially, not an entire long source. Preserve reserved loading space and the user's reading position; do not force-scroll on background status updates.

## Forms and interaction contracts

- Use semantic labels with meaningful field names. Appropriate types/input modes apply to each field; leave paste enabled. Selectable technology/collection rows make the label and control one hit area.
- Keep form actions available before submission so users can discover inline validation. On invalid submit, show a summary linked to field errors and focus the first invalid field. Missing usable knowledge uses **Add sources**/**Upload documents** as the primary action instead of a dead disabled question form.
- During a pending mutation/turn, retain its action label with an ellipsis such as **Sending…** and a busy indicator, block duplicate dispatch, and keep focus stable. After acceptance, show durable queued/running status; allow navigation and recover that same turn on return. Completion/error messages remain visible near the affected content; transient toasts are supplementary.
- Warn before leaving dirty project/settings forms or an unsent question. Add a route guard and a browser unload warning only while such a draft exists; remove them after save/discard. Keep drafts in memory, not persistent browser storage.
- Use Enter to submit single-line forms. In the conversation composer, Enter inserts a newline; the helper shows Ctrl+Enter on Windows/Linux or Command+Enter on macOS to send. Skip submission during IME composition. **Send message** works without shortcuts; one active turn blocks another submission in that conversation, while other conversations remain usable.
- Drag-and-drop upload supplements a labeled **Choose files** control; all upload actions work without dragging. Show per-file errors and preserve successful entries when one file fails.
- Use labeled icon buttons for menu/close/copy actions; tooltips supplement accessible names. Avoid hover-only actions and mobile autofocus. Indicate unsaved changes next to **Save changes**.
- Use **Cancel** in confirmation dialogs to mean dismissing the decision. Do not present question/request cancellation as stopping provider billing; the current API does not promise that behavior.

## App flows

### 1. First project

1. Choose Google, GitHub, or email/password login and select/create a permitted workspace. Login alone does not connect repository access.
2. Choose **Import from GitHub** or **Set up manually**. Both paths retain required project-goal entry and optional environment/architecture/constraints.
3. On the GitHub path, connect the actor's account if needed, choose an accessible repository/branch/application, scan, then review the detected stack and docs-version choices. Manual setup lets the user select technologies and supply unresolved version/source details.
4. Select **Create project and import docs** after stack review. Create the project and durably queue only approved catalog/version selections. Open its overview with real processing state.
5. Unknown documentation origins, private lookup consent, and unaccepted major/minor fallbacks stay pending. Complete their batch review in the setup/Sources view; **Approve and import** queues them afterward. Project creation is not blocked by an unavailable dependency's documentation.
6. Show **Waiting for processing capacity** for missing provider/allowance capacity. Ready knowledge enables **New conversation**; partial coverage stays visible and private uploads remain available.

### 2. Import official documentation

1. Approved selected-source imports start at project creation. Open Sources for catalog entries, approved external origins, pending discovery/review, version targets, or unavailable documentation.
2. Select **Import docs** and show the job reference and queued/processing state.
3. Keep navigation available while import continues. Source rows show ready/partial/failed outcomes, indexed sections, snapshot date, known version, and excluded content. Poll while visible; slow down when the page is hidden and stop at a terminal state. Announce meaningful status transitions once, not every poll.
4. Link failures to Activity with a safe explanation and a retry action when eligible.
5. When at least one source is usable, offer **Ask a question**. A capped or partially failed import stays labeled partial.

A refresh shows changed/unchanged/failed coverage. Display dependency constraint/resolution, selected docs target, actual publisher coverage, and capture time as separate facts. A major/minor fallback has an explicit acceptance label; unresolved version is not an installed-version claim. Show **Version not specified** for unknown source declarations and **Documentation unavailable** when no suitable source exists.

### 3. Add private project documents

1. Open Documents and select/create a permitted collection.
2. Review its read/write grants and the hosted providers/backends approved to process private content.
3. Before the first indexing attempt, explain that hosted embedding/reranking also sends content externally. If approval is missing, show **Awaiting processing approval** and a permitted settings link.
4. Upload PDF, TXT, Markdown, or DOCX. Keep server-defined limits and supported-format messaging aligned with architecture.
5. Show per-file validation/parsing/indexing progress, then ready or a specific safe failure.
6. Open a ready document to inspect metadata, versions, and authorized captured text.

Show whether malware scanning is enabled. Explain unsupported/encrypted/scanned-without-text files and offer an actionable supported-format alternative; do not imply OCR exists.

### 4. Converse and inspect evidence

1. Open Ask and choose a recent private conversation or **New conversation**. Show the current project goal/stack, ready source coverage, and readable collection selection.
2. For a new conversation, select Gemini, Groq, or Hugging Face once. Explain required Gemini retrieval processing and any excluded readable collections. Show the fixed provider/model in resumed conversations; switching requires a fresh conversation.
3. Enter the message and select **Send message**. A follow-up uses the project's current context and this conversation's authorized history. After a project edit, show **Project context updated** on the next turn.
4. Show durable queued/running status after acceptance. Navigating/reloading resumes the same turn; do not resubmit. Show the final validated response, never unvalidated tokens or fabricated stage progress.
5. Render an answer, focused clarification question, or evidence-based abstention as a distinct assistant reply. User answers to clarification continue the same thread. Announce completion without stealing unrelated focus.
6. Inline citations open exact retained spans, locators, capture/version labels, and safe original links. Accessible name example: **Source 1: FastAPI security**. Match highlight/source number to the selected claim; reuse one inspector.
7. **Response details** shows provider/model/backend, context/source revision, timing, estimated/metered usage, and request ID. Keep operational detail out of ordinary prose.
8. Disclose when older turns are condensed for model context. The full authorized transcript remains readable. A summary is not a cited source; there is no arbitrary message-count cutoff.

Project descriptions and reviewed dependency facts guide context but are not proof of deployed behavior or documentary API claims. For GitHub projects show the last accepted commit/scan revision and current access status. A branch changing elsewhere does not silently change the current project's context. Render code as escaped text with **Copy code**; there is no execute or deploy action.

### 5. Abstention and operational failure

For insufficient, conflicting, or unsuitable-version evidence, show a clear abstention and a next step such as importing a source or supplying a project document. Never replace this state with an unsupported confidence percentage.

For a failed turn, show a distinct operational error, request ID, and retryability. Browser disconnection first recovers server status. If provider completion is unknown, say the request may have incurred cost and require an explicit retry decision; never treat it as a safe automatic replay. Login/resume does not resend messages or change the fixed provider.

For budget/rate limits, use the server's retry information and never invent a countdown. Show this workspace's usage/allowance only. Global capacity exhaustion uses a generic application-capacity message; other tenants' financial data and the operator's global balance remain private.

### 6. Refresh, replace, revoke, and delete

An ordinary source refresh or document replacement updates the active source for new questions. Historical answers continue to open their retained authorized snapshot and display its capture date.

Before a destructive document action, identify the document and explain that deletion removes it from search and can make dependent history unavailable. Confirmation uses **Delete document** and **Cancel**, with initial focus on Cancel. Grant/provider-policy changes show the affected access before confirmation. Keep ordinary navigation/imports free of redundant confirmation dialogs.

After access revocation/deletion, hide affected content/derived memory and pause further turns in dependent conversations. Show **This conversation uses knowledge that is no longer available** and **New conversation** without revealing former private titles, quotes, or filenames. Do not transfer affected memory automatically. Enforce this on navigation/refetch and protected-view updates; already-viewed/copied text cannot be recalled. Loss of private GitHub eligibility also hides repo-derived context/labels and pauses dependent conversations. A connection outage uses a safe temporary verification state rather than exposing retained private analysis. Authorized transcripts/snapshots otherwise remain until explicit deletion.

### 7. Investigate a job

Open Activity from a source/file status or project navigation. Show job type, resource label, state, attempts, timestamps, safe stage/error details, and request ID. Only authorized users see a retry control; policy/validation failures explain the required correction instead. Documents and Activity use server cursor pagination at the architecture's default page size; preserve filters and cursor in the URL. Pagination keeps these lists below the threshold that would require virtualization.

Operational dashboards and evaluation reports are linked from their existing tools when available. This draft does not add a separate frontend evaluation authoring interface.

### 8. Connect GitHub and review a detected stack

1. **Connect GitHub** explains selected-repository Contents read permission: the grant covers repo contents broadly, while DocWeave fetches only supported metadata/config/lockfiles. It requests no writes and does not replace sign-in.
2. Complete GitHub App authorization/installation. Show connected account and organization/install approval issues only to that user. Never imply an owner can connect on behalf of a teammate.
3. Select an accessible repository, branch (default selected initially), and monorepo application if applicable. Display the resolved commit and scan timestamp.
4. Show scanning/partial/ready/error status and file coverage. The preview lists package/ecosystem/role, safe file/field provenance, declared constraint, lockfile-resolved version/revision, conditions, and uncertainty.
5. Confirmed direct runtime dependencies start selected; development tools are optional; transitive-only libraries are not selected automatically. Requirements/frozen lists with unknown role/directness require user selection, and constraint-only entries are not selected. Unsupported ecosystems/lock schemas and private/local/Git dependencies are labeled, not guessed.
6. Require docs-version selection for unresolved/multiple versions. Preserve the original detected facts alongside any manual correction; a chosen target is never renamed “installed version.”
7. Ask for explicit approval before any public lookup of private/unresolved identifiers. Explain that raw configs, credentials, private repo URLs, and unrelated values are not sent.
8. Review the stack and create the project with the user's goal. Approved selections auto-import; missing source/version approvals remain visible in the next setup step.

### 9. Review noncatalog documentation and version fallbacks

Show catalog-verified versus publisher-linked/reviewed sources distinctly. Candidate cards/rows include package, registry relationship evidence, documentation URL/path, selected target, actual coverage, and exclusions. User approval affects this project/workspace only.

Batch **Approve and import** for selected new origins. For exact docs unavailable, show the publisher's major/minor alternative and require **Use this documentation version**; otherwise keep unavailable with a reviewed official URL/upload option. Approval never overrides network/robots/quota/processing controls. Avoid declaring every homepage “official documentation.”

### 10. Rescan or disconnect

**Rescan repository** produces a new commit-pinned preview. Show dependency/version/role/condition additions/removals and proposed documentation changes; **Apply stack changes** updates approved project context and queues approved documentation work. Old context remains until applied; the next conversation turn shows the revision update.

Disconnect operates on the current user's connection. Remove access to affected private analysis and pause their dependent conversations; reconnect/revalidate before reuse. Public documentation and manual projects remain available under their ordinary grants. **Delete analysis** uses the established explicit deletion/retention policy. No push autosync or external webhook relay is implied.

## Shared UI states

| State | Expected presentation |
| --- | --- |
| Initial loading | Skeleton or busy indicator with a meaningful accessible label |
| Empty workspace/project | Explain the next permitted create/select action |
| No ready knowledge | Explain how to import/upload; prevent a question submission that cannot use evidence |
| Partial coverage | Identify ready and missing sections; let the user continue with ready knowledge |
| Permission denied | Safe access message; remove protected content rather than rendering stale cached details |
| Session expired | Reauthenticate and recover persisted status; never replay paid requests automatically |
| Summary memory | Explain condensed older context while retaining the full authorized transcript |
| Pending recovered turn | Restore queued/running/completed state after reload without duplicate dispatch |
| Completion unknown | Explain possible execution/cost and require an explicit retry decision |
| Paused conversation | Safe access-change explanation and fresh-conversation action |
| Waiting for allowance | Show workspace processing/allowance configuration is needed; import remains queued |
| GitHub authorization/organization approval needed | Explain the actor's next step; keep manual setup available |
| Partial/unsupported scan | List safe supported facts and missing coverage; never imply a complete stack |
| Unresolved dependency version | Preserve the declaration and require a docs target choice |
| New documentation origin | Publisher-linked candidate, source/path/version review, then explicit import approval |
| Rescan diff pending | Keep accepted project context until the authorized user applies the diff |
| Private repository unavailable | Hide derived facts and pause their dependent conversations; recheck/reconnect without leaks |
| Provider unavailable | Show profile availability and corrective action; keep selection explicit |
| Form error | Inline field explanation plus summary; preserve non-sensitive inputs |
| Background operation | Real status and counts when known; no invented completion percentage |
| Destructive action | Specific target, consequence, confirm/cancel controls, visible outcome |

## Content and formatting

Use direct, sentence-case interface copy consistently: **Create project and import docs**, **Import docs**, **Upload documents**, **New conversation**, **Send message**, **Refresh**, and **Retry job**. This is the deliberate frontend-design copy convention; the external review guide's Title Case recommendation is not adopted. Preserve official technology/model names. Avoid AI marketing language and implementation terms in the main flow; technical details belong in the response-details/evidence sections when they help the engineer.

| Situation | Example copy |
| --- | --- |
| No knowledge | “Add documentation or project files to ask your first question.” |
| Partial import | “Some sections could not be imported. You can ask about the ready sections.” |
| No supporting evidence | “The indexed sources do not support an answer. Add a relevant source or refine your question.” |
| Provider failure | “The selected provider could not complete this request. Retry or choose another configured provider.” |
| Permission changed | “This evidence is no longer available.” |
| Unknown version | “Version not specified” |

Use an ellipsis character for loading text (**Importing…**) and explicit visible labels, not placeholder-only fields. Format dates/times with `Intl.DateTimeFormat` and numbers/USD estimates with `Intl.NumberFormat`, using the user's locale/timezone; budget reset dates follow the Asia/Calcutta budget boundary in architecture. Show an absolute timestamp and timezone for source captures, even when a relative “updated” label is offered. Distinguish **Estimated cost** from metered charges.

Use nonbreaking spaces between values and units where needed. Mark code, identifiers, and technology/model names as nontranslatable. Application copy remains English in this release; locale formatting does not imply translated documentation support.

## Accessibility and frontend acceptance

- Complete sign-in handoff, project setup, source import, upload, question, evidence inspection, and authorized retry using the keyboard.
- Use semantic landmarks, labeled inputs, visible focus, logical headings, and a logical tab order. Announce asynchronous results politely; errors that need action must remain visible.
- Include a **Skip to main content** link, one page-level heading, semantic tables/list structures, and native buttons/links before adding ARIA. Decorative icons are hidden from assistive technology; icon-only actions have accessible names.
- Keep text contrast at least 4.5:1 for normal text and meaningful control/focus boundaries at least 3:1. Use a 2px accent `:focus-visible` ring with offset; never remove an outline without a replacement. Status must remain understandable without color.
- Ensure dialogs/drawers have a name, contained focus where modal, Escape dismissal where safe, and focus restoration.
- Keep touch controls usable, text readable at 200% zoom, and the main layout usable at 320px width; code/data regions may have their own scrolling.
- Preserve pinch/browser zoom and native coarse-pointer navigation. Gestures always have tap/keyboard alternatives. Apply scroll containment to modal sheets, without suppressing page scroll/navigation globally.
- Sanitize rendered answers/source excerpts and restrict link schemes. Avoid browser-persistent storage for private documents, credentials, or raw answer history.
- Verify ready/partial/failed imports, abstention versus provider failure, revoked evidence, session expiry, unavailable profiles, and budget/rate-limit UI with deterministic fixtures.
- Verify retained historical citations after refresh, paused affected conversations after revocation/deletion, checkpoint/summary non-disclosure, and clean memory in a new conversation.
- Test extremely long/empty names, long code, many citations, translated browser text, slow/offline requests, repeated submissions, unsaved navigation, keyboard focus after dialogs, and workspace switching during an outstanding request.
- Respect forced-colors/high-contrast and reduced-motion preferences. Test screen-reader announcements for one import completion, one answer completion, and one inline form error.
- Keep typing responsive and avoid layout reads during render. Load pages on demand; mount bounded source excerpts and paginated rows. Preserve stable dimensions for loading states and any future images; meaningful media, if added, requires appropriate text alternatives.

## Review basis and limits

Reviewed against [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md), fetched 2026-10-28, and the frontend-design skill. The applicable design-level checks cover semantics, focus, forms, motion, typography, content overflow, navigation/state, touch, safe areas, locale, performance, and interaction feedback.

Current scope has no media, downloaded fonts, or server-side hydration; those guideline branches become applicable if added. Both light and dark theme branches apply now, including native controls, focus, code, diagrams, and status views. Source excerpts remain sanitized and link schemes restricted. This document is a design specification, not a UI-code audit or a claim of WCAG conformance.

## Implementation verification

The direction and app flows were confirmed after grilling. Pixel values/palettes are explicit implementation defaults, not rendered proof. Verify OAuth/email/invitation states, separate GitHub App connection, repository/stack/source reviews, version-aware imports, manual fallback, rescan diff application, upstream access loss, memory/clarification, async turn recovery, workspace spending visibility, and themes end to end. Test OS preference, persisted override, unavailable storage, first-paint theme, and native controls in both modes. Rendered contrast, responsiveness, keyboard/screen-reader behavior, and performance remain unverified.
