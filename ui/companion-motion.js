/* Pure animation sequencing for the asset gallery. Not installed firmware. */
(function (root) {
  'use strict';
  function frameAt(animation, elapsed) {
    const duration = animation.durations_ms.reduce((sum, ms) => sum + ms, 0);
    let phase = Math.max(0, elapsed) % duration;
    for (let i = 0; i < animation.frames.length; i++) {
      if (phase < animation.durations_ms[i]) return animation.frames[i];
      phase -= animation.durations_ms[i];
    }
    return animation.frames[0];
  }
  class Motion {
    constructor(manifest, seed, now) {
      this.manifest = manifest;
      this.seed = seed >>> 0 || 1;
      this.events = [];
      this.lastKey = now;
      this.previous = -1;
      this.activity = null;
      this.streakPending = false;
      this.lastCelebration = -Infinity;
      this.due = now + this.delay(manifest.random_idle.first_delay_ms);
    }
    random() {
      let x = this.seed;
      x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
      return this.seed = x >>> 0;
    }
    delay(bounds) { return bounds[0] + this.random() % (bounds[1] - bounds[0] + 1); }
    wpm(now) {
      this.events = this.events.filter(time => now - time < 4000);
      return Math.min(999, this.events.length * 3);
    }
    tap(now) {
      const previous = this.wpm(now);
      this.events.push(now);
      if (this.events.length > 334) this.events.shift();
      const current = this.wpm(now);
      if (((previous < 60 && current >= 60) || (previous < 100 && current >= 100)) &&
          now - this.lastCelebration >= 12000) this.streakPending = true;
      this.lastKey = now;
      this.activity = null;
      this.due = now + this.delay(this.manifest.random_idle.after_typing_delay_ms);
    }
    tick(now, quiet = false) {
      const wpm = this.wpm(now);
      if (quiet) {
        this.activity = null; this.streakPending = false; this.due = now + 12000;
        return {frame: 0, activity: 'quiet', wpm};
      }
      if (this.events.length && now - this.lastKey < 1400) {
        const mode = wpm >= 100 ? 'zoom' : wpm >= 60 ? 'flow' : 'typing';
        return {frame: frameAt(this.manifest.animation[mode], now), activity: mode, wpm};
      }
      if (this.streakPending) {
        this.activity = {name: 'streak', started: now};
        this.streakPending = false; this.lastCelebration = now;
      }
      if (!this.activity && now >= this.due) {
        const names = this.manifest.random_idle.clips;
        let choice = this.random() % names.length;
        if (choice === this.previous) choice = (choice + 1 + this.random() % (names.length - 1)) % names.length;
        this.previous = choice;
        this.activity = {name: names[choice], started: now};
      }
      if (this.activity) {
        const {name, started} = this.activity;
        const clip = this.manifest.animation[name];
        if (now - started < clip.durations_ms.reduce((a, b) => a + b, 0))
          return {frame: frameAt(clip, now - started), activity: name, wpm};
        this.activity = null;
        this.due = now + this.delay(this.manifest.random_idle.cooldown_ms);
      }
      const sleepy = now - this.lastKey >= 8000;
      return {frame: sleepy ? 5 : now % 4000 >= 3840 ? 1 : 0, activity: sleepy ? 'sleep' : 'idle', wpm};
    }
  }
  const api = {Motion, frameAt};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.CompanionMotion = api;
})(typeof window !== 'undefined' ? window : globalThis);
