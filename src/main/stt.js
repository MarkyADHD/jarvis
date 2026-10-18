// Speech-to-text: local Whisper (transformers.js + onnxruntime-node), no Python, no API.
// Model downloads once to %LOCALAPPDATA%/jarvis-v3/models, then stays warm in memory.
const path = require('path');
const os = require('os');

const MODEL = process.env.JARVIS_STT_MODEL || 'Xenova/whisper-small.en';   // small handles accents (British) far better than base; ~1-2s warm on CPU
let asrP = null;

function load() {
  asrP ??= (async () => {
    const { pipeline, env } = await import('@huggingface/transformers');
    env.cacheDir = path.join(process.env.LOCALAPPDATA || os.homedir(), 'jarvis-v3', 'models');
    // Gaming: cap Whisper to a quarter of the logical cores (ORT defaults to every physical core), so a hands-free
    // phrase mid-match doesn't spike the whole CPU. ponytail: fixed ratio; make it a setting if he wants faster/slower.
    return pipeline('automatic-speech-recognition', MODEL, { dtype: 'q8', session_options: { intraOpNumThreads: Math.max(2, Math.floor(os.cpus().length / 4)) } });
  })().catch(e => { asrP = null; throw e; });
  return asrP;
}

// pcm: Float32Array, mono, 16 kHz.
async function transcribe(pcm) {
  if (!(pcm instanceof Float32Array) || pcm.length < 16000 * 0.3) return '';
  const asr = await load();
  const { text } = await asr(pcm);
  return cleanTranscript(text);
}

// Whisper hallucinates these on silence/noise.
const JUNK = /^(\[.*\]|\(.*\)|you\.?|thank you\.?|thanks for watching!?|\.+)$/i;
function cleanTranscript(t) {
  const s = String(t || '').replace(/\s+/g, ' ').trim();
  return JUNK.test(s) ? '' : s;
}

module.exports = { load, transcribe, cleanTranscript };
