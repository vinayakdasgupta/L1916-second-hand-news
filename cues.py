"""The cue rules: find sentences where the writer marks something as coming from elsewhere.

Rules only, no model. Used by s3a_find.py. Taken from rising_reach.py, with two changes:
  * only 'received' cues are kept (missing, asking and restricted are outside this study);
  * every candidate carries its sentence positions, so later steps can find the sentences after it.
"""
import re

REPORT_VERBS = (r"says?|said|writes?|wrote|written|writing|tells?|told|informs?|informed|informing|"
                r"states?|stated|reports?|reported|mentions?|mentioned|assures?|assured|adds?|added|"
                r"hears?|heard|learns?|learned|learnt|understands?|understood|gathers?|gathered|"
                r"advises?|advised|notifies|notified|wires?|wired|cables?|cabled|announces?|announced|"
                r"declares?|declared|claims?|claimed|admits?|admitted")
# when the writer is the subject, these are the writer RECEIVING; the others are the writer telling
WRITER_RECEIVES = re.compile(r"^(hear|heard|learn|learned|learnt|understand|understood|gather|gathered)$", re.I)
WRITER_CONNECT = re.compile(r"\b(am|was|are|were) told\b|\b(is|are|was|were) (said|reported|understood)\b", re.I)
STOP = {"that", "and", "but", "who", "which", "when", "as", "if", "for", "because", "so", "then",
        "while", "where", "also", "now", "just", "yesterday", "today", "again", "still", "has",
        "have", "had", "be", "been", "not", "never", "always", "often", "already", "only", "even",
        "from", "what", "sure", "am", "is", "are", "was", "were", "sorry", "glad", "afraid", "told",
        "see", "know", "think", "believe", "hope", "fear", "suppose", "dear", "with", "by", "of", "in"}
MODAL = {"can", "could", "will", "would", "shall", "should", "must", "to", "please", "do", "let",
         "may", "might", "kindly", "pray", "cant", "cannot", "wont", "couldnt", "wouldnt", "dont",
         "didnt", "shouldnt", "wasnt", "isnt", "never"}
PRONOUNS = {"he", "she", "they", "it"}
FIRST = {"i", "we"}

PRINT = re.compile(r"\b(by the papers?|in the papers?|the papers? (say|says|state|states|report|reports|have)|"
                   r"newspapers?|the Independent|Freeman'?s? Journal|the Freeman|Irish Times|Evening Mail|"
                   r"Evening Herald|Daily Mail|Daily Sketch|Irish Independent|Sinn Fein Rebellion Handbook|"
                   r"proclamation|poster|placard|manifesto|handbill|pamphlet|I (saw|read) in)\b", re.I)
OFFICIAL = re.compile(r"\b(notice|order from|communiqu[eé]|bulletin|enclosed (document|plan|copy)|"
                      r"copy of the (original )?plan|permit|official|War Office|Home Office|Dublin Castle|"
                      r"the authorities|military authorities|informs me|has informed me|I am directed|"
                      r"I am to say|I am instructed)\b", re.I)
LETTER_FROM = re.compile(r"\b(?:a |the |your |her |his |their |my )?(?:letter|card|postcard|note|wire|telegram|cable|message)s?"
                         r"(?: from| of)? ?((?:Fr\.? |Father |Mrs\.? |Mr\.? |Miss |Dr\.? )?[A-Z][\w']+(?: [A-Z][\w']+)?)?", re.I)
HAD_LETTER = re.compile(r"\b(I|we) (have |had )?(just )?(had|got|received|have had|have got|have received|get|got) "
                        r"(a |an |your |another )?(letter|card|postcard|note|wire|telegram|cable|message)s?"
                        r"( from ((?:Fr\.? |Father |Mrs\.? |Mr\.? |Miss |Dr\.? )?[A-Z][\w']+(?: [A-Z][\w']+)?))?", re.I)
YOUR_LETTER = re.compile(r"\byour (letter|note|card|wire|telegram)\b|\byou (say|write|wrote|tell|told|mention|mentioned|"
                         r"state|stated|inform|informed|said|add|added)\b", re.I)
WORD_CAME = re.compile(r"\b(word|news|information|tidings|the report|the rumou?r)( has| had)? (come|came|reached|"
                       r"arrived|got)\b|\bit is (said|reported|understood|rumou?red)\b|\b(they|people) say\b|"
                       r"\brumou?rs?\b|\b(I|we) (have )?(just )?(heard|hear|learned|learnt|learn|am told|are told|"
                       r"was told|were told|gather|understand)\b|\bI am (sorry|grieved|glad|pained) to (hear|learn)\b", re.I)
HEARSAY = re.compile(r"\b(they say|it is said|people say|rumou?rs?|it is rumou?red)\b", re.I)

