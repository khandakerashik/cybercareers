"""Text mining helpers: Bangla/English dates, deadlines, experience and location.

Bangladeshi circulars commonly write deadlines as "Last date of application:
20 November 2026", "Apply before 20-11-2026" or in Bangla, e.g.
"আবেদনের শেষ তারিখ: ২০ নভেম্বর ২০২৬". These helpers turn those into ISO dates
so expiry/freshness logic works for PDF, RSS, email and search sources too.
"""
from __future__ import annotations

import re
from datetime import date, datetime

BN_DIGITS = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')
MONTHS = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
    'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'sept': 9,
    'september': 9, 'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
    # Bangla (Gregorian month names as used in circulars)
    'জানুয়ারি': 1, 'জানুয়ারী': 1, 'জানুয়ারি': 1, 'ফেব্রুয়ারি': 2, 'ফেব্রুয়ারী': 2, 'ফেব্রুয়ারি': 2,
    'মার্চ': 3, 'এপ্রিল': 4, 'মে': 5, 'জুন': 6, 'জুলাই': 7, 'আগস্ট': 8, 'অগাস্ট': 8,
    'সেপ্টেম্বর': 9, 'অক্টোবর': 10, 'নভেম্বর': 11, 'ডিসেম্বর': 12,
}
_MONTH_RX = '|'.join(sorted((re.escape(m) for m in MONTHS), key=len, reverse=True))
WORD_NUMBERS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8,
                'nine': 9, 'ten': 10, 'twelve': 12, 'fifteen': 15}


def bn_to_ascii_digits(text: str) -> str:
    return str(text or '').translate(BN_DIGITS)


def _mk(y: int, m: int, d: int) -> str:
    try:
        if y < 100:
            y += 2000
        if not 2000 <= y <= 2100:
            return ''
        return date(y, m, d).isoformat()
    except ValueError:
        return ''


def parse_date(raw: object) -> str:
    """Best-effort ISO date (YYYY-MM-DD) from many formats; '' if unknown."""
    if raw is None or raw == '':
        return ''
    text = bn_to_ascii_digits(str(raw)).strip()
    if not text:
        return ''
    if re.fullmatch(r'\d{10,13}(?:\.\d+)?', text):  # unix seconds / millis
        try:
            n = float(text)
            n = n / 1000 if n > 1e11 else n
            return datetime.utcfromtimestamp(n).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ''
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).date().isoformat()
    except ValueError:
        pass
    low = text.lower()
    m = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', low)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r'\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b', low)
    if m:  # Bangladesh uses day-first numeric dates.
        return _mk(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?[-\s,]*(' + _MONTH_RX + r')\.?[-\s,]*(\d{2,4})', low)
    if m:
        return _mk(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r'(' + _MONTH_RX + r')\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})', low)
    if m:
        return _mk(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    return ''


_DEADLINE_LABEL = re.compile(
    r'(?:application\s+deadline|deadline(?:\s+for\s+application)?|last\s+date(?:\s+(?:of|for)\s+(?:submission|application|applying))?'
    r'|apply\s+(?:before|by|within)|closing\s+date|applications?\s+close[sd]?(?:\s+on)?|valid\s+(?:through|till|until)|'
    r'আবেদনের\s*শেষ\s*তারিখ|আবেদন\s*জমা(?:র)?\s*শেষ\s*তারিখ|শেষ\s*তারিখ|আবেদনের\s*সময়সীমা|আবেদনের\s*সময়সীমা)'
    r'\s*[:\-–—]?\s*(?:is\s+|on\s+)?(.{4,40})', re.I)
_POSTED_LABEL = re.compile(r'(?:published(?:\s+on)?|posted(?:\s+on)?|date\s+posted|প্রকাশের\s*তারিখ)\s*[:\-–—]?\s*(.{4,40})', re.I)


def find_deadline(text: str) -> str:
    for m in _DEADLINE_LABEL.finditer(str(text or '')[:20000]):
        found = parse_date(m.group(1))
        if found:
            return found
    return ''


def find_posted(text: str) -> str:
    for m in _POSTED_LABEL.finditer(str(text or '')[:6000]):
        found = parse_date(m.group(1))
        if found:
            return found
    return ''


def years_required(text: str) -> int | None:
    """Minimum years of experience from English or Bangla requirement text."""
    t = bn_to_ascii_digits(str(text or ''))[:15000]
    low = t.lower()
    for word, n in WORD_NUMBERS.items():
        low = re.sub(r'\b' + word + r'\b(?=\s*(?:\(\d+\)\s*)?\+?\s*(?:years?|yrs?))', str(n), low)
    patterns = (
        r'\b(?:minimum|at\s+least|min\.?|over|more\s+than)\s*(?:of\s*)?(\d{1,2})\s*\+?\s*(?:years?|yrs?)',
        r'\b(\d{1,2})\s*(?:-|–|to)\s*\d{1,2}\s*(?:years?|yrs?)',
        r'\b(\d{1,2})\s*\+\s*(?:years?|yrs?)',
        r'\b(\d{1,2})\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+|professional\s+|hands-on\s+|work\s+)?experience',
        r'experience\s*[:\-]\s*(?:minimum\s+|at\s+least\s+)?(\d{1,2})\s*(?:years?|yrs?)',
        r'(?:ন্যূনতম|কমপক্ষে|নূন্যতম)\s*(\d{1,2})\s*(?:\(.*?\)\s*)?বছর',
        r'(\d{1,2})\s*(?:\(.*?\)\s*)?বছরের\s*(?:বাস্তব\s*)?অভিজ্ঞতা',
    )
    for p in patterns:
        m = re.search(p, low, re.I)
        if m and 0 <= int(m.group(1)) <= 30:
            return int(m.group(1))
    return None


BD_CITY = re.compile(r'\b(Dhaka|Chattogram|Chittagong|Sylhet|Rajshahi|Khulna|Rangpur|Barishal|Barisal|Mymensingh|'
                     r'Gazipur|Narayanganj|Cumilla|Comilla|Bogura|Bogra|Cox.?s Bazar|Savar|Tongi)\b', re.I)


def bd_city(text: str) -> str:
    m = BD_CITY.search(str(text or ''))
    return m.group(1).title() if m else ''
