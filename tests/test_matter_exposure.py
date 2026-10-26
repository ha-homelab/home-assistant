"""Verify additive Matter publication without contacting a bridge or controller."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'tools/matter_exposure.py'
spec = importlib.util.spec_from_file_location('matter_exposure', MODULE)
matter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matter)


def node(entity, endpoint, name):
    return {'endpoint': endpoint, 'id': {'global': 'stable-' + entity}, 'parts': [],
            'state': {'homeAssistantEntity': {'entity': {'entity_id': entity}},
                      'bridgedDeviceBasicInformation': {'uniqueId': entity, 'serialNumber': entity,
                                                       'reachable': True, 'nodeLabel': name}}}


class FakeHub:
    def __init__(self):
        self.calls = []
        self.bridge = {
            'id': 'fixture-bridge', 'name': 'Fixture', 'port': 5540, 'status': 'running',
            'deviceCount': 1, 'filter': {'include': [{'type': 'pattern', 'value': 'light.existing'}],
                                       'exclude': [{'type': 'entity_category', 'value': 'diagnostic'}]},
            'featureFlags': {'stableIdentity': True, 'coverUseHomeAssistantPercentage': True},
            'uniqueIdSuffix': 'keep', 'commissioning': {'isCommissioned': True,
                'manualPairingCode': 'DO-NOT-PRINT', 'fabrics': [{'fabricIndex': 1, 'fabricId': 'private'}]},
        }
        self.mappings = {'light.existing': {'customName': 'Old Name', 'powerEntity': 'sensor.existing_power',
                                           'customDeviceType': 'DimmableLight'}}
        self.graph = {'endpoint': 0, 'id': {'global': 'root'}, 'parts': [node('light.existing', 1, 'Old Name')], 'state': {}}
        self.new_reachable = True
        self.mutate_identity = False
        self.mutate_fabric = False
        self.raise_on_mapping_put = False
        self.inject_config_drift = False
        self.bridge_gets = 0

    def call(self, path, method='GET', data=None):
        self.calls.append((path, method, copy.deepcopy(data)))
        base = '/matter/bridges/fixture-bridge'
        if path == base and method == 'GET':
            self.bridge_gets += 1
            result = copy.deepcopy(self.bridge)
            if self.inject_config_drift and self.bridge_gets > 1:
                result['port'] = 5555
            return result
        if path == base and method == 'PUT':
            self.bridge.update(copy.deepcopy(data))
            return copy.deepcopy(self.bridge)
        if path == base + '/devices':
            return copy.deepcopy(self.graph)
        if path == '/entity-mappings/fixture-bridge':
            return {'bridgeId': 'fixture-bridge', 'mappings': [dict(entityId=k, **v) for k, v in self.mappings.items()]}
        if path.startswith('/entity-mappings/fixture-bridge/') and method == 'PUT':
            if self.raise_on_mapping_put:
                raise matter.ExposureError('Uncertain mapping write')
            entity = path.rsplit('/', 1)[1]
            self.mappings[entity] = copy.deepcopy(data)
            return dict(entityId=entity, **data)
        if path == '/matter/filter-preview':
            entities = {v['value'] for v in data['include'] if v['type'] == 'pattern'}
            return {'total': len(entities), 'truncated': False,
                    'entities': [{'entity_id': e} for e in sorted(entities)]}
        if path == '/home-assistant/refresh':
            return {}
        if path == base + '/actions/refresh':
            existing = {matter.entity_id(n): n for n in self.graph['parts']}
            for item in self.bridge['filter']['include']:
                entity = item['value']
                if entity not in existing:
                    added = node(entity, len(self.graph['parts']) + 1, entity)
                    added['state']['bridgedDeviceBasicInformation']['reachable'] = self.new_reachable
                    self.graph['parts'].append(added)
            for child in self.graph['parts']:
                entity = matter.entity_id(child)
                if entity in self.mappings:
                    child['state']['bridgedDeviceBasicInformation']['nodeLabel'] = self.mappings[entity]['customName']
            self.bridge['deviceCount'] = len(self.graph['parts'])
            if self.mutate_identity:
                self.graph['parts'][0]['state']['bridgedDeviceBasicInformation']['uniqueId'] = 'wrong'
            if self.mutate_fabric:
                self.bridge['commissioning']['fabrics'][0]['fabricId'] = 'wrong'
            return {}
        raise AssertionError(f'Unexpected API operation: {method} {path}')


class MatterExposureTest(unittest.TestCase):
    entities: ClassVar[dict[str, str]] = {'light.existing': 'Existing Light', 'light.new': 'New Light'}

    def test_dry_run_does_not_modify_bridge_or_mappings(self):
        hub = FakeHub()
        original = copy.deepcopy(hub.bridge)
        result = matter.run(hub, 'fixture-bridge', self.entities)
        self.assertEqual(result['mode'], 'dry-run')
        self.assertEqual(result['filters_to_add'], 1)
        self.assertEqual(hub.bridge, original)
        self.assertEqual(hub.mappings['light.existing']['customName'], 'Old Name')
        self.assertTrue(all(method == 'GET' or path == '/matter/filter-preview'
                            for path, method, _ in hub.calls))
        self.assertNotIn('DO-NOT-PRINT', json.dumps(result))
        self.assertNotIn('private', json.dumps(result))

    def test_apply_preserves_filters_flags_mapping_fields_and_identity(self):
        hub = FakeHub()
        flags = copy.deepcopy(hub.bridge['featureFlags'])
        excluded = copy.deepcopy(hub.bridge['filter']['exclude'])
        result = matter.run(hub, 'fixture-bridge', self.entities, apply=True, settle_seconds=0)
        self.assertTrue(result['verified'])
        self.assertEqual(result['after_devices'], 2)
        self.assertEqual(hub.bridge['featureFlags'], flags)
        self.assertEqual(hub.bridge['filter']['exclude'], excluded)
        self.assertEqual(hub.bridge['uniqueIdSuffix'], 'keep')
        self.assertEqual(hub.mappings['light.existing']['powerEntity'], 'sensor.existing_power')
        self.assertEqual(hub.mappings['light.existing']['customDeviceType'], 'DimmableLight')
        bridge_put = next(data for path, method, data in hub.calls
                          if method == 'PUT' and path == '/matter/bridges/fixture-bridge')
        self.assertNotIn('commissioning', bridge_put)
        self.assertNotIn('status', bridge_put)
        self.assertNotIn('deviceCount', bridge_put)

    def test_reapplying_does_not_duplicate_filters_or_rewrite_mappings(self):
        hub = FakeHub()
        matter.run(hub, 'fixture-bridge', self.entities, apply=True, settle_seconds=0)
        hub.calls.clear()
        result = matter.run(hub, 'fixture-bridge', self.entities, apply=True, settle_seconds=0)
        self.assertTrue(result['verified'])
        self.assertEqual(result['filters_to_add'], 0)
        self.assertFalse(any(method == 'PUT' for _, method, _ in hub.calls))

    def test_offline_endpoint_is_reported_as_not_verified(self):
        hub = FakeHub()
        hub.new_reachable = False
        result = matter.run(hub, 'fixture-bridge', self.entities, apply=True, settle_seconds=0)
        self.assertFalse(result['verified'])
        self.assertEqual(result['unreachable'], ['light.new'])
        self.assertTrue(result['controller_fabrics_preserved'])

    def test_endpoint_identity_and_fabric_change_fail_verification(self):
        for change in ('mutate_identity', 'mutate_fabric'):
            with self.subTest(change=change):
                hub = FakeHub()
                setattr(hub, change, True)
                with self.assertRaises(matter.ExposureError):
                    matter.run(hub, 'fixture-bridge', self.entities, apply=True, settle_seconds=0)

    def test_existing_endpoint_cannot_silently_change_its_ha_entity(self):
        hub = FakeHub()
        original = hub.call
        def call(path, method='GET', data=None):
            result = original(path, method, data)
            if path.endswith('/actions/refresh'):
                # The old endpoint is outside the requested manifest. All Matter
                # identity fields stay unchanged, but it controls a different load.
                hub.graph['parts'][0]['state']['homeAssistantEntity']['entity']['entity_id'] = 'switch.other_power'
            return result
        hub.call = call
        with self.assertRaisesRegex(matter.ExposureError, 'changed its HA entity'):
            matter.run(hub, 'fixture-bridge', {'light.new': 'New Light'}, apply=True, settle_seconds=0)

    def test_refreshed_device_count_must_still_respect_the_limit(self):
        for count in (81, -1, None, True, '2'):
            with self.subTest(count=count):
                hub = FakeHub()
                original = hub.call
                def call(path, method='GET', data=None, *, _original=original, _hub=hub, _count=count):
                    result = _original(path, method, data)
                    if path.endswith('/actions/refresh'):
                        # A registry refresh can add devices after a valid preview.
                        _hub.bridge['deviceCount'] = _count
                    return result
                hub.call = call
                with self.assertRaisesRegex(matter.ExposureError, 'Refreshed device count'):
                    matter.run(hub, 'fixture-bridge', self.entities, apply=True,
                               max_devices=80, settle_seconds=0)

    def test_config_drift_stops_before_mutation(self):
        hub = FakeHub()
        hub.inject_config_drift = True
        with self.assertRaisesRegex(matter.ExposureError, 'changed after planning'):
            matter.run(hub, 'fixture-bridge', self.entities, apply=True)
        self.assertFalse(any(method == 'PUT' for _, method, _ in hub.calls))

    def test_uncertain_write_is_not_retried(self):
        hub = FakeHub()
        hub.raise_on_mapping_put = True
        with self.assertRaisesRegex(matter.ExposureError, 'Uncertain'):
            matter.run(hub, 'fixture-bridge', self.entities, apply=True)
        self.assertEqual(sum(method == 'PUT' for _, method, _ in hub.calls), 1)

    def test_size_limit_blocks_before_writes(self):
        hub = FakeHub()
        with self.assertRaisesRegex(matter.ExposureError, 'device limit'):
            matter.run(hub, 'fixture-bridge', self.entities, apply=True, max_devices=1)
        self.assertFalse(any(method == 'PUT' for _, method, _ in hub.calls))

    def test_invalid_existing_count_blocks_before_writes(self):
        for count in (81, -1, None, True, '2'):
            with self.subTest(count=count):
                hub = FakeHub()
                hub.bridge['deviceCount'] = count
                with self.assertRaisesRegex(matter.ExposureError, 'Existing device count'):
                    matter.run(hub, 'fixture-bridge', self.entities, apply=True)
                self.assertFalse(any(method == 'PUT' for _, method, _ in hub.calls))

    def test_invalid_preview_blocks_before_writes(self):
        valid_entities = [{'entity_id': entity} for entity in self.entities]
        invalid = [
            {'total': count, 'entities': valid_entities} for count in (-1, True, '2', 1, 3)
        ] + [
            {'total': 2, 'entities': valid_entities, 'truncated': True},
            {'total': 2, 'entities': valid_entities + [{'entity_id': 'light.extra'}]},
            {'total': 2, 'entities': [{'entity_id': 'light.existing'}] * 2},
            {'total': 2, 'entities': [None, {'entity_id': 'light.new'}]},
            {'total': 2, 'entities': [{'entity_id': []}, {'entity_id': 'light.new'}]},
        ]
        for preview in invalid:
            with self.subTest(preview=preview):
                hub = FakeHub()
                original = hub.call
                def call(path, method='GET', data=None, *, _preview=preview, _original=original):
                    if path == '/matter/filter-preview':
                        return _preview
                    return _original(path, method, data)
                hub.call = call
                with self.assertRaises(matter.ExposureError):
                    matter.run(hub, 'fixture-bridge', self.entities, apply=True)
                self.assertFalse(any(method == 'PUT' for _, method, _ in hub.calls))

    def test_missing_preview_entity_blocks_before_writes(self):
        hub = FakeHub()
        original = hub.call
        def call(path, method='GET', data=None):
            if path == '/matter/filter-preview':
                return {'total': 1, 'truncated': False, 'entities': [{'entity_id': 'light.existing'}]}
            return original(path, method, data)
        hub.call = call
        with self.assertRaisesRegex(matter.ExposureError, 'missing from preview'):
            matter.run(hub, 'fixture-bridge', self.entities, apply=True)
        self.assertFalse(any(method == 'PUT' for _, method, _ in hub.calls))

    def test_unsupported_mapping_shape_cannot_erase_existing_mapping(self):
        with self.assertRaisesRegex(matter.ExposureError, 'schema'):
            matter.mapping_index({'bridgeId': 'fixture', 'mappings': [{'name': 'old'}]}, 'fixture')

    def test_manifest_rejects_wildcards_actions_duplicate_names_and_long_names(self):
        invalid = [
            [{'entity_id': 'light.*', 'name': 'All'}],
            [{'entity_id': 'button.restart', 'name': 'Restart'}],
            [{'entity_id': 'automation.shutdown', 'name': 'Shutdown'}],
            [{'entity_id': 'light.a', 'name': 'Same'}, {'entity_id': 'light.b', 'name': 'same'}],
            [{'entity_id': 'light.a', 'name': 'é' * 17}],
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            for entries in invalid:
                path.write_text(json.dumps({'entities': entries}))
                with self.subTest(entries=entries), self.assertRaises(matter.ExposureError):
                    matter.read_manifest(path)

    def test_checked_in_manifest_contains_only_explicit_unique_controls(self):
        entries = matter.read_manifest(matter.DEFAULT_MANIFEST)
        self.assertEqual(len(entries), 46)
        self.assertEqual(entries['light.porch_one'], 'Porch Light 1')
        self.assertEqual(entries['light.porch_two'], 'Porch Light 2')
        self.assertEqual(entries['light.porch_light'], 'Porch Light')
        self.assertEqual(entries['cover.studio_curtains'], 'Studio Curtains')
        self.assertNotIn('cover.office_curtains_r', entries)
        self.assertNotIn('switch.bath2', entries)
        self.assertNotIn('switch.bath_2', entries)

    def test_transport_errors_do_not_echo_private_urls_or_response_bodies(self):
        client = matter.Client('http://hub.example.invalid')
        with (patch.object(client.opener, 'open', side_effect=matter.error.URLError('PRIVATE-TOKEN')),
              self.assertRaises(matter.ExposureError) as raised):
            client.call('/anything')
        self.assertNotIn('PRIVATE-TOKEN', str(raised.exception))
        self.assertNotIn('example.invalid', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
