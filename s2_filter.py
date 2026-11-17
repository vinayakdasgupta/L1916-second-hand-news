"""STEP 2 of the protocol: keep personal letters, set the rest aside.

One model call per letter. The model sees who wrote to whom and the first and last words of the
letter, and chooses one group:

    personal         one private person writing to another (family, friends, neighbours),
                     including a prisoner's letter to family or friends
    to_authority     a private person or group writing to an authority (petition, complaint,
                     application, enquiry)
    official         a document issued by or for an authority (order, notice, circular, form,
                     summons, permit, receipt, an official's reply, a copy of a government document)
    organisational   the business of a political or military organisation, committee or firm
    unclear          cannot tell

Kept for the next step: personal + unclear (so that the filter loses no letters on a doubt).
No person reviews this: each choice carries the words that justify it, and a choice whose words
are not found in the letter is marked in the 'check' column, not changed.

Usage (from the Letters1916 folder):
    py pipeline/s2_filter.py rising_letters.jsonl
Writes out/filter.csv (every letter, its group, the words) and out/personal_ids.txt (the letters kept).
Progress is saved after every letter: run the same command again to resume.
"""
import argparse
import http.client
import sys
import time
from pathlib import Path

import common as C

GROUPS = ["personal", "to_authority", "official", "organisational", "unclear"]
KEEP = {"personal", "unclear"}

SYSTEM = """You will be given the beginning and the end of one document from 1915 or 1916, and who it is from and to, and ONE question about it.

- Decide from the words of the document itself.
- group: choose one of the groups the question lists.
- evidence: copy the few words from the document that show your choice, exactly as written there (a salutation, a letterhead, a phrase of instruction). These words are checked against the document. If you choose "unclear", leave evidence empty.
- If the document does not show it and you would have to guess, choose "unclear"."""

QUESTION = """Question: What kind of document is this?

Choose one group:
- personal: a letter from one private person to another, about their own affairs or news: family, friends, neighbours, acquaintances. A prisoner's or soldier's letter to family or friends is personal, even though it was read by a censor. A letter between two people who happen to be officers of an organisation is still personal if it is written in their own voice about private matters.
- to_authority: a letter from a private person or group to an authority or office: the government, army, police, a prison, a court, a bishop's or ministry's office. A petition, a complaint, an application, an appeal, an enquiry about a prisoner.
- official: a document issued by or for an authority or an organisation as an instrument: an order, a notice, a circular, a printed proclamation, a form filled in, a summons, a permit, a receipt, a mobilisation order, an official's reply to a private person, a copy of a government document.
- organisational: the business of a political or military organisation, a committee or a firm, written by its officers in that capacity: Volunteer headquarters correspondence, committee minutes or letters, instructions between officers, business letters.
- unclear: you cannot tell from what is shown.

Look for: how the writer addresses the reader (a private name and affection, or a title and formal terms), whether there is a letterhead or an office, whether the text gives instructions or announces something, and whose voice it is in."""

SCHEMA = {"type": "object",
          "properties": {"group": {"type": "string", "enum": GROUPS},
                         "evidence": {"type": "string"}},
          "required": ["group", "evidence"]}

COLUMNS = ["letter", "date", "sender", "recipient", "words", "group", "kept", "evidence", "check", "model"]


def shown(text, head=170, tail=70):
    words = text.split()
    if len(words) <= head + tail:
        return " ".join(words)
    return " ".join(words[:head]) + "\n[... middle of the document not shown ...]\n" + " ".join(words[-tail:])


def write_outputs(rows_path, out_dir):
    rows = C.read_jsonl(rows_path)
    C.write_csv(out_dir / "filter.csv", rows, COLUMNS)
    kept = [r["letter"] for r in rows if r["group"] in KEEP]
    (out_dir / "personal_ids.txt").write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    counts = {g: sum(1 for r in rows if r["group"] == g) for g in GROUPS}
    return counts, len(kept)


def main():
    ap = argparse.ArgumentParser(description="Step 2: keep personal letters")
    ap.add_argument("letters", nargs="+")
    ap.add_argument("--only", help="a file of letter ids to run")
    C.common_args(ap)
    a = ap.parse_args()

    out = Path(a.out_dir)
    out.mkdir(exist_ok=True)
    rows_f, log_f = out / "filter.jsonl", out / "filter_log.txt"
    if a.restart:
        for f in (rows_f, log_f, out / "filter.csv", out / "personal_ids.txt"):
            f.unlink(missing_ok=True)
    done = {r["letter"] for r in C.read_jsonl(rows_f)}

    C.check_ollama()
    letters = C.load_letters(a.letters, only=a.only)
    todo = [r for r in letters if r["id"] not in done]
    print(f"{len(letters)} letters; {len(letters) - len(todo)} already sorted; {len(todo)} to go")
    if a.limit:
        todo = todo[:a.limit]
        print(f"This run: {len(todo)} letters")
    t_all = time.time()

    for i, r in enumerate(todo, 1):
        t0 = time.time()
        text = r["text"]
        user = (f"DOCUMENT {r['id']}\nDate: {r.get('date') or 'undated'}\n"
                f"From: {C.who_is(r['sender'])}\nTo: {C.who_is(r['recipient'])}\n\n"
                f"THE DOCUMENT (beginning and end):\n{shown(text)}\n\n{QUESTION}")
        try:
            ans = C.call(a.model, SYSTEM, user, SCHEMA, a.ctx) or {}
        except (TimeoutError, OSError) as e:
            C.log(log_f, f"[{i}/{len(todo)}] {r['id']}  STALLED ({e}) - skipped, retried on the next run")
            continue
        group = ans.get("group", "unclear")
        ev = (ans.get("evidence") or "").strip()
        check = ""
        if group not in ("unclear",) and not C.found_in(ev, text):
            check = "evidence not found in the letter"
        if group not in GROUPS:
            group = "unclear"
        C.append_jsonl(rows_f, {"letter": r["id"], "date": (r.get("date") or "")[:10],
                                "sender": C.who_is(r["sender"]), "recipient": C.who_is(r["recipient"]),
                                "words": len(text.split()), "group": group, "kept": group in KEEP,
                                "evidence": C.clip(ev, 25), "check": check, "model": a.model})
        C.log(log_f, f"[{i}/{len(todo)}] {r['id']} {r.get('date')}  {time.time() - t0:.0f}s  {group}")

    counts, kept = write_outputs(rows_f, out)
    n = max(1, len(todo))
    print(f"\nRun done in {(time.time() - t_all) / 60:.1f} min ({(time.time() - t_all) / n:.0f} s per letter).")
    for g, c in counts.items():
        print(f"  {g:15} {c}")
    print(f"Kept for the next step: {kept}  ->  {out / 'personal_ids.txt'}")
    left = len(letters) - len({r['letter'] for r in C.read_jsonl(rows_f)})
    if left:
        print(f"{left} letters still to sort: run the same command again.")


if __name__ == "__main__":
    try:
        main()
    except C.CONNECTION_ERRORS + (http.client.HTTPException,) as e:
        sys.exit(f"Lost contact with Ollama: {e}. Start it and run the same command to resume.")
