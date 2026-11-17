"""STEP 3a of the protocol: find the passages where the writer marks information as second-hand.

Two passes over each personal letter (the letters listed in out/personal_ids.txt):

  1. RULES (no model). Words that mark a source: "Kate writes that", "I hear", "I read in the
     paper", "a letter from X", "they say", "I am told", an enclosed copy. A cue whose source is
     the addressee ("you say", "in your letter") is dropped: the reader already has that.
     The sentences that carry on the same relayed passage are kept with it, up to the next marker,
     a question, or the writer speaking again in the first person ("I saw...").
  2. MODEL, over what the rules left out. The model reads the letter as numbered sentences, the
     rules' passages marked [found], and lists any other sentence in which the writer marks a
     source other than themselves and the addressee. Each one must give the exact marker words,
     and those words must be in that sentence, or the item is dropped (logged in find_dropped.jsonl).

This step finds candidates only. Whether a candidate really is second-hand information, how many
hands it passed through, and whether the writer doubts it are decided by the next steps.

Usage (from the Letters1916 folder):
    py pipeline/s3a_find.py rising_letters.jsonl --only out/personal_ids.txt
    --rules-only   no model at all: write what the rules find (to inspect them)
Writes out/find.jsonl (read by the next step) and out/find.csv (to look at).
Progress is saved after every letter: run the same command again to resume.
"""
import argparse
import http.client
import re
import sys
import time
from pathlib import Path

import common as C
import cues

SYSTEM = """You will be given one letter from 1915 or 1916 as numbered sentences, and ONE question about it.

- Decide from the words of the letter. Do not use your own knowledge of history to supply what the letter does not say.
- The WRITER wrote the letter. The ADDRESSEE is the person it was written to; "you" means the addressee. [word?] marks an uncertain reading and [...] a gap in the transcription. Spelling is the writer's own.
- For every item, copy the marker words exactly as they are written in that sentence. These words are checked against the sentence, and an item whose words are not there is thrown away.
- If the letter does not show it and you would have to guess, leave the item out."""

QUESTION = """Question: Which sentences, other than those marked [found], tell the addressee something that the writer says came from someone or something else, other than the writer and other than the addressee?

Include a sentence only if the writer's own words mark where the information came from, such as "Kate writes that", "I heard", "I read in the paper", "they say", "according to", "the priest told me", "a letter from X says", "I am told".
Do not include:
- what the writer saw, did, felt or thinks themselves;
- a statement with no source marked;
- requests, wishes, thanks, plans, greetings;
- anything that came from the addressee ("you say", "in your letter", "as you told me").

For each sentence give n (its number) and marker (the exact words of that sentence that mark the source). If there are none, give an empty list."""

SCHEMA = {"type": "object",
          "properties": {"items": {"type": "array",
                                   "items": {"type": "object",
                                             "properties": {"n": {"type": "integer"}, "marker": {"type": "string"}},
                                             "required": ["n", "marker"]}}},
          "required": ["items"]}

COLUMNS = ["id", "letter", "date", "sender", "recipient", "found_by", "marker", "passage", "rule_chain",
           "rule_medium", "rule_role"]

# A marker the model proposes must contain a word that can name a source. This list is much
# wider than the rules' cues (it is only a floor: a marker with none of these words is not a marker).
SOURCE_WORD = re.compile(
    r"\b(told|tell|tells|telling|said|say|says|saying|writes?|wrote|written|writing|heard|hear|hears|"
    r"read|reads|letters?|wires?|telegrams?|cables?|cards?|notes?|papers?|newspapers?|news|information|"
    r"informed|informs?|according|reported|reports?|word|message|learn\w*|understand|understood|"
    r"gather\w*|rumou?rs?|mention\w*|assur\w*|given|asked|advis\w*|stated|states?|announce\w*|notice|"
    r"proclamation|bulletin|communiqu\w*)\b", re.I)
MAX_MARKER_WORDS = 12


def numbered_chunks(sents, covered, max_words=600):
    """The sentences as '[n] text' lines, in chunks of about max_words words."""
    chunks, cur, words = [], [], 0
    for n, s in enumerate(sents):
        line = f"[{n}]{' [found]' if n in covered else ''} {s}"
        w = len(s.split())
        if cur and words + w > max_words:
            chunks.append(cur)
            cur, words = [], 0
        cur.append(line)
        words += w
    if cur:
        chunks.append(cur)
    return chunks


def model_pass(model, ctx, r, sents, covered, addressee):
    """Sentences the rules left out in which the model sees a marked outside source.
    Returns (items, dropped)."""
    items, dropped = [], []
    for chunk in numbered_chunks(sents, covered):
        user = f"{C.header(r)}THE LETTER, as numbered sentences:\n" + "\n".join(chunk) + "\n\n" + QUESTION
        ans = C.call(model, SYSTEM, user, SCHEMA, ctx) or {}
        for it in ans.get("items") or []:
            try:
                n, marker = int(it.get("n")), (it.get("marker") or "").strip()
            except (TypeError, ValueError):
                continue
            why = ""
            if not (0 <= n < len(sents)):
                why = "no such sentence"
            elif n in covered:
                why = "already found by the rules"
            elif not C.found_in(marker, sents[n]) or len(marker.split()) < 1:
                why = "marker words not in that sentence"
            elif not SOURCE_WORD.search(marker):
                why = "marker has no word that can name a source"
            elif len(marker.split()) > MAX_MARKER_WORDS or (
                    len(sents[n].split()) > 6 and len(marker) >= 0.8 * len(sents[n])):
                why = "marker is the whole sentence, not a marker"
            elif sents[n].rstrip().endswith("?"):
                why = "a question"
            elif cues.is_addressee(marker, addressee):
                why = "source is the addressee"
            rec = {"letter": r["id"], "n": n, "marker": marker, "sentence": C.clip(sents[n], 40) if 0 <= n < len(sents) else ""}
            if why:
                dropped.append({**rec, "why": why})
            elif not any(i["n"] == n for i in items):
                items.append(rec)
    return items, dropped


