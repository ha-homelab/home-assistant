// Run only the real bundle's discovery and summary functions in an offline VM.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { original, patched } = JSON.parse(fs.readFileSync(0, 'utf8'));
const keys = ['FrontLeft', 'FrontRight', 'RearLeft', 'RearRight'].map(s => `tirePressure${s}`);
const filters = Object.fromEntries(keys.map(key => [key, { suffix: `_${key.toLowerCase()}` }]));
filters.odometer = { suffix: '_odometer' };
filters.tirePressureWarning = { suffix: '_tirewarninglamp' };

function extract(source, start, end) {
  const offset = source.indexOf(start);
  assert.ok(offset >= 0, `Missing function: ${start}`);
  const stop = source.indexOf(end, offset);
  assert.ok(stop > offset);
  return source.slice(offset, stop);
}

function pressureMethod(source, card) {
  const assignment = extract(source, 'this.getMinMaxTyrePressure=()=>{', ',this._setUpButtonAnimation=');
  vm.runInNewContext(`(function(){${assignment}}).call(card)`, { card });
  return () => card.getMinMaxTyrePressure();
}

function discover(source, hass, rows) {
  // qH contains the entity suffix map; sZ is memoizeOne. Neither does I/O.
  const assignment = extract(source, 'ZH=sZ(async(', ');async function GH') + ')';
  const lookup = vm.runInNewContext(`let ${assignment}; ZH`, { sZ: f => f, qH: filters });
  hass.callWS = async request => {
    assert.equal(request.type, 'config/entity_registry/list');
    return rows;
  };
  return lookup(hass, { entity: 'sensor.car' }, {});
}

