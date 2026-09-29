## Render Post v1.9.1

Fix: turning on the per-image character checkbox right before pressing Rewrite, Enhance, or Angles
could occasionally send the job before the checkbox's own save had landed, silently generating
without the character (about 1 in 5 tries). Those requests now carry the checkbox's current state
directly, so there's nothing left to race.

Added a small scroll-to-top button that appears once you've scrolled down the page.

Nothing else changed since 1.9.0.
