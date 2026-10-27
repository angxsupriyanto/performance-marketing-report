"""Dark mode for every page the viewer serves. The page code keeps writing its colours as hex; this module turns the known ones into CSS
variables on the way out (so the light palette stays exactly as it was) and adds the dark palette, the saved choice and the switch.
Nothing here touches the report files themselves, so the PDF and the print view stay light."""
from __future__ import annotations

import re

# name: (light, dark). Light values are the colours the pages already use. Dark pairs are checked at 4.5:1 for text, 3:1 for control borders.
PALETTE = {
    "bg": ("#f4f7fb", "#191919"), "surface": ("#ffffff", "#1f1f1f"), "text": ("#17283e", "#ececec"), "text2": ("#394d65", "#cbcbcb"),
    "muted": ("#607188", "#9d9d9d"), "border": ("#dfe7f0", "#333333"), "ctrl": ("#6f8199", "#808080"), "link": ("#2159a9", "#8bb8f2"),
    "primary": ("#2159a9", "#2f6fc4"), "focus": ("#2159a9", "#8bb8f2"), "good-bg": ("#e6f5ed", "#183326"), "good": ("#087450", "#7fd9ac"),
    "bad-bg": ("#fcecec", "#3a2020"), "bad": ("#ac3d3d", "#f4a9a9"), "neu-bg": ("#eef2f7", "#2b2b2b"), "accent-bg": ("#edf4ff", "#232d3b"),
}
# hex -> variable, for the colours whose role does not depend on where they are written
FIXED = {"#17283e": "text", "#394d65": "text2", "#607188": "muted", "#6f8199": "ctrl", "#dfe7f0": "border", "#e3e9f1": "border", "#4a5b70": "text2",
         "#ac3d3d": "bad", "#087450": "good", "#fcecec": "bad-bg", "#e6f5ed": "good-bg", "#eef2f7": "neu-bg", "#edf4ff": "accent-bg", "#f4f7fb": "bg"}
KNOWN = re.compile(r"#(?:" + "|".join(h[1:] for h in [*FIXED, "#2159a9", "#ffffff"]) + r"|fff)\b", re.I)
BACKGROUND = re.compile(r"background(?:-color)?\s*:\s*[^;{}\"']*$", re.I)
OUTLINE = re.compile(r"outline(?:-color)?\s*:\s*[^;{}\"']*$", re.I)
TEXT_COLOUR = re.compile(r"(?<![a-z-])color\s*:\s*$", re.I)


def _role(hex_value: str, before: str) -> str | None:
    h = hex_value.lower()
    if h in FIXED:
        return FIXED[h]
    tail = re.split(r"[;{\"']", before)[-1]
    if h == "#2159a9":
        return "primary" if BACKGROUND.search(tail) else "focus" if OUTLINE.search(tail) else "link"
    return None if TEXT_COLOUR.search(tail) else "surface"  # white text stays white (it sits on the blue button); every other white is a surface


def to_variables(html: str) -> str:
    def swap(m: re.Match) -> str:
        role = _role("#ffffff" if m.group(0).lower() == "#fff" else m.group(0), html[max(0, m.start() - 60):m.start()])
        return m.group(0) if role is None else f"var(--c-{role})"
    return KNOWN.sub(swap, html)


def _declarations(index: int) -> str:
    return ";".join(f"--c-{name}:{pair[index]}" for name, pair in PALETTE.items())


def stylesheet() -> str:
    return (f":root{{{_declarations(0)};color-scheme:light}}"
            f"@media (prefers-color-scheme:dark){{:root:not([data-theme=\"light\"]){{{_declarations(1)};color-scheme:dark}}}}"
            f":root[data-theme=\"dark\"]{{{_declarations(1)};color-scheme:dark}}"
            f"@media print{{:root:root:root{{{_declarations(0)};color-scheme:light}}}}"
            ".vw-seg{display:inline-flex;border:1px solid var(--c-ctrl);border-radius:6px;overflow:hidden}"
            ".vw-menu .vw-seg button{min-height:36px;padding:0 9px;background:none;color:var(--c-text2);font:500 13px Inter,Arial,sans-serif}"
            ".vw-menu .vw-seg button+button{border-left:1px solid var(--c-ctrl)}"
            ".vw-menu .vw-seg button[aria-pressed=true]{background:var(--c-primary);color:#ffffff}")


EARLY = "(function(){try{var t=localStorage.getItem('vw-theme');if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t);}catch(e){}})();"
SWITCH = """(function(){
  var root=document.documentElement,btns=[].slice.call(document.querySelectorAll('[data-theme-set]'));
  function saved(){try{var t=localStorage.getItem('vw-theme');return t==='dark'||t==='light'?t:'auto';}catch(e){return 'auto';}}
  function show(){var t=saved();btns.forEach(function(b){b.setAttribute('aria-pressed',b.dataset.themeSet===t?'true':'false');});}
  btns.forEach(function(b){b.addEventListener('click',function(){var t=b.dataset.themeSet;
    try{if(t==='auto')localStorage.removeItem('vw-theme');else localStorage.setItem('vw-theme',t);}catch(e){}
    if(t==='auto')root.removeAttribute('data-theme');else root.setAttribute('data-theme',t);show();});});
  show();
})();"""


def switch_html() -> str:
    labels = (("light", "Terang"), ("dark", "Gelap"), ("auto", "Otomatis"))
    return ('<div class="vw-seg" role="group" aria-label="Tampilan">' + "".join(f'<button type="button" data-theme-set="{key}" aria-pressed="false">{text}</button>' for key, text in labels) + "</div>")


def apply(html: str, nonce: str = "") -> str:
    """The page with its colours as variables, the dark palette in its head and the saved choice applied before the first paint."""
    attr = f' nonce="{nonce}"' if nonce else ""
    body = to_variables(html)
    head_bits = f'<meta name="color-scheme" content="light dark"><style{attr}>{stylesheet()}</style><script{attr}>{EARLY}</script>'
    tail = f"<script{attr}>{SWITCH}</script>"
    body = body.replace("</head>", head_bits + "</head>", 1) if "</head>" in body else head_bits + body
    return body.replace("</body>", tail + "</body>", 1) if "</body>" in body else body + tail
