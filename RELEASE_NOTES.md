## Render Post v1.13.2

A batch of fixes. Most of them stop paid work from being charged twice or lost.

**Fix: double and triple charges.** If the connection dropped while RenderPost was waiting for
a result, it used to submit the whole job again, and you paid again. That affected fal and also
Higgsfield and Nim.video. A long Nim video that hit the waiting limit could be submitted three
times. Now a retry keeps waiting on the job that's already running instead.

**Fix: Cancel on Higgsfield and Nim.video** now cancels cleanly. It used to retry for about 12
seconds and then show a failure with an empty "Higgsfield: " error.

**Fix: downloads from Higgsfield and Nim.video** now retry a dropped connection, the same as fal
does since v1.13.1. If one of several variations fails to download, the ones that did download
now still show up.

**Fix: clips and reels on Windows failed** when the folder path had certain accented, Greek or
Cyrillic letters (for example "Á"). The paid video downloaded, then the clip showed as failed.

**Fix: Make clips used the wrong model.** If you changed the Video model after writing motion
prompts, the clips could fail, or run on a different model than the card and the price showed.
Clips now use the model you have selected when you press Make, which is also what the price was
based on.

**Fix: multi-shot Kling clips ran longer than you chose** (a 5s clip with 3 shots went out as
9s and cost more than the estimate). Shots now fit inside the length you pick.

**Fix: the running spend total under-counted some videos** (for example Kling 4K and Veo Ultra
were counted at their cheapest tier). It also now counts images you paid for even if a download
fails.

**Fix: two clips finishing at the same moment** could save to the same file, losing one.

**Fix: deleting a version could overwrite an earlier deleted one** in enhanced/trash. Trash now
keeps both.

**Fix: renders with square brackets in the name**, like "View [A].png", lost their version
history when you reopened the folder.
