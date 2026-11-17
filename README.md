# Second-hand news: code and data

Code and data for a pilot study of how letter writers report second-hand information. The study measures how many links separate the writer from the information, and whether expressed doubt varies with that distance. The letters are the 519 transcriptions tagged "Easter Rising Ireland 1916" in [Letters 1916-1923](https://letters1916.ie), dated 10 November 1915 to 4 May 1917.

A local language model (qwen3:8b, run through Ollama at temperature 0) makes every model decision. The Python scripts do the rest. 

## Files

| File | Step | What it does |
|---|---|---|
| `s2_filter.py` | 2 | The model classifies each letter as personal or not (for example a formal letter to an authority). Only personal letters go on. |
| `cues.py` | 3 | Rules (no model) that mark phrases where the writer attributes something to a source: "X writes that", "I hear", "I am told", "a letter from X", "the papers say". Imported by `s3a_find.py`. |
| `s3a_find.py` | 3a | Finds candidate passages with the cues, and the model proposes further candidates. Each candidate keeps two sentences of context before and after. |
| `s3b_code.py` | 3b | With the whole letter in view, the model labels each candidate (second-hand, own experience, from the addressee, or not information). For second-hand passages it lists up to three sources from the writer outward, with the first source's medium. |
| `s3c_doubt.py` | 3c | The model flags doubt: the writer's own, or doubt the writer reports in someone else, with the words that show it. |
| `links.csv` | | The coded attributions, after hand correction. See below. |

## Running it

Steps run in order, from the folder that holds the letters. Each script saves progress after every letter or candidate, so rerunning the same command resumes.

```
ollama pull qwen3:8b
py s2_filter.py <letters.jsonl>
py s3a_find.py <letters.jsonl> --only <personal_ids.txt>
py s3b_code.py <letters.jsonl>
py s3c_doubt.py <coded.jsonl>
```

`<letters.jsonl>` is one letter per line (id, date, sender, recipient, text), made from the TEI files of the archive. The scripts also import a helper module, `common.py`, [add to the repo].

## Placement in the rings

Each attribution is placed by the first rule that applies:

1. Hearsay, if the first source is unnamed or absent.
2. Outer band, if the first source's medium is print or official. These are not counted as links.
3. Otherwise by the number of links: one link, or two or more.

A passage with several parallel sources is split into one row per source, so the unit is the attribution.

## `links.csv`

One row per candidate passage or attribution.

| Column | Meaning |
|---|---|
| `id`, `letter` | passage id (`letter#n`) and letter id |
| `date`, `sender`, `recipient` | from the letter |
| `status` | `in` (kept) or `out:<reason>` |
| `found_by`, `marker` | `rules` or `model`, and the words that flagged it |
| `passage`, `after` | the passage and the following context |
| `category` | second_hand, first_hand, from_addressee or not_information |
| `source_first`, `source_kind`, `source_role` | first source, whether named or described, and its role |
| `medium` | spoken, letter, print, official or not stated |
| `chain`, `hops` | the chain of sources from the writer, and its length |
| `distance` | distance as coded by the model |
| `doubt`, `doubt_words` | doubt flag and the words that show it |
| `check` | notes from the hand check |
| `model` | `qwen3:8b`, or `qwen3:8b; hand-checked` |

Every attribution kept in the study was checked by hand: about 40 of 329 (12%) were corrected, fixing 78 errors. The 215 dropped candidates were not checked.

## Data and licence

The letters belong to the Letters 1916-1923 project (Maynooth University). The passages in `links.csv` are quoted from their transcriptions. 
