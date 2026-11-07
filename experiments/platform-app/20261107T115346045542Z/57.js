// The audio-thread side of a call's noise suppression (app/denoise.js). It cuts the microphone into
// numbered hops of 10 ms for the worker (denoise.worker.js) and plays the cleaned hops the worker
// returns, in order. A muted microphone's hops are silence: they are not sent, and play as silence.
// Until the worker's model is ready, the microphone passes as it is. A worker that falls behind
// on this machine leaves the microphone passing as it is for good, and the page is told.
const HOP = 480;
const LEAD = 2; // cleaned hops waiting before playing starts or resumes, against the worker's jitter
const MOST = LEAD + 3; // cleaned hops waiting beyond this are dropped, to keep the delay bounded
const BEHIND = 10; // hops the worker may owe before it counts as too slow

class Denoise extends AudioWorkletProcessor {
  constructor() {
    super();
    this.model = null; // the worker's port, once its model is ready
    this.hop = new Float32Array(HOP);
    this.filled = 0;
    this.sent = 0; // hops numbered so far
    this.owed = 0; // hops sent to the worker and not back
    this.cleaned = new Map(); // hop number -> cleaned samples, or null for silence
    this.next = 0; // the hop playing
    this.played = 0; // its samples played
    this.playing = false;
    this.port.onmessage = ({ data: port }) => {
      port.onmessage = ({ data }) => {
        if (data.ready) { this.model = port; return; }
        this.owed--;
        // A hop that comes back after its turn was passed over (MOST) is dropped.
        if (data.index >= this.next) this.cleaned.set(data.index, data.samples);
      };
    };
  }

  process([[input]], [[output]]) {
    if (!input) return true;
    if (!this.model) { output.set(input); return true; }
    for (let at = 0; at < input.length;) {
      const take = Math.min(input.length - at, HOP - this.filled);
      this.hop.set(input.subarray(at, at + take), this.filled);
      this.filled += take;
      at += take;
      if (this.filled === HOP) this.send();
    }
    if (this.owed > BEHIND) {
      this.model = null;
      this.port.postMessage('slow');
      output.set(input);
      return true;
    }
    while (this.cleaned.has(this.next + MOST)) { this.cleaned.delete(this.next++); this.played = 0; }
    for (let at = 0; at < output.length;) {
      if (!this.playing && !this.cleaned.has(this.next + LEAD - 1)) { output.fill(0, at); break; }
      const samples = this.cleaned.get(this.next);
      if (samples === undefined) { this.playing = false; output.fill(0, at); break; }
      this.playing = true;
      const take = Math.min(output.length - at, HOP - this.played);
      if (samples) output.set(samples.subarray(this.played, this.played + take), at);
      else output.fill(0, at, at + take);
      at += take;
      this.played += take;
      if (this.played === HOP) { this.cleaned.delete(this.next++); this.played = 0; }
    }
    return true;
  }

  send() {
    const index = this.sent++;
    this.filled = 0;
    if (this.hop.every((sample) => sample === 0)) { this.cleaned.set(index, null); return; }
    const samples = this.hop.slice();
    this.owed++;
    this.model.postMessage({ index, samples }, [samples.buffer]);
  }
}

registerProcessor('denoise', Denoise);
