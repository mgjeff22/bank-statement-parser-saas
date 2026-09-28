"""
Normalizer & Classifier for Bank Statement Extraction.

Provides robust:
- Date normalization to ISO-8601 (YYYY-MM-DD)
- Amount and sign parsing (currencies, commas, parentheses, DR/CR, +/-)
- Merchant/Payee description cleanup
- Transaction category heuristic classification
"""
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

CENT = Decimal("0.01")

# Category heuristic keywords mapping
CATEGORY_RULES = [
    (
        "Income / Payroll",
        [
            r"\bpayroll\b",
            r"\bdirect\s+dep\b",
            r"\bdirect\s+deposit\b",
            r"\bsalary\b",
            r"\bclient\s+wire\b",
            r"\binflow\b",
            r"\bdividend\b",
            r"\binterest\s+earned\b",
            r"\binterest\s+paid\b",
            r"\btreasury\s+dir\b",
            r"\brevenue\b",
        ],
    ),
    (
        "Utilities",
        [
            r"\belectric\b",
            r"\bgas\s+&\s+electric\b",
            r"\bwater\b",
            r"\butility\b",
            r"\butilities\b",
            r"\bpacific\s+gas\b",
            r"\bpge\b",
            r"\bconed\b",
            r"\bcomcast\b",
            r"\bverizon\b",
            r"\bat&t\b",
            r"\bbroadband\b",
            r"\binternet\b",
        ],
    ),
    (
        "Groceries",
        [
            r"\bwhole\s+foods\b",
            r"\btrader\s+joe\b",
            r"\bsafeway\b",
            r"\bkroger\b",
            r"\bsupermarket\b",
            r"\bgrocery\b",
            r"\bcostco\b",
            r"\baldi\b",
            r"\bwegmans\b",
            r"\bpublix\b",
            r"\bfresh\s+market\b",
        ],
    ),
    (
        "Dining / Food",
        [
            r"\brestaurant\b",
            r"\bcafe\b",
            r"\bcoffee\b",
            r"\bstarbucks\b",
            r"\bblue\s+bottle\b",
            r"\bmcdonald\b",
            r"\bchipotle\b",
            r"\bdoordash\b",
            r"\buber\s*eats\b",
            r"\bgrubhub\b",
            r"\btavern\b",
            r"\bbakery\b",
            r"\bbistro\b",
            r"\bpizza\b",
            r"\bburger\b",
            r"\bdiner\b",
        ],
    ),
    (
        "Rent & Mortgage",
        [
            r"\brent\b",
            r"\bmortgage\b",
            r"\bwework\b",
            r"\bleasing\b",
            r"\bproperty\s+mgmt\b",
            r"\bapartments?\b",
            r"\brealty\b",
        ],
    ),
    (
        "Software & Subscriptions",
        [
            r"\baws\b",
            r"\bamazon\s+web\s+services\b",
            r"\bgoogle\s+cloud\b",
            r"\bgithub\b",
            r"\bnetflix\b",
            r"\bspotify\b",
            r"\bzoom\b",
            r"\badobe\b",
            r"\bslack\b",
            r"\bnotion\b",
            r"\bheroku\b",
            r"\bopenai\b",
            r"\bsaas\b",
            r"\bmicrosoft\b",
            r"\bapple\.com/bill\b",
        ],
    ),
    (
        "Transfers & Wire",
        [
            r"\bwire\s+transfer\b",
            r"\bzelle\b",
            r"\bvenmo\b",
            r"\bach\s+transfer\b",
            r"\binternal\s+transfer\b",
            r"\btransfer\s+to\b",
            r"\btransfer\s+from\b",
            r"\bxfer\b",
        ],
    ),
    (
        "Bank Fees",
        [
            r"\boverdraft\s+fee\b",
            r"\bservice\s+charge\b",
            r"\bmonthly\s+(?:account\s+)?maintenance\b",
            r"\bmaintenance\s+fee\b",
            r"\batm\s+fee\b",
            r"\bwire\s+fee\b",
            r"\bforeign\s+transaction\s+fee\b",
            r"\blate\s+fee\b",
            r"\bbank\s+fee\b",
            r"\baccount\s+fee\b",
        ],
    ),
    (
        "Healthcare & Medical",
        [
            r"\bcvs\b",
            r"\bwalgreens\b",
            r"\bpharmacy\b",
            r"\bhospital\b",
            r"\bclinic\b",
            r"\bdental\b",
            r"\bdoctor\b",
            r"\bhealth\b",
            r"\boptometry\b",
            r"\blabcorp\b",
        ],
    ),
    (
        "Travel & Transportation",
        [
            r"\buber\b(?!\s*eats)",
            r"\blyft\b",
            r"\bdelta\b",
            r"\bunited\s+airlines\b",
            r"\bamerican\s+air\b",
            r"\bamtrak\b",
            r"\btransit\b",
            r"\bairline\b",
            r"\bchevron\b",
            r"\bshell\s+oil\b",
            r"\bexxon\b",
            r"\bgas\s+station\b",
            r"\bparking\b",
            r"\bhertz\b",
        ],
    ),
    (
        "Shopping & Retail",
        [
            r"\bamazon\b",
            r"\bamzn\b",
            r"\btarget\b",
            r"\bwalmart\b",
            r"\bbest\s+buy\b",
            r"\bretail\b",
            r"\bdepartment\s+store\b",
            r"\bhome\s+depot\b",
            r"\blowes\b",
            r"\bclothing\b",
        ],
    ),
    (
        "Insurance",
        [
            r"\bgeico\b",
            r"\bstate\s+farm\b",
            r"\ballstate\b",
            r"\bprogressive\b",
            r"\binsurance\b",
            r"\bprudential\b",
        ],
    ),
    (
        "Taxes",
        [
            r"\birs\b",
            r"\bus\s+treasury\b",
            r"\bstate\s+tax\b",
            r"\bftb\b",
            r"\btax\s+payment\b",
        ],
    ),
]


