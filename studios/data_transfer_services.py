import copy
import csv
import io
import re
from html import unescape
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q

from classes.models import Class, ClassType, Season
from enrollments.models import Enrollment
from families.models import Family, Guardian
from instructors.models import Instructor
from students.models import Student
from costumes.models import Vendor, VendorSizeChart, VendorSizeEntry

from .data_transfer_history_services import snapshot_instance


IMPORT_TYPES = {
    "students": {
        "label": "Students",
        "description": "Student names, birthdays, status, medical notes, and family references.",
        "fields": [
            ("first_name", "First name"),
            ("last_name", "Last name"),
            ("birthday", "Birthday"),
            ("gender", "Gender"),
            ("family_email", "Family / guardian email"),
            ("medical_conditions", "Medical conditions"),
            ("allergies", "Allergies"),
            ("comments", "Comments"),
            ("paper_waiver_on_file", "Paper waiver on file"),
            ("performing", "Performing"),
            ("is_active", "Active"),
            ("emergency_contact_name", "Emergency contact name"),
            ("emergency_contact_phone", "Emergency contact phone"),
            ("emergency_contact_relationship", "Emergency contact relationship"),
            ("how_did_you_hear_about_us", "How did you hear about us"),
        ],
        "required_mapping": ["first_name", "last_name", "birthday"],
    },
    "families": {
        "label": "Families",
        "description": "Family contact, address, emergency contact, and account-level notes.",
        "fields": [
            ("family_name", "Family name"),
            ("primary_contact_first_name", "Primary contact first name"),
            ("primary_contact_last_name", "Primary contact last name"),
            ("primary_email", "Primary email"),
            ("secondary_email", "Secondary email"),
            ("primary_phone", "Primary phone"),
            ("secondary_phone", "Secondary phone"),
            ("address_line_1", "Address line 1"),
            ("address_line_2", "Address line 2"),
            ("city", "City"),
            ("state", "State"),
            ("postal_code", "Postal code"),
            ("emergency_contact_name", "Emergency contact name"),
            ("emergency_contact_phone", "Emergency contact phone"),
            ("emergency_contact_relationship", "Emergency contact relationship"),
            ("notes", "Notes"),
            ("is_active", "Active"),
        ],
        "required_mapping": [],
    },
    "guardians": {
        "label": "Guardians",
        "description": "Guardian contacts and their relationship to a family.",
        "fields": [
            ("family_email", "Family primary email"),
            ("first_name", "First name"),
            ("last_name", "Last name"),
            ("relationship", "Relationship"),
            ("email", "Email"),
            ("phone", "Phone"),
            ("is_primary", "Primary guardian"),
            ("is_authorized_for_pickup", "Authorized for pickup"),
            ("is_financially_responsible", "Financially responsible"),
            ("is_active", "Active"),
        ],
        "required_mapping": ["family_email", "first_name", "last_name"],
    },
    "instructors": {
        "label": "Teachers / Instructors",
        "description": "Instructor contact information, address, emergency contacts, and bio.",
        "fields": [
            ("first_name", "First name"),
            ("last_name", "Last name"),
            ("email", "Email"),
            ("phone", "Phone"),
            ("address_line_1", "Address line 1"),
            ("address_line_2", "Address line 2"),
            ("city", "City"),
            ("state", "State"),
            ("postal_code", "Postal code"),
            ("emergency_contact_name", "Emergency contact name"),
            ("emergency_contact_phone", "Emergency contact phone"),
            ("emergency_contact_relationship", "Emergency contact relationship"),
            ("bio", "Bio"),
            ("is_active", "Active"),
        ],
        "required_mapping": ["first_name", "last_name"],
    },
    "classes": {
        "label": "Classes",
        "description": "Class identity, season/type references, teacher, capacity, tuition, and registration status.",
        "fields": [
            ("class_id", "Class ID"),
            ("name", "Class name"),
            ("season", "Season"),
            ("class_type", "Class type"),
            ("instructor_email", "Instructor email"),
            ("description", "Description"),
            ("dress_code", "Dress code"),
            ("capacity", "Capacity"),
            ("min_age", "Minimum age"),
            ("max_age", "Maximum age"),
            ("gender_restriction", "Gender restriction"),
            ("tuition_amount", "Tuition amount"),
            ("is_active", "Active"),
            ("registration_open", "Registration open"),
            ("notes", "Notes"),
        ],
        "required_mapping": ["class_id", "name", "season", "class_type", "instructor_email"],
    },
    "enrollments": {
        "label": "Enrollments",
        "description": "Links students to classes using student details and Encore class IDs.",
        "fields": [
            ("student_first_name", "Student first name"),
            ("student_last_name", "Student last name"),
            ("student_birthday", "Student birthday"),
            ("class_id", "Class ID"),
            ("status", "Enrollment status"),
            ("tuition_override", "Tuition override"),
            ("notes", "Notes"),
        ],
        "required_mapping": ["student_first_name", "student_last_name", "student_birthday", "class_id"],
    },
    "costume_vendors": {
        "label": "Costume Vendors",
        "description": "Costume vendor contact, account, address, website, and studio-specific notes.",
        "fields": [
            ("name", "Vendor name"),
            ("abbreviation", "Abbreviation"),
            ("contact_name", "Vendor contact"),
            ("address_line_1", "Address line 1"),
            ("address_line_2", "Address line 2"),
            ("city", "City"),
            ("state", "State"),
            ("postal_code", "Postal code"),
            ("phone", "Phone"),
            ("fax", "Fax"),
            ("email_or_website", "Email / website source"),
            ("required_date_source", "Studio Director required date"),
            ("customer_number", "Customer number"),
            ("notes", "Notes"),
        ],
        "required_mapping": ["name"],
    },
    "costume_vendor_size_charts": {
        "label": "Costume Vendor Size Charts",
        "description": "Vendor chart names, girth ranges, sizes, and notes from Studio Director.",
        "fields": [
            ("vendor_chart", "Vendor / chart"),
            ("girth_min", "Girth from"),
            ("girth_max", "Girth to"),
            ("size_label", "Size"),
            ("notes", "Notes"),
        ],
        "required_mapping": ["vendor_chart", "size_label"],
    },
}


ALIASES = {
    "first_name": {"first name", "firstname", "first", "fname", "student first", "student_first"},
    "last_name": {"last name", "lastname", "last", "lname", "student last", "student_last"},
    "birthday": {"birthday", "birth date", "birthdate", "date of birth", "dob"},
    "student_birthday": {"student birthday", "student birth date", "student dob", "dob", "birthdate"},
    "email": {"email", "email address", "e-mail"},
    "primary_email": {"primary email", "parent email", "family email", "email"},
    "secondary_email": {"secondary email", "email 2", "alternate email"},
    "family_email": {"family email", "parent email", "guardian email", "primary email"},
    "phone": {"phone", "phone number", "mobile", "cell", "cell phone"},
    "primary_phone": {"primary phone", "phone", "mobile", "cell"},
    "secondary_phone": {"secondary phone", "phone 2", "alternate phone"},
    "family_name": {"family name", "household", "household name", "account name"},
    "relationship": {"relationship", "relation"},
    "address_line_1": {"address", "address 1", "street", "street address"},
    "address_line_2": {"address 2", "apt", "suite", "unit"},
    "city": {"city"},
    "state": {"state", "province"},
    "postal_code": {"zip", "zip code", "postal code", "postcode"},
    "class_id": {"class id", "class_id", "course id", "course_id", "class number"},
    "name": {"name", "class name", "course", "course name"},
    "season": {"season", "term", "session"},
    "class_type": {"class type", "type", "discipline", "category"},
    "instructor_email": {"instructor email", "teacher email", "staff email"},
    "capacity": {"capacity", "max students", "maximum enrollment"},
    "tuition_amount": {"tuition", "tuition amount", "price", "class price"},
    "tuition_override": {"tuition override", "student tuition", "override tuition"},
    "status": {"status", "enrollment status"},
    "notes": {"notes", "note", "comments"},
    "comments": {"comments", "comment", "notes"},
    "is_active": {"active", "is active", "status"},
    "performing": {"performing", "performance", "performs"},
    "gender": {"gender", "sex"},
    "gender_restriction": {"gender restriction", "gender", "restriction"},
    "registration_open": {"registration open", "open registration", "registration status"},
    "student_first_name": {"student first name", "student firstname", "student first", "first name"},
    "student_last_name": {"student last name", "student lastname", "student last", "last name"},
    "abbreviation": {"vendor abbrev", "abbreviation", "abbrev"},
    "contact_name": {"vendor contact", "contact", "contact name"},
    "fax": {"fax", "fax number"},
    "customer_number": {"customer number", "customer #", "account number"},
    "email_or_website": {"email", "website", "email / website"},
    "required_date_source": {"required date"},
    "vendor_chart": {"vendor", "vendor chart", "vendor / chart"},
    "girth_min": {"girth from", "girth minimum", "girth min"},
    "girth_max": {"girth to", "girth maximum", "girth max"},
    "size_label": {"size", "size label"},
}


