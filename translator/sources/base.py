"""What every source site's scraper shares: the browser identity, the "stop, we're blocked" signal,
and lines that aggregator sites inject into any novel they copy."""
import re

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

# Watermark lines injected by aggregators, and the fan translator's end-of-chapter notes.
JUNK = re.compile(
    r"n[o0]v[e3]l\W{0,2}b[i1]n|novellunar|freewebnovel|lightnovelpub|lightnovelworld"
    r"|\bwww\.|\.(com|net|org|me)\b"
    r"|review this novel|bonus chapters? on reaching|^happy reading\W*$"
    r"|ko-?fi|patreon|bonus chapters? thanks to|advanced? (chapters|tiers)"
    r"|thank you (very much )?for visiting our website",
    re.I,
)


class Blocked(Exception):
    pass
