// Speech-to-text: local Whisper (transformers.js + onnxruntime-node), no Python, no API.
// Model downloads once to %LOCALAPPDATA%/jarvis-v3/models, then stays warm in memory.
const path = require('path');
const os = require('os');

const MODEL = process.env.JARVIS_STT_MODEL || 'Xenova/whisper-base.en';   // ~0.6s per utterance warm on a modern CPU
let asrP = null;

function load() {
  asrP ??= (async () => {
    const { pipeline, env } = await import('@huggingface/transformers');
    env.cacheDir = path.join(process.env.LOCALAPPDATA || os.homedir(), 'jarvis-v3', 'models');
    return pipeline('automatic-speech-recognition', MODEL, { dtype: 'q8' });
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
