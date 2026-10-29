# Pinterest pin kit — Peel sticker packs

Ready to paste. **Nothing here has been posted.** Pins go out only on Yow's explicit go.

Two things that were true when this file was written are not true now, and both were corrected on
29 October 2026.

- **Peel is in production**, live on Google Play since 12 October. The old line about promotion
  being frozen until it gets there is gone.
- **The account question is settled.** Pins go out under the **RefineCo** Pinterest account, not
  the Oyen Kampung one — Yow chose that on 29 Oct, and it is also the account that already owns the
  `refineco.app` domain claim. One task comes with it: `peel.refineco.app` still has to be claimed,
  and it can only be claimed by **HTML tag or HTML file, never a TXT record**, because the name is
  a CNAME to `refine-co.github.io` and DNS will not let a CNAME share a name with other records.
  Until that claim lands, pins to the packs page earn the account nothing.

## The three claims that may appear in a pin, and the ones that may not

This file used to promise pinners that Peel "works entirely offline", that "no account is needed"
and that there is "No internet permission at all". **All three are false.** Peel signs in with
Google and has collected email since 2.4.4, and its Play listing carries a Data safety card saying
so. A pin making any of those claims would contradict Peel's own store page.

Safe to write, because they are true and checked:

- **No ads.**
- **No watermark.**
- **Making stickers is free.**

Never write: offline, no account, no internet permission, nothing is uploaded.

## Where the keywords come from

Yow's own Pinterest Trends reading, United States, 4 October 2026: **"stickers for messages
reaction"** climbs from about 20 to 100 over twelve months. Related rising terms shown with it:
*stickers for imessage funny*, *funny imessage stickers*, *funny tiktok stickers*,
*reaction stickers*.

Two of those say **iMessage**, which is iOS, and Peel is Android only. Writing pins to an iMessage
query would earn clicks from people who cannot use the app, so the copy below uses only the terms
Peel can honour: reaction stickers, WhatsApp stickers, Halloween stickers, sticker maker.

Pinterest's index is relative — it shows direction, not volume. Treat a climbing line as a reason
to publish, not as proof of an audience.

## Boards to make first

| Board | What goes in it |
|---|---|
| Reaction stickers | Say it, Midnight Replies |
| Halloween stickers | Peel Halloween, Halloween Night, Low Light |
| WhatsApp sticker packs | every free pack, the catch-all board |
| Make your own stickers | screens of Peel itself, the demo films |

Reactions is **not** on any board. See the hold below.

## Pins

Each pin is 1000x1500 at `packs/img/<pack>/pin.png`, built by `site/pins/make-pin.py`, which reads
the art straight out of the shipped `.peel` so a pin cannot drift from what the pack contains.
Each links to **its own pack** on the packs page.

| Pin | Image | Link |
|---|---|---|
| Peel Halloween | `packs/img/halloween/pin.png` | `https://peel.refineco.app/packs.html#halloween` |
| Halloween Night | `packs/img/halloween-night/pin.png` | `https://peel.refineco.app/packs.html#halloween-night` |
| Midnight Replies | `packs/img/midnight-replies/pin.png` | `https://peel.refineco.app/packs.html#midnight-replies` |
| Low Light | `packs/img/low-light/pin.png` | `https://peel.refineco.app/packs.html#low-light` |
| Say it | `packs/img/say-it/pin.png` | `https://peel.refineco.app/packs.html#say-it` |

The fragment matters. The packs page opens on one pack with the rest waiting in the rail, so a
Halloween pin that lands on the Halloween sheet keeps the promise its picture made. Pinterest
demotes a pin whose landing page does not.

**Only free packs are pinned.** Every pin image carries the line "Free download", so a paid pack
cannot use this template without changing it. Dead Honest, Sir Crow, Divine Blessings, Lakshmi,
Little Diya, Mayil and Kolam Lights all need a different footer before they can be pinned at all.

### Peel Halloween

- **Title:** Free Halloween stickers for WhatsApp — 20 cute spooky reactions
- **Description:** Twenty hand-drawn Halloween stickers for WhatsApp: a ghost, a black cat, a bat, a
  jack-o'-lantern and a small one-eyed monster saying Boo, Trick or treat, Spooky and Happy
  Halloween. Free to download, no ads, no watermark. Made with Peel, the sticker maker for Android.
- **Alt text:** A grid of cute Halloween stickers — a ghost in an orange scarf, a startled black
  cat, a bat and a smiling pumpkin, each with its word printed underneath.

### Halloween Night

