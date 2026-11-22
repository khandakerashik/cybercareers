# Measured source audit — 22 November 2026

This audit distinguishes extraction fixes from the current accessibility of external websites. It does not certify that every vacancy was collected. See `source-audit-2026-11-22.json` for complete observations and `source-audit-2026-11-22.csv` for a compact per-source view.

## Scope and results

The registry contains 193 entries: 151 employer sources, six publisher feeds and 36 directory/restricted/manual-link entries. The measured network audit covers the 151 employers. It does not exercise private mailboxes, authenticated search APIs or all feed providers.

| Observation set | Readable recruitment source | Limited coverage | Blocked or unavailable |
| --- | ---: | ---: | ---: |
| Initial full employer audit (151) | 47 | 61 | 43 |
| Targeted rechecks (28) | 10 | 18 | 0 |
| Latest recorded observation per employer (151) | 53 | 66 | 32 |

The last row combines the latest actual observation for each employer from two phases. It is not a fresh full production sweep. The initial audit ran from approximately 21:43 to 21:49 BDT; targeted rechecks ran from approximately 21:49 to 21:50 BDT. Every row retains its exact UTC timestamp and phase.

Both phases used HTTP only. Chromium launch was blocked by the execution environment, so JavaScript rendering could not be validated live. The initial sweep used eight workers and a shared 450-request follow-up budget. Rechecks used six workers and 12 follow-up requests per selected employer. Code changes made after a particular observation are not retroactively described as live-verified.

## Remaining limitations

| Recorded reason | Sources | Interpretation |
| --- | ---: | --- |
| Readable recruitment content | 53 | Usable recruiting content or an explicit no-openings message; still not exhaustive coverage |
| Homepage only | 31 | Employer reachable; an actionable recruitment page was not verified |
| Vacancy list not found | 21 | Career/landing page reachable but no readable vacancy list or explicit empty-state evidence |
| JavaScript required | 9 | Thin app shell or client-rendered list; deployment rendering needs verification |
| Incomplete bounded scan | 5 | Some discovered pages, details or pagination could not be checked |
| Robots policy unavailable | 25 | Policy retrieval failed, often HTTP 5xx; collection waits instead of assuming permission |
| Access blocked | 6 | Access denial/challenge from the site or network path |
| Other unavailable response | 1 | No usable page read; exact recorded message is in the audit |

Readable sources can legitimately have zero cybersecurity openings. The 36 directory/manual-link entries are not failed automated fetches. LinkedIn discovery comes from configured alert/search channels rather than pretending its directory link was scraped.

## Verified employer route changes

These changes are supported by employer-published links. Publication of a route is separate from live reachability. A changed URL may still appear as limited or blocked in the audit.

| Employer | Updated route | Evidence | Latest probe |
| --- | --- | --- | --- |
| Rupali Bank | https://www.rupalibank.com.bd/notice_jquery.php?type=20 | [Employer source](https://www.rupalibank.com.bd/) | partial |
| BRAC Bank | https://www.bracbank.com/en/career | [Employer source](https://www.bracbank.com/en/career) | ok |
| Dutch-Bangla Bank | https://app.dutchbanglabank.com/Online_Job/currentJob | [Employer source](https://www.dutchbanglabank.com/help-desk/sitemap.html) | ok |
| First Security Islami Bank | https://erecruitment.fsiblbd.com/test_erc/fsibl_site.php | [Employer source](https://fsibplc.com/) | partial |
| IFIC Bank | https://career.ificbankbd.com/ | [Employer source](https://ificbank.com.bd/career) | partial |
| Meghna Bank | https://career.meghnabank.com.bd/ | [Employer source](https://www.meghnabank.com.bd/page/sitemap/retail) | partial |
| Mutual Trust Bank | https://www.mutualtrustbank.com/about-us/career/ | [Employer source](https://www.mutualtrustbank.com/about-us/career/) | ok |
| NRBC Bank | https://career.nrbcommercialbank.com/ | [Employer source](https://www.nrbcommercialbank.com/career) | ok |
| City Bank | https://www.citybankplc.com/life-at-city-evp/job-list | [Employer source](https://www.citybankplc.com/life-at-city-evp/job-list) | ok |
| State Bank of India Bangladesh | https://bd.statebank/career | [Employer source](https://bd.statebank/career) | ok |
| SSL Wireless | https://sslwireless.com/all-jobs | [Employer source](https://sslwireless.com/all-jobs) | partial |
| BRAC | https://careers.brac.net/jobs | [Employer source](https://careers.brac.net/jobs) | partial |
| icddr,b | https://career.icddrb.org/ | [Employer source](https://www.icddrb.org/work-with-us) | ok |
| Brain Station 23 | https://brainstation-23.easy.jobs/ | [Employer source](https://brainstation-23.com/) | partial |
| Cefalo | https://career.cefalo.com/ | [Employer source](https://career.cefalo.com/) | ok |
| Vivasoft | https://vivasoftltd.com/career/ | [Employer source](https://vivasoftltd.com/career/) | ok |

## Repeat diagnostics in the deployment environment

```powershell
python -m collector.diagnose --failed-only --limit 250 --output source-diagnostics.json
```

This command is read-only with respect to jobs, progress and source history. For JavaScript sources, enable `RENDER_JS=1` and install Chromium as explained in the upgrade guide. The hourly collector will continue normal permitted retries, respecting policy and provider limits.
