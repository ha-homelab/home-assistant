"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { FEATURES: F, normalizeConfig, planDispatch, executePlan } = require("../config/www/radio-console-card.js");

function fixture() {
  const players = ["phone", "lifesize", "echo", "offline", "unsupported"].map((id) => ({ entity: `media_player.${id}`, name: id }));
  const config = normalizeConfig({ players, stations: [{ id: "radio", name: "Example radio", url: "https://audio.example.org/radio.mp3",
    sources: { "media_player.phone": "701 — Example", "media_player.lifesize": "Example · 701" } }],
    limits: [{ name: "PBX", entities: ["media_player.phone", "media_player.lifesize"], max: 2 }] });
  const state = (features, sources) => ({ state: "idle", attributes: { supported_features: features, source_list: sources } });
  const states = { "media_player.phone": state(F.SELECT_SOURCE | F.PLAY_MEDIA | F.STOP | F.VOLUME_SET, ["701 — Example"]),
    "media_player.lifesize": state(F.SELECT_SOURCE | F.STOP, ["Example · 701"]),
    "media_player.echo": state(F.PLAY_MEDIA | F.STOP | F.VOLUME_SET),
    "media_player.offline": { state: "unavailable", attributes: { supported_features: F.PLAY_MEDIA } },
    "media_player.unsupported": state(0) };
  return { config, states };
}

test("routes each station through its own exact source or HTTP URL", () => {
  const { config, states } = fixture();
  const plan = planDispatch(config, states, ["media_player.phone", "media_player.lifesize", "media_player.echo"], { action: "play", stationId: "radio" });
  assert.deepEqual(plan.errors, []);
  assert.equal(plan.calls[0].service, "select_source"); assert.equal(plan.calls[0].data.source, "701 — Example");
  assert.equal(plan.calls[1].data.source, "Example · 701");
  assert.equal(plan.calls[2].service, "play_media"); assert.equal(plan.calls[2].data.media_content_type, "music");
  assert.equal(plan.calls[2].data.extra.metadata.title, "Example radio");
  assert.deepEqual(plan.calls.map((c) => c.data.entity_id), ["media_player.phone", "media_player.lifesize", "media_player.echo"]);
});

test("custom URL skips station-only LifeSize, offline and unsupported targets", () => {
  const { config, states } = fixture();
  const plan = planDispatch(config, states, config.players.map((p) => p.entity), { action: "play", customUrl: "https://audio.example.org/custom.mp3" });
  assert.deepEqual(plan.calls.map((c) => c.entity), ["media_player.phone", "media_player.echo"]);
  assert.equal(plan.excluded.length, 3); assert.equal(plan.calls[0].data.source, undefined);
});

test("oversized phone group sends nothing, including otherwise valid Echo targets", async () => {
  const { config, states } = fixture(); config.limits[0].max = 1;
  const plan = planDispatch(config, states, ["media_player.phone", "media_player.lifesize", "media_player.echo"], { action: "play", stationId: "radio" });
  assert.equal(plan.calls.length, 0); assert.match(plan.errors[0], /at most 1/);
  let calls = 0; await executePlan({ callService: () => { calls++; } }, plan); assert.equal(calls, 0);
  const stop = planDispatch(config, states, ["media_player.phone", "media_player.lifesize"], { action: "stop" });
  assert.equal(stop.calls.length, 2, "Capacity limits must not prevent stopping playback");
});

test("requires explicit selection and rejects unconfigured recipients and credentials", () => {
  const { config, states } = fixture();
  for (const selected of [[], ["media_player.not_configured"]]) {
    assert.equal(planDispatch(config, states, selected, { action: "play", stationId: "radio" }).calls.length, 0);
  }
  for (const url of ["javascript:alert(1)", "https://user:secret@audio.example.org/music", "not a URL"]) {
    const plan = planDispatch(config, states, ["media_player.echo"], { action: "play", customUrl: url });
    assert.equal(plan.calls.length, 0); assert.ok(plan.errors.length);
  }
});

test("source mismatch does not accidentally fall back to another station or URL", () => {
  const { config, states } = fixture(); states["media_player.phone"].attributes.source_list = ["702 — Different"];
  const plan = planDispatch(config, states, ["media_player.phone"], { action: "play", stationId: "radio" });
  assert.equal(plan.calls.length, 0); assert.match(plan.excluded[0].reason, /not currently available/);
});

test("volume is its own explicit action and never part of Play", () => {
  const { config, states } = fixture();
  const play = planDispatch(config, states, ["media_player.echo"], { action: "play", stationId: "radio", volume: 0.8 });
  assert.equal(play.calls.length, 1); assert.equal(play.calls[0].data.volume_level, undefined);
  const volume = planDispatch(config, states, ["media_player.echo", "media_player.lifesize"], { action: "volume", volume: 0.2 });
  assert.equal(volume.calls.length, 1); assert.equal(volume.calls[0].data.volume_level, 0.2);
  assert.equal(planDispatch(config, states, ["media_player.echo"], { action: "volume", volume: 1.1 }).calls.length, 0);
});

test("execution sends only planned recipient actions, reports individual failures and never retries", async () => {
  const { config, states } = fixture();
  const plan = planDispatch(config, states, ["media_player.phone", "media_player.echo"], { action: "play", stationId: "radio" });
  const calls = [], reports = [];
  const result = await executePlan({ callService: async (...args) => {
    calls.push(args); if (args[2].entity_id === "media_player.phone") throw new Error("private https://secret.invalid/?token=secret");
  } }, plan, (r) => reports.push(r));
  assert.equal(calls.length, 2); assert.deepEqual(result.map((r) => r.ok), [false, true]);
  assert.equal(reports.length, 2); assert.ok(!JSON.stringify(result).includes("secret"));
  assert.equal(calls[1][2].entity_id, "media_player.echo");
});

test("executor refuses unsupported service and cross-target plan data", async () => {
  let sent = 0;
  const plan = { errors: [], calls: [
    { entity: "media_player.phone", name: "Phone", domain: "homeassistant", service: "restart", data: { entity_id: "media_player.phone" } },
    { entity: "media_player.phone", name: "Phone", domain: "media_player", service: "media_stop", data: { entity_id: "media_player.echo" } },
  ] };
  const results = await executePlan({ callService: () => { sent++; } }, plan);
  assert.equal(sent, 0); assert.ok(results.every((r) => !r.ok));
});
