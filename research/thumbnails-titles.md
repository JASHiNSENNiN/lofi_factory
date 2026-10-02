# Thumbnails and titles: sources and what the code does

| Finding | Source | What the code does |
|---|---|---|
| Thumbnail text works best under ~4 words; one focal point, at most ~3 elements; high contrast that survives phone size. | [increv.co](https://increv.co/), [growthos.in](https://growthos.in/) thumbnail guides | Thumbnail text is the title's scene phrase (≤ 4 words); one room, one window, one figure. Legibility and brightness checks were kept. |
| The lofi look is a figure seen from behind with headphones, a window, a desk and a cat, in warm interior light; Lofi Girl made this the genre's visual identity. | Academic and trade coverage of the Lofi Girl channel (a Taylor & Francis journal article on Lofi Girl; Alibaba articles on the channel's branding) | `_listener`, `_window_box`, `_lamp`, cat on the sill. |
| Complementary warm/cool light (teal–orange) reads as cinematic and separates subject from background. | [Piktochart color guide](https://piktochart.com/), [architecturecourses.org color harmony](https://architecturecourses.org/) | Warm lamp pool vs cool window light; `split_tone` grades shadows cool and highlights warm. |
| Titles: about 40–60 characters so they aren't truncated in search; the searched keyword in the first words. | Postlia, Teleprompter.com and Miracamp title-length guides | Titles held to 40–62 characters; genre tag inside the brackets; the length tag is dropped first if a title runs long. |
| Lofi titles follow "scene/mood + emoji + [genre / use]". | Lofi Girl, Chillhop and Gridfiti's lofi title collections | `titles.build` forms: scene, moment, radio. |

Limits: the room is drawn with PIL shapes, not illustrated, so it is a
clean flat-vector look rather than a painted one.