BOOLEAN_FIELDS = {
    "paper_waiver_on_file",
    "performing",
    "is_active",
    "is_primary",
    "is_authorized_for_pickup",
    "is_financially_responsible",
    "registration_open",
}
DATE_FIELDS = {"birthday", "student_birthday"}
INTEGER_FIELDS = {"capacity", "min_age", "max_age"}
DECIMAL_FIELDS = {"tuition_amount", "tuition_override", "girth_min", "girth_max"}
EMAIL_FIELDS = {"email", "primary_email", "secondary_email", "family_email", "instructor_email"}
PHONE_FIELDS = {"phone", "primary_phone", "secondary_phone", "emergency_contact_phone"}


TRUE_VALUES = {"1", "true", "t", "yes", "y", "active", "enabled", "open"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "inactive", "disabled", "closed"}


def normalize_header(value):
    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )


def auto_map_headers(headers, import_type):
    allowed = {key for key, _label in IMPORT_TYPES[import_type]["fields"]}
    mapping = {}
    used = set()

    for header in headers:
        normalized = normalize_header(header)
        selected = ""

        for field in allowed:
            aliases = set(ALIASES.get(field, set()))
            aliases.add(normalize_header(field))
            if normalized in aliases and field not in used:
                selected = field
                used.add(field)
                break

        mapping[header] = selected

    return mapping


COSTUME_VENDOR_REPORT_HEADERS = [
    "Vendor Desc",
    "Vendor Abbrev",
    "Vendor Contact",
    "Address1",
    "Address2",
    "City",
    "State",
    "ZIP",
    "Phone",
    "Fax",
    "Email",
    "Required Date",
    "Customer Number",
    "Notes",
]


def _parse_costume_vendor_report(text, preview_limit=None):
    """Repair Studio Director's Costume Vendors CSV when Notes contain raw line breaks.

    The source export can emit multi-line Notes without valid CSV quoting. A physical
    line with the full 14-column vendor shape starts a new vendor; other non-empty
    lines are retained as continuation Notes for the preceding vendor.
    """
    lines = str(text or "").splitlines()
    rows = []
    current = None

    for source_line, raw_line in enumerate(lines[1:], start=2):
        stripped = raw_line.strip()
        if not stripped or stripped == '"':
            continue

        try:
            values = next(csv.reader([raw_line]))
        except csv.Error:
            values = [raw_line]

        if len(values) >= len(COSTUME_VENDOR_REPORT_HEADERS) and str(values[0] or "").strip():
            if len(values) > len(COSTUME_VENDOR_REPORT_HEADERS):
                values = (
                    values[: len(COSTUME_VENDOR_REPORT_HEADERS) - 1]
                    + [",".join(values[len(COSTUME_VENDOR_REPORT_HEADERS) - 1 :])]
                )
            values = values + [""] * (len(COSTUME_VENDOR_REPORT_HEADERS) - len(values))
            row = {
                header: str(values[index] or "").strip()
                for index, header in enumerate(COSTUME_VENDOR_REPORT_HEADERS)
            }
            if not any(row.values()):
                continue
            row["_source_line"] = source_line
            rows.append(row)
            current = row
            continue

        continuation = stripped.strip('"').strip()
        if continuation and current is not None:
            existing = str(current.get("Notes") or "").strip()
            current["Notes"] = f"{existing}\n{continuation}".strip() if existing else continuation

    visible_rows = rows if preview_limit is None else rows[:preview_limit]
    return {
        "headers": list(COSTUME_VENDOR_REPORT_HEADERS),
        "rows": visible_rows,
        "total_rows": len(rows),
    }


def parse_csv_text(text, preview_limit=None):
    first_line = str(text or "").splitlines()[0] if str(text or "").splitlines() else ""
    try:
        first_headers = [value.strip() for value in next(csv.reader([first_line]))]
    except (csv.Error, StopIteration):
        first_headers = []

    if first_headers == COSTUME_VENDOR_REPORT_HEADERS:
        return _parse_costume_vendor_report(text, preview_limit=preview_limit)

    stream = io.StringIO(text)
    reader = csv.DictReader(stream)
    headers = [header.strip() if header else "" for header in (reader.fieldnames or [])]

    if not headers:
        raise ValueError("The CSV does not contain a header row.")
    if any(not header for header in headers):
        raise ValueError("Every CSV column must have a header before Encore can map it.")
    if len(set(headers)) != len(headers):
        raise ValueError("The CSV contains duplicate column headers. Rename them before importing.")

    rows = []
    total_rows = 0
    for row in reader:
        if not any(str(value or "").strip() for value in row.values()):
            continue
        total_rows += 1
        if preview_limit is None or len(rows) < preview_limit:
            rows.append({header: (row.get(header) or "").strip() for header in headers})

    return {"headers": headers, "rows": rows, "total_rows": total_rows}


def parse_csv_upload(uploaded_file, preview_limit=8):
    raw = uploaded_file.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig")
    else:
        text = raw

    parsed = parse_csv_text(text, preview_limit=preview_limit)
    return {
        "headers": parsed["headers"],
        "preview_rows": parsed["rows"],
        "total_rows": parsed["total_rows"],
        "text": text,
    }


