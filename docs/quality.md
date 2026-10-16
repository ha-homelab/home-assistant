# Quality evidence and limitations

Configuration CI validates root and bundled YAML contracts, builds the complete
source overlay and runs production automation/script scenarios inside a pinned
Home Assistant image without network or hardware access. The notification frame
cache wheel is one component; an assessment must also cover the complete bundled
configuration, maintenance helpers and external runtime integration inventory.

YAML validation or an offline wheel test does not prove camera transport,
credential protection or actual device safety. Internal HTTP camera/notification
clients and deployment-specific integrations require a separate scoped review.
No complete code-coverage percentage, universal TLS policy or whole-dependency
clean scan is claimed. See [public source boundaries](public-source.md) and the
[security policy](../SECURITY.md).

The primary maintainer personally confirms knowledge of secure design and common
Python/network application vulnerabilities, and no bug, feature or vulnerability
reports outside GitHub in the preceding twelve months as of 2026-10-16. These are
human attestations, not automated findings. Public issue history and current
diagnostics must also be reviewed for each assessment update.