MISSING = re.compile(r"\b(no (news|word|letter|line|information|tidings|reply|answer)|not (had|heard|received|got) "
                     r"(a |any |one )?(word|line|letter|news|reply|answer|thing)?|have not heard|had no (news|word)|"
                     r"without (news|word)|hearing nothing|nothing (has been )?heard|cannot (find out|learn|tell where)|"
                     r"do not know where|don'?t know where|(anxious|longing|waiting) (to hear|for news|for word)|"
                     r"not (been )?told|never (told|heard))\b", re.I)
RESTRICT = re.compile(r"\b(censor\w*|opened|read before|before it goes|not allowed to|not permitted|forbidden|"
                      r"may not (write|say)|one letter|only one letter|cannot say more|can say no more|"
                      r"non[- ]?political|nothing political|not at liberty|must not write|are not let|"
                      r"letters? (are|is) (read|stopped|opened)|no politics)\b", re.I)
ASK = re.compile(r"\b((let|have) (me|us) know|write (and|&) tell|tell me|send me (word|news|a line)|any (news|word)|"
                 r"have you heard|do you know|what (has )?become of|find out|enquir\w+|inquir\w+|collect any (gossip|news)|"
                 r"keep me (informed|posted)|let us know|are you aware)\b", re.I)

FAMILY = r"mother|father|mam|mamma|mother|brother|sister|husband|wife|son|daughter|cousin|uncle|aunt|nephew|niece|parents|fiancee?"
ROLES = [("family", re.compile(rf"\b({FAMILY})\b", re.I)),
         ("clergy", re.compile(r"\b(Fr\.?|Father|Rev\.?|priest|curate|bishop|canon|chaplain|Sister|nun|minister)\b")),
         ("legal", re.compile(r"\b(solicitor|barrister|counsel|lawyer|judge|magistrate|court)\b", re.I)),
         ("official", re.compile(r"\b(Governor|Commandant|Major|Captain|Capt\.?|Colonel|General|Sergeant|police|"
                                 r"constable|War Office|Home Office|Castle|Secretary|authorit\w+|warder|censor)\b", re.I)),
         ("friend", re.compile(r"\b(friend|neighbour|comrade|colleague)\b", re.I))]



def role_of(text):
    t = text.lower()
    if "official" in t or "enclosed document" in t:
        return "official"
    if "print" in t:
        return "press"
    if "addressee" in t:
        return "correspondent"
    for name, rx in ROLES:
        if rx.search(text):
            return name
    return "unknown"


def join_wrapped(text):
    """A transcribed line that carries on into the next one is one sentence: join a line to the
    next when the next starts with a lower-case letter and this one does not end a sentence."""
    lines = [l.strip() for l in text.split("\n")]
    out = []
    for l in lines:
        if out and l and out[-1] and l[0].islower() and not out[-1].endswith((".", "!", "?")):
            out[-1] = out[-1] + " " + l
        else:
            out.append(l)
    return "\n".join(out)


# A full stop after one of these does not end a sentence: titles, initials ("Sir P. Smith", "the G.P.O."),
# and the usual abbreviations of the period. A new capital after them is the same sentence going on.
ABBREV = {"mr", "mrs", "messrs", "dr", "st", "fr", "rev", "col", "lt", "capt", "gen", "maj", "sgt", "pte", "cpl",
          "prof", "hon", "rt", "sr", "jr", "co", "bros", "no", "nos", "vol", "inst", "ult", "prox", "esq",
          "ald", "cr", "msgr", "mt", "ft", "p", "pp", "viz", "i.e", "e.g", "cf", "etc", "mme", "mlle"}
_BOUNDARY = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\[(])')


def _abbreviation_before(text, pos):
    """True when the word that ends just before pos (a full stop follows it) is an abbreviation or initials."""
    m = re.search(r"(\S+)$", text[:pos])
    if not m:
        return False
    w = m.group(1).strip("\"'([")
    if not w.endswith("."):
        return False
    core = w.rstrip(".")
    if re.fullmatch(r"(?:[A-Za-z]\.)*[A-Za-z]", core) and (core.isupper() or "." in core):
        return True                                   # an initial or initials: K.  G.P.O.  R.C.
    return core.lower() in ABBREV


def split_sentences(block):
    out, start = [], 0
    for m in _BOUNDARY.finditer(block):
        if _abbreviation_before(block, m.start()):
            continue
        out.append(block[start:m.start()])
        start = m.end()
    out.append(block[start:])
    return out


