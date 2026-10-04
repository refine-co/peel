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
