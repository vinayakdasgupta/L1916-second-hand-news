"""STEP 3b of the protocol: decide what each candidate is, and code its source and distance.

Reads out/find.jsonl (from s3a_find.py). For every candidate the model sees the whole letter with
the passage marked, and is asked two questions.

  A. What is the writer doing in this passage?
        second_hand      tells the addressee something the writer says came from a source other
                         than the writer and the addressee  -> IN
        first_hand       tells what the writer saw, did, heard with their own ears, or felt -> out
        from_addressee   the information came from the addressee (a reply)            -> out
        not_information  a request, question, wish, thanks, plan, opinion, greeting,
                         or the writer's own letters and enclosures                  -> out
  B. (only for second_hand) Who does the writer say it came from, and, ONLY if the passage says
     that source got it from someone else, who that was, and so on (at most three).

Distance is the writer's own account, counted from B:
        1, 2, 3            a chain of people (or papers), each link stated in the passage
        institutional      a single paper, notice or official statement
        unknown, 1+        "they say", "I hear", "it is said": a source the writer does not give

A chain is one line of transmission. Two letters, two visitors, two papers that each told the
writer something are PARALLEL sources, not a chain; the first is coded and the others are noted
in the 'check' column. A later link whose words are not in the passage is cut, and the chain
with it, so hops never exceed what the passage itself shows.

Every answer carries words copied from the passage. Words that cannot be found are flagged in the
'check' column; they do not remove the row. Rows that are out stay in coded.jsonl with their
reason, so you can see what was excluded.

Usage (from the Letters1916 folder):
    py pipeline/s3b_code.py rising_letters.jsonl
Writes out/coded.jsonl (read by the next step) and out/coded.csv (to look at).
Progress is saved after every candidate: run the same command again to resume.
"""
import argparse
import http.client
import re
import sys
import time
from pathlib import Path

import common as C
import cues

SYSTEM = """You will be given one letter from 1915 or 1916 with one passage marked, and ONE question about that passage.

- Decide from the words of the MARKED PASSAGE. The rest of the letter is there only to tell you who "he", "she" or "they" is. Do not use your own knowledge of history to supply what the letter does not say.
- The WRITER wrote the letter. The ADDRESSEE is the person it was written to; "you" means the addressee. [word?] marks an uncertain reading and [...] a gap in the transcription. Spelling is the writer's own. The passage may begin or end mid-sentence.
- Words you are asked to copy must be copied exactly as they are written in the passage. They are checked against the letter.
- If the passage does not show it and you would have to guess, choose the answer that claims less: fewer sources, a shorter chain, "unnamed" rather than a name."""

Q_A = """Question: In the marked passage, what is the writer doing?

Choose one category:
- second_hand: the writer passes on something and says it came from a source other than the writer and other than the addressee: a person who told or wrote to the writer, a letter or telegram received, a newspaper, an official notice, or "they say" / "I hear" / "it is said".
- first_hand: the writer tells what they themselves saw, did, felt or experienced, with no one else given as the source. Hearing a sound with one's own ears (guns, a bang, people singing, a sermon) is first_hand, even though the writer says "we heard".
- from_addressee: the information came from the addressee: the writer is replying to the addressee's letter, repeating what the addressee told them, or supposing what the addressee already knows ("I suppose you heard").
- not_information: the passage does not report anything to the addressee: a request, a question to the addressee, a wish, thanks, a plan, an opinion or argument, a greeting, a message to be passed on to someone else, or the writer's own letters, enclosures and telegrams sent or to be sent.

Rules of thumb:
- A passage that names people is not second_hand because of the names. It is second_hand only if the writer says one of them is where the information came from.
- "I wrote to X", "I have told X", "tell X that", "I enclose my letter / leaflets / petition" are the writer's own doing: not_information (or first_hand), never second_hand.
- A source that is said NOT to have given anything ("neither wrote", "has not written", "they know nothing of it", "he did not succeed in seeing you") is not a source.
- If a passage mixes the writer's own experience with something someone else told them, choose second_hand when the part someone else said is information for the addressee.

Then give evidence: the exact words of the MARKED PASSAGE that show your choice. For second_hand also give source_words: the exact words of the MARKED PASSAGE that name or describe where the information came from."""