def build_rows(r, sents, rule_cands, model_items):
    base = {"letter": r["id"], "date": (r.get("date") or "")[:10],
            "sender": C.who_is(r["sender"]), "recipient": C.who_is(r["recipient"])}
    rows = []
    for c in rule_cands:
        rows.append({**base, "id": f"{r['id']}#{c['idx']}", "idx": c["idx"], "last": c["last"],
                     "found_by": "rules", "marker": c["marker"], "quote": c["quote"],
                     "passage": " ".join([c["quote"]] + c["also"]), "rule_chain": c["rule_chain"],
                     "rule_medium": c["rule_medium"], "rule_role": c["rule_role"],
                     "unresolved": c["unresolved"]})
    for it in model_items:
        rows.append({**base, "id": f"{r['id']}#{it['n']}", "idx": it["n"], "last": it["n"],
                     "found_by": "model", "marker": it["marker"], "quote": sents[it["n"]],
                     "passage": sents[it["n"]], "rule_chain": "", "rule_medium": "", "rule_role": "",
                     "unresolved": ""})
    rows.sort(key=lambda x: x["idx"])
    for k, x in enumerate(rows):
        # the sentences after the passage, up to two, but never into the next passage:
        # doubt in the next passage belongs to that passage, not this one
        stop = rows[k + 1]["idx"] if k + 1 < len(rows) else len(sents)
        x["after"] = " ".join(sents[x["last"] + 1:min(x["last"] + 3, stop)])
    return rows


def main():
    ap = argparse.ArgumentParser(description="Step 3a: find marked second-hand passages")
    ap.add_argument("letters", nargs="+")
    ap.add_argument("--only", help="a file of letter ids to run (out/personal_ids.txt)")
    ap.add_argument("--min-words", type=int, default=0)
    ap.add_argument("--rules-only", action="store_true", help="no model: write what the rules find")
    C.common_args(ap)
    a = ap.parse_args()

    out = Path(a.out_dir)
    out.mkdir(exist_ok=True)
    rows_f, done_f, log_f, drop_f = out / "find.jsonl", out / "find_done.txt", out / "find_log.txt", out / "find_dropped.jsonl"
    if a.restart:
        for f in (rows_f, done_f, log_f, drop_f, out / "find.csv"):
            f.unlink(missing_ok=True)
    done = set(done_f.read_text().split()) if done_f.exists() else set()

    if not a.rules_only:
        C.check_ollama()
    letters = C.load_letters(a.letters, only=a.only, min_words=a.min_words)
    todo = [r for r in letters if r["id"] not in done]
    print(f"{len(letters)} letters; {len(letters) - len(todo)} already done; {len(todo)} to go")
    if a.limit:
        todo = todo[:a.limit]
        print(f"This run: {len(todo)} letters")
    t_all = time.time()
    tag = a.model + ("|rules-only" if a.rules_only else "")

    for i, r in enumerate(todo, 1):
        t0, C.CALLS[0] = time.time(), 0
        addressee = C.who_is(r["recipient"])
        sents, rule_cands = cues.find_candidates(r["text"], addressee)
        covered = {k for c in rule_cands for k in range(c["idx"], c["last"] + 1)}
        items, dropped = [], []
        if not a.rules_only and len(sents) >= 2:
            try:
                items, dropped = model_pass(a.model, a.ctx, r, sents, covered, addressee)
            except (TimeoutError, OSError) as e:
                C.log(log_f, f"[{i}/{len(todo)}] {r['id']}  STALLED ({e}) - skipped, retried on the next run")
                continue
        rows = build_rows(r, sents, rule_cands, items)
        for x in rows:
            x["model"] = tag
            C.append_jsonl(rows_f, x)
        for d in dropped:
            C.append_jsonl(drop_f, d)
        with open(done_f, "a") as f:
            f.write(r["id"] + "\n")
        C.log(log_f, f"[{i}/{len(todo)}] {r['id']} {r.get('date')}  {time.time() - t0:.0f}s  "
                     f"rules: {len(rule_cands)}  model: {len(items)}  dropped: {len(dropped)}  calls: {C.CALLS[0]}")

    allrows = C.read_jsonl(rows_f)
    C.write_csv(out / "find.csv", allrows, COLUMNS)
    n = max(1, len(todo))
    print(f"\nRun done in {(time.time() - t_all) / 60:.1f} min ({(time.time() - t_all) / n:.0f} s per letter). "
          f"{len(allrows)} candidates in all ({sum(1 for x in allrows if x['found_by'] == 'rules')} by rules, "
          f"{sum(1 for x in allrows if x['found_by'] == 'model')} by the model).")
    left = len(letters) - len(set(done_f.read_text().split()) if done_f.exists() else set())
    if left:
        print(f"{left} letters still to do: run the same command again.")


if __name__ == "__main__":
    try:
        main()
    except C.CONNECTION_ERRORS + (http.client.HTTPException,) as e:
        sys.exit(f"Lost contact with Ollama: {e}. Start it and run the same command to resume.")
