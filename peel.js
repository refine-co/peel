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

  /* ---- the rail: drag it, flick it, and the card in the middle is the open section ----
     Eight sections laid out at once made the page 35,821 px tall. Now the rail is the index
     and exactly one section is in the layout.

     The gesture is handled here rather than left to the native scroller, because the native
     one cannot be told how hard it was thrown: `scroll-behavior` is a fixed curve and
     `scroll-snap` re-snaps every programmatic write, so both were acting on the drag itself.
     What is kept is the element's own `overflow-x`, so a trackpad, a wheel and a screen
     reader still scroll it; those paths land on a card through the settle below.

     This block sits BEFORE the reduced-motion return further down on purpose: a visitor who
     asked for less motion still gets the short page and a rail they can drag. */

  // One call per rail: the page has a Sticker packs rail and a Scenes rail, and each runs this
  // whole block on its own, with its own cards, sections, arrows and position.
  document.querySelectorAll(".rail").forEach(function (rail) {
    var kind = rail.dataset.kind;            // "packs" or "scenes"

    var cards = Array.prototype.slice.call(rail.querySelectorAll(".pcard"));
    if (!cards.length) return;

    var sections = {};
    cards.forEach(function (card) {
      var el = document.getElementById(card.dataset.for);
      if (el) sections[card.dataset.for] = el;
    });

    // The pack group headings sit outside every section, so hiding only the sections would leave
    // "Festive" and "From the makers" standing over nothing. The scenes have no such headings:
    // the Scenes heading and its note belong to the section, and stay.
    if (kind === "packs") {
      ["halloween-h", "reactions-h"].forEach(function (id) {
        var h = document.getElementById(id);
        if (h) h.hidden = true;
      });
    }

    // Where "scroll to the rail" lands (the section heading, so the heading is not left above
    // the screen), and this rail's own arrows: found from the rail, never from the page, or the
    // second rail would move the first one.
    var wrap = document.getElementById(rail.dataset.anchor) || rail.parentElement;
    var nav = rail.closest(".rail-wrap") || rail.parentElement;
    var prev = nav.querySelector(".rail-arrow.prev");
    var next = nav.querySelector(".rail-arrow.next");
    var open = null;

    /* ---- geometry, measured once ----
       Reading offsetLeft inside the draw loop meant a style-and-layout flush per card per
       frame, right in the middle of the gesture. None of it moves while you drag, so it is
       measured on load and on resize and read from here afterwards. */
    var geo = [], railW = 1, maxScroll = 0, pitch = 1;

    function measure() {
      railW = rail.clientWidth || 1;
      maxScroll = Math.max(rail.scrollWidth - railW, 0);
      geo = cards.map(function (c) { return { left: c.offsetLeft, w: c.offsetWidth }; });
      pitch = geo.length > 1 ? Math.abs(geo[1].left - geo[0].left) : geo[0].w;
      if (!pitch) pitch = geo[0].w || 1;
    }

    function centreOf(i) { return geo[i].left - (railW - geo[i].w) / 2; }

    function indexNearest(at) {
      var mid = at + railW / 2, best = 0, gap = Infinity;
      for (var i = 0; i < geo.length; i++) {
        var d = Math.abs(geo[i].left + geo[i].w / 2 - mid);
        if (d < gap) { gap = d; best = i; }
      }
      return best;
    }

    /* The rail's position, owned here. Written to the element, never read back during a
       gesture — reading scrollLeft after writing it flushes the scroll the write queued. */
    var pos = 0;

    function setPos(v) {
      if (v < 0) v = 0;
      else if (v > maxScroll) v = maxScroll;
      pos = v;
      rail.scrollLeft = v;
      redraw();
    }

    /* ---- the ring ----
       Every card is a plank on a cylinder lying across the screen: the one in front is flat
       and nearest, its neighbours rotate away on their own vertical axis and sink back. One
       rAF, one transform each, no measuring. */
    /* Ten cards on the arc, not three. The whole shelf is the point: a wheel showing one
       card and two slivers says as little about what is here as the old straight row did.
       Every number below is per step, and a step is one card along the track. */
    var STEP = 14;      // degrees of turn per card away from the middle
    var DEPTH = 44;     // how far each step sinks into the screen, in px
    var RISE = 110;     // the radius the drop is taken from, in px
    var SHRINK = 0.05;  // how much smaller each step is
    var LEAN = 3;       // degrees each card leans in the plane of the screen, per step
    var FADE = 0.12;    // how much a card loses per step
    var ARC = 5;        // steps before the ring stops turning any further

    // Half the deepest drop the arc can produce, which is where the ring is hung from.
    var SAG = (1 - Math.cos(ARC * STEP * Math.PI / 180)) * RISE / 2;

    var ring = !calm && CSS.supports("perspective", "1px");
    if (ring) rail.classList.add("is-ring");

    var frame = 0;
    function draw() {
      frame = 0;
      var mid = pos + railW / 2;
      for (var i = 0; i < cards.length; i++) {
        var d = (geo[i].left + geo[i].w / 2 - mid) / pitch;
        if (d < -ARC) d = -ARC;
        else if (d > ARC) d = ARC;
        var far = d < 0 ? -d : d;
        // The wheel is seen slightly from above, so its rim falls away: a card's drop is the
        // sagitta of its own angle, which is what makes the row read as a curve rather than
        // as a straight line of tilted cards.
        // Centred on the arc rather than hung from its top: the middle card rides a little
        // above the line and the rim falls a little below it, so the wheel needs half the
        // vertical room and the rail does not grow a scrollbar underneath it.
        var drop = (1 - Math.cos(d * STEP * Math.PI / 180)) * RISE - SAG;
        cards[i].style.transform =
          "translateY(" + drop.toFixed(1) + "px)" +
          " rotate(" + (d * LEAN).toFixed(2) + "deg)" +
          " rotateY(" + (-d * STEP).toFixed(2) + "deg)" +
          " translateZ(" + (-far * DEPTH).toFixed(1) + "px)" +
          " scale(" + (1 - far * SHRINK).toFixed(3) + ")";
        cards[i].style.opacity = Math.max(1 - far * FADE, 0.3).toFixed(3);
      }
    }
    function redraw() {
      if (!ring || frame) return;
      frame = requestAnimationFrame(draw);
    }

    /* Marking the card is a class toggle. Swapping the section lays out between 20 and 81
       images, every one of them lazy and most without declared dimensions, so it reflows for
       as long as they decode. The highlight may follow the finger; the section waits. */
    function mark(slug) {
      var at = 0;
      cards.forEach(function (card, i) {
        if (card.dataset.for === slug) at = i;
      });
      cards.forEach(function (card, i) {
        var on = i === at;
        card.classList.toggle("is-on", on);
        card.setAttribute("aria-selected", on ? "true" : "false");
        card.tabIndex = on ? 0 : -1;
        // Set here, not per frame: the order only changes when the middle card does.
        card.style.zIndex = String(100 - Math.abs(i - at));
      });
    }

    // [quiet] leaves the address bar alone. The first open of each rail on load is quiet, because
    // both rails open something and the second would overwrite a link to the first.
    function show(slug, focus, quiet) {
      if (!sections[slug]) return;
      if (slug === open) { if (focus) reveal(slug); return; }
      Object.keys(sections).forEach(function (key) {
        sections[key].hidden = key !== slug;
      });
      mark(slug);
      open = slug;
      // replaceState, not pushState: a swipe is not a page, and eight of them should not
      // bury the way back to wherever the visitor came from.
      if (!quiet) history.replaceState(null, "", "#" + slug);
      if (focus) reveal(slug);
    }

    function reveal(slug) {
      sections[slug].tabIndex = -1;
      sections[slug].focus({ preventScroll: true });
      // The rail, not the section. Scrolling to the pack alone puts the only evidence that
      // there are seven others off the top of the screen.
      wrap.scrollIntoView({ block: "start", behavior: calm ? "auto" : "smooth" });
    }

    function arrows() {
      if (!prev || !next) return;
      var i = indexNearest(pos);
      prev.hidden = next.hidden = false;
      prev.disabled = i <= 0;
      next.disabled = i >= cards.length - 1;
    }

    function indexOfOpen() {
      for (var i = 0; i < cards.length; i++) if (cards[i].dataset.for === open) return i;
      return indexNearest(pos);
    }

    /* ---- the landing ----
       easeOutCubic: quick off the mark, soft arrival. 1.1 ms per pixel puts a one-card move
       at about 200 ms and a two-card one at about 400, which is the whole of the range the
       gesture can actually produce; 0.65 left everything under 1.4 cards pinned at the floor. */
    var glideId = 0;
    function stopGlide() { if (glideId) { cancelAnimationFrame(glideId); glideId = 0; } }

    function glide(to) {
      stopGlide();
      if (to < 0) to = 0;
      else if (to > maxScroll) to = maxScroll;
      var from = pos;
      var span = to - from;
      if (calm || Math.abs(span) < 1) { setPos(to); settleNow(); return; }
      var ms = Math.min(420, Math.max(180, Math.abs(span) * 1.1));
      var t0 = performance.now();
      glideId = requestAnimationFrame(function run(now) {
        var p = (now - t0) / ms;
        if (p > 1) p = 1;
        setPos(from + span * (1 - Math.pow(1 - p, 3)));
        if (p < 1) glideId = requestAnimationFrame(run);
        else { glideId = 0; settleNow(); }
      });
    }

    function centre(card) { glide(centreOf(cards.indexOf(card))); }

    /* Everything expensive happens here, once the rail has stopped: the section swap, the
       hash, the arrows — and a landing for the scroll paths nobody snapped, which is every
       trackpad, wheel, Home/End and screen-reader scroll now that scroll-snap is gone. */
    var settleTimer;
    function settleNow() {
      clearTimeout(settleTimer);
      if (dragging) return;
      var i = indexNearest(pos);
      show(cards[i].dataset.for, false);
      arrows();
      if (!glideId && Math.abs(pos - centreOf(i)) > 1) glide(centreOf(i));
    }

    rail.addEventListener("scroll", function () {
      if (dragging || glideId) return;       // those two own `pos` already
      pos = rail.scrollLeft;
      redraw();
      clearTimeout(settleTimer);
      settleTimer = setTimeout(settleNow, 140);
    }, { passive: true });

    addEventListener("resize", function () {
      measure();
      setPos(centreOf(indexOfOpen()));
      arrows();
    });

    /* ---- the drag ----
       1:1 with the finger and nothing else: a direct-manipulation gesture with a curve on it
       reads as lag. Six pixels tells a drag from a tap; past that the click is swallowed. */
    var GRAB = 6;          // px before a press becomes a drag
    var WINDOW = 90;       // ms of pointer history the flick is measured over
    var THROW = 140;       // ms of travel a flick is projected along
    var REACH = 3;         // cards a single flick may cross
    var NUDGE = 0.35;      // px/ms that counts as a flick even without travel

    var dragging = false, pid = null, startX = 0, startPos = 0, moved = false;
    var samples = [], suppress = false, pointerFocus = false;

    function sample(e) {
      var t = e.timeStamp || performance.now();
      samples.push({ x: e.clientX, t: t });
      while (samples.length > 2 && t - samples[0].t > WINDOW) samples.shift();
    }

    rail.addEventListener("pointerdown", function (e) {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      if (pid !== null) return;              // one finger owns the rail
      stopGlide();
      clearTimeout(settleTimer);
      pid = e.pointerId;
      dragging = true;
      moved = false;
      suppress = false;
      // pointerdown focuses a <button>, and the focus handler below would start a glide into
      // the same scrollLeft this drag is about to write. It stands down until the finger is up.
      pointerFocus = true;
      startX = e.clientX;
      startPos = pos = rail.scrollLeft;
      samples = [];
      sample(e);
      try { rail.setPointerCapture(pid); } catch (err) { /* capture is a nicety */ }
      rail.classList.add("is-dragging");
      document.body.classList.add("rail-dragging");
    });

    rail.addEventListener("pointermove", function (e) {
      if (!dragging || e.pointerId !== pid) return;
      var dx = startX - e.clientX;
      if (!moved && Math.abs(dx) > GRAB) moved = true;
      if (moved) {
        setPos(startPos + dx);
        e.preventDefault();
      }
      sample(e);
    });

    function land(flick) {
      var from = indexNearest(startPos);
      var to = from;
      if (flick) {
        var last = samples[samples.length - 1], first = samples[0];
        var dt = Math.max(last.t - first.t, 1);
        var v = (first.x - last.x) / dt;             // px/ms, positive = rail moving forward
        var travel = pos - startPos;
        to = indexNearest(pos + v * THROW);
        // A short, gentle flick is the first thing anyone tries. Without this it lands back
        // where it started, which reads as the rail ignoring you.
        var way = travel > 0 || v > 0 ? 1 : (travel < 0 || v < 0 ? -1 : 0);
        if (to === from && way && (Math.abs(travel) > pitch * 0.25 || Math.abs(v) > NUDGE)) {
          to = from + way;
        }
        if (to > from + REACH) to = from + REACH;
        else if (to < from - REACH) to = from - REACH;
      } else {
        to = indexNearest(pos);
      }
      if (to < 0) to = 0;
      else if (to > cards.length - 1) to = cards.length - 1;
      mark(cards[to].dataset.for);                   // the cheap half, immediately
      glide(centreOf(to));
    }

    function release(e, flick) {
      if (!dragging || (e && e.pointerId !== pid)) return;
      dragging = false;
      pid = null;
      pointerFocus = false;
      suppress = moved;
      rail.classList.remove("is-dragging");
      document.body.classList.remove("rail-dragging");
      land(flick && moved && samples.length > 1);
    }

    rail.addEventListener("pointerup", function (e) { release(e, true); });
    // The browser claims a gesture it decides is vertical. Land on the nearest card rather
    // than flicking on a velocity that belonged to a scroll somebody else is now doing.
    rail.addEventListener("pointercancel", function (e) { release(e, false); });

    cards.forEach(function (card) {
      card.addEventListener("click", function (e) {
        if (suppress) { suppress = false; e.preventDefault(); return; }
        centre(card);
        show(card.dataset.for, true);
      });
      card.addEventListener("focus", function () {
        if (pointerFocus || dragging) return;        // a pointer is already driving this
        centre(card);
      });
    });

    function step(by) {
      var i = indexNearest(pos) + by;
      if (i < 0 || i >= cards.length) return;
      mark(cards[i].dataset.for);
      glide(centreOf(i));
      cards[i].tabIndex = 0;
      cards[i].focus({ preventScroll: true });
    }

    if (prev) prev.addEventListener("click", function () { step(-1); });
    if (next) next.addEventListener("click", function () { step(1); });

    rail.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
      if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    });

    /* Which of THIS rail's cards the address asks for, or null when it asks for something that
       belongs to the other rail or to nothing. The null matters: a link to a scene must not
       send the packs rail back to its first card. #packs is the hero's "See the sheets" button
       and #scenes the chip over the Scenes heading; each means "the first one". */
    function wanted() {
      var hash = (location.hash || "").slice(1);
      if (sections[hash]) return hash;
      if (hash === rail.dataset.anchor) return cards[0].dataset.for;
      if (kind === "packs" && (hash === "reactions-h" || hash === "halloween-h")) return cards[0].dataset.for;
      return null;
    }

    // The document is about to lose 30,000 px of height, and the browser has already tried to
    // restore a scroll position against the tall version.
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";

    measure();
    var first = wanted() || cards[0].dataset.for;
    show(first, false, true);
    /* Re-measure and put the open card back in the middle. It centres the *open* card and
       not whatever is nearest, because the first measurement happens before the images and
       the web font have sizes: the rail is not yet scrollable, the opening position clamps
       to zero, and centring "the nearest" would then quietly adopt the wrong card. */
    function recentre() {
      measure();
      setPos(centreOf(indexOfOpen()));
      arrows();
    }
    setPos(centreOf(cards.map(function (c) { return c.dataset.for; }).indexOf(first)));
    arrows();
    // Again once the layout has settled: the first pass runs before the web font has swapped
    // and before the open section's images have sizes, and either can move the track.
    requestAnimationFrame(recentre);
    addEventListener("load", recentre);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(recentre);

    /* A link to a pack from elsewhere on the page — the hero's chips, the footer — changes
       only the fragment, so no load happens and nothing else would move the rail. */
    addEventListener("hashchange", function () {
      var slug = wanted();
      if (!slug) return;                     // not ours: the other rail answers it
      show(slug, true);
      glide(centreOf(indexOfOpen()));
    });

    if (location.hash && wanted()) {
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
       time it comes into view it slides a little and settles back — enough to say "this
       scrolls" without taking the page over. Once only, never after the visitor has touched
       it, and never for someone who asked for less motion. */
    if (!calm && "IntersectionObserver" in window) {
      var nudged = false, touched = false;
      rail.addEventListener("pointerdown", function () { touched = true; }, { passive: true });
      rail.addEventListener("wheel", function () { touched = true; }, { passive: true });
      var hint = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting || nudged) return;
          nudged = true;
          hint.disconnect();
          if (touched || maxScroll <= 0) return;
          var home = pos;
          glide(home + 26);
          setTimeout(function () { if (!touched) glide(home); }, 430);
        });
      }, { threshold: 0.6 });
      hint.observe(rail);
    }
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

