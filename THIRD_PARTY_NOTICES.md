# Third-party notices

The root MIT license covers original Home Assistant configuration, bundled automation/script source, tools and documentation maintained by this project. It does not replace upstream licenses or grant rights to external firmware, media or datasets.

The shared release/versioning and workflow-contract helpers are vendored from [venus-os-ci-toolkit](https://github.com/victron-venus/venus-os-ci-toolkit). Their [MIT notice](third_party/venus-os-ci-toolkit-LICENSE) is preserved.

The DESLOC project icon at `config/www/desloc/icon.png` is copied unchanged from
[`ha-homelab/ha-desloc`](https://github.com/ha-homelab/ha-desloc/blob/e78d824455edf825368db477f0bbc12b973571c6/custom_components/desloc/brand/icon.png),
copyright (c) 2026 HA Homelab contributors. Its [MIT notice](third_party/ha-desloc-LICENSE)
is preserved. SHA-256: `ae753a08cbbb70221f6fdbb208d57b624c906487e5aa15bb51efde91aaa45c86`.

The Tuya generated quirk and OTA firmware come from [romasku/tuya-zigbee-switch](https://github.com/romasku/tuya-zigbee-switch). Keep the upstream terms beside the [quirk](config/custom_zha_quirks/TUYA-UPSTREAM-LICENSE.txt) and [OTA artifacts](config/ota/tuya_ts0041/UPSTREAM-LICENSE.txt), plus their [source/build provenance](config/ota/tuya_ts0041/provenance.json). The root license does not relicense these artifacts.

Home Assistant, installed integrations and frontend cards remain separate upstream projects. References, compatibility tests, hashes and links do not change their licenses. Preserve any notices in source fragments or separately fetched packages when redistributing them. This repository's package distribution contains only the documented notification-frame-cache library; it is not a distribution of Home Assistant or a running household installation.
