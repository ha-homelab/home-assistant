"""Check the shipped OTA and real ZHA registration without device/network I/O."""
import binascii
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
OTA = ROOT / 'config/ota/tuya_ts0041'
QUIRK = ROOT / 'config/custom_zha_quirks/tuya_binding_switch.py'
TARGET = ('mrpevh8p', 'TS0041-TB')
HEADER = struct.Struct('<I5HIH32sI')
RUNTIME_AVAILABLE = all(importlib.util.find_spec(name) is not None
                        for name in ('homeassistant', 'zha', 'zigpy', 'zhaquirks'))
if os.environ.get('REQUIRE_HA_RUNTIME') == '1' and not RUNTIME_AVAILABLE:
    raise RuntimeError('Home Assistant and its ZHA runtime are required')


class GarageButtonOtaTest(unittest.TestCase):
    def setUp(self):
        entries = json.loads((OTA / 'index.json').read_text())
        self.assertEqual(len(entries), 1, 'Only the normal-update image may be advertised')
        self.entry = entries[0]
        filename = self.entry['path']
        self.assertEqual(filename, Path(filename).name, 'Image must remain beside the index')
        self.assertEqual(self.entry['fileName'], filename)
        self.image = (OTA / filename).read_bytes()

    def test_index_targets_only_converted_button_and_matching_local_image(self):
        self.assertEqual(self.entry['manufacturerName'], [TARGET[0]])
        self.assertEqual(self.entry['modelId'], TARGET[1])
        self.assertEqual(self.entry['manufacturerCode'], 4417)
        self.assertEqual(self.entry['imageType'], 45636)
        self.assertEqual(self.entry['fileVersion'], 0x11033001)
        self.assertEqual(self.entry['fileSize'], len(self.image))
        self.assertEqual(self.entry['sha512'], hashlib.sha512(self.image).hexdigest())

    def test_ota_header_and_payload_match_index_and_device(self):
        self.assertGreaterEqual(len(self.image), HEADER.size + 6 + 32)
        (magic, revision, header_size, flags, manufacturer, image_type,
         version, stack, label, size) = HEADER.unpack_from(self.image)
        self.assertEqual((magic, revision, header_size, flags),
                         (0x0BEEF11E, 0x100, HEADER.size, 0))
        self.assertEqual((manufacturer, image_type, version),
                         (self.entry['manufacturerCode'], self.entry['imageType'],
                          self.entry['fileVersion']))
        self.assertEqual(stack, 2)
        self.assertEqual(label.rstrip(b'\0').decode('ascii'), self.entry['otaHeaderString'])
        self.assertEqual(size, len(self.image))
        tag, payload_size = struct.unpack_from('<HI', self.image, header_size)
        payload = self.image[header_size + 6:]
        self.assertEqual((tag, payload_size), (0, len(payload)))
        # SDK 3.7.2.0 rejects the full QueryNextImage imageSize before download,
        # separately from its embedded firmware-size check before reboot.
        self.assertLessEqual(len(self.image), 0x34000, 'SDK OTA acceptance limit is 208 KiB')
        self.assertEqual(payload[8:12], b'KNLT')
        self.assertEqual(payload[6:8], b'\x5d\x02')
        self.assertEqual(int.from_bytes(payload[2:6], 'little'), version)
        self.assertEqual(int.from_bytes(payload[0x18:0x1c], 'little'), len(payload))
        self.assertEqual(int.from_bytes(payload[-4:], 'little'),
                         binascii.crc32(payload[:-4]) ^ 0xFFFFFFFF)
        self.assertIn(b'mrpevh8p;TS0041-TB;BB4d;SB5u;ID2;BTB5;M;', payload)


@unittest.skipUnless(RUNTIME_AVAILABLE, 'Requires Home Assistant and its ZHA runtime')
class GarageButtonQuirkTest(unittest.TestCase):
    def test_real_registration_is_target_only_and_exposes_hold_off_mode(self):
        from zha.quirks import DEVICE_REGISTRY

        # Preserve the native registry so broad unittest discovery remains isolated.
        # The imported module executes the real builder and cluster definitions.
        with DEVICE_REGISTRY.preserve_state():
            before = {id(entry) for entry in DEVICE_REGISTRY}
            module_name = f'_garage_button_contract_{id(self)}'
            spec = importlib.util.spec_from_file_location(module_name, QUIRK)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            self.addCleanup(sys.modules.pop, spec.name, None)
            spec.loader.exec_module(module)
            added = [entry for entry in DEVICE_REGISTRY if id(entry) not in before]
            self.assertEqual(len(added), 1)
            entry = added[0]
            self.assertEqual(tuple(entry.device_match.applies_to), (TARGET,))
            self.assertIs(DEVICE_REGISTRY.match_entry(
                SimpleNamespace(manufacturer=TARGET[0], model=TARGET[1])), entry)
            for manufacturer, model in (
                ('_TZ3000_mrpevh8p', 'TS0041'),
                ('another_manufacturer', TARGET[1]),
                (TARGET[0], 'TS0042'),
            ):
                with self.subTest(manufacturer=manufacturer, model=model):
                    self.assertFalse(entry.device_match.matches(
                        SimpleNamespace(manufacturer=manufacturer, model=model)))
            cluster = module.CustomOnOffConfigurationCluster
            self.assertEqual(cluster.cluster_id, 0x0007)
            mode = cluster.AttributeDefs.binded_mode
            self.assertEqual(mode.id, 0xFF05)
            self.assertFalse(mode.is_manufacturer_specific)
            self.assertIs(mode.type, module.BindedMode)
            self.assertEqual(int(module.BindedMode.ShortPressLongOff), 4)
            self.assertEqual(int(module.BindedMode.PressStart), 1)
            self.assertEqual(cluster.AttributeDefs.long_press_duration.id, 0xFF03)


if __name__ == '__main__':
    unittest.main()