def sentences(text):
    """Split into sentences; long run-ons are cut at the comma nearest the middle."""
    out = []
    for block in re.split(r"\n+", join_wrapped(text)):
        block = block.strip()
        if not block:
            continue
        for s in split_sentences(block):
            s = s.strip()
            while len(s.split()) > 50:
                words, mid = s.split(), len(s.split()) // 2
                cut, best = None, 10 ** 9
                pos = 0
                for i, w in enumerate(words):
                    pos += 1
                    if w.endswith((",", ";")) or w in ("&", "and"):
                        if abs(i - mid) < best:
                            cut, best = i, abs(i - mid)
                if cut is None:
                    cut = 39                      # no punctuation to cut at: cut at 40 words
                out.append(" ".join(words[:cut + 1]).strip())
                s = " ".join(words[cut + 1:]).strip()
            out.append(s)
    # drop debris: letterheads, dates, one-word fragments, all-capital lines
    keep = []
    for s in out:
        w = s.split()
        if len(w) < 4 or s.isupper() or not re.search(r"[a-z]{3}", s):
            continue
        keep.append(s)
    return keep

def subject_before(words, i):
    """The few words before the verb at index i, up to a stop word or punctuation."""
    sub = []
    for j in range(i - 1, max(-1, i - 5), -1):
        w = words[j]
        bare = re.sub(r"[^\w.'-]", "", w)
        if not bare or bare.lower() in STOP or w.endswith((",", ";", ":", ".")) and j != i - 1:
            break
        sub.insert(0, bare)
        if w.endswith((",", ";", ":")):
            break
    return " ".join(sub)


def frames(sentence, state):
    """Reception frames in one sentence, in order: dicts source, medium, how."""
    words = sentence.split()
    hits = []
    low = sentence.lower()

    for m in HAD_LETTER.finditer(sentence):
        src = m.group(8) or "unnamed"
        hits.append({"pos": m.start(), "source": src, "medium": m.group(6).lower().replace("postcard", "card"),
                     "how": m.group(0)})
    for m in re.finditer(r"\b(I|we) (beg|have the honou?r|am directed|am instructed|am desired) to (enclose|forward|send|transmit)\b|"
                         r"\b(I|we) (enclose|forward|send you|transmit)\b|\bthe enclosed\b|\benclosed (is|are|herewith)\b", sentence, re.I):
        hits.append({"pos": m.start(), "source": "enclosed document", "medium": "official", "how": m.group(0)})
    for m in YOUR_LETTER.finditer(sentence):
        hits.append({"pos": m.start(), "source": "addressee", "medium": "letter", "how": m.group(0)})
    for m in re.finditer(r"\b(?:letter|card|postcard|wire|telegram|cable|message)s? from ("
                         r"(?:Fr\.? |Father |Mrs\.? |Mr\.? |Miss |Dr\.? )?[A-Z][\w']+(?: [A-Z][\w']+)?)", sentence):
        if not any(abs(h["pos"] - m.start()) < 40 and h["source"] == m.group(1) for h in hits):
            hits.append({"pos": m.start(), "source": m.group(1), "medium": "letter", "how": m.group(0)})
    # reporting verbs with a subject
    for i, w in enumerate(words):
        bare = re.sub(r"[^\w']", "", w).lower()
        if not re.fullmatch(REPORT_VERBS, bare):
            continue
        prev = re.sub(r"[^\w]", "", words[i - 1]).lower() if i else ""
        if i == 0 or prev in MODAL:
            continue                                   # imperative or "can write"
        subj = subject_before(words, i)
        s_low = subj.lower()
        if not subj or s_low in ("is", "are", "was", "were"):
            continue
        nxt = " ".join(words[i + 1:i + 4]).lower()
        if s_low.split()[0] in FIRST or s_low.endswith((" i", " we")):
            if not WRITER_RECEIVES.match(bare):
                continue                               # the writer telling, not receiving
            hits.append({"pos": sentence.find(w), "source": "unnamed", "medium": "heard", "how": f"{subj} {w}"})
            continue
        if s_low == "you":
            hits.append({"pos": sentence.find(w), "source": "addressee", "medium": "letter", "how": f"{subj} {w}"})
            continue
        if not (nxt.startswith(("that", "me", "us", "him", "her", "them", "how", "in his", "in her", "in a", "in the", "to me")) or
                re.match(r"^(he|she|they|it|the|a|an|there|this|these|all|some|many|few|no|[a-z]+ (is|are|was|were|has|have|had))", nxt)):
            continue
        med = "letter" if re.match(r"writ|wrote|wire|cable", bare) else "spoken" if re.match(r"say|said|tell|told|mention|inform|assure|add|state", bare) else "heard"
        hits.append({"pos": sentence.find(w), "source": subj, "medium": med, "how": f"{subj} {w}"})
    for m in WRITER_CONNECT.finditer(sentence):
        hits.append({"pos": m.start(), "source": "unnamed", "medium": "heard", "how": m.group(0)})
    if PRINT.search(sentence):
        m = PRINT.search(sentence)
        hits.append({"pos": m.start(), "source": "print", "medium": "print", "how": m.group(0)})
    if OFFICIAL.search(sentence) and not any(h["medium"] == "print" for h in hits):
        m = OFFICIAL.search(sentence)
        hits.append({"pos": m.start(), "source": "official", "medium": "official", "how": m.group(0)})
    if HEARSAY.search(sentence):
        m = HEARSAY.search(sentence)
        hits.append({"pos": m.start(), "source": "unnamed", "medium": "rumour", "how": m.group(0)})
    elif WORD_CAME.search(sentence) and not hits:
        m = WORD_CAME.search(sentence)
        hits.append({"pos": m.start(), "source": "unnamed", "medium": "heard", "how": m.group(0)})

    hits.sort(key=lambda h: h["pos"])
    # pronouns point back to the last named source
    for h in hits:
        if h["source"].lower() in PRONOUNS:
            h["pronoun"] = h["source"]
            h["source"] = state.get("last") or h["source"]
            if state.get("last"):
                h["medium"] = state.get("last_medium", h["medium"])     # "she said" in a letter: still the letter
        elif h["source"] not in ("unnamed", "print", "official", "addressee"):
            state["last"], state["last_medium"] = h["source"], h["medium"]
    if any(h["source"] == "enclosed document" for h in hits):
        hits = [h for h in hits if h["source"] != "official"]
    # one writer-side "I hear" is dropped when a named person follows it in the same sentence
    if any(h["source"] not in ("unnamed",) for h in hits):
        hits = [h for h in hits if not (h["source"] == "unnamed" and h["medium"] == "heard")]
    seen, out = set(), []
    for h in hits:
        key = (h["source"].lower(), h["medium"])
        if h["source"].lower() in ("unnamed",) or key not in seen:
            out.append(h)
        seen.add(key)
    # same person by letter and by speech in one sentence is one hop
    uniq, names = [], set()
    for h in out:
        k = h["source"].lower()
        if k in names and k not in ("unnamed",):
            continue
        names.add(k)
        uniq.append(h)
    return uniq


