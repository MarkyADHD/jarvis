const test = require('node:test');
const assert = require('node:assert');
const { cleanTranscript } = require('../src/main/stt');

test('Parakeet sound-alikes of the wake word become "Jarvis"; ordinary words are left alone', () => {
  assert.strictEqual(cleanTranscript('Charvis, play some music.'), 'Jarvis, play some music.');
  assert.strictEqual(cleanTranscript('Okay Joffice, clip that.'), 'Okay Jarvis, clip that.');
  assert.strictEqual(cleanTranscript('You Jarvis, turn the lights off.'), 'Yo Jarvis, turn the lights off.');
  assert.strictEqual(cleanTranscript('Chavez'), 'Jarvis');
  assert.strictEqual(cleanTranscript('Hey Jarvis, what time is it?'), 'Hey Jarvis, what time is it?');
  assert.strictEqual(cleanTranscript('Gives me a minute.'), 'Gives me a minute.');
  assert.strictEqual(cleanTranscript('Office, hi.'), 'Office, hi.');
  assert.strictEqual(cleanTranscript('Thanks for watching!'), '');
});
