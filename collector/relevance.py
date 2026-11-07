"""Weighted cybersecurity relevance engine (English + Bangla).

v4.2 used plain substring matching, which accepted false positives such as
"mechan-isms" (matched ``isms``) and "cred-it audit" (matched ``it audit``) and
missed common titles such as "Network Security Engineer". This module scores
titles and descriptions with word-boundary patterns, explicit negatives for
physical-security / finance roles, and description evidence for generic
Bangladeshi bank titles ("Senior Principal Officer") that only state the
department in the body text.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Strong title signals: any one of these in a title makes the role relevant.
# --------------------------------------------------------------------------
_STRONG_EN = [
    r'cyber\s*-?\s*(?:security|defen[cs]e|risk|threat|resilience|intelligence|operations|analyst|engineer|expert|specialist|consultant|lead|manager|architect|fraud|crime)?',
    r'information\s+security', r'info\s*-?\s*sec', r'infosecurity',
    r'(?:it|ict|i\.t\.)\s+security', r'(?:it|ict)\s+&\s+security',
    r'information\s+(?:systems?\s+)?(?:security|assurance|audit(?:or)?)', r'is\s+audit(?:or)?',
    r'penetration\s+test\w*', r'pen\s*-?\s*test\w*', r'vapt', r'ethical\s+hack\w*', r'bug\s+bounty',
    r'(?:red|blue|purple)\s+team\w*', r'offensive\s+security', r'adversary\s+emulation',
    r'app\s*sec', r'application\s+security', r'api\s+security', r'(?:web|mobile)\s+(?:app(?:lication)?\s+)?security',
    r'product\s+security', r'platform\s+security', r'software\s+security', r'secure\s+(?:coding|code\s+review|sdlc)',
    r'dev\s*sec\s*ops', r'sec\s*ops', r'security\s+devops',
    r'soc\s*(?:l[1-3]|tier\s*[1-3]|analyst|engineer|manager|lead|operator|specialist)?',
    r'security\s+operations?(?:\s+cent(?:er|re))?', r'siem', r'soar', r'[ex]dr\s+(?:engineer|analyst|specialist)',
    r'threat\s+(?:intel\w*|hunt\w*|detect\w*|research\w*|analy\w*|model\w*|management)',
    r'incident\s+(?:respon\w*|handl\w*)', r'dfir', r'(?:digital|computer|cyber)\s+forensic\w*', r'malware',
    r'reverse\s+engineer\w*', r'detection\s+engineer\w*', r'csirt', r'cert\s+analyst',
    r'vulnerability\s*(?:management|assessment|analyst|researcher|engineer)?', r'exploit\s+develop\w*',
    r'ciso', r'biso', r'chief\s+(?:information\s+)?security', r'head\s+of\s+(?:information\s+|cyber\s*)?security',
    r'security\s+(?:engineer|analyst|architect|researcher|specialist|consultant|administrator|admin|developer|tester|auditor|automation|assurance|governance|compliance|risk|testing|assessment|monitoring|champion|program|programme|expert|operations|controls?|data\s+engineer)',
    r'iam', r'identity\s+(?:and|&)\s+access', r'identity\s+(?:security|governance|engineer)', r'privileged\s+access', r'pam\s+(?:engineer|admin\w*|specialist|analyst)',
    r'grc', r'isms', r'iso\s*/?\s*-?27001', r'pci\s*-?\s*dss', r'swift\s+(?:security|csp|cscf)',
    r'(?:cloud|network|infrastructure|endpoint|data(?:base)?|email|ot|ics|scada|iot|wireless|perimeter|enterprise|identity|ai|llm|ml|model|blockchain|smart\s+contract)\s+security',
    r'network\s+(?:&|and)\s+security', r'firewall', r'waf', r'ids\s*/\s*ips', r'zero\s+trust', r'sase',
    r'(?:it|ict|technology|cyber|information|operational\s+technology)\s+risk', r'technology\s+(?:audit\w*|controls?)',
    r'(?:it|ict)\s+(?:audit\w*|governance|compliance)', r'information\s+systems?\s+(?:audit\w*|control)',
    r'data\s+(?:privacy|protection\s+officer|loss\s+prevention)', r'dlp', r'privacy\s+(?:officer|engineer|analyst|counsel)', r'dpo',
    r'cryptograph\w*', r'pki', r'hsm\s+(?:engineer|admin\w*|specialist)', r'security\s+awareness',
    r'third[\s-]+party\s+(?:cyber|security|it)\s+risk', r'vendor\s+security',
]
_STRONG_BN = [
    'সাইবার', 'তথ্য নিরাপত্তা', 'তথ্য সুরক্ষা', 'ইনফরমেশন সিকিউরিটি', 'আইটি সিকিউরিটি', 'আইসিটি সিকিউরিটি',
    'অ্যাপ্লিকেশন সিকিউরিটি', 'অ্যাপ্লিকেশন নিরাপত্তা', 'নেটওয়ার্ক নিরাপত্তা', 'নেটওয়ার্ক সিকিউরিটি',
    'পেনিট্রেশন', 'পেনেট্রেশন', 'পেন্টেস্ট', 'ভিএপিটি', 'ভালনারেবিলিটি', 'সিকিউরিটি অপারেশনস',
    'তথ্যপ্রযুক্তি নিরীক্ষা', 'আইটি অডিট', 'আইএস অডিট', 'সিকিউরিটি অডিট', 'আইটি ঝুঁকি', 'আইসিটি ঝুঁকি',
    'ডিজিটাল ফরেনসিক', 'এপিআই সিকিউরিটি', 'এপিআই নিরাপত্তা', 'আইসিটি নিরাপত্তা', 'আইটি নিরাপত্তা',
    'নিরাপত্তা প্রকৌশলী', 'নিরাপত্তা বিশ্লেষক', 'সিকিউরিটি ইঞ্জিনিয়ার', 'সিকিউরিটি অ্যানালিস্ট',
]
# "Security" plus a leadership/officer word is ambiguous in Bangladesh (factory
# security managers, guards). It needs IT context in the title or description.
_AMBIGUOUS_SECURITY = re.compile(
    r'\bsecurity\b.{0,30}\b(officer|manager|lead|head|director|supervisor|in-?charge|executive|advisor|associate|coordinator|specialist)\b|'
    r'\b(officer|manager|lead|head|director|executive|advisor|associate)\b.{0,30}\bsecurity\b', re.I)
_IT_CONTEXT = re.compile(
    r'\b(it|ict|information|technology|tech|cyber|network|cloud|application|software|data|system|systems|digital|'
    r'computer|soc|siem|iso\s*27001|firewall|infrastructure|endpoint|server|database|devops)\b', re.I)

# --------------------------------------------------------------------------
# Negatives: physical security, finance/AML and other look-alike titles.
# --------------------------------------------------------------------------
_NEGATIVE_TITLE = re.compile(
    r'\b(security\s+guard|guard\s+commander|armed\s+guard|physical\s+security|security\s+personnel|'
    r'security\s+supervisor|security\s+in-?charge|security\s+agent|security\s+camera|cctv\s+operator|'
    r'airport\s+security|aviation\s+security|maritime\s+security|event\s+security|close\s+protection|'
    r'social\s+security|food\s+security|security\s+deposit|security\s+printing|safety\s+officer|fire\s+safety|'
    r'loss\s+prevention\s+(?:officer|associate|agent)|bouncer|watchman|gatekeeper|night\s+guard|'
    r'anti[\s-]?money\s+laundering|aml\s+(?:analyst|officer|specialist)|credit\s+(?:audit|risk|analyst)|'
    r'shariah|shari\'?ah|market\s+risk|tax\s+compliance|securities\s+(?:sales|trader|dealer|broker))\b', re.I)
_NEGATIVE_BN = re.compile(r'নিরাপত্তা\s*(?:প্রহরী|রক্ষী|কর্মী)|সিকিউরিটি\s*গার্ড|দারোয়ান|দারোয়ান|প্রহরী|আনসার')

_GENERIC_ROLE_EN = re.compile(
    r'\b(engineer|analyst|manager|specialist|advisor|adviser|consultant|auditor|lead|officer|executive|associate|'
    r'architect|administrator|expert|head|principal|assistant|deputy|senior|junior|trainee|intern)\b', re.I)
_GENERIC_ROLE_BN = re.compile(r'কর্মকর্তা|প্রকৌশলী|বিশ্লেষক|ব্যবস্থাপক|পরামর্শক|প্রধান|অফিসার|অডিটর|বিশেষজ্ঞ|নির্বাহী|ইঞ্জিনিয়ার')
_DEPARTMENT = re.compile(
    r'\b(information|cyber|it|ict|technology)\s+security\s+(division|department|dept\.?|unit|team|wing|cell|function|office)\b|'
    r'\bsecurity\s+operations?\s+cent(?:er|re)\b|\bciso\s+(?:office|division)\b|'
    r'তথ্য\s*নিরাপত্তা\s*(?:বিভাগ|ইউনিট|শাখা)|সাইবার\s*নিরাপত্তা\s*(?:বিভাগ|ইউনিট|শাখা)|আইসিটি\s*নিরাপত্তা\s*বিভাগ', re.I)

_STRONG_EN_RX = [re.compile(r'(?<![a-z0-9])(?:' + p + r')(?![a-z0-9])', re.I) for p in _STRONG_EN]
# Bare 'cyber' must be its own word or prefix (cybersecurity, cyber-security).
_STRONG_EN_RX[0] = re.compile(r'(?<![a-z0-9])cyber', re.I)


def _norm(text: str) -> str:
    text = unicodedata.normalize('NFKC', str(text or ''))
    text = text.replace('​', '').replace('‌', '').replace('‍', '')
    return re.sub(r'\s+', ' ', text).strip()


def strong_terms(text: str, limit: int = 40) -> list[str]:
    """Distinct strong cybersecurity terms found in text (lower-cased, de-duplicated)."""
    text = _norm(text)
    found: list[str] = []
    for rx in _STRONG_EN_RX:
        for m in rx.finditer(text):
            term = re.sub(r'\s+', ' ', m.group(0).lower()).strip(' -')
            if term and term not in found:
                found.append(term)
            if len(found) >= limit:
                return found
    for term in _STRONG_BN:
        if term in text and term not in found:
            found.append(term)
    return found


@dataclass
class Relevance:
    relevant: bool
    score: int
    reason: str
    terms: list[str] = field(default_factory=list)


def assess(title: str, description: str = '') -> Relevance:
    title = _norm(title)[:300]
    desc = _norm(description)[:12000]
    if not title:
        return Relevance(False, 0, 'empty title')
    if _NEGATIVE_TITLE.search(title) or _NEGATIVE_BN.search(title):
        # A negative only wins when the title has no explicit cyber signal
        # ("Credit Risk & Cyber Risk Analyst" is still relevant).
        explicit = [t for t in strong_terms(title) if not t.startswith(('security ', 'firewall'))]
        if not explicit or _NEGATIVE_BN.search(title):
            return Relevance(False, 0, 'excluded title (physical security / finance look-alike)')
    title_terms = strong_terms(title)
    desc_terms = strong_terms(desc) if desc else []
    if title_terms:
        score = min(98, 72 + 6 * (len(title_terms) - 1) + min(20, 2 * len(desc_terms)))
        return Relevance(True, score, 'security role title', title_terms + [t for t in desc_terms if t not in title_terms][:10])
    if _AMBIGUOUS_SECURITY.search(title):
        if _IT_CONTEXT.search(title) or len(desc_terms) >= 1 or _DEPARTMENT.search(desc):
            return Relevance(True, min(90, 60 + 4 * len(desc_terms)), 'security title with IT context', ['security'] + desc_terms[:10])
        return Relevance(False, 15, 'ambiguous security title without IT context')
    if re.search(r'\bsecurity\b', title, re.I) and len(desc_terms) >= 2:
        return Relevance(True, min(85, 55 + 4 * len(desc_terms)), 'security title, cyber description', ['security'] + desc_terms[:10])
    generic = _GENERIC_ROLE_EN.search(title) or _GENERIC_ROLE_BN.search(title)
    if generic and desc:
        if _DEPARTMENT.search(desc) and desc_terms:
            return Relevance(True, min(80, 50 + 4 * len(desc_terms)), 'generic title, security department', desc_terms[:12])
        if _GENERIC_ROLE_BN.search(title) and any(t in desc for t in _STRONG_BN):
            return Relevance(True, 55, 'Bangla role with Bangla security description', desc_terms[:12])
        core = [t for t in desc_terms if re.search(r'cyber|information security|penetration|soc|siem|incident|threat|vapt|appsec|application security|iso|isms|security (?:engineer|analyst|operations)', t)]
        if len(set(core)) >= 3:
            return Relevance(True, min(70, 40 + 4 * len(desc_terms)), 'generic title, strong cyber description', desc_terms[:12])
    return Relevance(False, 5 * len(desc_terms), 'no cybersecurity role signal', desc_terms[:6])


def is_relevant(title: str, description: str = '') -> bool:
    return assess(title, description).relevant
