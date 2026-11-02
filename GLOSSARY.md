# Glossary

| Term | Meaning |
| --- | --- |
| slug | Lowercase ASCII identifier made of `[a-z0-9]` runs joined by single hyphens, no leading/trailing hyphen |
| word | A maximal run of letters/digits; inner apostrophes (`'`, `’`) and hyphens keep it one word (`don't`, `well-known`) |
| truncate | Shorten text to a character limit that *includes* the suffix, cutting at a word boundary when possible |
| suffix | String appended by `truncate` to signal cut text; default `…` (one character) |
| initials | First letter of each word, uppercased, accents kept |
| reading time | Minutes to read a text: `ceil(word_count / wpm)`, 0 for text without words |
| normalize | Unicode NFKC form of a text (canonical composition plus compatibility mappings, e.g. `ﬁ` -> `fi`); case, accents, whitespace and punctuation are untouched |
| sentence | Segment of text ending in a run of `.`, `!` or `?` (a run counts as one end); the unterminated tail counts too. A segment counts only if it contains a word |
| char count | Number of code points in a text for which `str.isspace()` is false (punctuation and digits count; combining marks count individually) |
| unique words | Number of distinct words in a text after `casefold()`, using the same definition of *word* |
