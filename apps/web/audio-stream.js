/* Shared incremental playback for HTTP and WebSocket TTS. */
(function (root) {
  class PcmPlayer {
    constructor(context, onFirstAudio = () => {}) {
      this.context = context;
      this.onFirstAudio = onFirstAudio;
      this.nextTime = 0;
      this.sources = new Set();
      this.waiters = [];
      this.stopped = false;
      this.started = false;
    }

    enqueue(data, sampleRate, channels = 1) {
      if (this.stopped) return;
      const binary = atob(data);
      if (!binary.length || binary.length % (2 * channels)) throw new Error("Invalid PCM chunk");
      const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
      const pcm = new DataView(bytes.buffer);
      const frames = bytes.length / (2 * channels);
      const buffer = this.context.createBuffer(channels, frames, sampleRate);
      for (let channel = 0; channel < channels; channel += 1) {
        const output = buffer.getChannelData(channel);
        for (let frame = 0; frame < frames; frame += 1) {
          output[frame] = pcm.getInt16((frame * channels + channel) * 2, true) / 32768;
        }
      }
      const source = this.context.createBufferSource();
      source.buffer = buffer;
      source.connect(this.context.destination);
      source.onended = () => {
        source.disconnect();
        this.sources.delete(source);
        if (!this.sources.size) this.resolveWaiters();
      };
      this.sources.add(source);
      const startAt = Math.max(this.nextTime, this.context.currentTime + 0.04);
      source.start(startAt);
      this.nextTime = startAt + buffer.duration;
      if (!this.started) {
        this.started = true;
        this.onFirstAudio();
      }
    }

    finish() {
      // A network "done" event only means production finished. Wait for the
      // browser's last source.onended before closing its AudioContext.
      if (!this.sources.size || this.stopped) return Promise.resolve();
      return new Promise((resolve) => this.waiters.push(resolve));
    }

    resolveWaiters() {
      this.waiters.splice(0).forEach((resolve) => resolve());
    }

    stop() {
      if (this.stopped) return;
      this.stopped = true;
      for (const source of this.sources) {
        source.onended = null;
        source.stop();
        source.disconnect();
      }
      this.sources.clear();
      this.resolveWaiters();
      void this.context.close().catch(() => {});
    }
  }

  async function readEvents(response, onEvent) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        pending += done ? decoder.decode() : decoder.decode(value, { stream: true });
        let end;
        while ((end = pending.indexOf("\n")) >= 0) {
          const line = pending.slice(0, end).trim();
          pending = pending.slice(end + 1);
          if (line) onEvent(JSON.parse(line));
        }
        if (pending.length > 4 * 1024 * 1024) throw new Error("TTS event exceeds 4MB");
        if (done) break;
      }
      if (pending.trim()) onEvent(JSON.parse(pending));
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }

  const api = { PcmPlayer, readEvents };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.OpenInterviewAudioStream = api;
})(globalThis);