Q_B = """Question: Who does the writer say this information came from?

List the sources in order, nearest the writer first:
1. The source the WRITER got it from. There is exactly one. If the passage gives no one ("they say", "I hear", "it is said", "it is rumoured"), write "unnamed" and stop.
2. Only if the passage SAYS that the first source got it from someone else ("X told me that Y said", "X wrote that he had a letter from Y", "a letter from X enclosing one from Y", "as I learned from his comrades"), the person or paper the first source got it from.
3. Likewise for a third, only if the passage says so.

Stop as soon as the passage stops saying who told whom. At most three.

Do NOT list as a source:
- the person or thing the news is ABOUT (the man who was shot, the officer who did it, the soldiers who sang, the friend who has gone to Stafford, the people who signed a petition);
- someone the writer is asked to tell, or will tell, or sends love to;
- another separate source of the same or different news ("a letter from X and a letter from Y", "X says ... and Y says the same", "X told me ... Y also came up"). Only the first is the chain; mark the others as separate (see "relation");
- a name that occurs only elsewhere in the letter, not in the marked passage (use the rest of the letter only to say who "he" or "she" is);
- the writer or the addressee as the FIRST source;
- a place, an institution the news is about, or a person who merely posted a newspaper to the writer (the newspaper is the source; the sender is not a link);
- a source the passage says gave nothing ("neither wrote", "has not written", "know nothing of it").

For each source give:
- who: the name or description as the writer gives it ("Kate", "the priest", "my sister", "a man", "the Irish Times"). If the passage says only "she" or "he", use the rest of the letter to say who. If the writer gives no one, write "unnamed".
- kind: person_named (a proper name), person_described (a description: "a man", "the post mistress", "my nephew", "a friend who is a clerk"), unnamed ("they", "people", "I hear"), paper (a newspaper, cutting or printed item) or official (a notice, order, government or military statement).
- medium: letter, telegram, spoken, print, official or unspecified. Someone in the same house or the same prison as the writer speaks; letters come from people elsewhere.
- relation: "first" for the first source; "got_it_from_previous" when the passage says the previous source got it from this one; "separate" for another, independent source mentioned in the passage (listed only so it can be noted, not as a link in the chain).
- words: the exact words of the MARKED PASSAGE that show this source. For a second or third source the words must show the relay ("told me that ... said", "had a letter from", "heard from")."""

SCHEMA_A = {"type": "object",
            "properties": {"category": {"type": "string",
                                        "enum": ["second_hand", "first_hand", "from_addressee", "not_information"]},
                           "evidence": {"type": "string"},
                           "source_words": {"type": "string"}},
            "required": ["category", "evidence", "source_words"]}
SCHEMA_B = {"type": "object",
            "properties": {"sources": {"type": "array", "maxItems": 4,
                                       "items": {"type": "object",
                                                 "properties": {
                                                     "who": {"type": "string"},
                                                     "kind": {"type": "string", "enum": [
                                                         "person_named", "person_described", "unnamed", "paper", "official"]},
                                                     "medium": {"type": "string", "enum": [
                                                         "letter", "telegram", "spoken", "print", "official", "unspecified"]},
                                                     "relation": {"type": "string", "enum": [
                                                         "first", "got_it_from_previous", "separate"]},
                                                     "words": {"type": "string"}},
                                                 "required": ["who", "kind", "medium", "relation", "words"]}}},
            "required": ["sources"]}

COLUMNS = ["id", "letter", "date", "sender", "recipient", "status", "found_by", "marker", "passage", "after",
           "category", "evidence", "source_first", "source_kind", "source_role", "medium", "chain", "hops",
           "distance", "check", "model"]