def normalize_date(date_str: str, default_year: Optional[int] = None) -> Optional[str]:
    """
    Parses arbitrary date formats and standardizes to ISO-8601 (YYYY-MM-DD).
    Supported formats include:
    - YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
    - MM/DD/YYYY, MM-DD-YYYY
    - DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    - DD-Mon-YYYY (e.g. 28-Sep-2026), DD-Month-YYYY
    - Mon DD YYYY, DD Mon YYYY, Mon DD, YYYY (e.g. Sep. 28, 2026)
    - Mon DD, DD.MM, DD-Mon (uses default_year or current year)
    """
    if not date_str:
        return None
    s = date_str.strip()

    # 1. Direct ISO match: YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
    iso_match = re.match(r"^(\d{4})[-/. ](\d{1,2})[-/. ](\d{1,2})$", s)
    if iso_match:
        y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
        try:
            return datetime(y, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 2. Direct European dot match: DD.MM.YYYY
    euro_dot_match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if euro_dot_match:
        d, m, y = int(euro_dot_match.group(1)), int(euro_dot_match.group(2)), int(euro_dot_match.group(3))
        try:
            return datetime(y, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 3. Clean month abbreviation periods (e.g. "Sep." -> "Sep") and remove commas
    s_clean = re.sub(r"\b([A-Za-z]{3,})\.", r"\1", s).replace(",", "").strip()

    formats = [
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
        "%m.%d.%Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d %Y",
        "%B %d %Y",
        "%b-%d-%Y",
        "%b-%d-%y",
        "%d-%b-%y",
        "%m/%d/%y",
        "%d/%m/%y",
        "%d.%m.%y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(s_clean, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # 4. Two-part dates without year (e.g. "Sep 14", "09/14", "28.09", "28-Sep")
    year = default_year or datetime.now().year
    no_year_formats = [
        "%b %d",
        "%B %d",
        "%m/%d",
        "%m-%d",
        "%d.%m",
        "%d-%b",
        "%b-%d",
    ]
    for fmt in no_year_formats:
        try:
            dt = datetime.strptime(f"{s_clean} {year}", f"{fmt} %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def parse_amount(
    raw_amount: str,
    default_type: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Extracts positive Decimal amount string and inferred direction ('debit' or 'credit').
    Handles:
    - '$1,250.50'
    - '($150.00)' -> debit, '150.00'
    - '-$45.00' -> debit, '45.00'
    - '+$120.00' -> credit, '120.00'
    - '120.00 CR' -> credit, '120.00'
    - '45.00 DR' -> debit, '45.00'
    - European '1.250,50 €'
    """
    if not raw_amount:
        return None, None

    s = raw_amount.strip()
    is_debit = False
    is_credit = False

    # Check parentheses: (150.00)
    if (s.startswith("(") and s.endswith(")")) or (s.startswith("-$") or s.startswith("-")):
        is_debit = True
    elif s.startswith("+") or s.startswith("+$"):
        is_credit = True

    if re.search(r"\bCR\b", s, re.IGNORECASE):
        is_credit = True
    elif re.search(r"\bDR\b", s, re.IGNORECASE):
        is_debit = True

    # Strip currency symbols, parentheses, signs, text
    cleaned = re.sub(r"[\$\€\£\¥\(\)\+\-a-zA-Z\s]", "", s)

    # Handle European comma decimal (e.g. 1.250,50)
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            # Comma is decimal separator (e.g. 1.250,50)
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # Period is decimal separator (e.g. 1,250.50)
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned and "." not in cleaned:
        # Check if comma represents cents e.g. 150,50
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            cleaned = f"{parts[0]}.{parts[1]}"
        else:
            cleaned = cleaned.replace(",", "")

    try:
        dec = Decimal(cleaned).quantize(CENT, rounding=ROUND_HALF_UP)
        amt_str = f"{abs(dec):.2f}"
    except Exception:
        return None, None

    tx_type = "debit" if is_debit else ("credit" if is_credit else (default_type or "debit"))
    return amt_str, tx_type


def clean_payee(raw_desc: str) -> str:
    """
    Cleans raw transaction descriptions into human-readable merchant/payee names.
    Removes POS terminal references, check numbers, location suffixes, and asterisks.
    """
    if not raw_desc:
        return "Unknown"

    cleaned = raw_desc.strip()

    # Common POS/Card noise prefixes
    patterns_to_remove = [
        r"^POS\s+(?:PURCHASE|DEBIT)\s*(?:AUTHORIZED\s+ON\s+\d{2}/\d{2})?\s*",
        r"^PURCHASE\s+AUTHORIZED\s+ON\s+\d{2}/\d{2}\s*",
        r"^CARD\s+\d{4,}\s*",
        r"^CHECK\s+#?\s*\d+\s*",
        r"^ATM\s+(?:WITHDRAWAL|DEPOSIT)\s*",
        r"^ELECTRONIC\s+(?:WITHDRAWAL|DEPOSIT)\s*",
        r"^DEBIT\s+CARD\s+PURCHASE\s*",
        r"^ACH\s+(?:DEBIT|CREDIT)\s*",
        r"^ONLINE\s+PAYMENT\s*",
    ]
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    # Clean prefixes like "SQ *", "TST* ", "AMZN Mktp US*"
    cleaned = re.sub(r"^(?:SQ\s*\*|TST\s*\*|PAYPAL\s*\*|SP\s*\*)\s*", "", cleaned, flags=re.IGNORECASE)

    # Remove trailing reference IDs or city/state codes e.g. "SAN FRANCISCO CA" or "REF 9821389"
    cleaned = re.sub(r"\s+REF\s*#?\s*\w+$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+\d{4,}\b", "", cleaned)  # trailing numbers/card digits

    # Well-known merchant simplifications
    if re.search(r"\bAMZN\b|\bAMAZON\b", cleaned, re.IGNORECASE):
        return "Amazon"
    if re.search(r"\bWHOLE\s+FOODS\b", cleaned, re.IGNORECASE):
        return "Whole Foods Market"
    if re.search(r"\bTRADER\s+JOE\b", cleaned, re.IGNORECASE):
        return "Trader Joe's"
    if re.search(r"\bSTARBUCKS\b", cleaned, re.IGNORECASE):
        return "Starbucks"
    if re.search(r"\bBLUE\s+BOTTLE\b", cleaned, re.IGNORECASE):
        return "Blue Bottle Coffee"
    if re.search(r"\bWEWORK\b", cleaned, re.IGNORECASE):
        return "WeWork"
    if re.search(r"\bUBER\s*EATS\b", cleaned, re.IGNORECASE):
        return "Uber Eats"
    elif re.search(r"\bUBER\b", cleaned, re.IGNORECASE):
        return "Uber"
    if re.search(r"\bLYFT\b", cleaned, re.IGNORECASE):
        return "Lyft"
    if re.search(r"\bDOORDASH\b", cleaned, re.IGNORECASE):
        return "DoorDash"
    if re.search(r"\bTARGET\b", cleaned, re.IGNORECASE):
        return "Target"
    if re.search(r"\bWALMART\b", cleaned, re.IGNORECASE):
        return "Walmart"

    # Normalize all-caps names to title case
    if cleaned.isupper() and len(cleaned) > 2:
        minor_words = {"on", "the", "in", "of", "and", "at", "by", "for", "with", "a", "an"}
        words = cleaned.split()
        cleaned = " ".join(
            w.lower() if w.lower() in minor_words and idx != 0 else w.capitalize()
            for idx, w in enumerate(words)
        )

    # Normalize multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else raw_desc.strip()


def classify_category(payee: str, raw_desc: str = "") -> str:
    """
    Classifies a transaction into a category using keyword heuristics.
    """
    text = f"{payee} {raw_desc}".lower()
    for category, patterns in CATEGORY_RULES:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return category
    return "Miscellaneous"
