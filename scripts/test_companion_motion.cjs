/* Test the pure preview sequencer without hardware or a browser. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {Motion, Visitor, frameAt} = require('../ui/companion-motion.js');
const library = JSON.parse(fs.readFileSync('ui/assets/characters/index.json'));
for (const entry of library.characters) {
  const manifest = JSON.parse(fs.readFileSync('ui/' + entry.manifest));
  assert.equal(manifest.frames.length, 12);
  for (const clip of Object.values(manifest.animation)) {
    assert.equal(clip.frames.length, clip.durations_ms.length);
    assert(clip.frames.every(frame => Number.isInteger(frame) && frame >= 0 && frame < 12));
    assert(clip.durations_ms.every(ms => Number.isInteger(ms) && ms > 0));
  }
  assert.equal(frameAt(manifest.animation.zoom, 0), 2);
  assert.equal(frameAt(manifest.animation.zoom, 85), 3);
  assert.equal(frameAt(manifest.animation.zoom, 170), 2);
  const a = new Motion(manifest, 75, 0), b = new Motion(manifest, 75, 0);
  const activityNames = new Set(manifest.random_idle.clips);
  const observed = new Set();
  let previous = null, previousEnd = null, current = null;
  for (let now = 0; now < 600000; now += 20) {
    const state = a.tick(now);
    assert.deepEqual(state, b.tick(now));
    assert(state.frame >= 0 && state.frame < 12);
    if (activityNames.has(state.activity) && current === null) {
      assert.notEqual(state.activity, previous);
      if (previousEnd !== null) assert(now - previousEnd >= 12000);
      observed.add(state.activity); current = state.activity;
    } else if (!activityNames.has(state.activity) && current !== null) {
      previous = current; current = null; previousEnd = now;
    }
  }
  assert.equal(observed.size, 3);
  const interrupted = new Motion(manifest, 9, 0);
  const first = interrupted.tick(interrupted.due);
  assert(activityNames.has(first.activity));
  interrupted.tap(interrupted.due + 1);
  const typing = interrupted.tick(interrupted.lastKey);
  assert.equal(typing.activity, 'typing');
  assert([2, 3].includes(typing.frame));
  assert.equal(interrupted.activity, null);
  const fast = new Motion(manifest, 9, 0);
  for (let i = 0; i < 35; i++) fast.tap(i * 80);
  assert.equal(fast.tick(2720).activity, 'zoom');
  assert.equal(fast.tick(2720).wpm, 105);
  assert.equal(fast.tick(4120).activity, 'streak');
  assert.notEqual(fast.tick(6000).activity, 'streak');
  assert.equal(fast.tick(10000).wpm, 0);
  for (let i = 0; i < 1000; i++) fast.tap(11000 + i);
  assert.equal(fast.tick(12000).wpm, 999);
  assert(fast.events.length <= 334);
  const quiet = new Motion(manifest, 2, 0);
  for (let now = 0; now < 600000; now += 1000) {
    const state = quiet.tick(now, true);
    assert.equal(state.frame, 0); assert.equal(state.activity, 'quiet');
  }
  assert(!activityNames.has(quiet.tick(600000).activity));
  assert.notEqual(new Motion(manifest, 11, 0).due, new Motion(manifest, 912, 0).due);
}
console.log('Four companions passed: paired scenes, random variety, cooldown, no repeats, immediate typing interruption, streaks, quiet mode and bounded state.');

const visitor = new Visitor(75, 0);
const arrival = visitor.due;
assert.equal(visitor.tick(arrival - 1, false).visible, false);
const seen = new Set();
for (let elapsed = 0; elapsed < 8000; elapsed += 20) {
  const frame = visitor.tick(arrival + elapsed, false);
  assert(frame.visible && frame.frame >= 0 && frame.frame < 16);
  assert(frame.x >= 79 && frame.x <= 128);
  assert.equal(frame.flip, elapsed >= 6000);
  seen.add(frame.frame);
  assert.equal(visitor.tick(arrival + elapsed, true).visible, false);
}
assert.equal(seen.size, 16);
assert.equal(visitor.tick(arrival + 8000, false).visible, false);
assert(visitor.due >= arrival + 33000);
console.log('Sixteen visitor frames, entry/exit, cooldown and reduced motion passed.');
