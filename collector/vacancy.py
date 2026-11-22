"""Vacancy evidence, kept separate from cybersecurity keyword relevance.

A page about cybersecurity is not automatically a job.  In particular, event
registration, career advice and search/listing pages must not become vacancies
just because their title contains ``SOC`` or ``information security``.  These
checks are deliberately local: they never fetch a restricted job portal.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse


def _text(value: str, limit: int = 14000) -> str:
    value = unicodedata.normalize('NFKC', str(value or ''))
    value = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', value)
    return re.sub(r'\s+', ' ', value).strip()[:limit]


_ROLE = re.compile(
    r'\b(?:engineer|analyst|officer|manager|specialist|consultant|architect|auditor|'
    r'administrator|developer|tester|pentester|researcher|responder|handler|hunter|'
    r'operator|investigator|hacker|cryptographer|cryptanalyst|counsel|intern|internship|'
    r'trainee|apprentice|lead|head|director|executive|associate|advisor|adviser|'
    r'coordinator|expert|instructor|trainer|ciso|biso|dpo)\b|'
    r'কর্মকর্তা|অফিসার|প্রকৌশলী|বিশ্লেষক|বিশেষজ্ঞ|ব্যবস্থাপক|নির্বাহী|'
    r'পরামর্শক|প্রধান|অডিটর|ইঞ্জিনিয়ার|প্রশিক্ষক|ইন্টার্ন', re.I)
_TEACHING_ROLE = re.compile(
    r'\b(?:trainer|instructor|lecturer|professor|curriculum\s+(?:developer|designer)|'
    r'training\s+(?:specialist|manager|coordinator|engineer))\b|প্রশিক্ষক', re.I)
_EVENT = re.compile(
    r'\b(?:webinar|seminar|conference|summit|workshop|boot\s?camp|hackathon|'
    r'competition|capture\s+the\s+flag|ctf|masterclass|career\s+fair|job\s+fair|'
    r'awareness\s+(?:day|week|month|session|program(?:me)?|campaign)|training\s+(?:course|program(?:me)?|session)|'
    r'(?:online|free|certification)\s+course|certification\s+exam)\b|'
    r'ওয়েবিনার|ওয়েবিনার|সেমিনার|সম্মেলন|কর্মশালা|হ্যাকাথন|প্রতিযোগিতা|বুটক্যাম্প|'
    r'প্রশিক্ষণ(?:ে|এর)?\s*(?:নিবন্ধন|কোর্স|কর্মসূচি)|সচেতনতা\s*কর্মসূচি', re.I)
_TRAINING_HEADLINE = re.compile(
    r'\b(?:training|course|certification)\s+(?:on|in|for)\b|'
    r'\b(?:training|course|courses|certification)\s*(?:\d{4})?\s*$|'
    r'প্রশিক্ষণ\s*(?:কোর্স|কর্মসূচি|কর্মশালা|বিজ্ঞপ্তি)?\s*$', re.I)
_ARTICLE = re.compile(
    r'^(?:how\s+to|what\s+(?:is|are)|why\s+(?:is|are)|learn\s+(?:about|to)|'
    r'a\s+guide\s+to|guide\s+to|the\s+future\s+of|become\s+(?:a|an)|'
    r'top\s+\d+|best\s+\d+)\b|'
    r'\b(?:interview\s+questions|career\s+(?:guide|roadmap)|salary\s+guide|'
    r'salary\s+survey|salaries\s+in|study\s+guide|exam\s+(?:questions|dumps)|'
    r'press\s+release|appoints|appointed|appointment\s+of|promoted\s+to|joins\s+as|joined\s+as)\b|'
    r'\b(?:announces?|launches?|hosts?|hosted|conducted|celebrates?|wins?)\b.{0,75}'
    r'\b(?:event|webinar|workshop|award|conference|summit|partnership|initiative)\b|'
    r'কর্মশালা\s*(?:অনুষ্ঠিত|আয়োজন)|সম্মেলন\s*অনুষ্ঠিত', re.I)
_LISTING = re.compile(
    r'^\s*[\d,]+\+?\s+.{0,100}\bjobs\b|'
    r'\b(?:jobs|vacancies)\s+(?:in|near|at|for|available)\b|'
    r'\b(?:jobs|careers|vacancies)\s*(?:[|–—-].*)?$|'
    r'^(?:careers?\s+in|job\s+search|search\s+results|all\s+jobs|'
    r'current\s+openings|open\s+positions)\b', re.I)
_SERVICE = re.compile(
    r'\b(?:services|solutions|consulting|capabilities|our\s+team)\b|'
    r'^(?:our|meet\s+the)\b.{0,60}\bteam\s*$|সেবাসমূহ', re.I)
_NON_TITLE_FRAGMENT = re.compile(
    r'^(?:reports?|reporting)\s+to\b|'
    r'^(?:work|working|collaborate|collaborating|coordinate|coordinating|liaise)\s+'
    r'(?:(?:closely|directly)\s+)?(?:with|alongside)\b|'
    r'^(?:for\s+(?:enquiries|inquiries|queries|details|information)\b.{0,40}\bcontact|'
    r'(?:contact|hiring\s+manager|reporting\s+line)\s*[:–—-])|'
    r'^(?:experience|knowledge|skills?|qualifications?)\s+(?:in|of|with|as|for|required)\b|'
    r'^(?:must|should)\s+have\b|^responsible\s+for\b|'
    r'^(?:the|an?)\b.{0,100}\b(?:will|shall|must)\b|'
    r'^(?:যোগাযোগ|রিপোর্টিং|দায়িত্ব|দায়িত্ব)\s*[:–—-]', re.I)
_APPLICATION = re.compile(
    r'\bapply\s+(?:now|here|online|today|by|before|via|through|to\s+(?:this|the|join)|'
    r'for\s+(?:this|the|our)\s+(?:job|position|role|vacancy))\b|'
    r'\b(?:submit|send|email|upload)\s+(?:(?:us|your|an|a)\s+){0,2}'
    r'(?:cv|resume|résumé|applications?)\b|'
    r'\bapplication\s+(?:deadline|procedure|process|form|instructions|closing\s+date)\b|'
    r'\b(?:apply|applications?)\s*(?:at|to)\s+[^\s]+@|'
    r'আবেদন\s*(?:করুন|করতে|পদ্ধতি|পত্র|প্রক্রিয়া|জমা)|'
    r'আবেদনের\s*(?:শেষ|সময়|নিয়ম)|জীবনবৃত্তান্ত\s*(?:পাঠান|জমা)', re.I)
_RECRUITMENT = re.compile(
    r'\b(?:hiring|recruiting|recruitment\s+(?:circular|notice)|job\s+(?:circular|opening|'
    r'vacancy)|vacanc(?:y|ies)|we\s+are\s+looking\s+for|'
    r'(?:seeking|looking\s+for)\s+(?:an?\s+)?(?:experienced|senior|junior|skilled|'
    r'qualified|motivated|talented|security|cyber|information))\b|'
    r'নিয়োগ|নিয়োগ|শূন্যপদ|চাকরির\s+বিজ্ঞপ্তি', re.I)
_JOB_SECTIONS = (
    ('responsibilities', re.compile(r'\b(?:job\s+)?responsibilit(?:y|ies)\b|\bwhat\s+you(?:\s+will|[’\']ll)\s+do\b|দায়িত্ব|দায়িত্ব|কাজের\s*বিবরণ', re.I)),
    ('requirements', re.compile(r'\b(?:qualifications?|requirements?|what\s+you(?:\s+will|[’\']ll)\s+bring)\b|যোগ্যতা|অভিজ্ঞতা', re.I)),
    ('employment', re.compile(r'\b(?:employment\s+type|full[ -]time|part[ -]time|contract\s+(?:role|position)|internship)\b|চাকরির\s*(?:ধরন|প্রকৃতি)', re.I)),
    ('compensation', re.compile(r'\b(?:salary|compensation|remuneration)\b|বেতন|পারিশ্রমিক', re.I)),
    ('experience', re.compile(r'\b\d+\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+)?experience\b|[০-৯\d]+\s*বছরের?\s*অভিজ্ঞতা', re.I)),
)
_EVENT_ACTION = re.compile(
    r'\b(?:register\s+(?:now|here|today|for)|registration\s+(?:fee|open|deadline)|'
    r'buy\s+tickets?|book\s+(?:your|a)\s+(?:seat|ticket)|event\s+(?:date|venue)|'
    r'course\s+fee|attend\s+(?:our|the|this)\s+(?:webinar|workshop|conference|event))\b|'
    r'রেজিস্ট্রেশন\s*(?:ফি|করুন)|নিবন্ধন\s*(?:ফি|করুন)|কোর্স\s*ফি', re.I)
_CLOSED = re.compile(
    r'\b(?:no\s+longer\s+accepting\s+applications|(?:applications|recruitment)\s+'
    r'(?:are\s+)?closed|position\s+(?:has\s+been\s+)?filled|job\s+(?:has\s+)?expired)\b|'
    r'আবেদন\s*(?:গ্রহণ\s*)?বন্ধ', re.I)


def has_role_title(title: str) -> bool:
    """A specific occupational title, rather than a cybersecurity topic label."""
    return bool(_ROLE.search(_text(title, 350)))


def non_vacancy_title_reason(title: str) -> str:
    """Clear title negatives shared with the relevance engine.

    Teaching is a legitimate occupation.  A Cybersecurity Trainer vacancy is
    retained, while an invitation to Cybersecurity Training is rejected.
    """
    title = _text(title, 350)
    if _NON_TITLE_FRAGMENT.search(title):
        return 'description, reporting line or contact text rather than a job title'
    if _ARTICLE.search(title):
        return 'article, advice or news headline'
    if _EVENT.search(title) and not _TEACHING_ROLE.search(title):
        return 'event or course announcement'
    if _TRAINING_HEADLINE.search(title) and not _TEACHING_ROLE.search(title):
        return 'training or certification announcement'
    if _LISTING.search(title):
        return 'job listing/search page, not one vacancy'
    if _SERVICE.search(title) and not has_role_title(title):
        return 'service or company page, not one vacancy'
    return ''


def _host_is(host: str, domain: str) -> bool:
    return host == domain or host.endswith('.' + domain)


def is_portal_job_url(url: str) -> bool:
    """Recognise individual job routes without contacting the portal."""
    try:
        parsed = urlparse(str(url or ''))
        host, path = (parsed.hostname or '').lower(), unquote(parsed.path).lower()
        if parsed.scheme not in ('https', 'http') or not host:
            return False
        query = parse_qs(parsed.query)
    except (ValueError, TypeError):
        return False
    if _host_is(host, 'linkedin.com'):
        return bool(re.fullmatch(r'/(?:comm/)?jobs/view/(?:[^/?#]+-)?\d+/?', path))
    if _host_is(host, 'bdjobs.com'):
        return bool(re.search(r'/(?:jobdetails?\.asp|jobsdetails\.asp)$', path) and
                    any(str(v[0]).isdigit() for k, v in query.items() if k.lower() == 'id' and v)) or \
            bool(re.search(r'/(?:details|jobdetails|jobs/details)/[^/]+/?$', path))
    if _host_is(host, 'indeed.com'):
        return bool(query.get('jk') or query.get('vjk'))
    if _host_is(host, 'glassdoor.com'):
        return bool(query.get('jl') or query.get('jobListingId'))
    if _host_is(host, 'dohaj.com'):
        return '/job-details/' in path
    return False


def is_job_detail_url(url: str) -> bool:
    if is_portal_job_url(url):
        return True
    try:
        parsed = urlparse(str(url or ''))
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            return False
        path = unquote(parsed.path).lower()
        query = parse_qs(parsed.query)
    except (ValueError, TypeError):
        return False
    if re.search(r'/(?:search|category|tag|events?|webinars?|workshops?|blog)(?:/|$)', path):
        return False
    if re.search(r'/(?:jobs?|careers?|positions?|vacanc(?:y|ies)|openings?|recruitment|'
                 r'opportunities|job-details?)/[^/]+(?:/[^/]+)*/?$', path):
        return True
    if re.search(r'/(?:job|vacancy|position|opening)-[^/]+/?$', path):
        return True
    return any(k.lower() in ('jobid', 'job_id', 'job', 'vacancyid', 'positionid', 'requisitionid') and v
               for k, v in query.items())


@dataclass
class VacancyEvidence:
    vacancy: bool
    score: int
    reason: str
    signals: list[str] = field(default_factory=list)


def assess_vacancy(title: str, description: str = '', url: str = '', *,
                   source_kind: str = 'html') -> VacancyEvidence:
    """Assess recruitment evidence independently of cybersecurity relevance.

    source_kind: ``jobposting`` / ``ats`` / ``publisher`` are structured job
    sources; ``alert`` is a subscribed job-alert card; ``official_rss`` is a
    discovered employer recruitment feed.  ``html``, ``pdf``, ``index``,
    ``feed`` and ``legacy`` require independent recruitment/detail evidence.
    None of these scores is a probability or proof that a vacancy remains open.
    """
    title, desc = _text(title, 350), _text(description)
    if not title:
        return VacancyEvidence(False, 0, 'empty title')
    negative = non_vacancy_title_reason(title)
    if negative:
        return VacancyEvidence(False, 0, negative)
    role = has_role_title(title)
    detail = is_job_detail_url(url)
    portal = is_portal_job_url(url)
    combined = title + ' ' + desc
    application = bool(_APPLICATION.search(combined))
    recruitment = bool(_RECRUITMENT.search(combined))
    sections = [name for name, rx in _JOB_SECTIONS if rx.search(desc)]
    signals = (['role title'] if role else []) + (['individual job URL'] if detail else [])
    if application:
        signals.append('application instructions')
    if recruitment:
        signals.append('recruitment language')
    signals.extend(sections)
    # A job may mention attendance at conferences as a benefit.  Only an
    # event-registration lead without employment evidence is disqualifying.
    if _EVENT_ACTION.search(desc[:1800]) and not (recruitment and (application or len(sections) >= 2)):
        return VacancyEvidence(False, 5, 'event registration rather than recruitment', signals)
    if source_kind in ('jobposting', 'ats', 'publisher'):
        return VacancyEvidence(True, 95, 'structured job-source evidence', signals + [source_kind])
    if portal and role:
        return VacancyEvidence(True, 85, 'individual portal job with role title', signals)
    if source_kind == 'alert' and role and detail:
        return VacancyEvidence(True, 80, 'subscribed alert for an individual job', signals)
    if source_kind == 'official_rss' and role and detail:
        return VacancyEvidence(True, 78, 'employer recruitment feed and individual job URL', signals)
    if role and application and (recruitment or detail or len(sections) >= 1):
        return VacancyEvidence(True, 82, 'role with application and recruitment evidence', signals)
    if role and recruitment and (detail or len(sections) >= 2):
        return VacancyEvidence(True, 75, 'role with recruitment evidence', signals)
    if role and detail and len(sections) >= 2:
        return VacancyEvidence(True, 72, 'individual role with employment details', signals)
    if role and application and source_kind == 'pdf':
        return VacancyEvidence(True, 75, 'role and application instructions in circular', signals)
    if source_kind == 'legacy' and role and detail and desc.strip():
        # Earlier versions retained only brief summaries.  Do not destroy a
        # plausible archived lead merely because the new parser demands more
        # evidence from newly fetched HTML; explicit false positives above are
        # still removed.  This is visibly lower confidence, never "verified".
        return VacancyEvidence(True, 55, 'historical job lead; verify on original posting', signals)
    return VacancyEvidence(False, min(50, 12 * len(signals)), 'insufficient evidence of an individual vacancy', signals)


def source_kind_for_record(job: dict) -> str:
    level = str(job.get('verification_level') or '').lower()
    source = str(job.get('source') or '').lower()
    if 'structured data' in level:
        return 'jobposting'
    if 'ats api' in level:
        return 'ats'
    if level == 'publisher page verified':
        return 'publisher'
    if 'public api' in level or 'public api' in source or 'aggregator api' in level:
        return 'publisher'
    if 'workday career' in source:
        return 'ats'
    if 'email alert' in level or 'alert email' in source:
        return 'alert'
    if 'official employer rss' in source:
        return 'official_rss'
    if source == 'official employer':
        return 'legacy'
    if 'pdf circular' in source or 'pdf circular' in level:
        return 'pdf'
    if 'search' in level or ' index' in source:
        return 'index'
    if 'custom feed' in source or 'user feed' in level:
        return 'feed'
    return 'legacy'


def assess_record(job: dict) -> VacancyEvidence:
    """Recheck persisted or newly collected records through both gates.

    Caller retains rejected records separately.  The input is never mutated;
    original publication dates, source links and provenance remain intact.
    """
    from .relevance import assess
    title = str(job.get('title') or '')
    description = str(job.get('description') or '')
    extra = []
    for field_name in ('requirements', 'responsibilities'):
        items = job.get(field_name)
        if isinstance(items, list) and items:
            extra.append(field_name + ': ' + ' '.join(str(x) for x in items))
    relevance = assess(title, description + ' ' + ' '.join(extra))
    if not relevance.relevant:
        return VacancyEvidence(False, 0, relevance.reason, relevance.terms)
    if job.get('employment_type') and str(job['employment_type']).lower() != 'not specified':
        extra.append('Employment type: ' + str(job['employment_type']))
    return assess_vacancy(title, description + ' ' + ' '.join(extra),
                          str(job.get('source_url') or job.get('apply_url') or ''),
                          source_kind=source_kind_for_record(job))
