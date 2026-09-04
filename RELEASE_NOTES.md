## Render Post v1.8.1

First public release build. Windows only. Download `RenderPost.exe` below, drop it in a folder of renders, double-click. First launch asks for your own fal.ai key. Windows will show "protected your PC" once: More info, Run anyway. The user guide is in `docs/RenderPost-Guide.pdf`.

### What's in this build (for Filip, and anyone following along)

**Your feedback, resolved**
- Prompt box losing an edited draft when switching versions: fixed. Edits survive browsing older versions and return on the latest.
- Reel downsampling: it sized to the first clip; it now sizes to the largest clip in the reel.
- Reel order: tick order is final, and each Add to reel toggle shows its number.
- Music: a folder button beside the Music dropdown opens the render folder where the track goes; Start at lets you cut in.
- Catalog: a "catalog" link beside the model dropdown opens the URL field, load status and the JSON format. This repo's `models.json` is the default catalog.
- Picks tab with a thumbnail gallery.
- Export prompts for images as well as video, with hosted image URLs for other tools.
- Angles count updates on the buttons immediately.
- H3 Max: 480P/768P, integer duration, 5s minimum. H3 Max Turbo available under show all.
- Camera energy (Calm / Moderate / Dynamic) for the static-video problem.
- Character: generate or upload one person, consistent across enhancements and angles; take-only on the video side, as suggested.
- Connection refused: was the app quitting when the tab went to the background. Fixed since 1.3.4.

**New for a smoother day**
- Enhance selected: tick images, the main button becomes "Enhance N selected".
- Grid / Detail switch for scanning many renders; shift-click selects.
- Running spend in the header from fal list prices (GPT Image 2 counted at $0.25 an image), amber past a threshold you set. An estimate, not a bill.
- Settings folded: character, variations, angles, catalog and spend limit under More.
- Delete a version (to `enhanced/trash`).
- In-app confirms and toasts everywhere; no more Windows dialog boxes.
- Folder watching: dropped renders appear on their own; drag images onto the window too.
- Selecting an angle switches the viewer to After.
- New project: switch folders from inside the app, with recents.
- Update check: the header shows a link when a newer release exists here.

**Still to verify against live fal**
- H3 Max with the corrected parameters.
- Whether Dynamic camera energy moves the camera, or the models are the limit.
