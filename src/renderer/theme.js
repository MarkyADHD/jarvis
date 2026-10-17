// HUD colour themes, picked in Settings and remembered per PC (localStorage, which the voice overlay shares).
// Only colours and the --theme CSS class change; layout and behaviour are the same in every theme.
const THEMES = {
  default: { cyan: '#35d6ff', cyan2: '#7fe7ff', blue: '#2a9fe0', amber: '#ffa928', gold: '#ffd23f', white: '#eafcff', hi: '#46beff', glow: '#8fe3ff',
    deep: '#125f8c', pale: '#d2f8ff', bg: '#010509', core0: '#0c2a3b', core1: '#04121c', core2: '#01070c' },
  vice: { cyan: '#ff3ea5', cyan2: '#ff9ad5', blue: '#25e2e6', amber: '#ff8a3d', gold: '#ffcf5c', white: '#fff0f9', hi: '#5ff5f0', glow: '#ffb0dd',
    deep: '#78145a', pale: '#ffdcf2', bg: '#0e0219', core0: '#3a0d40', core1: '#1a0524', core2: '#0b0212' },
};
function applyTheme(C, name) {
  if (name === undefined) try { name = localStorage.getItem('jarvis.theme'); } catch {}
  if (!THEMES[name]) name = 'default';
  Object.assign(C, THEMES[name]);
  document.documentElement.classList.toggle('vice', name === 'vice');
  return name;
}
