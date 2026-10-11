"""Watermarks a source site plants mid-sentence that survived into some translations, e.g. novelight's
"◆ Nоvеlіgһt ◆ (Only on Nоvеlіgһt)", "[# Nоvеlight #]", "⊛ Nоvеlιght ⊛ (Đọc toàn bộ câu chuyện)": any
symbol pair around the name (often spelled with Cyrillic/Greek look-alikes), then the short note after it.
The English is cleaned when scraped (sources/novelight.py); this catches what reached the Vietnamese."""
import re

NOVELIGHT = r"N[oоο][vѵν][eеε][lӏ][iіıι][gɡ][hһ][tт]"
STAMP = re.compile(rf"\s*\[?\s*[^\w\s\[\]()]{{1,2}}\s*{NOVELIGHT}\s*[^\w\s\[\]()]{{1,2}}(?:\s*\])?(?:\s*\([^()]{{0,40}}\))?", re.I)


def strip(text):
    return STAMP.sub("", text)