/* Like counts, fetched when somebody opens the page.
 *
 * The build writes the numbers in, so the page is right the moment it renders and right
 * without JavaScript at all. This only replaces them with fresher ones. Nothing moves: the
 * rails measure themselves from the card order at startup, so re-sorting here would leave the
 * wheel pointing at the wrong card. Order follows the build, which is also when packs are
 * published.
 *
 * Read-only by design. Liking needs an account, accounts live in the app, and giving the
 * website a sign-in to support a heart would be a login page's worth of risk for a number.
 */
(function () {
  var slots = document.querySelectorAll("[data-likes-for]");
  if (!slots.length) return;
  fetch("https://peel-submit.refineco.workers.dev/packs/likes", {
    method: "POST",
    // text/plain keeps this a simple request: no preflight, no OPTIONS route to maintain on a
    // Worker that only answers POST. The endpoint ignores the body.
    headers: { "Content-Type": "text/plain" },
    body: "{}",
  })
    .then(function (answer) { return answer.ok ? answer.json() : null; })
    .then(function (data) {
      if (!data || !data.likes) return;
      slots.forEach(function (slot) {
        var n = data.likes[slot.dataset.likesFor];
        // A pack with no likes shows nothing rather than a nought, the same as the build does.
        slot.textContent = n ? "♥ " + n : "";
      });
    })
    .catch(function () {
      // Offline, blocked, or the Worker is down. The built-in numbers stay, which is the
      // whole reason they are written into the page.
    });
})();
