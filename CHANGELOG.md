# Portable library changelog

## [0.1.1] - 2026-10-14

### Changed

- Validate each public release candidate with bounded, network-isolated fuzz campaigns against its exact source revision.
- Require positive engine execution counts, instrumented production code and validated seed corpora; retain source-bound reports and diagnostic evidence.
- Run deterministic seed and configuration checks in ordinary CI without starting mutation campaigns on betas.

### Upgrade

Use the existing installation procedure, preserve local configuration and keep the previous accepted package for rollback. This maintenance release updates release validation and does not change the application configuration format. Deployment and applicable device or integration acceptance remain separate from publication.

### Security

RC publication rejects absent or invalid source-bound fuzz reports. The fuzz runner bounds corpus paths, file types and size. No application vulnerability or new target-device acceptance is claimed by these tooling changes.

## [0.1.0]

### Added

- Package the existing notification-frame cache as an installable Python wheel
  and source distribution using an explicit three-file build inventory.
- Bind beta/RC package metadata and receipts to frozen version plans; require
  the bounded Linux frame-parser campaign before RC publication.

### Upgrade

install the exact archive into an isolated Python environment and
  supply a private cache directory explicitly. Existing household deployment
  and configuration tooling is unchanged and is not invoked by publication.

### Security

packages exclude household configuration, endpoint-bearing helpers,
  private state and child libraries. Synthetic tests do not establish live
  camera, notification-delivery or installation acceptance.
