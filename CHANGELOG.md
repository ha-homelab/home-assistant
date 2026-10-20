# Portable library changelog

## [0.1.4] - 2026-10-20

### Fixed

- Preserve complete notification frames up to one MiB when their network chunk also contains part of the next frame.
- Consume larger incoming chunks in bounded segments and recover from oversized incomplete frames without losing a split next-frame start marker.
- Correct the documented package source inventory to include its existing `LICENSE` input.

### Upgrade

Install the chosen beta wheel or source archive into an isolated Python environment and keep the private cache directory explicit. The cache API, private frame permissions, lock ownership, write throttle and cleanup behavior remain unchanged. Preserve the previous package for rollback. This release does not deploy Home Assistant configuration or services.

### Validation

Synthetic regression cases cover exact-limit frames, coalesced chunks and recovery at split markers. Package installation and source checks do not establish live camera or notification-delivery acceptance.

## [0.1.3] - 2026-10-18

### Changed

- Document the notification cache and host-side maintenance flow with updated architecture and operations guidance.
- Preserve owner-only snapshot permissions in the source-only camera helper, including existing snapshots retained during rotation.
- Publish the unchanged portable notification-frame cache implementation under a new reviewed source revision.

### Upgrade

Install the exact notification-frame cache wheel or source archive into an isolated Python environment, keep the private cache directory explicit, and preserve the previous package for rollback. The camera helper is excluded from these distribution assets: operators who adopt that source change must update their separately managed helper. Its snapshot contract assumes the helper and snapshot-serving process use the same operating-system owner. No household configuration or service is deployed by this release.

### Security

The source-only camera helper retains temporary files at mode 0600 and repairs a retained snapshot to owner-only permissions instead of preserving mode 0644. A focused regression covers snapshot rotation and its permissions. The portable package inventory and runtime behavior remain unchanged; it still excludes endpoint-bearing helpers, household configuration and private state. Offline tests do not establish live camera or notification-delivery acceptance.

## [0.1.2] - 2026-10-17

### Changed

- Move installation-specific device identifiers and notification endpoints out of bundled examples into explicit external bindings.
- Reduce installation presentation metadata, use portable source references and correct script and runner guidance.
- License the original configuration and cache package under MIT and add required source-security checks and maintenance policies.

### Upgrade

Install the exact notification-frame cache wheel or source archive into an isolated Python environment and keep the private cache directory explicit. Existing installations must provide their own external device and notification bindings when adopting the examples. Preserve existing private configuration and the previous package for rollback.

### Security

Published examples avoid installation-specific endpoints and identifiers; packages retain the existing allowlisted portable cache inventory. Synthetic validation does not establish live camera, notification-delivery or household deployment acceptance.

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
