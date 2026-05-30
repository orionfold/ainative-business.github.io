"""Client-side workaround for vLLM's byte-level BPE detokenization leak.

vLLM 0.21 + DeepSeek-R1-0528-Qwen3-8B's LlamaTokenizerFast returns text where
control bytes are still in their GPT-2 byte-level BPE encoded form
(`Ġ` for space, `Ċ` for newline, `ĉ` for tab, etc.). This module provides a
post-decode fixer so the rest of the corpus pipeline can treat outputs as
normal UTF-8.
"""


def _bytes_to_unicode() -> dict[int, int]:
    bs = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("¡"), ord("¬") + 1))
        + list(range(ord("®"), ord("ÿ") + 1))
    )
    cs = bs[:]
    n = 0
    for b in range(2**8):
        if b not in bs:
            bs.append(b)
            cs.append(2**8 + n)
            n += 1
    return dict(zip(bs, cs))


_B2U = _bytes_to_unicode()
_U2B = {chr(c): b for b, c in _B2U.items()}


def fix_bpe(s: str) -> str:
    """Reverse GPT-2 byte-level BPE encoding on a string."""
    out = bytearray()
    for c in s:
        b = _U2B.get(c)
        if b is not None:
            out.append(b)
        else:
            out.extend(c.encode("utf-8"))
    return out.decode("utf-8", errors="replace")


if __name__ == "__main__":
    sample = "<think>ĊFirst,ĠtheĠuserĠhasĠgivenĠmeĠexcerptsĠfromĠtheĠMPEPĠandĠasked"
    print("INPUT :", sample)
    print("OUTPUT:", fix_bpe(sample))
