/* Peel interactions.
   Drag a sticker toward its top-left and it peels off the backing; let go and it snaps back.
   The whole animation is one CSS custom property, --p, so the browser does the drawing. */

(function () {
  "use strict";

  var calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var PULL = 110;   // pixels of drag for a full peel

  /* ---- drag to peel ---- */

  document.querySelectorAll(".peel").forEach(function (el) {
    var id = null, x0 = 0, y0 = 0;

    el.addEventListener("pointerdown", function (e) {
      if (e.button !== 0 && e.pointerType === "mouse") return;
      id = e.pointerId;
      x0 = e.clientX;
      y0 = e.clientY;
      el.classList.add("dragging");
      el.setPointerCapture(id);
    });

    el.addEventListener("pointermove", function (e) {
      if (e.pointerId !== id) return;
      // peeling means pulling up and to the left, away from the bottom-right corner
      var dx = x0 - e.clientX;
      var dy = y0 - e.clientY;
      var pulled = (dx + dy) / 2;
      var p = Math.max(0, Math.min(1, pulled / PULL));
      el.style.setProperty("--p", p.toFixed(3));
      if (p > 0.05) e.preventDefault();
    });

    function release(e) {
      if (e.pointerId !== id) return;
      id = null;
      el.classList.remove("dragging");   // transition comes back, so it springs home
      el.style.removeProperty("--p");
    }

    el.addEventListener("pointerup", release);
    el.addEventListener("pointercancel", release);
  });

  /* ---- a scene fills itself in ----
     Each piece carries the home the .chill gave it, and the board carries a ghost of every
     piece already sitting at that home. Markup order is the order the picture is painted in,
     back to front, so the ghosts stack correctly however you click them.

     Without this script the ghosts are all visible, which is the finished picture. The script
     adds .live, which takes them off and hands them to the tray. */

  document.querySelectorAll(".scene").forEach(function (scene) {
    var board = scene.querySelector(".board");
    var pieces = Array.prototype.slice.call(scene.querySelectorAll(".piece"));
    if (!board || !pieces.length) return;

    var ghosts = {};
    scene.querySelectorAll(".board .ghost").forEach(function (g) { ghosts[g.dataset.i] = g; });

    var fill = scene.querySelector(".fill");
    var empty = scene.querySelector(".clear");
    var done = scene.querySelector(".done");
    var placed = 0;
    var timers = [];

    scene.classList.add("live");

    function check() {
      if (fill) fill.hidden = placed === pieces.length;
      if (empty) empty.hidden = placed === 0;
      if (done) done.hidden = placed !== pieces.length;
    }

    function put(piece) {
      var g = ghosts[piece.dataset.i];
      if (!g || piece.classList.contains("down")) return;
      g.classList.remove("peek");
      g.classList.add("on");
      piece.classList.add("down");
      piece.setAttribute("aria-disabled", "true");
      placed++;
      check();
    }

    function reset() {
      timers.forEach(clearTimeout);
      timers = [];
      pieces.forEach(function (piece) {
        var g = ghosts[piece.dataset.i];
        if (g) g.classList.remove("on", "peek");
        piece.classList.remove("down");
        piece.removeAttribute("aria-disabled");
      });
      placed = 0;
      check();
    }

    pieces.forEach(function (piece) {
      var g = ghosts[piece.dataset.i];

      function peek(on) {
        if (!g || piece.classList.contains("down")) return;
        g.classList.toggle("peek", on);
        g.classList.toggle("on", on);
      }

      piece.addEventListener("pointerenter", function () { peek(true); });
      piece.addEventListener("pointerleave", function () { peek(false); });
      piece.addEventListener("focus", function () { peek(true); });
      piece.addEventListener("blur", function () { peek(false); });
      piece.addEventListener("click", function () { put(piece); });
    });

    if (fill) fill.addEventListener("click", function () {
      pieces.forEach(function (piece, i) {
        if (piece.classList.contains("down")) return;
        if (calm) return put(piece);
        timers.push(setTimeout(function () { put(piece); }, i * 45));
      });
    });

    if (empty) empty.addEventListener("click", reset);

    check();
  });

  /* ---- reveal on scroll, 40ms micro cascade ---- */

  if (calm || !("IntersectionObserver" in window)) {
    document.querySelectorAll(".reveal").forEach(function (el) { el.classList.add("in"); });
    return;
  }

  var seen = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var el = entry.target;
      var group = el.parentElement;
      var i = Array.prototype.indexOf.call(group.children, el);
      el.style.setProperty("--d", Math.min(i, 11) * 40 + "ms");   // cap the cascade at 440ms
      el.classList.add("in");
      seen.unobserve(el);
    });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });

  document.querySelectorAll(".reveal").forEach(function (el) { seen.observe(el); });
})();