- **Title:** Monster reply stickers for WhatsApp — 20 free, mummies to cauldrons
- **Description:** Twenty Halloween stickers for the replies you actually send: So tired, Wait ah,
  Good morning, No energy, Let's eat, Cheers. Mummies, skeletons, a wolf and a bubbling cauldron,
  drawn with a white die-cut edge and ready for WhatsApp. Free, no ads, no watermark.
- **Alt text:** A grid of Halloween stickers — a tired mummy, a sitting skeleton, a howling wolf and
  a smiling cauldron, each with its reply printed underneath.

### Midnight Replies

- **Title:** Cat reply stickers for WhatsApp — Seen, Typing, On my way
- **Description:** Eighteen black-cat stickers for the replies a group chat runs on: OK, Thank you,
  Seen, Typing, Still waiting, On my way, Call me, Congratulations. Free to download and ready for
  WhatsApp. Made with Peel, the sticker maker for Android. No ads, no watermark.
- **Alt text:** A grid of black cat stickers in purple witch hats, each with a chat reply printed
  underneath — OK, Thank you, Seen, Typing, On my way.

### Low Light

- **Title:** Pumpkin stickers for WhatsApp — 12 free battery moods
- **Description:** Twelve jack-o'-lantern stickers that run from Fully charged to Running on empty:
  Flickering, Second wind, Warming up, Still burning, Low battery, Burning bright. One idea, twelve
  moods, free for WhatsApp. No ads, no watermark.
- **Alt text:** A grid of pumpkin stickers glowing at different brightnesses, each with a battery
  mood printed underneath.

### Say it

- **Title:** 30 free reaction stickers for WhatsApp — LOL, OMG, On my way
- **Description:** Thirty reaction stickers for the things people actually send: LOL, OMG, On my
  way, Thank you, Good night, BRB. Bold lettering with a white die-cut edge, free to download and
  ready for WhatsApp. Built into Peel, the sticker maker for Android.
- **Alt text:** Six bold lettered reaction stickers reading LOL, OMG, On my way, Thank you, Love it
  and YES, each on a bright burst with a white outline.
- **Note:** the pin image was rebuilt on 29 Oct. The old one said "the offline sticker maker" and
  pointed at `refine-co.github.io/peel`; both are gone. Sticker 09 is deliberately not among the
  nine shown — the word *Congrats!* is broken across two lines mid-word in that piece, and that
  defect is still in the pack itself.

### Reactions — **ON HOLD, do not pin**

The pin that used to live here promised "real faces, moving", and that is exactly the problem. All
ten pieces are photographs of five identifiable people, and nothing in the project records where
those photographs came from or under what licence — see [[2026-10-29-peel-pack-art-audit]]. Two of
its animation frames are also visibly broken. Nothing about this pack is published anywhere until
Yow can answer the provenance question.

### Peel itself (make one from a demo film, once there is a board for it)

- **Title:** Turn any photo into a WhatsApp sticker — free, in under a minute
- **Description:** Peel cuts the subject out of your photo on the phone and builds a WhatsApp
  sticker pack from it. Animated stickers from a short video, a whole pack of text stickers in one
  pass, and a transparent cut-out you can save for TikTok or Canva. No ads. No watermark. Making
  stickers is free.

## Rules for writing more of these

1. Lead the title with what someone types into the search box, not with the brand.
2. Say **WhatsApp** and **Android** somewhere, because that is who can use it.
3. Never write iMessage or iPhone into a pin. The traffic cannot convert.
4. One pin per pack per board, not the same pin everywhere.
5. Say free, because making stickers is. Never say offline, no account, or no internet permission.
6. **Never ship a pack of TikTok meme characters or viral faces**, however well the keyword reads.
   That is what *funny tiktok stickers* searchers are looking for, and it is other people's
   copyright — the same takedown surface that ruled out open community uploads. Serve the keyword
   with Peel's own art or not at all. The Reactions hold above is this rule arriving late.
7. **For TikTok and CapCut, say gallery, never pack.** Neither has a sticker-pack surface. What
   works is: save a sticker to your phone's gallery, then place it in their editor as an overlay.
   Checked by hand on 4 Oct 2026 — a still PNG and an animated GIF both place on a TikTok
   timeline, and the GIF keeps moving. **Save to Photos shipped in 2.4.8 and is live**, so a TikTok
   line is now allowed; it was not when this rule was written.
8. **Look at the pin before it goes out.** Not the description, the picture. A title that says
   skeletons over a grid of mummies is the same failure as a caption that says crescent moon over a
   crescent and star.
