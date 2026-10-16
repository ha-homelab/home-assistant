# Security policy

Report vulnerabilities through [GitHub private reporting](https://github.com/ha-homelab/home-assistant/security/advisories/new)
or privately to **alvit.work@gmail.com**. Public issues are for non-sensitive bugs
and suggestions. Include the affected revision, prerequisites, impact and a
minimal synthetic reproduction. Never send live tokens, household recordings,
backups, private device inventories or access to another person's equipment.

The primary maintainer aims to acknowledge reports within 14 days; follow up
privately if no acknowledgement arrives. Triage impact and affected versions,
coordinate remediation and disclosure with the reporter, and credit fixed
vulnerability reports unless anonymity is requested. Handle critical issues
immediately and fix known medium-or-higher vulnerabilities in supported project
results within 60 days of public disclosure. A reviewed mitigation or disabling
an affected supported path may be needed while awaiting an upstream fix.

Security maintenance targets the current default branch and latest published
release, where one exists. Older snapshots are not maintained branches. Release
notes must include the vulnerability's impact, affected/fixed versions, available
CVE/GHSA identifiers and upgrade or mitigation instructions, without secrets.
This is a response commitment, not evidence that no vulnerabilities exist.

The full project includes configuration, bundled automation/script libraries,
maintenance helpers and the standalone notification cache package. Private
secrets stay outside Git and are supplied during deployment. Camera and
notification clients include internal HTTP paths: a private network alone is
not encryption. Do not expose these services to untrusted networks; assess
transport and access controls for the actual deployment. The project does not
claim a universal secure transport profile for every optional integration.

CI uses synthetic fixtures and no deployment credentials. A successful build
or test does not authorize changing a live home or prove actuator safety.
Deployment requires an immutable source revision, verified backup, operator
review and device-specific validation/rollback. See [public source boundaries](docs/public-source.md)
and [quality evidence](docs/quality.md).
