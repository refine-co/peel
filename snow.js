/* Christmas snow (10 Nov 2026, Yow: "deco the website ... even better snowing").
 *
 * Falls from 1 November to 6 January and then switches itself off, so nobody has to remember to
 * take it down. One canvas behind the page (z-index -1, the same layer as the drifting colour in
 * style.css), so flakes pass behind text and cards, never over a button. The snow piled on the
 * menu bar and the big buttons is CSS, keyed on html.snowy.
 *
 * The snowflake button turns it all off, and the choice is remembered on this device only.
 * Reduced motion: the flakes are drawn once and stay still.
 */
(function () {
  var now = new Date();
  var m = now.getMonth(), d = now.getDate();
  if (!(m === 10 || m === 11 || (m === 0 && d <= 6))) return;

  var KEY = "peel-snow";
  var on = true;
  try { on = localStorage.getItem(KEY) !== "off"; } catch (e) { /* storage blocked: snow stays on */ }

  var root = document.documentElement;
  var still = window.matchMedia("(prefers-reduced-motion: reduce)");
  var dark = window.matchMedia("(prefers-color-scheme: dark)");
  var canvas = null, ctx = null, flakes = [], frame = 0, last = 0, w = 0, h = 0, dpr = 1;

  function size() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth; h = window.innerHeight;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // About one flake per 11 px of width: ~35 on a phone, capped at 80 on a desktop.
    var want = Math.max(24, Math.min(80, Math.round(w / 11)));
    while (flakes.length < want) flakes.push(flake(true));
    flakes.length = want;
  }

  function flake(anywhere) {
    var r = Math.random() < 0.12 ? 3.2 + Math.random() * 1.6 : 1 + Math.random() * 2.2;
    return {
      x: Math.random() * w,
      y: anywhere ? Math.random() * h : -10,
      r: r,
      v: 0.25 + r * 0.22 + Math.random() * 0.2,   // bigger flakes are nearer, so they fall faster
      sway: 0.4 + Math.random() * 0.9,
      phase: Math.random() * Math.PI * 2,
      a: 0.55 + Math.random() * 0.4
    };
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    // On the cream theme a white dot disappears, so each flake gets a soft blue rim there.
    var rim = !dark.matches;
    for (var i = 0; i < flakes.length; i++) {
      var f = flakes[i];
      ctx.beginPath();
      ctx.arc(f.x, f.y, f.r, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255,255,255," + f.a + ")";
      ctx.fill();
      if (rim) {
        ctx.lineWidth = 1;
        ctx.strokeStyle = "rgba(110,140,190," + (f.a * 0.55) + ")";
        ctx.stroke();
      }
    }
  }

  function tick(t) {
    var dt = last ? Math.min((t - last) / 16.7, 3) : 1;
    last = t;
    for (var i = 0; i < flakes.length; i++) {
      var f = flakes[i];
      f.phase += 0.012 * dt;
      f.y += f.v * dt;
      f.x += Math.sin(f.phase) * f.sway * 0.35 * dt;
      if (f.y > h + 8) { flakes[i] = flake(false); flakes[i].x = Math.random() * w; }
      if (f.x < -8) f.x = w + 8; else if (f.x > w + 8) f.x = -8;
    }
    draw();
    frame = requestAnimationFrame(tick);
  }

  function run() {
    cancelAnimationFrame(frame); last = 0;
    if (!canvas || document.hidden) return;
    if (still.matches) { draw(); return; }
    frame = requestAnimationFrame(tick);
  }

  function start() {
    root.classList.add("snowy");
    canvas = document.createElement("canvas");
    canvas.className = "snow";
    canvas.setAttribute("aria-hidden", "true");
    ctx = canvas.getContext("2d");
    document.body.appendChild(canvas);
    flakes = [];
    size();
    run();
  }

  function stop() {
    root.classList.remove("snowy");
    cancelAnimationFrame(frame);
    if (canvas) canvas.remove();
    canvas = null;
  }

  function init() {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "snow-toggle";
    button.textContent = "❄";
    function label() {
      button.setAttribute("aria-pressed", on ? "true" : "false");
      button.setAttribute("aria-label", on ? "Turn the snow off" : "Turn the snow on");
      button.title = on ? "Snow off" : "Snow on";
    }
    button.addEventListener("click", function () {
      on = !on;
      try { localStorage.setItem(KEY, on ? "on" : "off"); } catch (e) { /* this visit only */ }
      if (on) start(); else stop();
      label();
    });
    label();
    document.body.appendChild(button);
    if (on) start();

    window.addEventListener("resize", function () { if (canvas) { size(); if (still.matches) draw(); } });
    document.addEventListener("visibilitychange", run);
    if (still.addEventListener) still.addEventListener("change", run);
    if (dark.addEventListener) dark.addEventListener("change", function () { if (canvas) draw(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
