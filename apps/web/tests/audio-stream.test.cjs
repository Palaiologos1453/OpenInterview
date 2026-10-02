const { test } = require("node:test");
const assert = require("node:assert/strict");
const { PcmPlayer, readEvents } = require("../audio-stream.js");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function audioContext() {
  return {
    currentTime: 0, destination: {}, closed: false, sources: [],
    createBuffer(channels, frames, rate) {
      const data = Array.from({ length: channels }, () => new Float32Array(frames));
      return { duration: frames / rate, getChannelData: (channel) => data[channel] };
    },
    createBufferSource() {
      const source = { connect() {}, disconnect() {}, stop() { this.stopped = true; },
        start(time) { this.startTime = time; } };
      this.sources.push(source);
      return source;
    },
    close() { this.closed = true; return Promise.resolve(); }
  };
}

test("PCM starts before finish, keeps the tail, and schedules chunks in order", async () => {
  const context = audioContext();
  const player = new PcmPlayer(context);
  const pcm = Buffer.from([0x00, 0x80, 0xff, 0x7f]).toString("base64");
  player.enqueue(pcm, 24000);
  player.enqueue(pcm, 24000);
  assert.equal(context.sources.length, 2);
  assert.equal(context.sources[0].buffer.getChannelData(0)[0], -1);
  assert.ok(context.sources[1].startTime >= context.sources[0].startTime + 2 / 24000);
  let finished = false;
  const completion = player.finish().then(() => { finished = true; });
  await Promise.resolve();
  assert.equal(finished, false);
  assert.equal(context.closed, false);
  context.sources[0].onended();
  await Promise.resolve();
  assert.equal(finished, false);
  context.sources[1].onended();
  await completion;
  player.stop();
  assert.equal(context.closed, true);
});

test("cancellation stops scheduled audio and resolves playback waiters", async () => {
  const context = audioContext();
  const player = new PcmPlayer(context);
  player.enqueue("AAA=", 24000);
  const completion = player.finish();
  player.stop();
  await completion;
  assert.equal(context.sources[0].stopped, true);
  player.enqueue("AAA=", 24000);
  assert.equal(context.sources.length, 1);
});

test("HTTP events arrive before EOF, including split JSON and UTF-8 characters", async () => {
  const encoder = new TextEncoder();
  const bytes = encoder.encode('{"type":"chunk","text":"你好"}\n');
  let controller;
  let firstDelivered;
  const first = new Promise((resolve) => { firstDelivered = resolve; });
  const stream = new ReadableStream({ start(value) { controller = value; } });
  const events = [];
  const reading = readEvents(new Response(stream), (event) => {
    events.push(event);
    firstDelivered();
  });
  const split = bytes.indexOf(0xe4) + 1;
  controller.enqueue(bytes.slice(0, split));
  controller.enqueue(bytes.slice(split));
  await first;
  assert.equal(events[0].text, "你好");
  controller.enqueue(encoder.encode('{"type":"done"}'));
  controller.close();
  await reading;
  assert.equal(events[1].type, "done");
});

test("a stream error cancels the reader instead of leaking the request", async () => {
  let cancelled = false;
  const response = new Response(new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('{"type":"error"}\n')); },
    cancel() { cancelled = true; }
  }));
  await assert.rejects(readEvents(response, () => { throw new Error("provider failed"); }), /provider failed/);
  assert.equal(cancelled, true);
});

test("the app waits for actual playback after the WebSocket done event", async () => {
  const context = audioContext();
  const player = new PcmPlayer(context);
  player.enqueue("AAA=", 24000);
  const sandbox = vm.createContext({
    URLSearchParams, URL, console, performance, setTimeout, clearTimeout,
    window: { location: { search: "" } },
    localStorage: { getItem: () => null },
    document: { querySelector: () => ({}), querySelectorAll: () => [] },
    player, cleanups: 0,
  });
  const source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8").replace("init();", "");
  vm.runInContext(source, sandbox);
  vm.runInContext(`
    state.pcmPlayer = player;
    state.realtimeSocket = {};
    resetRealtimeUi = () => { cleanups += 1; player.stop(); };
    updateVoiceTiming = () => {};
    updateTranscriptStatus = () => {};
    setStatus = () => {};
    handleDuplexMessage({ type: "done", skipped: false });
  `, sandbox);
  await Promise.resolve();
  assert.equal(sandbox.cleanups, 0);
  assert.equal(context.closed, false);
  context.sources[0].onended();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(sandbox.cleanups, 1);
  assert.equal(context.closed, true);
});
