// Speech-to-text, all local, no Python, no API.
// Live voice: NVIDIA Parakeet TDT 0.6B v2 (ONNX, CC-BY-4.0) on onnxruntime-node -- GPU via DirectML or CPU int8.
// Clip captions: Whisper (transformers.js), because clips.caption needs Whisper's word timestamps.
// Models download once to %LOCALAPPDATA%/jarvis-v3/models, then stay warm in memory.
const path = require('path');
const os = require('os');
const fs = require('fs');

const CACHE = path.join(process.env.LOCALAPPDATA || os.homedir(), 'jarvis-v3', 'models');
const MODEL = process.env.JARVIS_STT_MODEL || 'Xenova/whisper-small.en';   // small handles accents (British) far better than base
const PK = 'istupakov/parakeet-tdt-0.6b-v2-onnx', PK_REV = '0bbb45a3365852604aef28b538a8f066f4ccaa85';
// Gaming: cap CPU inference to a quarter of the logical cores (ORT defaults to every physical core), so a hands-free
// phrase mid-match doesn't spike the whole CPU. ponytail: fixed ratio; make it a setting if he wants faster/slower.
const THREADS = Math.max(2, Math.floor(os.cpus().length / 4));
// CPU by default: on his RTX 4070 the int8 CPU encoder beat DirectML (0.1-0.4 s vs 0.25-0.7 s a phrase); GPU is opt-in.
let asrP = null, voiceP = null, live = null, mode = 'cpu', current = 'loading';

// Whisper pipeline (clip captions + fallback if Parakeet can't load).
function load() {
  asrP ??= (async () => {
    const { pipeline, env } = await import('@huggingface/transformers');
    env.cacheDir = CACHE;
    return pipeline('automatic-speech-recognition', MODEL, { dtype: 'q8', session_options: { intraOpNumThreads: THREADS } });
  })().catch(e => { asrP = null; throw e; });
  return asrP;
}

async function download(files) {
  const dir = path.join(CACHE, PK);
  fs.mkdirSync(dir, { recursive: true });
  for (const f of files) {
    const out = path.join(dir, f);
    if (fs.existsSync(out)) continue;
    const r = await fetch(`https://huggingface.co/${PK}/resolve/${PK_REV}/${f}`);
    if (!r.ok) throw new Error(`download ${f}: HTTP ${r.status}`);
    await require('stream/promises').pipeline(require('stream').Readable.fromWeb(r.body), fs.createWriteStream(out + '.part'));
    fs.renameSync(out + '.part', out);
  }
  return dir;
}

// Parakeet TDT: preprocessor -> encoder (GPU or CPU) -> greedy token-and-duration decode (always CPU: tiny per-step calls).
async function parakeet(gpu) {
  const ort = require('onnxruntime-node');
  const T = (type, data, dims) => new ort.Tensor(type, data, dims);
  const small = ['nemo128.onnx', 'vocab.txt', 'decoder_joint-model.int8.onnx'];
  let dir = await download(small);
  const pre = await ort.InferenceSession.create(path.join(dir, 'nemo128.onnx'));
  // DirectML works on any DX12 GPU without CUDA installs. Probe it on the tiny model before fetching 2.4 GB of weights.
  // ponytail: any DX12 adapter passes, integrated GPUs included; check adapter VRAM if a weak iGPU ever picks this.
  if (gpu) await (await ort.InferenceSession.create(path.join(dir, 'nemo128.onnx'), { executionProviders: ['dml'] })).release();
  const encFiles = gpu ? ['encoder-model.onnx', 'encoder-model.onnx.data'] : ['encoder-model.int8.onnx'];
  dir = await download(encFiles);
  const enc = await ort.InferenceSession.create(path.join(dir, encFiles[0]), gpu ? { executionProviders: ['dml'] } : { intraOpNumThreads: THREADS });
  const dec = await ort.InferenceSession.create(path.join(dir, 'decoder_joint-model.int8.onnx'), { intraOpNumThreads: 1 });
  const vocab = fs.readFileSync(path.join(dir, 'vocab.txt'), 'utf8').trim().split('\n').map(l => l.slice(0, l.lastIndexOf(' ')));
  const blank = vocab.length - 1;

  async function run(pcm) {
    const { features, features_lens } = await pre.run({ waveforms: T('float32', pcm, [1, pcm.length]), waveforms_lens: T('int64', BigInt64Array.of(BigInt(pcm.length)), [1]) });
    const { outputs, encoded_lengths } = await enc.run({ audio_signal: features, length: features_lens });
    const [, D, N] = outputs.dims, e = outputs.data, len = Number(encoded_lengths.data[0]), frame = new Float32Array(D);
    let s1 = T('float32', new Float32Array(1280), [2, 1, 640]), s2 = T('float32', new Float32Array(1280), [2, 1, 640]);
    const toks = [];
    for (let t = 0, emitted = 0; t < len;) {
      for (let d = 0; d < D; d++) frame[d] = e[d * N + t];
      const r = await dec.run({ encoder_outputs: T('float32', frame, [1, D, 1]), targets: T('int32', Int32Array.of(toks.length ? toks.at(-1) : blank), [1, 1]),
        target_length: T('int32', Int32Array.of(1), [1]), input_states_1: s1, input_states_2: s2 });
      const o = r.outputs.data;   // [token logits..., duration logits (0..4 frames)...]
      let tok = 0, step = 0;
      for (let i = 1; i < vocab.length; i++) if (o[i] > o[tok]) tok = i;
      for (let i = vocab.length + 1; i < o.length; i++) if (o[i] > o[vocab.length + step]) step = i - vocab.length;
      if (tok !== blank) { s1 = r.output_states_1; s2 = r.output_states_2; toks.push(tok); emitted++; }
      if (step > 0) { t += step; emitted = 0; } else if (tok === blank || emitted === 10) { t++; emitted = 0; }
    }
    return toks.map(i => vocab[i]).join('').replace(/▁/g, ' ').trim();
  }
  await run(new Float32Array(16000));   // warm-up: DirectML compiles its kernels on the first run
  return { name: `Parakeet on ${gpu ? 'GPU' : 'CPU'}`, run, release: () => Promise.all([pre, enc, dec].map(s => s.release())) };
}

