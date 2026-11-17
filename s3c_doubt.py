"""STEP 3c of the protocol: does the writer openly doubt the information?

Reads the rows that s3b_code.py marked 'in'. For each one the model sees the passage and the two
sentences that follow it (where "I can hardly credit it" would sit), and chooses:

    none      the writer does not express doubt (saying "I hear" or "they say" is not doubt)
    writer    the writer says, in their own words, that they doubt it, don't believe it, can't
              vouch for it, think it may be untrue, or calls it a rumour or unconfirmed
    reported  the writer reports that someone else doubts it

A 'writer' or 'reported' answer must quote the doubting words, and the words must be in the passage
or the sentences after it. A claim without a verifiable quote is NOT counted: the row is marked
'none' and the claim is kept in the 'check' column for reference.

Usage (from the Letters1916 folder):
    py pipeline/s3c_doubt.py
Writes out/doubt.jsonl (read by the next step) and out/doubt.csv (to look at).
Progress is saved after every row: run the same command again to resume.
"""
import argparse
import http.client
import sys
import time
from pathlib import Path

import common as C

SYSTEM = """You will be given a passage from a 1915 or 1916 letter, the sentences that follow it, and ONE question.

- Decide from the words given. Do not use your own knowledge of history.
- The WRITER wrote the letter. The ADDRESSEE is the person it was written to.
- Words you are asked to copy must be copied exactly as written. They are checked.
- Saying "I hear", "they say" or "I am told" is NOT doubt on its own.
- If the words do not show doubt and you would have to guess, answer none."""

QUESTION = """Question: Does anyone openly doubt the information in the passage?

Choose one:
- none: no doubt is expressed. The writer simply reports it, or just says where it came from.
- writer: the writer says in their own words that they doubt it, do not believe it, cannot vouch for it, think it may be untrue or exaggerated, or calls it a rumour or unconfirmed.
- reported: the writer reports that someone else doubts it.

The doubt has to be about the information in the passage, in the passage itself or in the sentences that follow it. If you choose writer or reported, copy the exact words that show the doubt into "words"; otherwise leave "words" empty."""

SCHEMA = {"type": "object",
          "properties": {"doubt": {"type": "string", "enum": ["none", "writer", "reported"]},
                         "words": {"type": "string"}},
          "required": ["doubt", "words"]}

COLUMNS = ["id", "letter", "date", "sender", "recipient", "found_by", "marker", "passage", "after",
           "category", "source_first", "source_kind", "source_role", "medium", "chain", "hops", "distance",
           "doubt", "doubt_words", "check", "model"]


def judge_doubt(model, ctx, r, row):
    """-> (doubt, words, check)."""
    passage, after = row["passage"], row.get("after", "")
    user = (f"{C.header(r)}THE PASSAGE:\n\"{passage}\"\n\n"
            f"THE SENTENCES THAT FOLLOW IT:\n{after or '(none: the passage ends the letter or the paragraph)'}\n\n{QUESTION}")
    a = C.call(model, SYSTEM, user, SCHEMA, ctx) or {}
    doubt, words = a.get("doubt", "none"), (a.get("words") or "").strip()
    if doubt not in ("writer", "reported"):
        return "none", "", ""
    if words and C.found_in(words, passage + " " + after):
        return doubt, C.clip(words, 25), ""
    return "none", "", f"doubt claimed ({doubt}) but the words were not found: {C.clip(words, 15)}"


def main():
    ap = argparse.ArgumentParser(description="Step 3c: explicit doubt")
    ap.add_argument("letters", nargs="+")
    C.common_args(ap)
    a = ap.parse_args()

    out = Path(a.out_dir)
    coded_f, rows_f, log_f = out / "coded.jsonl", out / "doubt.jsonl", out / "doubt_log.txt"
    if not coded_f.exists():
        sys.exit(f"{coded_f} not found: run s3b_code.py first.")
    if a.restart:
        for f in (rows_f, log_f, out / "doubt.csv"):
            f.unlink(missing_ok=True)
    done = {r["id"] for r in C.read_jsonl(rows_f)}

    C.check_ollama()
    by_id = C.letters_by_id(a.letters)
    rows_in = [r for r in C.read_jsonl(coded_f) if r["status"] == "in"]
    todo = [r for r in rows_in if r["id"] not in done]
    print(f"{len(rows_in)} rows to judge; {len(rows_in) - len(todo)} already done; {len(todo)} to go")
    if a.limit:
        todo = todo[:a.limit]
    t_all = time.time()

    for i, row in enumerate(todo, 1):
        t0 = time.time()
        r = by_id.get(row["letter"])
        if r is None:
            continue
        try:
            doubt, words, check = judge_doubt(a.model, a.ctx, r, row)
        except (TimeoutError, OSError) as e:
            C.log(log_f, f"[{i}/{len(todo)}] {row['id']}  STALLED ({e}) - skipped, retried on the next run")
            continue
        rec = dict(row)
        rec.update({"doubt": doubt, "doubt_words": words,
                    "check": "; ".join(x for x in (row.get("check", ""), check) if x), "model": a.model})
        C.append_jsonl(rows_f, rec)
        C.log(log_f, f"[{i}/{len(todo)}] {row['id']}  {time.time() - t0:.0f}s  doubt: {doubt}")

    rows = C.read_jsonl(rows_f)
    C.write_csv(out / "doubt.csv", rows, COLUMNS)
    n = max(1, len(todo))
    print(f"\nRun done in {(time.time() - t_all) / 60:.1f} min ({(time.time() - t_all) / n:.0f} s per row). "
          f"{len(rows)} judged: writer {sum(1 for x in rows if x['doubt'] == 'writer')}, "
          f"reported {sum(1 for x in rows if x['doubt'] == 'reported')}.")


if __name__ == "__main__":
    try:
        main()
    except C.CONNECTION_ERRORS + (http.client.HTTPException,) as e:
        sys.exit(f"Lost contact with Ollama: {e}. Start it and run the same command to resume.")