def parse_csv_path(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return parse_csv_text(handle.read(), preview_limit=None)


def csv_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def required_mapping_errors(import_type, mapping):
    mapped = {value for value in mapping.values() if value}
    labels = dict(IMPORT_TYPES[import_type]["fields"])
    missing = [field for field in IMPORT_TYPES[import_type].get("required_mapping", []) if field not in mapped]
    return [f"Map a CSV column to {labels[field]}." for field in missing]


def _clean_text(value):
    return " ".join(str(value or "").strip().split())


def _clean_phone(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _parse_bool(value):
    text = normalize_header(value)
    if not text:
        return None, None
    if text in TRUE_VALUES:
        return True, None
    if text in FALSE_VALUES:
        return False, None
    return None, f'"{value}" is not a recognized Yes/No value.'


def _parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None, None

    formats = (
        "%Y-%m-%d",
        "%Y-%b-%d",
        "%Y-%B-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%m/%d/%y",
        "%m-%d-%y",
        "%B %d %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%b %d, %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            pass
    return None, f'"{value}" is not a recognized date.'


def _parse_int(value):
    text = str(value or "").strip()
    if not text:
        return None, None
    try:
        parsed = int(text)
    except ValueError:
        return None, f'"{value}" must be a whole number.'
    if parsed < 0:
        return None, f'"{value}" cannot be negative.'
    return parsed, None


def _parse_decimal(value):
    text = str(value or "").strip()
    if not text:
        return None, None
    text = text.replace("$", "").replace(",", "").strip()
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None, f'"{value}" is not a valid amount.'
    if parsed < Decimal("0"):
        return None, f'"{value}" cannot be negative.'
    return parsed, None


def _normalize_gender(value):
    text = normalize_header(value)
    if not text:
        return "", None
    mapping = {
        "f": "female",
        "female": "female",
        "girl": "female",
        "m": "male",
        "male": "male",
        "boy": "male",
    }
    if text in mapping:
        return mapping[text], None
    return None, f'"{value}" is not a supported student gender.'


def _normalize_gender_restriction(value):
    text = normalize_header(value)
    if not text:
        return None, None
    mapping = {
        "any": "any",
        "all": "any",
        "none": "any",
        "female": "female",
        "f": "female",
        "male": "male",
        "m": "male",
        "other": "other",
    }
    if text in mapping:
        return mapping[text], None
    return None, f'"{value}" is not a supported gender restriction.'


def _normalize_enrollment_status(value):
    text = normalize_header(value)
    if not text:
        return None, None
    mapping = {
        "active": "active",
        "enrolled": "active",
        "current": "active",
        "waitlist": "waitlisted",
        "waitlisted": "waitlisted",
        "dropped": "dropped",
        "drop": "dropped",
        "completed": "completed",
        "complete": "completed",
        "cancelled": "cancelled",
        "canceled": "cancelled",
    }
    if text in mapping:
        return mapping[text], None
    return None, f'"{value}" is not a supported enrollment status.'



KNOWN_EMAIL_DOMAINS = (
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "aol.com",
    "icloud.com",
    "me.com",
    "att.net",
    "comcast.net",
)


def _repair_email_candidate(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""

    # If multiple addresses were entered, use the first recognizable address.
    direct_candidates = re.split(r"[\s,;/|]+", text)
    for candidate in direct_candidates:
        candidate = candidate.strip("<>()[]{}")
        if not candidate:
            continue
        try:
            validate_email(candidate)
            return candidate
        except ValidationError:
            pass

    compact = re.sub(r"\s+", "", text)
    replacements = {
        "gmailcom": "gmail.com",
        "yahoocom": "yahoo.com",
        "hotmailcom": "hotmail.com",
        "outlookcom": "outlook.com",
        "aolcom": "aol.com",
        "icloudcom": "icloud.com",
        "attnet": "att.net",
        "comcastnet": "comcast.net",
    }

    for broken, fixed in replacements.items():
        compact = compact.replace("@" + broken, "@" + fixed)

    if "@" not in compact:
        for domain in KNOWN_EMAIL_DOMAINS:
            marker = domain.replace(".", "")
            index = compact.find(marker)
            if index > 0:
                compact = compact[:index] + "@" + domain + compact[index + len(marker):]
                break
            index = compact.find(domain)
            if index > 0:
                compact = compact[:index] + "@" + compact[index:]
                break

    # Catch missing period with a present @.
    if "@" in compact:
        local, domain = compact.split("@", 1)
        domain = replacements.get(domain, domain)
        compact = f"{local}@{domain}"

    try:
        validate_email(compact)
        return compact
    except ValidationError:
        return ""


def _parse_emergency_contact_text(value):
    text = _clean_text(value)
    if not text:
        return {}

    phone_match = re.search(
        r"(?:(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?:\s*(?:x|ext\.?)\s*\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    phone = phone_match.group(0).strip() if phone_match else ""
    remaining = text
    if phone:
        remaining = (text[:phone_match.start()] + " " + text[phone_match.end():]).strip(" ,-;/")

    relationship = ""
    relationship_match = re.search(
        r"\b(mother|mom|father|dad|parent|guardian|grandmother|grandma|grandfather|grandpa|"
        r"sister|brother|aunt|uncle|spouse|husband|wife|partner|friend)\b",
        remaining,
        flags=re.IGNORECASE,
    )
    if relationship_match:
        relationship = relationship_match.group(0).title()
        remaining = (
            remaining[:relationship_match.start()] + " " + remaining[relationship_match.end():]
        ).strip(" ,-;/")

    return {
        "emergency_contact_name": _clean_text(remaining),
        "emergency_contact_phone": _clean_phone(phone),
        "emergency_contact_relationship": relationship,
    }


def apply_vendor_transform(studio, import_type, source_row, normalized, vendor=None, vendor_step=None):
    if vendor != "studio_director":
        return normalized, []

    normalized = dict(normalized)
    warnings = []

    if vendor_step == "families":
        guardian_last = _clean_text(source_row.get("Guardian Last Name", ""))
        if guardian_last:
            normalized["family_name"] = normalized.get("family_name") or guardian_last
            normalized["primary_contact_last_name"] = guardian_last
        normalized.setdefault("is_active", True)

    elif vendor_step == "guardians":
        family_email = _repair_email_candidate(source_row.get("Email", ""))
        if family_email:
            normalized["family_email"] = family_email
        normalized.setdefault("is_active", True)

        if not normalized.get("family_email"):
            first_name = normalized.get("first_name") or _clean_text(source_row.get("Guardian", ""))
            last_name = normalized.get("last_name") or _clean_text(source_row.get("Guardian Last Name", ""))
            if first_name and last_name:
                guardian = (
                    Guardian.objects.filter(
                        family__studio=studio,
                        first_name__iexact=first_name,
                        last_name__iexact=last_name,
                    )
                    .select_related("family")
                    .first()
                )
                if guardian and guardian.family.primary_email:
                    normalized["family_email"] = guardian.family.primary_email

    elif vendor_step == "students":
        guardian_first = _clean_text(source_row.get("Guardian", ""))
        guardian_last = _clean_text(source_row.get("Last Name", ""))
        if guardian_first and guardian_last:
            guardian_qs = Guardian.objects.filter(
                family__studio=studio,
                first_name__iexact=guardian_first,
                last_name__iexact=guardian_last,
            ).select_related("family")
            matches = list(guardian_qs[:3])
            if len(matches) == 1:
                normalized["_resolved_family_id"] = matches[0].family_id
                if matches[0].family.primary_email:
                    normalized["family_email"] = matches[0].family.primary_email
            elif len(matches) > 1:
                warnings.append(
                    f'Multiple guardians named "{guardian_first} {guardian_last}" exist; family matching needs review.'
                )

    elif vendor_step == "instructors":
        normalized.setdefault("is_active", True)
        contact = _parse_emergency_contact_text(source_row.get("Emergency Contact", ""))
        for key, value in contact.items():
            if value:
                normalized[key] = value

    elif vendor_step == "costume_vendors":
        normalized["name"] = unescape(_clean_text(normalized.get("name")))
        normalized.setdefault("is_active", True)

        raw_contact = _clean_text(normalized.pop("email_or_website", ""))
        if raw_contact:
            repaired_email = _repair_email_candidate(raw_contact)
            if repaired_email:
                normalized["email"] = repaired_email
            else:
                website = raw_contact.strip().rstrip(".,;)")
                if re.match(r"^(?:https?://|www\.)", website, flags=re.IGNORECASE):
                    normalized["website"] = (
                        website if website.lower().startswith(("http://", "https://"))
                        else f"https://{website}"
                    )
                elif re.match(r"^[a-z0-9][a-z0-9.\-]+\.[a-z]{2,}(?:/\S*)?$", website, flags=re.IGNORECASE):
                    normalized["website"] = f"https://{website}"
                else:
                    warnings.append(f'Could not classify vendor Email/Website value "{raw_contact}".')

        required_date = _clean_text(normalized.pop("required_date_source", ""))
        notes = str(normalized.get("notes") or "").strip()
        if required_date:
            required_note = f"Studio Director Required Date: {required_date}"
            if required_note not in notes:
                notes = f"{notes}\n{required_note}".strip() if notes else required_note

        if not normalized.get("website") and notes:
            website_match = re.search(
                r"(?:web\s*site|website)\s*:\s*((?:https?://|www\.)?[^\s,;]+\.[a-z]{2,}(?:/[^\s,;]*)?)",
                notes,
                flags=re.IGNORECASE,
            )
            if website_match:
                website = website_match.group(1).rstrip(".,;)")
                normalized["website"] = (
                    website if website.lower().startswith(("http://", "https://"))
                    else f"https://{website}"
                )

        normalized["notes"] = notes

    elif vendor_step == "costume_vendor_size_charts":
        normalized["vendor_chart"] = unescape(_clean_text(normalized.get("vendor_chart")))

    return normalized, warnings

def normalize_field(field, raw_value):
    if field in BOOLEAN_FIELDS:
        return _parse_bool(raw_value)
    if field in DATE_FIELDS:
        return _parse_date(raw_value)
    if field in INTEGER_FIELDS:
        return _parse_int(raw_value)
    if field in DECIMAL_FIELDS:
        return _parse_decimal(raw_value)
    if field == "gender":
        return _normalize_gender(raw_value)
    if field == "gender_restriction":
        return _normalize_gender_restriction(raw_value)
    if field == "status":
        return _normalize_enrollment_status(raw_value)
    if field in PHONE_FIELDS:
        return _clean_phone(raw_value), None

    value = _clean_text(raw_value)
    if field in EMAIL_FIELDS and value:
        repaired = _repair_email_candidate(value)
        if not repaired:
            return None, f'"{raw_value}" is not a valid email address.'
        value = repaired
    return value, None


def map_and_normalize_row(source_row, mapping):
    normalized = {}
    raw_by_field = {}
    errors = []

    for source_header, target_field in mapping.items():
        if not target_field:
            continue
        raw_value = source_row.get(source_header, "")
        raw_by_field[target_field] = raw_value
        value, error = normalize_field(target_field, raw_value)
        if error:
            errors.append(f"{target_field.replace('_', ' ').title()}: {error}")
        else:
            normalized[target_field] = value

    return normalized, raw_by_field, errors


def _is_blank(value):
    return value in (None, "")


def _family_by_email(studio, email):
    if not email:
        return None
    return (
        Family.objects.filter(studio=studio)
        .filter(Q(primary_email__iexact=email) | Q(guardians__email__iexact=email))
        .distinct()
        .first()
    )


def _flatten_validation_error(exc):
    if hasattr(exc, "message_dict"):
        output = []
        for field, messages in exc.message_dict.items():
            label = field.replace("_", " ").title() if field != "__all__" else "Record"
            for message in messages:
                output.append(f"{label}: {message}")
        return output
    return list(exc.messages)




def _validate_existing_update(existing, normalized, direct_fields, relation_updates=None):
    candidate = copy.copy(existing)
    for field in direct_fields:
        if field in normalized and not _is_blank(normalized[field]):
            setattr(candidate, field, normalized[field])
    for field, value in (relation_updates or {}).items():
        if value is not None:
            setattr(candidate, field, value)
    try:
        candidate.full_clean()
    except ValidationError as exc:
        return _flatten_validation_error(exc)
    return []

def _changed(existing, field, value):
    if _is_blank(value):
        return False
    current = getattr(existing, field)
    if isinstance(current, Decimal) and value is not None:
        return current != Decimal(value)
    return current != value


def _result(row_number, source_row, status, label, reason, normalized, errors=None, warnings=None, key=None):
    return {
        "row_number": row_number,
        "source_row": source_row,
        "status": status,
        "label": label,
        "reason": reason,
        "normalized": normalized,
        "errors": errors or [],
        "warnings": warnings or [],
        "key": key,
    }


def _analyze_family(studio, row_number, source_row, normalized):
    identity_present = any(
        normalized.get(field)
        for field in ("family_name", "primary_contact_first_name", "primary_contact_last_name", "primary_email")
    )
    label = normalized.get("family_name") or " ".join(
        part for part in [normalized.get("primary_contact_first_name"), normalized.get("primary_contact_last_name")] if part
    ) or normalized.get("primary_email") or f"Family row {row_number}"

    if not identity_present:
        return _result(row_number, source_row, "error", label, "Family has no usable identity information.", normalized,
                       errors=["Provide a family name, primary contact name, or primary email."], key=None)

    existing = None
    if normalized.get("primary_email"):
        existing = Family.objects.filter(studio=studio, primary_email__iexact=normalized["primary_email"]).first()
    if existing is None and normalized.get("family_name"):
        existing = Family.objects.filter(studio=studio, family_name__iexact=normalized["family_name"]).first()

    key = (
        "family",
        (normalized.get("primary_email") or "").lower(),
        (normalized.get("family_name") or "").lower(),
        (normalized.get("primary_contact_first_name") or "").lower(),
        (normalized.get("primary_contact_last_name") or "").lower(),
    )

    direct_fields = [field for field, _ in IMPORT_TYPES["families"]["fields"]]
    if existing:
        changed = [field for field in direct_fields if field in normalized and _changed(existing, field, normalized[field])]
        if not changed:
            return _result(row_number, source_row, "skip", label, "Matches an existing family; no mapped values would change.", normalized, key=key)
        validation_errors = _validate_existing_update(existing, normalized, direct_fields)
        if validation_errors:
            return _result(row_number, source_row, "error", label, validation_errors[0], normalized, errors=validation_errors, key=key)
        return _result(row_number, source_row, "update", label, f"Matches existing family #{existing.pk}; {len(changed)} mapped field(s) would change.", normalized, key=key)

    candidate_kwargs = {field: value for field, value in normalized.items() if field in direct_fields and not _is_blank(value)}
    candidate = Family(studio=studio, **candidate_kwargs)
    try:
        candidate.full_clean()
    except ValidationError as exc:
        errors = _flatten_validation_error(exc)
        return _result(row_number, source_row, "error", label, errors[0], normalized, errors=errors, key=key)
    return _result(row_number, source_row, "create", label, "New family record.", normalized, key=key)


def _analyze_instructor(studio, row_number, source_row, normalized):
    errors = []
    for field, label in (("first_name", "First name"), ("last_name", "Last name")):
        if not normalized.get(field):
            errors.append(f"{label} is required.")
    label = " ".join(part for part in [normalized.get("first_name"), normalized.get("last_name")] if part) or f"Instructor row {row_number}"
    key = ("instructor", (normalized.get("email") or "").lower(), label.lower())
    if errors:
        return _result(row_number, source_row, "error", label, errors[0], normalized, errors=errors, key=key)

    existing = None
    if normalized.get("email"):
        existing = Instructor.objects.filter(studio=studio, email__iexact=normalized["email"]).first()
    if existing is None:
        existing = Instructor.objects.filter(
            studio=studio,
            first_name__iexact=normalized["first_name"],
            last_name__iexact=normalized["last_name"],
        ).first()

    direct_fields = [field for field, _ in IMPORT_TYPES["instructors"]["fields"]]
    if existing:
        changed = [field for field in direct_fields if field in normalized and _changed(existing, field, normalized[field])]
        if not changed:
            return _result(row_number, source_row, "skip", label, "Matches an existing instructor; no mapped values would change.", normalized, key=key)
        validation_errors = _validate_existing_update(existing, normalized, direct_fields)
        if validation_errors:
            return _result(row_number, source_row, "error", label, validation_errors[0], normalized, errors=validation_errors, key=key)
        return _result(row_number, source_row, "update", label, f"Matches existing instructor #{existing.pk}; {len(changed)} mapped field(s) would change.", normalized, key=key)

    kwargs = {field: value for field, value in normalized.items() if field in direct_fields and not _is_blank(value)}
    candidate = Instructor(studio=studio, **kwargs)
    try:
        candidate.full_clean()
    except ValidationError as exc:
        validation_errors = _flatten_validation_error(exc)
        return _result(row_number, source_row, "error", label, validation_errors[0], normalized, errors=validation_errors, key=key)
    return _result(row_number, source_row, "create", label, "New instructor record.", normalized, key=key)


def _analyze_student(studio, row_number, source_row, normalized):
    errors = []
    for field, label in (("first_name", "First name"), ("last_name", "Last name"), ("birthday", "Birthday")):
        if not normalized.get(field):
            errors.append(f"{label} is required.")

    label = " ".join(part for part in [normalized.get("first_name"), normalized.get("last_name")] if part) or f"Student row {row_number}"
    birthday = normalized.get("birthday")
    key = ("student", label.lower(), birthday.isoformat() if birthday else "")
    family = None
    resolved_family_id = normalized.get("_resolved_family_id")
    if resolved_family_id:
        family = Family.objects.filter(studio=studio, pk=resolved_family_id).first()
    family_email = normalized.get("family_email")
    if family_email and family is None:
        family = _family_by_email(studio, family_email)
        if family is None:
            errors.append(f'No family or guardian in this studio matches "{family_email}".')

    if birthday:
        today = date.today()
        age = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
        if age < 18 and family is None:
            errors.append("Students under 18 must resolve to an existing family/guardian before import.")

    if errors:
        return _result(row_number, source_row, "error", label, errors[0], normalized, errors=errors, key=key)

    existing = Student.objects.filter(
        studio=studio,
        first_name__iexact=normalized["first_name"],
        last_name__iexact=normalized["last_name"],
        birthday=birthday,
    ).first()

    direct_fields = [
        "first_name", "last_name", "birthday", "gender", "medical_conditions", "allergies", "comments",
        "performing", "is_active", "emergency_contact_name", "emergency_contact_phone",
        "emergency_contact_relationship", "how_did_you_hear_about_us",
    ]
    if existing:
        changed = [field for field in direct_fields if field in normalized and _changed(existing, field, normalized[field])]
        if family_email and family and existing.family_id != family.id:
            changed.append("family")
        if not changed:
            return _result(row_number, source_row, "skip", label, "Matches an existing student; no mapped values would change.", normalized, key=key)
        validation_errors = _validate_existing_update(existing, normalized, direct_fields, {"family": family} if family_email else None)
        if validation_errors:
            return _result(row_number, source_row, "error", label, validation_errors[0], normalized, errors=validation_errors, key=key)
        return _result(row_number, source_row, "update", label, f"Matches existing student #{existing.pk}; {len(changed)} mapped field(s) would change.", normalized, key=key)

    kwargs = {field: value for field, value in normalized.items() if field in direct_fields and not _is_blank(value)}
    candidate = Student(studio=studio, family=family, **kwargs)
    try:
        candidate.full_clean()
    except ValidationError as exc:
        validation_errors = _flatten_validation_error(exc)
        return _result(row_number, source_row, "error", label, validation_errors[0], normalized, errors=validation_errors, key=key)
    return _result(row_number, source_row, "create", label, "New student record.", normalized, key=key)


def _analyze_guardian(studio, row_number, source_row, normalized):
    errors = []
    for field, label in (("first_name", "First name"), ("last_name", "Last name")):
        if not normalized.get(field):
            errors.append(f"{label} is required.")

    family = _family_by_email(studio, normalized.get("family_email")) if normalized.get("family_email") else None
    if family is None and normalized.get("first_name") and normalized.get("last_name"):
        family = Family.objects.filter(
            studio=studio,
            primary_contact_first_name__iexact=normalized["first_name"],
            primary_contact_last_name__iexact=normalized["last_name"],
        ).first()
        if family is None:
            family = Family.objects.filter(
                studio=studio,
                family_name__iexact=normalized["last_name"],
                primary_contact_first_name__iexact=normalized["first_name"],
            ).first()
    if family is None:
        errors.append("No previously imported family could be matched for this guardian.")

    label = " ".join(part for part in [normalized.get("first_name"), normalized.get("last_name")] if part) or f"Guardian row {row_number}"
    key = ("guardian", family.pk if family else normalized.get("family_email", ""), (normalized.get("email") or label).lower())
    if errors:
        return _result(row_number, source_row, "error", label, errors[0], normalized, errors=errors, key=key)

    existing = None
    if normalized.get("email"):
        existing = Guardian.objects.filter(family=family, email__iexact=normalized["email"]).first()
    if existing is None:
        existing = Guardian.objects.filter(
            family=family,
            first_name__iexact=normalized["first_name"],
            last_name__iexact=normalized["last_name"],
        ).first()

    direct_fields = [field for field, _ in IMPORT_TYPES["guardians"]["fields"] if field != "family_email"]
    if existing:
        changed = [field for field in direct_fields if field in normalized and _changed(existing, field, normalized[field])]
        if not changed:
            return _result(row_number, source_row, "skip", label, "Matches an existing guardian; no mapped values would change.", normalized, key=key)
        validation_errors = _validate_existing_update(existing, normalized, direct_fields)
        if validation_errors:
            return _result(row_number, source_row, "error", label, validation_errors[0], normalized, errors=validation_errors, key=key)
        return _result(row_number, source_row, "update", label, f"Matches existing guardian #{existing.pk}; {len(changed)} mapped field(s) would change.", normalized, key=key)

    kwargs = {field: value for field, value in normalized.items() if field in direct_fields and not _is_blank(value)}
    candidate = Guardian(family=family, **kwargs)
    try:
        candidate.full_clean()
    except ValidationError as exc:
        validation_errors = _flatten_validation_error(exc)
        return _result(row_number, source_row, "error", label, validation_errors[0], normalized, errors=validation_errors, key=key)
    return _result(row_number, source_row, "create", label, "New guardian record.", normalized, key=key)


def _analyze_class(studio, row_number, source_row, normalized):
    errors = []
    required = (
        ("class_id", "Class ID"), ("name", "Class name"), ("season", "Season"),
        ("class_type", "Class type"), ("instructor_email", "Instructor email"),
    )
    for field, label in required:
        if not normalized.get(field):
            errors.append(f"{label} is required.")

    season = Season.objects.filter(studio=studio, name__iexact=normalized.get("season", "")).first() if normalized.get("season") else None
    class_type = ClassType.objects.filter(studio=studio, name__iexact=normalized.get("class_type", "")).first() if normalized.get("class_type") else None
    instructor = Instructor.objects.filter(studio=studio, email__iexact=normalized.get("instructor_email", "")).first() if normalized.get("instructor_email") else None
    if normalized.get("season") and season is None:
        errors.append(f'Season "{normalized["season"]}" does not exist in this studio.')
    if normalized.get("class_type") and class_type is None:
        errors.append(f'Class type "{normalized["class_type"]}" does not exist in this studio.')
    if normalized.get("instructor_email") and instructor is None:
        errors.append(f'Instructor "{normalized["instructor_email"]}" does not exist in this studio.')

    label = normalized.get("name") or normalized.get("class_id") or f"Class row {row_number}"
    key = ("class", (normalized.get("class_id") or "").lower())
    if errors:
        return _result(row_number, source_row, "error", label, errors[0], normalized, errors=errors, key=key)

    existing = Class.objects.filter(studio=studio, class_id__iexact=normalized["class_id"]).first()
    direct_fields = [
        "class_id", "name", "description", "dress_code", "capacity", "min_age", "max_age",
        "gender_restriction", "tuition_amount", "is_active", "registration_open", "notes",
    ]
    if existing:
        changed = [field for field in direct_fields if field in normalized and _changed(existing, field, normalized[field])]
        if existing.season_id != season.id:
            changed.append("season")
        if existing.class_type_id != class_type.id:
            changed.append("class_type")
        if existing.instructor_id != instructor.id:
            changed.append("instructor")
        if not changed:
            return _result(row_number, source_row, "skip", label, "Matches an existing class; no mapped values would change.", normalized, key=key)
        validation_errors = _validate_existing_update(
            existing,
            normalized,
            direct_fields,
            {"season": season, "class_type": class_type, "instructor": instructor},
        )
        if validation_errors:
            return _result(row_number, source_row, "error", label, validation_errors[0], normalized, errors=validation_errors, key=key)
        return _result(row_number, source_row, "update", label, f"Matches existing class #{existing.pk}; {len(changed)} mapped field(s) would change.", normalized, key=key)

    kwargs = {field: value for field, value in normalized.items() if field in direct_fields and not _is_blank(value)}
    if "capacity" not in kwargs:
        kwargs["capacity"] = 20
    if "gender_restriction" not in kwargs or kwargs["gender_restriction"] is None:
        kwargs["gender_restriction"] = "any"
    candidate = Class(studio=studio, season=season, class_type=class_type, instructor=instructor, **kwargs)
    try:
        candidate.full_clean()
    except ValidationError as exc:
        validation_errors = _flatten_validation_error(exc)
        return _result(row_number, source_row, "error", label, validation_errors[0], normalized, errors=validation_errors, key=key)
    return _result(row_number, source_row, "create", label, "New class record.", normalized, key=key)


def _analyze_enrollment(studio, row_number, source_row, normalized):
    errors = []
    required = (
        ("student_first_name", "Student first name"), ("student_last_name", "Student last name"),
        ("student_birthday", "Student birthday"), ("class_id", "Class ID"),
    )
    for field, label in required:
        if not normalized.get(field):
            errors.append(f"{label} is required.")

    student = None
    if normalized.get("student_first_name") and normalized.get("student_last_name") and normalized.get("student_birthday"):
        student = Student.objects.filter(
            studio=studio,
            first_name__iexact=normalized["student_first_name"],
            last_name__iexact=normalized["student_last_name"],
            birthday=normalized["student_birthday"],
        ).first()
        if student is None:
            errors.append("The referenced student does not exist in this studio.")

    class_instance = Class.objects.filter(studio=studio, class_id__iexact=normalized.get("class_id", "")).first() if normalized.get("class_id") else None
    if normalized.get("class_id") and class_instance is None:
        errors.append(f'Class ID "{normalized["class_id"]}" does not exist in this studio.')

    label = " ".join(part for part in [normalized.get("student_first_name"), normalized.get("student_last_name")] if part)
    if normalized.get("class_id"):
        label = f"{label} → {normalized['class_id']}".strip()
    label = label or f"Enrollment row {row_number}"
    birthday = normalized.get("student_birthday")
    key = (
        "enrollment",
        (normalized.get("student_first_name") or "").lower(),
        (normalized.get("student_last_name") or "").lower(),
        birthday.isoformat() if birthday else "",
        (normalized.get("class_id") or "").lower(),
    )
    if errors:
        return _result(row_number, source_row, "error", label, errors[0], normalized, errors=errors, key=key)

    existing = Enrollment.objects.filter(student=student, class_instance=class_instance).first()
    status = normalized.get("status") or "active"
    tuition_override = normalized.get("tuition_override")
    notes = normalized.get("notes", "")

    if existing:
        changed = []
        if "status" in normalized and normalized.get("status") and existing.status != status:
            changed.append("status")
        if "tuition_override" in normalized and tuition_override is not None and existing.tuition_override != tuition_override:
            changed.append("tuition_override")
        if "notes" in normalized and notes and existing.notes != notes:
            changed.append("notes")
        if not changed:
            return _result(row_number, source_row, "skip", label, "Matches an existing enrollment; no mapped values would change.", normalized, key=key)
    candidate = Enrollment(
        pk=existing.pk if existing else None,
        student=student,
        class_instance=class_instance,
        status=status if not existing or "status" in normalized else existing.status,
        source=Enrollment.Source.IMPORT,
        tuition_override=tuition_override if "tuition_override" in normalized else (existing.tuition_override if existing else None),
        notes=notes if "notes" in normalized and notes else (existing.notes if existing else ""),
    )
    try:
        candidate.full_clean()
    except ValidationError as exc:
        validation_errors = _flatten_validation_error(exc)
        return _result(row_number, source_row, "error", label, validation_errors[0], normalized, errors=validation_errors, key=key)

    if existing:
        return _result(row_number, source_row, "update", label, f"Matches existing enrollment #{existing.pk}; mapped values would be updated.", normalized, key=key)
    return _result(row_number, source_row, "create", label, "New enrollment record.", normalized, key=key)


VENDOR_DIRECT_FIELDS = [
    "name",
    "abbreviation",
    "contact_name",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "postal_code",
    "phone",
    "fax",
    "email",
    "customer_number",
    "website",
    "notes",
    "is_active",
]


def _analyze_costume_vendor(studio, row_number, source_row, normalized):
    name = unescape(_clean_text(normalized.get("name")))
    normalized["name"] = name
    if not name:
        return _result(
            row_number,
            source_row,
            "error",
            f"Vendor row {row_number}",
            "Vendor name is required.",
            normalized,
            errors=["Vendor name is required."],
            key=None,
        )

    existing = Vendor.objects.filter(studio=studio, name__iexact=name).first()
    key = ("costume_vendor", name.casefold())

    if existing:
        changed = [
            field
            for field in VENDOR_DIRECT_FIELDS
            if field in normalized
            and not _is_blank(normalized[field])
            and _changed(existing, field, normalized[field])
        ]
        if not changed:
            return _result(
                row_number,
                source_row,
                "skip",
                name,
                "Matches an existing costume vendor; no imported values would change.",
                normalized,
                key=key,
            )
        validation_errors = _validate_existing_update(existing, normalized, VENDOR_DIRECT_FIELDS)
        if validation_errors:
            return _result(
                row_number,
                source_row,
                "error",
                name,
                validation_errors[0],
                normalized,
                errors=validation_errors,
                key=key,
            )
        return _result(
            row_number,
            source_row,
            "update",
            name,
            f"Matches existing vendor #{existing.pk}; {len(changed)} imported field(s) would change.",
            normalized,
            key=key,
        )

    candidate = Vendor(
        studio=studio,
        **{
            field: normalized[field]
            for field in VENDOR_DIRECT_FIELDS
            if field in normalized and not _is_blank(normalized[field])
        },
    )
    try:
        candidate.full_clean()
    except ValidationError as exc:
        errors = _flatten_validation_error(exc)
        return _result(row_number, source_row, "error", name, errors[0], normalized, errors=errors, key=key)

    return _result(row_number, source_row, "create", name, "New costume vendor.", normalized, key=key)


def _size_chart_gender(chart_name):
    text = str(chart_name or "").casefold()
    if re.search(r"\b(boy|boys|men|mens|male)\b", text):
        return VendorSizeChart.Gender.MALE
    if re.search(r"\b(girl|girls|women|womens|female)\b", text):
        return VendorSizeChart.Gender.FEMALE
    return VendorSizeChart.Gender.ALL


def _resolve_vendor_chart(studio, compound):
    compound = unescape(_clean_text(compound))
    if not compound:
        return None, ""

    vendors = list(Vendor.objects.filter(studio=studio, is_active=True).order_by("name"))
    vendors.sort(key=lambda item: len(item.name), reverse=True)
    compound_folded = compound.casefold()

    for vendor in vendors:
        vendor_name = unescape(_clean_text(vendor.name))
        folded = vendor_name.casefold()
        if compound_folded == folded:
            return vendor, "Default"
        prefix = folded + "/"
        if compound_folded.startswith(prefix):
            return vendor, compound[len(vendor_name) + 1 :].strip() or "Default"

    return None, ""


def _analyze_vendor_size_entry(studio, row_number, source_row, normalized):
    compound = unescape(_clean_text(normalized.get("vendor_chart")))
    size_label = _clean_text(normalized.get("size_label"))
    vendor, chart_name = _resolve_vendor_chart(studio, compound)
    errors = []

    if not vendor:
        errors.append(
            f'No existing Encore costume vendor matches "{compound}". Import Costume Vendors first.'
        )
    if not chart_name:
        errors.append("The Studio Director Vendor value does not include a usable chart name.")
    if not size_label:
        errors.append("Size is required.")

    girth_min = normalized.get("girth_min")
    girth_max = normalized.get("girth_max")
    if girth_min is not None and girth_max is not None and girth_min > girth_max:
        errors.append("Girth From cannot be greater than Girth To.")

    label = f"{compound} — {size_label}" if size_label else (compound or f"Size chart row {row_number}")
    key = (
        "costume_vendor_size",
        vendor.pk if vendor else compound.casefold(),
        chart_name.casefold(),
        size_label.casefold(),
    )

    if errors:
        return _result(row_number, source_row, "error", label, errors[0], normalized, errors=errors, key=key)

    chart = VendorSizeChart.objects.filter(vendor=vendor, name__iexact=chart_name).first()
    entry = None
    if chart:
        entry = chart.entries.filter(size_label__iexact=size_label).first()

    normalized["_vendor_id"] = vendor.pk
    normalized["_chart_name"] = chart_name
    normalized["_chart_gender"] = _size_chart_gender(chart_name)
    normalized["_sort_order"] = max(0, row_number - 2)

    if entry:
        changed = (
            entry.girth_min != girth_min
            or entry.girth_max != girth_max
            or entry.notes != (normalized.get("notes") or "")
            or (chart and chart.gender != normalized["_chart_gender"])
        )
        if not changed:
            return _result(
                row_number,
                source_row,
                "skip",
                label,
                "This vendor size entry already matches Encore.",
                normalized,
                key=key,
            )
        return _result(
            row_number,
            source_row,
            "update",
            label,
            f"Updates {vendor.name} / {chart_name} / {size_label}.",
            normalized,
            key=key,
        )

    return _result(
        row_number,
        source_row,
        "create",
        label,
        f"Adds {size_label} to {vendor.name} / {chart_name}.",
        normalized,
        key=key,
    )


ANALYZERS = {
    "students": _analyze_student,
    "families": _analyze_family,
    "guardians": _analyze_guardian,
    "instructors": _analyze_instructor,
    "classes": _analyze_class,
    "enrollments": _analyze_enrollment,
    "costume_vendors": _analyze_costume_vendor,
    "costume_vendor_size_charts": _analyze_vendor_size_entry,
}


def analyze_import_rows(studio, import_type, rows, mapping, vendor=None, vendor_step=None):
    results = []
    seen_keys = {}
    analyzer = ANALYZERS[import_type]

    for row_number, source_row in enumerate(rows, start=2):
        normalized, _raw_by_field, normalization_errors = map_and_normalize_row(source_row, mapping)
        vendor_warnings = []
        if not normalization_errors:
            normalized, vendor_warnings = apply_vendor_transform(
                studio,
                import_type,
                source_row,
                normalized,
                vendor=vendor,
                vendor_step=vendor_step,
            )
        if normalization_errors:
            label = next((value for value in normalized.values() if isinstance(value, str) and value), f"Row {row_number}")
            result = _result(
                row_number,
                source_row,
                "error",
                str(label),
                normalization_errors[0],
                normalized,
                errors=normalization_errors,
            )
        else:
            result = analyzer(studio, row_number, source_row, normalized)
            if vendor_warnings:
                result["warnings"] = list(result.get("warnings") or []) + vendor_warnings

        key = result.get("key")
        if key and result["status"] != "error":
            if key in seen_keys:
                first_row = seen_keys[key]
                result["status"] = "skip"
                result["reason"] = f"Duplicate of CSV row {first_row}; only the first occurrence will be considered."
                result["warnings"] = ["Duplicate row in this CSV."]
            else:
                seen_keys[key] = row_number

        results.append(result)

    counts = {"total": len(results), "create": 0, "update": 0, "skip": 0, "error": 0}
    for result in results:
        counts[result["status"]] += 1

    return {"results": results, "counts": counts}


def _direct_fields_for(import_type):
    excluded = {
        "students": {"family_email"},
        "guardians": {"family_email"},
        "classes": {"season", "class_type", "instructor_email"},
        "enrollments": {"student_first_name", "student_last_name", "student_birthday", "class_id"},
        "costume_vendors": {"email_or_website", "required_date_source"},
        "costume_vendor_size_charts": {"vendor_chart"},
    }
    return [
        field
        for field, _label in IMPORT_TYPES[import_type]["fields"]
        if field not in excluded.get(import_type, set())
    ]


def _nonblank_kwargs(normalized, fields):
    return {
        field: normalized[field]
        for field in fields
        if field in normalized and not _is_blank(normalized[field])
    }


def _apply_nonblank_updates(instance, normalized, fields):
    changed_fields = []
    for field in fields:
        if field not in normalized or _is_blank(normalized[field]):
            continue
        value = normalized[field]
        if _changed(instance, field, value):
            setattr(instance, field, value)
            changed_fields.append(field)
    return changed_fields


def _commit_family(studio, normalized):
    existing = None
    if normalized.get("primary_email"):
        existing = Family.objects.filter(
            studio=studio,
            primary_email__iexact=normalized["primary_email"],
        ).first()
    if existing is None and normalized.get("family_name"):
        existing = Family.objects.filter(
            studio=studio,
            family_name__iexact=normalized["family_name"],
        ).first()

    direct_fields = _direct_fields_for("families")
    if existing:
        before_data = snapshot_instance(existing)
        changed = _apply_nonblank_updates(existing, normalized, direct_fields)
        existing.full_clean()
        if changed:
            existing.save()
        return existing, False, before_data

    obj = Family(studio=studio, **_nonblank_kwargs(normalized, direct_fields))
    obj.full_clean()
    obj.save()
    return obj, True, {}


def _commit_instructor(studio, normalized):
    existing = None
    if normalized.get("email"):
        existing = Instructor.objects.filter(
            studio=studio,
            email__iexact=normalized["email"],
        ).first()
    if existing is None:
        existing = Instructor.objects.filter(
            studio=studio,
            first_name__iexact=normalized.get("first_name", ""),
            last_name__iexact=normalized.get("last_name", ""),
        ).first()

    direct_fields = _direct_fields_for("instructors")
    if existing:
        before_data = snapshot_instance(existing)
        changed = _apply_nonblank_updates(existing, normalized, direct_fields)
        existing.full_clean()
        if changed:
            existing.save()
        return existing, False, before_data

    obj = Instructor(studio=studio, **_nonblank_kwargs(normalized, direct_fields))
    obj.full_clean()
    obj.save()
    return obj, True, {}


def _commit_student(studio, normalized):
    family = None
    if normalized.get("_resolved_family_id"):
        family = Family.objects.filter(studio=studio, pk=normalized["_resolved_family_id"]).first()
    if family is None:
        family = _family_by_email(studio, normalized.get("family_email"))
    existing = Student.objects.filter(
        studio=studio,
        first_name__iexact=normalized.get("first_name", ""),
        last_name__iexact=normalized.get("last_name", ""),
        birthday=normalized.get("birthday"),
    ).first()
    direct_fields = _direct_fields_for("students")

    if existing:
        before_data = snapshot_instance(existing)
        changed = _apply_nonblank_updates(existing, normalized, direct_fields)
        if normalized.get("family_email") and family and existing.family_id != family.id:
            existing.family = family
            changed.append("family")
        existing.full_clean()
        if changed:
            existing.save()
        return existing, False, before_data

    obj = Student(
        studio=studio,
        family=family,
        **_nonblank_kwargs(normalized, direct_fields),
    )
    obj.full_clean()
    obj.save()
    return obj, True, {}


def _commit_guardian(studio, normalized):
    family = _family_by_email(studio, normalized.get("family_email"))
    if family is None and normalized.get("first_name") and normalized.get("last_name"):
        family = Family.objects.filter(
            studio=studio,
            primary_contact_first_name__iexact=normalized["first_name"],
            primary_contact_last_name__iexact=normalized["last_name"],
        ).first()
        if family is None:
            family = Family.objects.filter(
                studio=studio,
                family_name__iexact=normalized["last_name"],
                primary_contact_first_name__iexact=normalized["first_name"],
            ).first()
    existing = None
    if normalized.get("email"):
        existing = Guardian.objects.filter(
            family=family,
            email__iexact=normalized["email"],
        ).first()
    if existing is None:
        existing = Guardian.objects.filter(
            family=family,
            first_name__iexact=normalized.get("first_name", ""),
            last_name__iexact=normalized.get("last_name", ""),
        ).first()

    direct_fields = _direct_fields_for("guardians")
    if existing:
        before_data = snapshot_instance(existing)
        changed = _apply_nonblank_updates(existing, normalized, direct_fields)
        existing.full_clean()
        if changed:
            existing.save()
        return existing, False, before_data

    obj = Guardian(family=family, **_nonblank_kwargs(normalized, direct_fields))
    obj.full_clean()
    obj.save()
    return obj, True, {}


def _commit_class(studio, normalized):
    season = Season.objects.filter(
        studio=studio,
        name__iexact=normalized.get("season", ""),
    ).first()
    class_type = ClassType.objects.filter(
        studio=studio,
        name__iexact=normalized.get("class_type", ""),
    ).first()
    instructor = Instructor.objects.filter(
        studio=studio,
        email__iexact=normalized.get("instructor_email", ""),
    ).first()

    existing = Class.objects.filter(
        studio=studio,
        class_id__iexact=normalized.get("class_id", ""),
    ).first()
    direct_fields = _direct_fields_for("classes")

    if existing:
        before_data = snapshot_instance(existing)
        changed = _apply_nonblank_updates(existing, normalized, direct_fields)
        for field, relation in (
            ("season", season),
            ("class_type", class_type),
            ("instructor", instructor),
        ):
            if relation is not None and getattr(existing, f"{field}_id") != relation.id:
                setattr(existing, field, relation)
                changed.append(field)
        existing.full_clean()
        if changed:
            existing.save()
        return existing, False, before_data

    kwargs = _nonblank_kwargs(normalized, direct_fields)
    kwargs.setdefault("capacity", 20)
    kwargs.setdefault("gender_restriction", "any")
    obj = Class(
        studio=studio,
        season=season,
        class_type=class_type,
        instructor=instructor,
        **kwargs,
    )
    obj.full_clean()
    obj.save()
    return obj, True, {}


def _commit_enrollment(studio, normalized):
    from django.utils import timezone

    student = Student.objects.filter(
        studio=studio,
        first_name__iexact=normalized.get("student_first_name", ""),
        last_name__iexact=normalized.get("student_last_name", ""),
        birthday=normalized.get("student_birthday"),
    ).first()
    class_instance = Class.objects.filter(
        studio=studio,
        class_id__iexact=normalized.get("class_id", ""),
    ).first()
    existing = Enrollment.objects.filter(
        student=student,
        class_instance=class_instance,
    ).first()

    status = normalized.get("status") or (existing.status if existing else Enrollment.Status.ACTIVE)
    tuition_override = (
        normalized.get("tuition_override")
        if "tuition_override" in normalized
        else (existing.tuition_override if existing else None)
    )
    notes = (
        normalized.get("notes")
        if normalized.get("notes")
        else (existing.notes if existing else "")
    )

    candidate = Enrollment(
        pk=existing.pk if existing else None,
        student=student,
        class_instance=class_instance,
        status=status,
        source=existing.source if existing else Enrollment.Source.IMPORT,
        tuition_override=tuition_override,
        notes=notes,
    )
    candidate.full_clean()

    if existing:
        before_data = snapshot_instance(existing)
        updates = {"updated_at": timezone.now()}
        if "status" in normalized and normalized.get("status"):
            updates["status"] = status
        if "tuition_override" in normalized and normalized.get("tuition_override") is not None:
            updates["tuition_override"] = tuition_override
        if "notes" in normalized and normalized.get("notes"):
            updates["notes"] = notes
        Enrollment.objects.filter(pk=existing.pk).update(**updates)
        existing.refresh_from_db()
        return existing, False, before_data

    # bulk_create deliberately bypasses Enrollment post_save billing automation.
    # Imported historical/current enrollment membership should not manufacture
    # tuition charges merely because a migration was run.
    created = Enrollment(
        student=student,
        class_instance=class_instance,
        status=status,
        source=Enrollment.Source.IMPORT,
        tuition_override=tuition_override,
        notes=notes,
    )
    created.full_clean()
    Enrollment.objects.bulk_create([created])
    return created, True, {}



def _commit_costume_vendor(studio, normalized):
    name = unescape(_clean_text(normalized.get("name")))
    existing = Vendor.objects.filter(studio=studio, name__iexact=name).first()
    before_data = snapshot_instance(existing) if existing else {}

    if existing:
        _apply_nonblank_updates(existing, normalized, VENDOR_DIRECT_FIELDS)
        existing.full_clean()
        existing.save()
        return existing, False, before_data

    created = Vendor(
        studio=studio,
        **{
            field: normalized[field]
            for field in VENDOR_DIRECT_FIELDS
            if field in normalized and not _is_blank(normalized[field])
        },
    )
    created.full_clean()
    created.save()
    return created, True, {}


def _commit_vendor_size_entry(studio, normalized):
    vendor = Vendor.objects.get(studio=studio, pk=normalized["_vendor_id"])
    chart_name = normalized["_chart_name"]
    chart = VendorSizeChart.objects.filter(vendor=vendor, name__iexact=chart_name).first()
    if chart is None:
        chart = VendorSizeChart.objects.create(
            vendor=vendor,
            name=chart_name,
            gender=normalized.get("_chart_gender") or VendorSizeChart.Gender.ALL,
        )
    elif chart.gender != normalized.get("_chart_gender"):
        chart.gender = normalized.get("_chart_gender") or VendorSizeChart.Gender.ALL
        chart.save(update_fields=["gender", "updated_at"])

    size_label = _clean_text(normalized.get("size_label"))
    entry = chart.entries.filter(size_label__iexact=size_label).first()
    before_data = snapshot_instance(entry) if entry else {}
    created = entry is None

    if entry is None:
        entry = VendorSizeEntry(chart=chart, size_label=size_label)

    entry.size_label = size_label
    entry.girth_min = normalized.get("girth_min")
    entry.girth_max = normalized.get("girth_max")
    entry.notes = normalized.get("notes") or ""
    entry.sort_order = normalized.get("_sort_order") or 0
    entry.full_clean()
    entry.save()
    return entry, created, before_data


COMMITTERS = {
    "students": _commit_student,
    "families": _commit_family,
    "guardians": _commit_guardian,
    "instructors": _commit_instructor,
    "classes": _commit_class,
    "enrollments": _commit_enrollment,
    "costume_vendors": _commit_costume_vendor,
    "costume_vendor_size_charts": _commit_vendor_size_entry,
}


def commit_import_result(studio, import_type, result):
    """Commit one analyzed create/update row and return (object, created, before_data)."""
    return COMMITTERS[import_type](studio, result["normalized"])
