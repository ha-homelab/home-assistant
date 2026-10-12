/* Run the real custom element with a small DOM boundary and fake HA transport. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(tag = 'element') { this.tagName = tag; this.children = []; this.attributes = {}; }
  appendChild(child) { this.children.push(child); return child; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; if (name === 'href') delete this.href; }
  attachShadow() { return (this.shadowRoot = new Element('shadow-root')); }
  set innerHTML(_) { throw new Error('Dynamic HTML parsing is forbidden in this card'); }
}
const registry = new Map();
const context = vm.createContext({
  HTMLElement: Element,
  document: { createElement: (tag) => new Element(tag) },
  customElements: { get: (name) => registry.get(name), define: (name, constructor) => registry.set(name, constructor) },
  window: { confirm: () => true },
  console,
  fetch: () => { throw new Error('The card must never call the updater HTTP endpoint'); },
});
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);
const Card = registry.get('core-update-card');
assert.equal(typeof Card, 'function');
assert.equal(context.window.customCards[0].type, 'core-update-card');

const candidate = 'a'.repeat(32);
const replacement = 'b'.repeat(32);
function makeHass(calls, attributes = {}, state = 'on', transport) {
  return {
    states: { 'update.home_assistant_core': { state, attributes: {
      installed_version: '2026.9.1', latest_version: '2026.10.0', target_version: '2026.10.0',
      candidate_id: candidate, stage: 'available', in_progress: false, ...attributes,
    } } },
    callService: transport || (async (domain, service, data) => calls.push({ domain, service, data })),
  };
}
function makeCard(calls = [], attributes = {}, state = 'on', transport) {
  const card = new Card();
  card.setConfig({});
  card.hass = makeHass(calls, attributes, state, transport);
  context.window.confirm = () => true;
  return card;
}
function normalize(value) { return JSON.parse(JSON.stringify(value)); }

(async () => {
  let passed = 0;
  const empty = new Card();
  assert.equal(empty._button.disabled, true);
  assert.equal(empty._badge.textContent, 'Unavailable');
  passed++;

  const calls = [];
  const card = makeCard(calls);
  assert.equal(card._installed.textContent, '2026.9.1');
  assert.equal(card._available.textContent, '2026.10.0');
  assert.equal(card._button.disabled, false);
  assert.equal(card._button.textContent, 'Install 2026.10.0');
  await card._button.onclick();
  assert.deepEqual(normalize(calls), [{ domain: 'script', service: 'core_update_approve',
    data: { target_version: '2026.10.0', candidate_id: candidate } }]);
  assert.match(card._result.textContent, /Check the updater status/);
  assert.doesNotMatch(card._result.textContent, /successfully updated/);
  passed++;

  const staleCalls = [];
  const stale = makeCard(staleCalls);
  let prompt;
  context.window.confirm = (message) => {
    prompt = message;
    stale.hass = makeHass(staleCalls, {
      candidate_id: replacement, latest_version: '2026.10.1', target_version: '2026.10.1',
    });
    return true;
  };
  await stale._button.onclick();
  assert.match(prompt, /2026\.10\.0/);
  assert.deepEqual(normalize(staleCalls[0].data), { target_version: '2026.10.0', candidate_id: candidate });
  assert.equal(stale._available.textContent, '2026.10.1');
  passed++;

  const oldHandlerCalls = [];
  const oldHandlerCard = makeCard(oldHandlerCalls);
  const renderedHandler = oldHandlerCard._button.onclick;
  oldHandlerCard.hass = makeHass(oldHandlerCalls, { candidate_id: replacement });
  await renderedHandler();
  assert.equal(oldHandlerCalls[0].data.candidate_id, candidate);
  passed++;

  const cancelCalls = [];
  const cancelCard = makeCard(cancelCalls);
  context.window.confirm = () => false;
  await cancelCard._button.onclick();
  assert.equal(cancelCalls.length, 0);
  assert.equal(cancelCard._busy, false);
  assert.equal(cancelCard._button.disabled, false);
  passed++;

  const duplicateCalls = [];
  let finish;
  const duplicateCard = makeCard(duplicateCalls, {}, 'on', async (...args) => {
    duplicateCalls.push(args);
    await new Promise((resolve) => { finish = resolve; });
  });
  let confirmations = 0;
  context.window.confirm = () => { confirmations++; return true; };
  const first = duplicateCard._button.onclick();
  assert.equal(duplicateCard._button.disabled, true);
  await duplicateCard._button.onclick();
  assert.equal(duplicateCalls.length, 1);
  assert.equal(confirmations, 1);
  finish();
  await first;
  assert.equal(duplicateCard._busy, false);
  passed++;

  for (const [state, attrs] of [
    ['unavailable', {}], ['unknown', {}], ['off', {}],
    ['on', { stage: 'backup' }], ['on', { stage: 'recovery_required' }],
    ['on', { in_progress: true }], ['on', { in_progress: 10 }],
    ['on', { candidate_id: 'not-a-candidate' }], ['on', { candidate_id: 'A'.repeat(32) }],
    ['on', { latest_version: '2026.10.1' }],
    ['on', { target_version: '2026.10.0\n', latest_version: '2026.10.0\n' }],
    ['on', { target_version: '<script>', latest_version: '<script>' }],
  ]) {
    const blockedCalls = [];
    const blocked = makeCard(blockedCalls, attrs, state);
    assert.equal(blocked._button.disabled, true, JSON.stringify([state, attrs]));
    await blocked._button.onclick();
    assert.equal(blockedCalls.length, 0);
  }
  passed++;

  const markup = '<img src=x onerror="throw new Error(1)">';
  const textCard = makeCard([], { last_error: markup, stage: 'failed' });
  textCard.setConfig({ title: markup });
  assert.equal(textCard._error.textContent, markup);
  assert.equal(textCard._title.textContent, markup);
  assert.equal(textCard._error.children.length, 0);
  passed++;

  const failedCard = makeCard([], {}, 'on', async () => { throw new Error('private transport detail'); });
  await failedCard._button.onclick();
  assert.match(failedCard._result.textContent, /may already have accepted/);
  assert.doesNotMatch(failedCard._result.textContent, /private transport detail/);
  assert.equal(failedCard._button.disabled, false);
  passed++;

  const release = makeCard([], { target_version: 'javascript:alert(1)', latest_version: 'javascript:alert(1)' });
  assert.equal(release._release.hidden, true);
  assert.equal(release._release.href, undefined);
  passed++;

  console.log(JSON.stringify({ result: 'passed', scenarios: passed }));
})().catch((error) => { console.error(error); process.exitCode = 1; });