SELF = {"the writer", "writer", "i", "me", "myself", "we", "us", "the author", "the speaker"}
UNNAMED = {"they", "people", "someone", "somebody", "everyone", "everybody", "one", "some one", "nobody",
           "no one", "folk", "folks", "unnamed", "unknown", "others", "some people", "a rumour", "rumour",
           "rumours", "reports", "some source or other"}

# A second or third hop needs a relay verb in the passage: without one the writer has not said who
# told whom, and the extra hop is the model's invention (the commonest error in the first run).
RELAY = re.compile(r"\b(told|tells|tell me|said|says|say|writes|wrote|written|heard from|hear from|hears from|"
                   r"learned from|learnt from|letter from|note from|card from|wire from|cable from|enclos\w*|"
                   r"informed|according to|report\w*|states?|stated|mentioned|from what|I understand from|"
                   r"I am told|I was told|I hear|I heard|I learn\w*)\b", re.I)


def distance_of(sources):
    """The writer's stated distance from the list of sources."""
    n = len(sources)
    if n == 0:
        return "unknown, 1+"
    if n == 1 and sources[0]["kind"] in ("paper", "official"):
        return "institutional"
    if n == 1 and sources[0]["kind"] == "unnamed":
        return "unknown, 1+"
    return str(n)


def role_for(src):
    if src["kind"] == "paper":
        return "press"
    if src["kind"] == "official":
        return "official"
    if src["kind"] == "unnamed":
        return "unnamed"
    return cues.role_of(src["who"] + " " + src["words"])


def key_of(who):
    return re.sub(r"[^a-z ]", "", who.lower()).strip()


def code_one(model, ctx, r, cand):
    """-> a dict of the coded fields. Raises on a stalled model."""
    passage, text = cand["passage"], r["text"]
    addressee = C.who_is(r["recipient"])
    user = (f"{C.header(r)}THE LETTER:\n{C.letter_for_prompt(text, passage)}\n\n"
            f"THE MARKED PASSAGE (somewhere in the letter): \"{C.clip(passage, 120)}\"\n\n")
    out, checks = {}, []

    a = C.call(model, SYSTEM, user + Q_A, SCHEMA_A, ctx) or {}
    cat = a.get("category")
    ev = (a.get("evidence") or "").strip()
    out["category"], out["evidence"] = cat or "unclear", C.clip(ev, 25)
    if cat != "second_hand":
        out["status"] = f"out:{cat or 'no answer'}"
        out["check"] = "" if cat else "the model gave no usable answer"
        return out
    if ev and not C.found_in(ev, passage):
        checks.append("evidence not in the passage" if not C.found_in(ev, text) else "evidence elsewhere in the letter")
    src_words = (a.get("source_words") or "").strip()
    if src_words and not C.found_in(src_words, passage):
        checks.append("source words not in the passage")

    b = C.call(model, SYSTEM, user + Q_B, SCHEMA_B, ctx) or {}
    sources, separate = [], []
    for s in (b.get("sources") or []):
        who, words = (s.get("who") or "").strip(), (s.get("words") or "").strip()
        if not who and not words:
            continue
        who_key = key_of(who)
        if who_key in SELF:
            checks.append("a source that is the writer was removed")
            continue                                   # the writer is not a source of their own information
        kind = s.get("kind", "unnamed")
        if who_key in UNNAMED:
            kind = "unnamed"                           # "they", "someone": the writer gives no one
        src = {"who": who or "unnamed", "kind": kind, "medium": s.get("medium", "unspecified"),
               "relation": s.get("relation", "first"), "words": words}
        if src["relation"] == "separate" and sources:
            separate.append(src["who"])                # a parallel source: noted, not a link
            continue
        if sources and src["who"] == sources[-1]["who"]:
            checks.append(f"duplicate source dropped ({src['who']})")
            continue
        if sources and (not words or not C.found_in(words, passage)):
            # A later hop the passage does not show: cut it and everything after it.
            checks.append(f"chain cut at hop {len(sources) + 1}: words not in the passage ({src['who']})")
            break
        if sources and kind == "unnamed" and sources[-1]["kind"] == "unnamed":
            checks.append("chain cut: unnamed after unnamed")
            break
        if words and not C.found_in(words, passage):
            checks.append(f"source words not in the passage ({src['who']})")
        sources.append(src)
        if len(sources) == 3:
            break
    if len(sources) > 1 and not RELAY.search(passage):
        checks.append(f"chain cut to 1: no relay verb in the passage ({sources[1]['who']})")
        sources = sources[:1]
    if sources and cues.is_addressee(sources[0]["who"], addressee):
        out["status"] = "out:from_addressee"
        out["check"] = "first source is the addressee"
        return out
    if not sources:
        checks.append("no source listed")
    if separate:
        checks.append("separate sources also named: " + ", ".join(dict.fromkeys(separate)))
    out["status"] = "in"
    out["hops"] = len(sources)
    out["distance"] = distance_of(sources)
    if sources:
        out["source_first"] = sources[0]["who"]
        out["source_kind"] = sources[0]["kind"]
        out["source_role"] = role_for(sources[0])
        out["medium"] = sources[0]["medium"]
    out["chain"] = " <- ".join(["writer"] + [f"{s['who']} ({s['medium']})" for s in sources])
    out["check"] = "; ".join(dict.fromkeys(checks))
    return out


