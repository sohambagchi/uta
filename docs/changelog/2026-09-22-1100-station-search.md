# Station search matches words, not a substring

- Every query word must start a word of the station, in any order: `3500 south 700 west` finds `700 W / 3500 S`.
- Abbreviations are equal to their full word (S/South, St/Street, Jct/Junction, …).
- Searches every member stop's full name (incl. parentheticals) and stop codes.
- Ranked by whole-word matches, then name prefix, then station size; up to 12 results.