TITLES = {"fr", "father", "mrs", "mr", "miss", "dr", "the", "my", "your", "our", "his", "her", "of", "and"}


def name_tokens(name):
    return {w for w in re.findall(r"[a-z']{3,}", (name or "").lower()) if w not in TITLES}


def is_addressee(source, addressee):
    """True when the source of a cue is the person being written to."""
    if source.lower() == "addressee":
        return True
    a = name_tokens(addressee)
    return bool(a) and bool(a & name_tokens(source))


def _has_other_cue(s):
    return bool(MISSING.search(s) or RESTRICT.search(s) or ASK.search(s))


def find_candidates(text, addressee=""):
    """Rules only. Returns (sentences, candidates).

    A candidate is a sentence in which the writer marks something as coming from a source
    other than themselves and other than the addressee, with the sentences that carry on
    the same relayed passage. Each candidate records its sentence positions (idx .. last)."""
    sents = sentences(text)
    state, out, used = {}, [], set()
    last_doc = -99
    for i, s in enumerate(sents):
        if i in used:
            continue
        if s.rstrip().endswith("?"):
            continue                                              # a question is a request, not a report
        fr = [h for h in frames(s, state) if not is_addressee(h["source"], addressee)]
        if not fr:
            continue
        if fr[0]["source"] == "enclosed document":
            if i - last_doc < 16 and last_doc >= 0:
                continue                                          # the same document again
            last_doc = i
        extra, extra_idx = [], []
        doc = fr[0]["source"] == "enclosed document"
        for j in range(i + 1, min(len(sents), i + (13 if doc else 9))):
            nxt = sents[j]
            if frames(nxt, dict(state)):
                break                                             # a new marker starts a new candidate
            if not doc and re.match(r"(?i)^(I|we|my)\b", nxt):
                break                                             # the writer speaks again: the relay is over
            asks = nxt.rstrip().endswith("?") or re.match(r"(?i)^(please|kindly|could you|do you|if you)", nxt)
            if doc or (not _has_other_cue(nxt) and not asks):
                extra.append(nxt)
                extra_idx.append(j)
                used.add(j)
        chain = " <- ".join(["writer"] + [f"{h['source']} ({h['medium']})" for h in fr])
        out.append({"idx": i, "last": max([i] + extra_idx), "quote": s, "also": extra,
                    "rule_chain": chain, "rule_medium": fr[0]["medium"],
                    "marker": "; ".join(h["how"] for h in fr),
                    "rule_role": role_of(" ".join(h["source"] for h in fr)),
                    "unresolved": next((h["pronoun"] for h in fr if "pronoun" in h and
                                        h["source"].lower() in PRONOUNS), "")})
    return sents, out
