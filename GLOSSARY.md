# Glossary

| Term | Meaning |
| --- | --- |
| slug | Lowercase ASCII identifier made of `[a-z0-9]` runs joined by single hyphens, no leading/trailing hyphen |
| word | A maximal run of letters/digits; inner apostrophes (`'`, `’`) and hyphens keep it one word (`don't`, `well-known`) |
| truncate | Shorten text to a character limit that *includes* the suffix, cutting at a word boundary when possible |
| suffix | String appended by `truncate` to signal cut text; default `…` (one character) |
| initials | First letter of each word, uppercased, accents kept |
| reading time | Minutes to read a text: `ceil(word_count / wpm)`, 0 for text without words |
| sentence | Segment of text ending in a run of `.`, `!` or `?` (a run counts as one end); the unterminated tail counts too. A segment counts only if it contains a word |