async function main() {
  const rows = [
    { entity_id: 'sensor.car', device_id: 'car' },
    ...keys.map((key, i) => ({ entity_id: `sensor.wheel_${i}`, unique_id: `vehicle_${key.toLowerCase()}`, device_id: 'car' })),
    { entity_id: 'sensor.odometer', unique_id: 'vehicle_odometer', device_id: 'car' },
    { entity_id: 'binary_sensor.warning', unique_id: 'vehicle_tirewarninglamp', device_id: 'car' },
    { entity_id: 'sensor.hidden', unique_id: 'vehicle_tirepressurefrontleft', device_id: 'car', hidden_by: 'user' },
    { entity_id: 'sensor.disabled', unique_id: 'vehicle_tirepressurerearright', device_id: 'car', disabled_by: 'user' },
    { entity_id: 'sensor.other_car', unique_id: 'other_tirepressurefrontleft', device_id: 'other' },
  ].map(row => ({ hidden_by: null, disabled_by: null, ...row }));
  const hass = { states: {}, localize: key => key === 'state.default.unavailable' ? 'Unavailable' : undefined };
  for (const row of rows) hass.states[row.entity_id] = { state: 'unavailable', attributes: { unit_of_measurement: 'psi' } };
  // Reproduce both defects in the original bundle.
  assert.equal(Object.keys(await discover(original, hass, rows)).length, 0);
  const mappings = await discover(patched, hass, rows);
  assert.deepEqual(Object.keys(mappings).sort(), [...keys, 'tirePressureWarning'].sort());
  assert.deepEqual(Object.values(mappings).map(e => e.entity_id).sort(), ['binary_sensor.warning', 'sensor.wheel_0', 'sensor.wheel_1', 'sensor.wheel_2', 'sensor.wheel_3']);
  const card = {
    _hass: hass, vehicleEntities: mappings, DataKeys: { tyrePressures: keys.map(key => ({ key })) },
    getEntityState: id => hass.states[id]?.state || '',
    getEntityAttribute: (id, key) => hass.states[id]?.attributes?.[key],
  };
  assert.match(pressureMethod(original, card)(), /NaN/);
  const summary = pressureMethod(patched, card);
  assert.equal(summary(), 'Unavailable');
  const set = (values, unit = 'psi') => values.forEach((state, i) => {
    hass.states[`sensor.wheel_${i}`] = { state, attributes: { unit_of_measurement: unit } };
  });
  // Same mappings/card instance recover without discovery or a page reload.
  set(['38', '39.25', '40', '41.75']);
  assert.equal(summary(), '38 - 41.8 psi');
  set(['2.4', '2.5', '2.6', '2.6'], 'bar');
  assert.equal(summary(), '2.4 - 2.6 bar');
  for (const invalid of ['unavailable', 'unknown', '', '  ', 'NaN', 'Infinity', '-Infinity', '-1', '40psi', '39,5', null, undefined]) {
    set(['38', '39', invalid, '40']);
    assert.equal(summary(), 'Unavailable', `Invalid pressure ${invalid}`);
  }
  set(['0', '0', '0', '0']);
  assert.equal(summary(), '0 - 0 psi');
  delete hass.states['sensor.wheel_3'];
  assert.equal(summary(), 'Unavailable');
  assert.equal(Object.keys(await discover(patched, hass, rows)).length, 5);
  set(['38', '39', '40', '41']);
  hass.states['sensor.wheel_0'].attributes.unit_of_measurement = 'bar';
  assert.equal(summary(), 'Unavailable');
  set(['38', '39', '40', '41'], undefined);
  delete hass.states['sensor.wheel_0'].attributes.unit_of_measurement;
  assert.equal(summary(), 'Unavailable');
  hass.localize = () => 'Недоступно';
  assert.equal(summary(), 'Недоступно');
  hass.localize = () => undefined;
  assert.equal(summary(), 'Unavailable');
  set(['38', '39', '40', '41']);
  assert.equal(summary(), '38 - 41 psi');
  card.DataKeys.tyrePressures.pop();
  assert.equal(summary(), 'Unavailable');

  // Selecting tires must not execute the unavailable hidden vehicle panel.
  const renderPrefix = extract(patched, '_renderCustomCard(){', 'const l=this.config.entity?');
  const renderSelected = vm.runInNewContext(`({${renderPrefix}return s;}})._renderCustomCard`, { iX: a => !a.length });
  for (const type of ['tripCards', 'vehicleCards', 'ecoCards', 'tyreCards', 'servicesCard']) {
    const calls = [];
    const fixture = {
      _currentCardType: type,
      buttonCards: { [type]: { card_type: 'default', custom_card: [] } },
      _showWarning: () => 'empty',
    };
    for (const [key, method] of Object.entries({ tripCards: 'Trip', vehicleCards: 'Vehicle', ecoCards: 'Eco', tyreCards: 'Tyre', servicesCard: 'ServiceControl' })) {
      fixture[key === 'servicesCard' ? '_renderServiceControl' : `_renderDefault${method}Card`] = () => { calls.push(key); return key; };
    }
    assert.equal(renderSelected.call(fixture), type);
    assert.deepEqual(calls, [type]);
    if (type !== 'servicesCard') {
      fixture.buttonCards[type] = { card_type: 'custom', custom_card: ['custom'] };
      calls.length = 0;
      assert.deepEqual(renderSelected.call(fixture), ['custom']);
      assert.deepEqual(calls, []);
    }
  }

  // Exercise the whole real tire panel render, including unknown warning state.
  const panelCode = extract(patched, '_renderDefaultTyreCard(){', 'toggleTireDirection(e){');
  const panel = vm.runInNewContext(`({${panelCode}})._renderDefaultTyreCard`, {
    oe: (strings, ...values) => strings.reduce((result, part, i) => result + part + (values[i] ?? ''), ''),
    Ne: value => value, dge: { BACK_TYRE: '' },
  });
  card.config = {};
  card.DataKeys.tyrePressures = keys.map(key => ({ key }));
  card.getBooleanState = id => hass.states[id]?.state === 'on';
  card.getStateDisplay = id => hass.states[id]?.state || 'Unavailable';
  card.localize = key => key === 'card.tyreCard.tireWarningOk' ? 'Pressure normal' : key === 'card.tyreCard.tireWarningProblem' ? 'Pressure warning' : 'Tire pressure';
  for (const [state, expected] of [['unavailable', 'Unavailable'], ['unknown', 'Unavailable'], ['on', 'Pressure warning'], ['off', 'Pressure normal']]) {
    hass.states['binary_sensor.warning'].state = state;
    const output = panel.call(card);
    assert.ok(output.includes(`<span>${expected}</span>`));
    if (!['on', 'off'].includes(state)) assert.ok(!output.includes('Pressure normal'));
  }
  console.log(JSON.stringify({ result: 'passed' }));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
