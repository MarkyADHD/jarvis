// Jarvis voice core: canvas recreation of Marky's own Photoshop design
// (segmented blue band, orange accent arc, tick rings, glowing wordmark).
// Motion and glow follow real state via core.energy (0 idle .. 1 speaking).
(function () {
  const TAU = Math.PI * 2, rad = d => d * Math.PI / 180;
  const cv = document.getElementById('core'), c = cv.getContext('2d');
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fit = () => { cv.width = cv.height = Math.round(cv.clientWidth * devicePixelRatio); };
  new ResizeObserver(fit).observe(cv); fit();
  const core = window.core = { target: .1 };
  let e = 0, t = 0, boot = still ? 1 : 0;
  const L = i => Math.max(0, Math.min(1, boot * 7 - i)); // layer i's boot progress

  const arc = (r, a0, a1, w, style, glow = 0) => {
    c.beginPath(); c.arc(0, 0, r, a0, a1); c.lineWidth = w; c.strokeStyle = style;
    c.shadowBlur = glow; c.shadowColor = style; c.stroke(); c.shadowBlur = 0;
  };
  const band = (r0, r1, a0, a1, fill) => {
    c.beginPath(); c.arc(0, 0, r1, a0, a1); c.arc(0, 0, r0, a1, a0, true); c.closePath(); c.fillStyle = fill; c.fill();
  };
  const spin = (a, fn) => { c.save(); c.rotate(a); fn(); c.restore(); };

  function frame() {
    boot = Math.min(1, boot + .01);
    e += (core.target - e) * .05;
    t += still ? 0 : (.004 + e * .014);
    const S = cv.width, R = S * .46;
    c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, S, S); c.translate(S / 2, S / 2);
    const cy = a => `rgba(63,214,255,${a})`;

    // atmosphere
    let g = c.createRadialGradient(0, 0, R * .3, 0, 0, R * 1.08);
    g.addColorStop(0, `rgba(20,90,130,${.35 + e * .2})`); g.addColorStop(.7, 'rgba(10,50,80,.25)'); g.addColorStop(1, 'rgba(0,0,0,0)');
    c.fillStyle = g; c.beginPath(); c.arc(0, 0, R * 1.08, 0, TAU); c.fill();

    // outer frame ring + brackets
    c.globalAlpha = L(0); c.save(); c.rotate((1 - L(0)) * 1.5);
    arc(R * .99, 0, TAU, S / 700, cy(.35));
    spin(t * .25, () => {
      for (let k = 0; k < 4; k++) {
        const a = rad(k * 90 + 20);
        arc(R * .985, a, a + rad(34), S / 110, cy(.85), 12);
        arc(R * .985, a + rad(38), a + rad(41), S / 110, cy(.85), 12);
      }
      arc(R * .955, rad(300), rad(345), S / 300, 'rgba(90,170,255,.9)', 10);
    });

    c.restore();
    // tick ring
    c.globalAlpha = L(1); c.save(); c.rotate((1 - L(1)) * -1.5);
    spin(-t * .12, () => {
      for (let i = 0; i < 120; i++) {
        const a = i / 120 * TAU, big = i % 5 === 0, r0 = R * (big ? .875 : .895), r1 = R * .925;
        c.strokeStyle = cy(big ? .9 : .45); c.lineWidth = S / (big ? 380 : 650);
        c.beginPath(); c.moveTo(Math.cos(a) * r0, Math.sin(a) * r0); c.lineTo(Math.cos(a) * r1, Math.sin(a) * r1); c.stroke();
      }
    });
    arc(R * .86, 0, TAU, S / 900, cy(.3));

    c.restore();
    // big segmented translucent band
    c.globalAlpha = L(2); c.save(); c.rotate((1 - L(2)) * 1.5);
    spin(t * .06, () => {
      const a0 = rad(160), a1 = rad(385), segs = 38, step = (a1 - a0) / segs;
      for (let i = 0; i < segs; i++) {
        const a = a0 + i * step, pulse = .45 + .25 * Math.sin(i * .5 - t * 6) * e;
        const bg = c.createRadialGradient(0, 0, R * .68, 0, 0, R * .83);
        bg.addColorStop(0, `rgba(90,200,255,${pulse + .15})`); bg.addColorStop(1, `rgba(40,120,210,${pulse * .7})`);
        band(R * .69, R * .83, a + step * .06, a + step * .94, bg);
      }
      arc(R * .835, a0, a1, S / 600, cy(.9), 8);
      // yellow indicator dots
      for (let k = 0; k < 5; k++) {
        const a = rad(245 + k * 13);
        c.fillStyle = `rgba(255,214,40,${.6 + .4 * Math.sin(t * 5 + k)})`; c.shadowBlur = 8; c.shadowColor = '#ffd628';
        c.beginPath(); c.arc(Math.cos(a) * R * .76, Math.sin(a) * R * .76, S / 260, 0, TAU); c.fill(); c.shadowBlur = 0;
      }
    });

    c.restore();
    // orange accent arc with end hooks
    c.globalAlpha = L(3); c.save(); c.rotate((1 - L(3)) * -1.5);
    spin(-t * .04, () => {
      const a0 = rad(150), a1 = rad(215), o = '#ff9d1c';
      arc(R * .655, a0, a1, S / 170, o, 14);
      [a0, a1].forEach(a => { c.beginPath(); c.moveTo(Math.cos(a) * R * .655, Math.sin(a) * R * .655); c.lineTo(Math.cos(a) * R * .70, Math.sin(a) * R * .70); c.stroke(); });
      arc(R * .6, rad(118), rad(126), S / 170, o, 10);
    });

    // voice bars around the inner ring when active
    if (e > .15) for (let i = 0; i < 96; i++) {
      const a = i / 96 * TAU, amp = Math.abs(Math.sin(i * .9 + t * 9) * Math.cos(i * .37 - t * 4)) * e;
      const r0 = R * .615, r1 = r0 + R * .07 * amp;
      c.strokeStyle = cy(.3 + amp * .6); c.lineWidth = S / 500;
      c.beginPath(); c.moveTo(Math.cos(a) * r0, Math.sin(a) * r0); c.lineTo(Math.cos(a) * r1, Math.sin(a) * r1); c.stroke();
    }

    c.restore();
    // inner rings
    c.globalAlpha = L(4); c.save(); c.rotate((1 - L(4)) * 1.5);
    arc(R * .6, 0, TAU, S / 130, cy(.9), 18 + e * 20);
    arc(R * .565, 0, TAU, S / 700, cy(.5));

    c.restore();
    // inner disc with faint rotating machinery
    c.globalAlpha = L(5); c.save(); c.rotate((1 - L(5)) * -1.5);
    g = c.createRadialGradient(0, 0, 0, 0, 0, R * .56);
    g.addColorStop(0, '#0b1a24'); g.addColorStop(1, '#050b10');
    c.fillStyle = g; c.beginPath(); c.arc(0, 0, R * .555, 0, TAU); c.fill();
    spin(-t * .3, () => {
      c.strokeStyle = cy(.1); c.lineWidth = S / 900;
      for (let k = 1; k <= 4; k++) { c.beginPath(); c.arc(0, 0, R * .11 * k, 0, TAU); c.stroke(); }
      for (let i = 0; i < 24; i++) {
        const a = i / 24 * TAU;
        c.beginPath(); c.moveTo(Math.cos(a) * R * .12, Math.sin(a) * R * .12); c.lineTo(Math.cos(a) * R * .5, Math.sin(a) * R * .5); c.stroke();
      }
      for (let i = 0; i < 36; i++) { const a = i / 36 * TAU; c.fillStyle = cy(.15); c.fillRect(Math.cos(a) * R * .47 - 2, Math.sin(a) * R * .47 - 2, 4, 4); }
    });

    // radar sweep across the inner disc
    const sw = t * 1.6 % TAU, sg = c.createConicGradient ? c.createConicGradient(sw - .9, 0, 0) : null;
    if (sg) {
      sg.addColorStop(0, 'rgba(63,214,255,0)'); sg.addColorStop(.14, `rgba(63,214,255,${.12 + e * .12})`); sg.addColorStop(.145, 'rgba(63,214,255,0)');
      c.fillStyle = sg; c.beginPath(); c.arc(0, 0, R * .55, 0, TAU); c.fill();
    }
    // curved micro text riding the outer ring
    spin(-t * .08, () => {
      const msg = ' JUST A RATHER VERY INTELLIGENT SYSTEM  //  CORE ' + (e > .3 ? 'ACTIVE' : 'STANDBY') + '  //  MARKYADHD  //', r = R * .945;
      c.font = `500 ${Math.round(R * .028)}px "Bahnschrift","Segoe UI",sans-serif`; c.fillStyle = cy(.55); c.textAlign = 'center';
      let a = rad(100);
      for (const ch of msg) { c.save(); c.rotate(a); c.translate(0, -r); c.fillText(ch, 0, 0); c.restore(); a += (c.measureText(ch).width + R * .004) / r; }
    });
    c.restore();
    // wordmark
    c.globalAlpha = L(6); c.save(); c.rotate((1 - L(6)) * 1.5);
    c.font = `600 ${Math.round(R * .15)}px "Bahnschrift","Segoe UI",sans-serif`;
    c.textAlign = 'center'; c.textBaseline = 'middle';
    g = c.createLinearGradient(0, -R * .08, 0, R * .08);
    g.addColorStop(0, '#ffffff'); g.addColorStop(.55, '#dff4ff'); g.addColorStop(1, '#8fb9cc');
    c.shadowBlur = 16 + e * 22; c.shadowColor = 'rgba(120,220,255,.9)';
    c.fillStyle = g; c.fillText('J.A.R.V.I.S.', 0, 0); c.shadowBlur = 0;
    arc(R * .42, rad(200), rad(340), S / 900, cy(.25));

    c.restore(); c.globalAlpha = 1;
    requestAnimationFrame(frame);
  }
  frame();
})();
