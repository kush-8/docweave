# Required publisher reference registry



`required-sources.json` records the 29 agreed technologies and 85 explicitly bounded official publisher pages. `required-sources-verification.json` contains the successful HTTP status, actual MIME, byte count, raw-response SHA256, title, first heading, timestamp and available HTTP validators for every page. The report binds the reviewed manifest with SHA256 of its UTF-8 text after CRLF-to-LF normalization. Publisher body hashes are never normalized.

The recorded final run verifies all 85 pages against robots policies across 24 origins and successfully parses all 85 with the application parser: 1,707,106 normalized characters and 798 chunks. Five offline tests check completeness, byte-level evidence, current parser-source hashes, manifest binding and reproducible robots decisions. These counts describe preparation proof; no embedding or index is created.



These are real read-only fetch observations, not just proposed URLs. Their scope is the enumerated page bodies and topics. The HTML title/headings were inspected for the expected subjects; redirect shells were replaced with their current publisher destinations. The Python `/3` pages identify a rolling documentation family. SQLAlchemy uses three commit-pinned official `rel_2_0` RST source files as plain text because its rendered docs origin redirects robots policy off-origin; RST roles/includes are not expanded. Neither is asserted to match an exact installed package release. Playwright uses three official commit-pinned Markdown source files to preserve the HTML depth64 guardrail. Markdown paths served as `text/plain` are passed to the parser as `text/markdown`, matching ingestion; SQLAlchemy RST remains `text/plain`. Most other sources use rolling/latest documentation, and AWS and GitHub Actions document hosted services rather than a matching package version.



Publisher identity, attribution and publisher license/terms pointers accompany each entry. They do not grant redistribution permission or substitute for license review. Robots decisions are recorded for the actual `DocWeave/0.1` agent using the standard-library `RobotFileParser`, including a bounded snapshot/hash of each origin's robots policy; 404 permits fetching and other non-200 statuses fail closed, matching ingestion. Crawl delays above 10 seconds fail closed. No documentation page body is committed. No copyright-bearing manual is vendored. Includes, links, generated APIs, interactive tabs, client-only text, images and executable examples are not expanded. These are bounded subject samples, not complete manuals or every subsection within the agreed subject areas.



Recheck from the repository root using PowerShell 7:



```powershell

pwsh -NoProfile -File backend/catalog/verify_sources.ps1

```



The verifier uses HTTPS GET against a fixed publisher-host list, refuses HTTP and HTML-refresh redirects, runs sequentially with at least one second between requests to the same host (honoring supported robots crawl delays), times out after 10 seconds across headers and body, and stops reading each page at 2 MiB and each robots policy at 256 KiB. Each admitted body is passed in memory to the actual application `parse_text` HTML/TXT parser before being discarded. The report records normalized SHA256, character/chunk counts, parser configuration and source hashes, with no document text. It saves metadata plus bounded robots-policy evidence and exits nonzero if any page or parse fails. It accepts no credentials or URL queries. It does not crawl links. A rerun replaces the report with new observations; rolling HTML (including site navigation) can change its hash without a topic change. Review resulting diffs before relying on the new evidence. This Windows review tool uses native TLS trust and is not the application's DNS/IP-pinned ingestion fetcher.



Run the offline evidence checks without a database or network:



```powershell

uv run --project backend --locked python -m pytest backend/tests/rag/test_required_catalog.py -q

```



This reference registry deliberately uses a different shape from `publisher-pages.json`, the operator's versioned Python/JavaScript `CatalogManifest`. It cannot be passed to `python -m docweave.catalog`, matched automatically to dependencies, or selected as an approved catalog revision. It supplies bounded publisher evidence for subsequent review. Operator approval, license review, exact release mapping where needed, subsequent guardrail admission and live index/retrieval verification and any separately authorized provider work remain separate gates. The existing three release-pinned examples remain unchanged.