const whisper = async () => { const asr = await load(); return { name: 'Whisper on CPU', run: async pcm => (await asr(pcm)).text, release: async () => {} }; };
const fallback = (from, e, next) => { console.error(`[jarvis] hearing: ${from} failed (${e.message}), falling back`); return next(); };

// Live-voice engine for the current mode: GPU -> CPU Parakeet -> Whisper, each step only if the one before fails.
function voice(gpu = mode === 'gpu') {
  const p = voiceP ??= (gpu ? parakeet(true).catch(e => fallback('GPU', e, () => parakeet(false))) : parakeet(false))
    .catch(e => fallback('Parakeet', e, whisper))
    .then(v => { if (voiceP === p) { live = v; current = v.name; } return v; },
      e => { if (voiceP === p) { voiceP = null; current = 'unavailable'; } throw e; });
  return voiceP;
}

function swap(gpu) {
  const old = voiceP; voiceP = null; live = null; current = 'loading';
  old?.then(v => v.release()).catch(() => {});
  return voice(gpu);
}

// 'gpu' | 'cpu' from settings. A change swaps the engine in the background, no restart.
function setMode(m) {
  if (!['gpu', 'cpu'].includes(m) || m === mode) return;
  mode = m; swap().catch(() => {});
}

// pcm: Float32Array, mono, 16 kHz.
async function transcribe(pcm) {
  if (!(pcm instanceof Float32Array) || pcm.length < 16000 * 0.3) return '';
  voice().catch(() => {});
  const v = live || await whisper();   // still loading (first run downloads up to 2.4 GB): Whisper covers meanwhile
  try { return cleanTranscript(await v.run(pcm)); }
  catch (e) {
    if (!v.name.includes('GPU')) throw e;
    console.error('[jarvis] hearing: GPU run failed, switching to CPU:', e.message);   // e.g. driver reset mid-game
    return cleanTranscript(await (await swap(false)).run(pcm));
  }
}

// Whisper hallucinates these on silence/noise.
const JUNK = /^(\[.*\]|\(.*\)|you\.?|thank you\.?|thanks for watching!?|\.+)$/i;
// Parakeet doesn't know the name "Jarvis" and spells it by sound ("Charvis", "Chavez", "Joffice", "Javis") -- fix it
// when it's the first word (after an optional greeting) so the hands-free wake word still matches.
// ponytail: sound-alike regex; train a hotword boost into the decoder if he keeps getting misses.
const WAKE_ISH = /^((?:hey|ok|okay|yo|you)[\s,]+)?(?:j|ch|g|dj|sh)\w{0,4}(?:v|f)\w{0,3}[szc]e?(?=[,.!?]|$)/i;
function cleanTranscript(t) {
  const s = String(t || '').replace(/\s+/g, ' ').trim();
  return JUNK.test(s) ? '' : s.replace(WAKE_ISH, (_m, g) => (g ? g.replace(/^you\b/i, 'Yo') : '') + 'Jarvis');
}

module.exports = { load, voice, setMode, engine: () => current, transcribe, cleanTranscript };
