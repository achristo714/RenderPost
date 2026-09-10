## Render Post v1.8.5

One fix. The running spend in the header could undercount when several images finished at the same moment: three workers each read the total, added their own image, and wrote it back, so one addition was lost. Writes to the project settings file are now serialized. Past totals are not corrected; new ones are right.

Nothing else changed since 1.8.4.