def main():
    ap = argparse.ArgumentParser(description="Step 3b: code the candidates")
    ap.add_argument("letters", nargs="+")
    C.common_args(ap)
    a = ap.parse_args()

    out = Path(a.out_dir)
    find_f, rows_f, log_f = out / "find.jsonl", out / "coded.jsonl", out / "coded_log.txt"
    if not find_f.exists():
        sys.exit(f"{find_f} not found: run s3a_find.py first.")
    if a.restart:
        for f in (rows_f, log_f, out / "coded.csv"):
            f.unlink(missing_ok=True)
    done = {r["id"] for r in C.read_jsonl(rows_f)}

    C.check_ollama()
    by_id = C.letters_by_id(a.letters)
    cands = [c for c in C.read_jsonl(find_f)]
    todo = [c for c in cands if c["id"] not in done]
    print(f"{len(cands)} candidates; {len(cands) - len(todo)} already coded; {len(todo)} to go")
    if a.limit:
        todo = todo[:a.limit]
        print(f"This run: {len(todo)} candidates")
    t_all = time.time()

    for i, c in enumerate(todo, 1):
        t0, C.CALLS[0] = time.time(), 0
        r = by_id.get(c["letter"])
        if r is None:
            continue
        try:
            fields = code_one(a.model, a.ctx, r, c)
        except (TimeoutError, OSError) as e:
            C.log(log_f, f"[{i}/{len(todo)}] {c['id']}  STALLED ({e}) - skipped, retried on the next run")
            continue
        rec = {k: c.get(k, "") for k in ("id", "letter", "date", "sender", "recipient", "found_by", "marker",
                                         "passage", "after", "idx", "last")}
        rec.update(fields)
        rec["passage"] = C.clip(rec["passage"], 120)
        rec["model"] = a.model
        C.append_jsonl(rows_f, rec)
        C.log(log_f, f"[{i}/{len(todo)}] {c['id']}  {time.time() - t0:.0f}s  calls: {C.CALLS[0]}  "
                     f"{rec['status']}  {rec.get('distance', '')}")

    rows = C.read_jsonl(rows_f)
    C.write_csv(out / "coded.csv", rows, COLUMNS)
    kept = sum(1 for x in rows if x["status"] == "in")
    n = max(1, len(todo))
    print(f"\nRun done in {(time.time() - t_all) / 60:.1f} min ({(time.time() - t_all) / n:.0f} s per candidate). "
          f"{len(rows)} coded: {kept} in, {len(rows) - kept} out.")
    left = len(cands) - len({x['id'] for x in rows})
    if left:
        print(f"{left} candidates still to do: run the same command again.")


if __name__ == "__main__":
    try:
        main()
    except C.CONNECTION_ERRORS + (http.client.HTTPException,) as e:
        sys.exit(f"Lost contact with Ollama: {e}. Start it and run the same command to resume.")
