# Third-party notices

The root MIT license covers original Home Assistant configuration, bundled automation/script source, tools and documentation maintained by this project. It does not replace upstream licenses or grant rights to external firmware, media or datasets.

The shared release/versioning and workflow-contract helpers are vendored from [venus-os-ci-toolkit](https://github.com/victron-venus/venus-os-ci-toolkit). Their [MIT notice](third_party/venus-os-ci-toolkit-LICENSE) is preserved.

The Tuya generated quirk and OTA firmware come from [romasku/tuya-zigbee-switch](https://github.com/romasku/tuya-zigbee-switch). Keep the upstream terms beside the [quirk](config/custom_zha_quirks/TUYA-UPSTREAM-LICENSE.txt) and [OTA artifacts](config/ota/tuya_ts0041/UPSTREAM-LICENSE.txt), plus their [source/build provenance](config/ota/tuya_ts0041/provenance.json). The root license does not relicense these artifacts.

Home Assistant, installed integrations and frontend cards remain separate upstream projects. References, compatibility tests, hashes and links do not change their licenses. Preserve any notices in source fragments or separately fetched packages when redistributing them. This repository's package distribution contains only the documented notification-frame-cache library; it is not a distribution of Home Assistant or a running household installation.
