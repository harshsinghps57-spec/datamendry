# Security and privacy — preview build

DataMendry v0.2 is a **public-preview prototype**, not a compliant production service. The default application has no user accounts, quotas, per-user rate limiting, or external security audit.

## Data handling

- Uploaded UTF-8 CSV files are **sent to the application host** and parsed into short-lived SQLite files.
- A randomly generated 128-bit dataset identifier is an **access secret**: whoever knows it can view/download or delete the dataset. Never share dataset URLs or logs.
- Workspaces are deleted when a user requests deletion or an expired dataset is next accessed; a new upload also triggers cleanup. In a low-traffic environment, old files can remain on disk past their TTL, so schedule cleanup externally for production.
- Public free hosting may erase files during redeploy or restart, even before configured expiry.
- There is no external AI processing service in v0.2.

## CSV export and safety

The exporter prefixes potentially spreadsheet-interpreted formulas with an apostrophe. This deliberately changes formula-like values; if preserving exact representation is critical, use the original file. Spreadsheet programs differ, so do not treat this as a universal guarantee against formula injection.

## Known public deployment gaps

Before collecting sensitive user data or promising reliable access, implement authentication, authorization, multi-tenant isolation, disk quotas, upload rate limits, virus/zip-bomb protection where relevant, edge and service-level request limits, structured log redaction, an external cleanup worker, background processing, capacity planning, abuse monitoring, HTTPS, dependency security checks, and an independent security review.

## Reporting vulnerabilities

For now, do not file exploits containing real data in public issues. Contact the maintainer privately through the repository profile; a dedicated security contact will be added after the repository is published.
