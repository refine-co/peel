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

  /* ---- the rail: swipe sideways, the middle card is the open section ----
     Eight sections laid out at once made the page 35,821 px tall. Now the rail is the index
     and exactly one section is in the layout. The snapping is the browser's; this only reads
     which card ended up in the middle and swaps the section under it.

     This block sits BEFORE the reduced-motion return below on purpose: a visitor who asked
     for less motion still gets the short page. */

  (function () {
    var rail = document.getElementById("rail");
    if (!rail) return;                       // every other page shares this script

    var cards = Array.prototype.slice.call(rail.querySelectorAll(".pcard"));
    if (!cards.length) return;

    var sections = {};
    cards.forEach(function (card) {
      var el = document.getElementById(card.dataset.for);
      if (el) sections[card.dataset.for] = el;
    });

    // The group headings and the scenes note sit outside every section, so hiding only the
    // sections would leave "Festive" and "From the makers" standing over nothing, and a
    // paragraph telling the reader to tap a piece that is not there.
    var headings = ["halloween-h", "reactions-h", "scenes"].map(function (id) {
      return document.getElementById(id);
    }).filter(Boolean);
    var scenesNote = (function () {
      var h = document.getElementById("scenes");
      var n = h && h.nextElementSibling;
      return n && n.classList.contains("note") ? n : null;
    })();
    headings.forEach(function (h) { h.hidden = true; });

    var wrap = document.getElementById("packs") || rail.parentElement;
    var prev = document.querySelector(".rail-arrow.prev");
    var next = document.querySelector(".rail-arrow.next");
    var open = null;

    function show(slug, focus) {
      if (!sections[slug] || slug === open) return;
      Object.keys(sections).forEach(function (key) {
        sections[key].hidden = key !== slug;
      });
      cards.forEach(function (card) {
        var on = card.dataset.for === slug;
        card.classList.toggle("is-on", on);
        card.setAttribute("aria-selected", on ? "true" : "false");
        card.tabIndex = on ? 0 : -1;
      });
      if (scenesNote) scenesNote.hidden = !sections[slug].classList.contains("scene");
      open = slug;
      // replaceState, not pushState: a swipe is not a page, and eight of them should not
      // bury the way back to wherever the visitor came from.
      history.replaceState(null, "", "#" + slug);
      if (focus) {
        sections[slug].tabIndex = -1;
        sections[slug].focus({ preventScroll: true });
        // The rail, not the section. Scrolling to the pack alone puts the only evidence that
        // there are seven others off the top of the screen.
        wrap.scrollIntoView({ block: "start", behavior: calm ? "auto" : "smooth" });
      }
    }

    function centre(card, smooth) {
      var to = card.offsetLeft - (rail.clientWidth - card.offsetWidth) / 2;
      rail.scrollTo({ left: to, behavior: smooth && !calm ? "smooth" : "auto" });
    }

    function nearest() {
      var mid = rail.scrollLeft + rail.clientWidth / 2;
      var best = cards[0], gap = Infinity;
      cards.forEach(function (card) {
        var d = Math.abs(card.offsetLeft + card.offsetWidth / 2 - mid);
        if (d < gap) { gap = d; best = card; }
      });
      return best;
    }

    function arrows() {
      if (!prev || !next) return;
      var i = cards.indexOf(nearest());
      prev.hidden = next.hidden = false;
      prev.disabled = i <= 0;
      next.disabled = i >= cards.length - 1;
    }

    var settle;
    rail.addEventListener("scroll", function () {
      clearTimeout(settle);
      settle = setTimeout(function () {
        show(nearest().dataset.for, false);
        arrows();
      }, 90);
    }, { passive: true });

    cards.forEach(function (card) {
      card.addEventListener("click", function () {
        centre(card, true);
        show(card.dataset.for, true);
        arrows();
      });
      card.addEventListener("focus", function () { centre(card, true); });
    });

    function step(by) {
      var i = cards.indexOf(nearest()) + by;
      if (i < 0 || i >= cards.length) return;
      centre(cards[i], true);
      show(cards[i].dataset.for, false);
      cards[i].tabIndex = 0;
      cards[i].focus({ preventScroll: true });
      arrows();
    }

    if (prev) prev.addEventListener("click", function () { step(-1); });
    if (next) next.addEventListener("click", function () { step(1); });

    rail.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
      if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    });

    /* Which one to open on arrival. #halloween is the hero's "See the sheets" button and
       #scenes is a chip over an <h2> that is not a section, so it means "the first scene". */
    function wanted() {
      var hash = (location.hash || "").slice(1);
      if (sections[hash]) return hash;
      if (hash === "packs") return cards[0].dataset.for;
      if (hash === "scenes" || hash === "reactions-h" || hash === "halloween-h") {
        var want = hash === "scenes";
        for (var i = 0; i < cards.length; i++) {
          var el = sections[cards[i].dataset.for];
          if (el && el.classList.contains("scene") === want) return cards[i].dataset.for;
        }
      }
      return cards[0].dataset.for;
    }

    // The document is about to lose 30,000 px of height, and the browser has already tried to
    // restore a scroll position against the tall version.
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";

    var first = wanted();
    show(first, false);
    function recentre() {
      cards.forEach(function (card) {
        if (card.dataset.for === open) centre(card, false);
      });
    }
    recentre();
    // Again once the layout has settled: the first pass runs before the web font has swapped
    // and before the open section's images have sizes, and either can move the track.
    requestAnimationFrame(recentre);
    window.addEventListener("load", recentre);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(recentre);
    arrows();
    if (location.hash) {
      // Everything above the rail — the hero art, the marquee — is lazy and undimensioned, so
      // it grows under us after this first scroll and carries the rail off the top. Hold the
      // position until the page stops moving or the visitor takes over.
      var held = true;
      var hold = function () { if (held) wrap.scrollIntoView({ block: "start", behavior: "auto" }); };
      addEventListener("wheel", function () { held = false; }, { passive: true, once: true });
      addEventListener("touchstart", function () { held = false; }, { passive: true, once: true });
      addEventListener("keydown", function () { held = false; }, { once: true });
      hold();
      requestAnimationFrame(hold);
      addEventListener("load", function () { hold(); setTimeout(function () { held = false; }, 400); });
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(hold);
    }

    /* A rail that has not moved looks like a row that ends where the screen does. The first
       time it comes into view it nudges itself a few pixels and settles back — enough to say
       "this scrolls" without taking the page over. Once only, never after a real scroll, and
       never for someone who asked for less motion. */
    if (!calm && "IntersectionObserver" in window) {
      var nudged = false;
      var touched = false;
      rail.addEventListener("pointerdown", function () { touched = true; }, { passive: true });
      rail.addEventListener("wheel", function () { touched = true; }, { passive: true });
      var hint = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting || nudged) return;
          nudged = true;
          hint.disconnect();
          if (touched || rail.scrollWidth <= rail.clientWidth) return;
          var home = rail.scrollLeft;
          rail.scrollTo({ left: home + 26, behavior: "smooth" });
          setTimeout(function () {
            if (!touched) rail.scrollTo({ left: home, behavior: "smooth" });
          }, 420);
        });
      }, { threshold: 0.6 });
      hint.observe(rail);
    }

    window.addEventListener("hashchange", function () {
      var slug = wanted();
      show(slug, true);
      cards.forEach(function (card) {
        if (card.dataset.for === slug) centre(card, true);
      });
      arrows();
    });
  })();

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
