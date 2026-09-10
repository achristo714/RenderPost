"""Art-director prompt briefs used to instruct the vision model."""


MOTION_BRIEF = """You write prompts for video models (Seedance, Kling) to animate a single
architectural visualization still. The still is frame one of the clip and must stay exactly
as it is: same architecture, materials, furniture, camera lens, and time of day. Motion
comes from the camera and from the world, never from redesigning the scene.

Structure the prompt the way these models are documented to want it, as short sentences
in this order, describing how the shot evolves over its full length:
1. What moves in the scene and how (subject and action): people walking or talking,
   leaves and curtains stirring, water, distant traffic, candle or lamp flicker, cloud
   drift. Only things already present or plausible. Natural speed.
2. The scene held constant: say explicitly that the architecture, materials, layout and
   lighting stay exactly as in the still.
3. ONE specific named camera move, slow and steady: slow push-in, slow pull-back, gentle
   dolly left or right, subtle orbit, or a slow crane. Never a vague word like "cinematic".
   Then state what the camera is NOT doing: no cuts, no zoom, no shake.
4. One short line of ambient sound that fits the space.
No text or captions in the video. Output ONLY the prompt. No preamble, no bullet points,
no quotes. Under 90 words."""

CHARACTER_BRIEF = """A SECOND input image is provided: a reference photo of one specific person. Include this
exact person in the scene, once, placed where a real person would be in this space and doing
something natural for it (seated at a table, standing at the counter, walking through, looking
at the view). Keep their face, hair, build and clothing consistent with the reference. Refer to
them in the prompt as "the person shown in the second input image". This overrides the rule
about not adding people, for this one person only; add nobody else unless the notes say so.
{note}"""

CHARACTER_T2I = ("Full-length reference photograph of one person for use as a consistent character in "
                 "architectural visualisation: {desc}. Plain light grey studio background, soft even "
                 "light, relaxed natural pose, facing the camera, photoreal, no text, no logos.")

TAKE_CHARACTER = """The LAST image is a reference of one specific person (@Image {n}). They appear in the take,
walking through the spaces at a natural pace, seen from behind or in three-quarter view more
than head-on, with consistent face, hair, build and clothing. Say so explicitly in the prompt."""

MOTION_CHARACTER = """The still contains a specific person. Keep their appearance exactly as in the still and give
them one small natural action across the clip (turn, take a few steps, sip, look up)."""

ENERGY = {
    "calm":     "Camera energy: CALM. One slow, steady move; the viewer should barely notice the camera. Suits stills for print and quiet interiors.",
    "moderate": "Camera energy: MODERATE. A clear, confident camera move that travels a noticeable distance over the clip (a dolly that crosses the room, an orbit of 20 to 30 degrees, a crane that rises past a balcony), plus visible life in the scene. Still smooth, never handheld.",
    "dynamic":  "Camera energy: DYNAMIC. A bold cinematic move with real parallax: a fast dolly or tracking shot, a sweeping orbit, a crane from ground to roofline, a drone-style reveal. Foreground elements should slide past the lens. The architecture still does not change; only the camera is brave.",
}

ANGLES_BRIEF = """You are an art director for architectural visualization. You are shown one finished
image of a space. Write {n} prompts for an image model that will produce {n} NEW stills of
this SAME space, each from a different camera position, as if a photographer had walked the
room. Every angle must be consistent with what the image shows: same architecture, materials,
furniture, fixtures, lighting and time of day. Nothing is redesigned; the camera moves, the
space does not.

Choose {n} genuinely different, useful angles for this space, for example: a wide
establishing view from the entrance, the reverse angle looking back, a low three-quarter view
across furniture, an elevated view, a tight detail vignette of the best material moment, a
view through an opening into the next space. Only propose angles this image gives enough
information to support. Name what the camera sees in each, using details visible in the image.

Format: EXACTLY {n} lines, one prompt per line, no numbering, no preamble, no quotes. Each
line starts with "Same space as the reference image, identical architecture, materials,
furniture, lighting and time of day." followed by the new camera position and what is in
frame. Under 60 words per line."""

MULTISHOT_BRIEF = """You write prompts for Seedance, a video model that supports multi-shot prompts:
several shots in one clip, cut together. You are given one architectural visualization still.
Write a prompt for a short sequence of {shots} shots of THIS space.

Rules:
- Shot 1 starts exactly on the still: same framing, same everything. Later shots are new
  camera setups of the same space (a closer detail, a reverse angle, a wider establishing
  view) that stay consistent with what the still shows: same architecture, materials,
  furniture, lighting and time of day. Never invent rooms or elements not implied by the still.
- Write EXACTLY one line per shot, each starting "Shot N:" in order. Within each line,
  follow the documented order: camera move first, then what moves in the scene, then a
  short sound cue. One slow camera move per shot. Do not use timestamps.
- No text, captions or logos.
- Output ONLY the shot lines, nothing else. Under 140 words total."""

TAKE_BRIEF = """You write prompts for Seedance reference-to-video. You are given several
architectural visualization stills of the same project, in order. ByteDance's documented
convention is to reference them as @Image 1, @Image 2, and so on. Write ONE prompt for a
single continuous cinematic take that tours the project, visiting the spaces in that
order, treating each image as the exact look of that space.
Rules:
- Reference each image explicitly by its @Image N tag, in order, and describe the camera
  move that carries the viewer from one to the next (walk through a doorway, glide along
  a facade, rise over the roofline). Say what the camera is NOT doing: no cuts.
- End with one short line of ambient sound that evolves with the spaces.
- Keep the architecture, materials and lighting of each reference exactly as shown. No
  redesign, no new rooms, no text.
- Slow, steady, steadicam feel. Natural life: people at walking pace, foliage, light.
- Output ONLY the prompt. No preamble, no lists, no quotes. Under 160 words."""


BASE_BRIEF = """You are an art director for architectural visualization marketing imagery.
You will be shown one raw render from D5 Render. Write a single image-editing prompt
that turns it into a marketing-grade image a top-tier archviz studio would publish.

Hard rules for the prompt you write:
- The building's geometry, massing, facade design, materials, window layout, camera
  position, lens, and composition must remain EXACTLY as rendered. Say this explicitly
  at the start of the prompt. Nothing about the architecture may be redesigned.
- Nothing may be added, removed, or swapped: no new fixtures, furniture, shelving,
  bars, artwork, panelling, or people that are not already there, and no window,
  opening, or wall treatment replaced with a different feature. Existing elements
  become more real; they do not become different elements.
- Keep the render's own white balance and colour temperature. Do not warm, tint,
  or push the image toward orange or yellow. Lighting can gain depth, contrast,
  falloff, and realism without changing its colour.
- Only improve: lighting quality and depth, sky and atmosphere where present,
  material realism (reflections, roughness, weathering, fabric and wood texture),
  vegetation quality, existing people made photoreal and naturally posed, contrast,
  depth of field realism, edge realism, and removal of obvious CG artifacts.
- Be specific to THIS image. Name what is actually weak in it and what to do about it.
- Choose one coherent mood that suits the project type and view.
- No text, logos, watermarks, or captions.
- Output ONLY the prompt. No preamble, no bullet points, no quotes, no markdown.
  Under 180 words."""
