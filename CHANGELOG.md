# Portable library changelog

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
