from collections import OrderedDict

STUDIO_DIRECTOR_STEPS = OrderedDict([
    ("families", {
        "number": 1,
        "title": "Families",
        "report": "Family List",
        "import_type": "families",
        "description": "Create family/household records before guardians and students.",
        "status_note": "Verified Studio Director report and mapping.",
        "mapping": {
            "Guardian": "primary_contact_first_name",
            "Guardian Last Name": "family_name",
            "Address 1": "address_line_1",
            "Address 2": "address_line_2",
            "City": "city",
            "State": "state",
            "ZIP": "postal_code",
            "Phone 1": "primary_phone",
            "Phone 2": "secondary_phone",
            "Phone 3": "",
            "Email": "primary_email",
            "Emergency Contact": "emergency_contact_name",
            "Emergency Contact Phone": "emergency_contact_phone",
            "Enrollment Blocked": "",
            "Balance Due": "",
        },
    }),
    ("guardians", {
        "number": 2,
        "title": "Parents / Guardians",
        "report": "Family List",
        "import_type": "guardians",
        "description": "Reuse Family List to create guardian records and attach them to the families from Step 1.",
        "mapping": {
            "Guardian": "first_name",
            "Guardian Last Name": "last_name",
            "Phone 1": "phone",
            "Email": "email",
        },
    }),
    ("students", {
        "number": 3,
        "title": "Students",
        "report": "Student List",
        "import_type": "students",
        "description": "Import students after guardians so minors can resolve to the correct family.",
        "mapping": {
            "First Name": "first_name",
            "Student Last Name": "last_name",
            "Dob": "birthday",
            "DOB": "birthday",
            "Gender": "gender",
            "Performing": "performing",
            "Waiver": "paper_waiver_on_file",
        },
    }),
    ("student_measurements", {
        "number": 4,
        "title": "Student Measurements",
        "report": "Costume / Student Measurement Worksheet → cleaned Encore CSV",
        "import_type": None,
        "description": "Import each student's latest Studio Director costume measurements after students exist. Encore matches by student name and DOB when available, validates measurement values, and preserves Date Last Measured as Measured at.",
        "discovery": True,
    }),
    ("costume_vendors", {
        "number": 5,
        "title": "Costume Vendors",
        "report": "Costume Vendors",
        "import_type": "costume_vendors",
        "description": "Import Studio Director costume vendors before size charts so every chart can attach to an existing Encore vendor.",
        "mapping": {
            "Vendor Desc": "name",
            "Vendor Abbrev": "abbreviation",
            "Vendor Contact": "contact_name",
            "Address1": "address_line_1",
            "Address2": "address_line_2",
            "City": "city",
            "State": "state",
            "ZIP": "postal_code",
            "Phone": "phone",
            "Fax": "fax",
            "Email": "email_or_website",
            "Required Date": "required_date_source",
            "Customer Number": "customer_number",
            "Notes": "notes",
        },
    }),
    ("costume_vendor_size_charts", {
        "number": 6,
        "title": "Costume Vendor Size Charts",
        "report": "Costume Vendor Size Charts",
        "import_type": "costume_vendor_size_charts",
        "description": "Attach Studio Director size charts and girth ranges to the costume vendors imported in the previous step.",
        "mapping": {
            "Vendor": "vendor_chart",
            "Girth From": "girth_min",
            "Girth To": "girth_max",
            "Size": "size_label",
            "Notes": "notes",
        },
    }),
    ("instructors", {
        "number": 7,
        "title": "Teachers / Instructors",
        "report": "Instructor List",
        "import_type": "instructors",
        "description": "Import teachers before classes so Studio Director instructor initials can later resolve to Encore instructors.",
        "mapping": {
            "First Name": "first_name",
            "Last Name": "last_name",
            "Address1": "address_line_1",
            "Address2": "address_line_2",
            "City": "city",
            "State": "state",
            "ZIP": "postal_code",
            "Primary Phone": "phone",
            "Emergency Contact": "emergency_contact_name",
            "Email": "email",
        },
    }),
    ("instructor_activation", {
        "number": 8,
        "title": "Instructor Activation",
        "report": "Encore account activation",
        "import_type": None,
        "description": (
            "Review imported instructors, choose who should be active, "
            "and send secure profile-claim emails so each instructor can "
            "verify their information and submit weekly availability."
        ),
        "instructor_activation": True,
    }),
    ("locations", {
        "number": 9,
        "title": "Locations",
        "report": "Encore Settings",
        "import_type": None,
        "description": "Confirm the studio's physical locations before rooms are imported. Add any secondary buildings or addresses in Rooms & Locations settings, then mark this step complete.",
        "manual": True,
        "settings_link_name": "studios:rooms_locations",
        "settings_link_label": "Manage Rooms & Locations",
    }),
    ("locations_rooms", {
        "number": 10,
        "title": "Rooms",
        "report": "Student Class List",
        "import_type": None,
        "description": "Discover unique Studio Director Location values and create Encore rooms under the correct physical location.",
        "discovery": True,
    }),
    ("seasons", {
        "number": 11,
        "title": "Seasons",
        "report": "Class List",
        "import_type": None,
        "description": "Discover and de-duplicate seasons from the Class List before classes are created.",
        "discovery": True,
    }),
    ("class_types", {
        "number": 12,
        "title": "Class Types",
        "report": "Class List",
        "import_type": None,
        "description": "Discover class types from Studio Director Type values and recognizable dance styles in class names.",
        "discovery": True,
    }),
    ("class_levels", {
        "number": 13,
        "title": "Class Levels",
        "report": "Encore Settings / client confirmation",
        "import_type": None,
        "description": "Define the studio's experience levels and shorthand aliases before class import so names such as Exp., Int., Adv., or numeric levels can be recognized.",
        "manual": True,
        "settings_link_name": "studios:class_level_list",
        "settings_link_label": "Manage Class Levels",
    }),
    ("import_vocabulary", {
        "number": 14,
        "title": "Import Vocabulary",
        "report": "Encore Settings / client confirmation",
        "import_type": None,
        "description": (
            "Define this studio's own class-name vocabulary before class import. "
            "Map phrases such as Preschool, Jr., Sr., Company, Rehearsal, or other "
            "studio-specific terms without hardcoding those meanings into Encore."
        ),
        "manual": True,
        "settings_link_name": "studios:studio_director_vocabulary",
        "settings_link_label": "Manage Import Vocabulary",
    }),
    ("classes_meetings", {
        "number": 15,
        "title": "Classes + Meetings",
        "report": "Class List",
        "import_type": None,
        "description": "Create scheduled class offerings, match instructor initials, and create meeting day/time/room records.",
        "discovery": True,
    }),
    ("tuition", {
        "number": 16,
        "title": "Tuition Setup",
        "report": "Client review / Studio Director tuition settings",
        "import_type": None,
        "description": "Confirm per-class or studio-wide tuition and enter the studio's current pricing before billing is activated.",
        "manual": True,
    }),
    ("special_class_tuition", {
        "number": "16A",
        "title": "Review Classes (Optional)",
        "report": "Encore class tuition exceptions",
        "import_type": None,
        "description": "Review class pricing, age groups, levels, and types. Set special tuition where needed, or skip if all classes use studio-wide pricing.",
        "special_class_tuition": True,
    }),
    ("enrollments", {
        "number": 17,
        "title": "Enrollments",
        "report": "Student Class List",
        "import_type": None,
        "description": "Match students to the correct scheduled class using student identity, season, class name, day, start time, and room.",
        "discovery": True,
    }),
    ("drop_history", {
        "number": 18,
        "title": "Drop History",
        "report": "Student Drop History",
        "import_type": None,
        "description": "Preserve dropped enrollment status, drop dates, reasons, and notes without manufacturing historical billing.",
        "discovery": True,
    }),
    ("client_billing_exceptions", {
        "number": 19,
        "title": "Client Billing Exceptions Review",
        "report": "Client confirmation",
        "import_type": None,
        "description": "Ask the client before billing cutover: Are any families on special tuition arrangements, scholarships, manual discounts, grandfathered rates, custom payment arrangements, or any other pricing that differs from the normal tuition rules? Also confirm that families will need to re-enter card/ACH payment methods in Encore and confirm the exact date Encore should begin creating new tuition charges.",
        "manual": True,
    }),
    ("billing_transition", {
        "number": 20,
        "title": "Billing Transition",
        "report": "Aging / Collections CSVs",
        "import_type": None,
        "description": "Import the studio's opening receivables and unapplied credits using the Family Balance Summary and Family Charge Detail CSVs, then record the date Encore billing begins.",
        "billing_transition": True,
    }),
    ("final_review", {
        "number": 21,
        "title": "Final Review",
        "report": "Encore",
        "import_type": None,
        "description": "Review unresolved rows, staffing cleanup, client billing exceptions, opening balances, tuition, and billing cutover before handoff.",
        "manual": True,
    }),
    ("billing_activation", {
        "number": 22,
        "title": "Activate Imported Enrollment Billing",
        "report": "Encore / final billing cutover",
        "import_type": None,
        "description": "Preview eligible active imported enrollments and safely activate future recurring tuition schedules without back-billing historical months.",
        "billing_activation": True,
    }),
])


def studio_director_step(step_key):
    return STUDIO_DIRECTOR_STEPS.get(step_key)


def studio_director_mapping(headers, step_key):
    step = studio_director_step(step_key) or {}
    expected = step.get("mapping", {})
    normalized_expected = {str(key).strip().lower(): value for key, value in expected.items()}
    return {
        header: normalized_expected.get(str(header).strip().lower(), "")
        for header in headers
    }


# -------------------------------------------------------------------
# Studio Director discovery helpers
# -------------------------------------------------------------------

import hashlib
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from classes.models import Class, ClassLevel, ClassMeeting, ClassType, Season
from costumes.models import StudentMeasurementSet
from instructors.models import Instructor
from enrollments.models import Enrollment
from students.models import Student
from studios.models import StudioRoom, VendorOnboardingRun


GENERIC_CLASS_TYPE_VALUES = {
    "",
    "dance",
    "class",
    "no charge",
    "nocharge",
    "none",
    "n/a",
    "na",
    "tbd",
}

DANCE_STYLE_ALIASES = [
    ("musical theatre", "Musical Theatre"),
    ("musical theater", "Musical Theatre"),
    ("hip hop", "Hip Hop"),
    ("hip-hop", "Hip Hop"),
    ("contemporary", "Contemporary"),
    ("lyrical", "Lyrical"),
    ("ballet", "Ballet"),
    ("pointe", "Pointe"),
    ("pre-pointe", "Pre-Pointe"),
    ("pre pointe", "Pre-Pointe"),
    ("jazz", "Jazz"),
    ("tap", "Tap"),
    ("acro", "Acro"),
    ("acrobatics", "Acro"),
    ("modern", "Modern"),
    ("pom", "Pom"),
    ("conditioning", "Conditioning"),
    ("technique", "Technique"),
    ("stretch", "Stretch"),
    ("creative movement", "Creative Movement"),
    ("combo", "Combo"),
]


def _source_value(row, *names):
    lookup = {str(key).strip().lower(): value for key, value in (row or {}).items()}
    for name in names:
        value = lookup.get(str(name).strip().lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _clean_token(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _season_years(value):
    text = _clean_token(value)
    four = [int(item) for item in re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", text)]

    range_match = re.search(
        r"\b(19\d{2}|20\d{2}|21\d{2})\s*[-/]\s*(\d{2}|\d{4})\b",
        text,
    )
    if range_match:
        start = int(range_match.group(1))
        end_raw = range_match.group(2)
        if len(end_raw) == 2:
            century = (start // 100) * 100
            end = century + int(end_raw)
            if end < start:
                end += 100
        else:
            end = int(end_raw)
        return start, end

    if len(four) >= 2:
        return four[0], four[1]
    if four:
        return four[0], None

    short_range = re.search(r"\b(\d{2})\s*[-/]\s*(\d{2})\b", text)
    if short_range:
        current_century = (date.today().year // 100) * 100
        start = current_century + int(short_range.group(1))
        end = current_century + int(short_range.group(2))
        if end < start:
            end += 100
        return start, end

    return None, None


def _season_term(value):
    text = _clean_token(value).lower()
    for term in ("fall", "summer", "spring", "winter"):
        if re.search(rf"\b{term}\b", text):
            return term
    return ""


def season_identity(value):
    text = _clean_token(value)
    start, end = _season_years(text)
    term = _season_term(text)

    # Generic vendor/studio words are deliberately ignored so
    # "Dance Place 2014" and "2014 Dance Place" collapse together.
    leftovers = text.lower()
    leftovers = re.sub(r"\b(19\d{2}|20\d{2}|21\d{2})\b", " ", leftovers)
    leftovers = re.sub(r"\b\d{2}\s*[-/]\s*\d{2}\b", " ", leftovers)
    leftovers = re.sub(r"\b(fall|summer|spring|winter)\b", " ", leftovers)
    leftovers = re.sub(r"\b(current|dance|season|studio|place)\b", " ", leftovers)
    leftovers = re.sub(r"[^a-z0-9]+", " ", leftovers)
    leftovers = " ".join(leftovers.split())

    return (start or 0, end or 0, term, leftovers)


def suggested_season_dates(value):
    start_year, end_year = _season_years(value)
    term = _season_term(value)
    warnings = []

    if start_year is None:
        return None, None, ["Encore could not infer a year from this season name."]

    if end_year and end_year - start_year > 2:
        warnings.append(
            f"Unusual year span detected ({start_year}-{end_year}). Confirm the dates before creating this season."
        )

    if term == "fall":
        return date(start_year, 9, 1), date(start_year, 12, 31), warnings
    if term == "summer":
        return date(start_year, 6, 1), date(start_year, 8, 31), warnings
    if term == "spring":
        return date(start_year, 1, 1), date(start_year, 5, 31), warnings
    if term == "winter":
        return date(start_year, 1, 1), date(start_year, 3, 31), warnings

    # Studio Director schools commonly use a school-year style season.
    # These are suggestions only and remain editable on the review screen.
    effective_end = end_year or (start_year + 1)
    return date(start_year, 6, 1), date(effective_end, 6, 30), warnings


def discover_rooms(studio, rows):
    values = {}
    existing = {
        room.name.strip().lower(): room
        for room in StudioRoom.objects.filter(studio=studio)
    }

    for row_number, row in enumerate(rows, start=2):
        raw = _source_value(row, "Location", "Room", "Studio")
        if not raw:
            continue
        key = raw.lower()
        item = values.setdefault(
            key,
            {
                "key": key,
                "name": raw,
                "source_rows": [],
                "status": "create",
                "reason": "New room discovered from Studio Director.",
            },
        )
        item["source_rows"].append(row_number)

    proposals = []
    for item in values.values():
        if item["key"] in existing:
            item["status"] = "skip"
            item["reason"] = "Room already exists in Encore."
            item["object_id"] = existing[item["key"]].pk
        item["count"] = len(item["source_rows"])
        proposals.append(item)

    return sorted(proposals, key=lambda item: item["name"].lower())


def discover_seasons(studio, rows):
    grouped = {}
    existing = list(Season.objects.filter(studio=studio))

    def add_group(key, raw_name, row_number, start_date=None, end_date=None, warnings=None, source="Studio Director Season"):
        item = grouped.setdefault(
            key,
            {
                "key": "|".join(str(part) for part in key) if isinstance(key, tuple) else str(key),
                "raw_names": [],
                "source_rows": [],
                "forced_start": start_date,
                "forced_end": end_date,
                "forced_name": raw_name if start_date and end_date else "",
                "warnings": list(warnings or []),
                "source": source,
            },
        )
        if raw_name not in item["raw_names"]:
            item["raw_names"].append(raw_name)
        item["source_rows"].append(row_number)

    for row_number, row in enumerate(rows, start=2):
        raw = _source_value(row, "Season")
        if raw:
            add_group(season_identity(raw), raw, row_number)

        special = special_session_for_row(row)
        if special:
            key = (
                "special",
                special["name"].strip().lower(),
                special["start_date"].isoformat(),
                special["end_date"].isoformat(),
            )
            warnings = []
            if special.get("kind") == "explicit":
                warnings.append(
                    "Specific class dates were detected. Encore will use the first and last dates as the session season range; verify the class meeting schedule separately."
                )
            add_group(
                key,
                special["name"],
                row_number,
                special["start_date"],
                special["end_date"],
                warnings,
                "Class-name date/session pattern",
            )

    proposals = []
    for identity, item in grouped.items():
        raw_name = item.get("forced_name") or item["raw_names"][0]
        if item.get("forced_start") and item.get("forced_end"):
            start_date = item["forced_start"]
            end_date = item["forced_end"]
            warnings = list(item.get("warnings") or [])
            match = next(
                (
                    season for season in existing
                    if season.name.strip().lower() == raw_name.strip().lower()
                    and season.start_date == start_date
                    and season.end_date == end_date
                ),
                None,
            )
        else:
            start_date, end_date, warnings = suggested_season_dates(raw_name)
            warnings = list(item.get("warnings") or []) + list(warnings)
            match = None
            for season in existing:
                if season_identity(season.name) == identity:
                    match = season
                    break

        proposal = {
            **item,
            "name": raw_name,
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
            "warnings": warnings,
            "count": len(item["source_rows"]),
            "status": "skip" if match else ("error" if not start_date or not end_date else "create"),
            "reason": (
                f'Matches existing season "{match.name}".'
                if match
                else (
                    "Review suggested dates, then create the season."
                    if start_date and end_date
                    else "A year could not be inferred. Enter dates before creating."
                )
            ),
            "object_id": match.pk if match else None,
        }
        proposals.append(proposal)

    return sorted(proposals, key=lambda item: (item["start_date"] or "9999", item["name"].lower()))



def normalize_class_type_name(value):
    text = _clean_token(value)
    if not text:
        return ""

    # Remove a leading or trailing four-digit year from a reusable class type.
    text = re.sub(r"^\s*(?:19|20|21)\d{2}\s*[-:/]?\s*", "", text)
    text = re.sub(r"\s*[-:/]?\s*(?:19|20|21)\d{2}\s*$", "", text)

    # Remove school-year wrappers like 2021-2022 / 2021-22 while preserving
    # meaningful age ranges such as 9-11.
    text = re.sub(
        r"^\s*(?:19|20|21)\d{2}\s*[-/]\s*(?:\d{2}|(?:19|20|21)\d{2})\s*[-:/]?\s*",
        "",
        text,
    )
    text = re.sub(
        r"\s*[-:/]?\s*(?:19|20|21)\d{2}\s*[-/]\s*(?:\d{2}|(?:19|20|21)\d{2})\s*$",
        "",
        text,
    )

    return _clean_token(text)


def class_type_identity(value):
    cleaned = normalize_class_type_name(value)
    return re.sub(r"[^a-z0-9]+", "", cleaned.lower())

def infer_class_type(source_type, class_name):
    raw_type = normalize_class_type_name(source_type)
    if raw_type and raw_type.lower() not in GENERIC_CLASS_TYPE_VALUES:
        # Only trust source Type when it looks like an actual dance/style label,
        # not Studio Director charge/status values.
        for alias, label in DANCE_STYLE_ALIASES:
            if alias in raw_type.lower():
                return label, "Studio Director Type"

    haystack = _clean_token(class_name).lower()
    for alias, label in DANCE_STYLE_ALIASES:
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", haystack):
            return label, "Class name"

    # If the source Type was meaningful but not in our known alias list, keep it
    # as a reviewable proposal instead of silently dropping it.
    if raw_type and raw_type.lower() not in GENERIC_CLASS_TYPE_VALUES:
        return normalize_class_type_name(raw_type), "Studio Director Type"

    return "", ""


def discover_class_types(studio, rows):
    grouped = {}
    unresolved = 0

    for row_number, row in enumerate(rows, start=2):
        source_type = _source_value(row, "Type", "Class Type")
        class_name = _source_value(row, "Name", "Class Name")
        inferred, source = infer_class_type(source_type, class_name)

        if not inferred:
            unresolved += 1
            continue

        inferred = normalize_class_type_name(inferred)
        key = class_type_identity(inferred)
        item = grouped.setdefault(
            key,
            {
                "key": key,
                "name": inferred,
                "source": source,
                "source_rows": [],
                "examples": [],
            },
        )
        item["source_rows"].append(row_number)
        if class_name and class_name not in item["examples"] and len(item["examples"]) < 3:
            item["examples"].append(class_name)

    existing = {
        class_type_identity(item.name): item
        for item in ClassType.objects.filter(studio=studio)
    }

    proposals = []
    for key, item in grouped.items():
        match = existing.get(key)
        item.update(
            {
                "count": len(item["source_rows"]),
                "status": "skip" if match else "create",
                "reason": (
                    "Class type already exists in Encore."
                    if match
                    else f'New class type inferred from {item["source"]}.'
                ),
                "object_id": match.pk if match else None,
            }
        )
        proposals.append(item)

    return sorted(proposals, key=lambda item: item["name"].lower()), unresolved


def parse_day(value):
    text = _clean_token(value).lower()
    names = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1, "tues": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }
    return names.get(text)


def parse_time(value):
    text = _clean_token(value)
    if not text or text.lower() in {"tbd", "none", "n/a", "na"}:
        return None

    formats = (
        "%I:%M %p",
        "%I:%M%p",
        "%I %p",
        "%I%p",
        "%H:%M",
        "%H:%M:%S",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text.upper(), fmt).time()
        except ValueError:
            continue
    return None


def parse_duration_minutes(value):
    text = _clean_token(value)
    if not text or text.lower() in {"tbd", "none", "n/a", "na"}:
        return 60

    # Studio Director commonly exports 0:15, 0:45, 1:00, etc.
    match = re.fullmatch(r"(\d+):(\d{1,2})", text)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))

    numeric = re.fullmatch(r"\d+(?:\.\d+)?", text)
    if numeric:
        value_num = float(text)
        if value_num <= 8:
            return max(1, int(round(value_num * 60)))
        return max(1, int(round(value_num)))

    return 60



TBD_INSTRUCTOR_FIRST_NAME = "TBD"
TBD_INSTRUCTOR_LAST_NAME = "Instructor"


def get_or_create_tbd_instructor(studio):
    instructor = Instructor.objects.filter(
        studio=studio,
        first_name__iexact=TBD_INSTRUCTOR_FIRST_NAME,
        last_name__iexact=TBD_INSTRUCTOR_LAST_NAME,
    ).first()

    if instructor is not None:
        if not instructor.is_active:
            instructor.is_active = True
            instructor.save(update_fields=["is_active", "updated_at"])
        return instructor

    return Instructor.objects.create(
        studio=studio,
        first_name=TBD_INSTRUCTOR_FIRST_NAME,
        last_name=TBD_INSTRUCTOR_LAST_NAME,
        email="",
        phone="",
        is_active=True,
    )

def resolve_instructor(studio, value):
    text = _clean_token(value)
    if not text or text.lower() in {"tbd", "none", "n/a", "na"}:
        return (
            get_or_create_tbd_instructor(studio),
            "Studio Director instructor was blank/TBD; Encore assigned the TBD Instructor placeholder.",
        )

    # Exact email / exact full-name support.
    exact = Instructor.objects.filter(studio=studio, email__iexact=text).first()
    if exact:
        return exact, ""

    normalized = re.sub(r"[^a-z]", "", text.lower())
    instructors = list(Instructor.objects.filter(studio=studio))

    full_matches = [
        inst for inst in instructors
        if re.sub(r"[^a-z]", "", f"{inst.first_name}{inst.last_name}".lower()) == normalized
    ]
    if len(full_matches) == 1:
        return full_matches[0], ""

    # Studio Director often exports initials.
    initials = normalized
    if 1 <= len(initials) <= 4:
        candidates = []
        for inst in instructors:
            first = re.sub(r"[^a-z]", "", inst.first_name.lower())
            last = re.sub(r"[^a-z]", "", inst.last_name.lower())
            candidate_values = {
                (first[:1] + last[:1]),
                (first[:1] + last[:2]),
                (first[:2] + last[:1]),
            }
            if initials in candidate_values:
                candidates.append(inst)
        if len(candidates) == 1:
            return candidates[0], ""
        if len(candidates) > 1:
            names = ", ".join(item.full_name for item in candidates[:4])
            return None, f'Instructor initials "{text}" match multiple instructors: {names}.'

    return None, f'No unique Encore instructor matches Studio Director value "{text}".'


def instructor_candidates_for_value(studio, value):
    """Return the likely existing instructor choices for an unresolved vendor value."""
    text = _clean_token(value)
    if not text:
        return []

    normalized = re.sub(r"[^a-z]", "", text.lower())
    instructors = list(
        Instructor.objects.filter(studio=studio, is_active=True)
        .order_by("last_name", "first_name")
    )

    candidates = []
    if 1 <= len(normalized) <= 4:
        for inst in instructors:
            first = re.sub(r"[^a-z]", "", inst.first_name.lower())
            last = re.sub(r"[^a-z]", "", inst.last_name.lower())
            candidate_values = {
                first[:1] + last[:1],
                first[:1] + last[:2],
                first[:2] + last[:1],
            }
            if normalized in candidate_values:
                candidates.append(inst)

    return candidates


def _match_season(studio, raw_name):
    exact = list(Season.objects.filter(studio=studio, name__iexact=_clean_token(raw_name))[:3])
    if len(exact) == 1:
        return exact[0]

    identity = season_identity(raw_name)
    matches = [
        season
        for season in Season.objects.filter(studio=studio)
        if season_identity(season.name) == identity
    ]
    return matches[0] if len(matches) == 1 else None


def _match_class_type(studio, source_type, class_name):
    inferred, _source = infer_class_type(source_type, class_name)
    if not inferred:
        return None

    target_identity = class_type_identity(inferred)
    for class_type in ClassType.objects.filter(studio=studio):
        if class_type_identity(class_type.name) == target_identity:
            return class_type
    return None


def _decimal_age(value):
    raw = _clean_token(value).lower()
    if not raw:
        return None

    month_match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*(?:months?|mos?|mo)",
        raw,
        re.IGNORECASE,
    )
    if month_match:
        months = Decimal(month_match.group(1))
        return (months / Decimal("12")).quantize(
            Decimal("0.01")
        )

    year_match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?|yo|y/o)?",
        raw,
        re.IGNORECASE,
    )
    if year_match:
        return Decimal(year_match.group(1)).quantize(
            Decimal("0.01")
        )

    return None


def infer_class_age_range(value):
    text = _clean_token(value)
    # Clock times are never ages: remove both endpoints of 8:05-8:55 PM
    # before searching for age ranges, including abbreviations like 8:05-8:55.
    text = re.sub(r"(?<!\d)\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)?\s*(?:-|–|—|to)\s*\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)?", " ", text, flags=re.I)
    text = re.sub(r"(?<!\d)\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)?", " ", text, flags=re.I)

    # Explicit mixed-unit age ranges such as "18 months-3yo".
    mixed = re.search(
        r"(?<!\d)"
        r"(\d+(?:\.\d+)?\s*(?:months?|mos?|mo|years?|yrs?|yo|y/o)?)"
        r"\s*(?:-|–|—|to)\s*"
        r"(\d+(?:\.\d+)?\s*(?:months?|mos?|mo|years?|yrs?|yo|y/o)?)",
        text,
        re.IGNORECASE,
    )
    if mixed:
        minimum = _decimal_age(mixed.group(1))
        maximum = _decimal_age(mixed.group(2))
        if (
            minimum is not None
            and maximum is not None
            and Decimal("0") <= minimum <= maximum <= Decimal("99")
        ):
            return minimum, maximum

    # Open-ended shorthand: "12 & up", "12 - up", "12 and up", "12+".
    open_ended = re.search(
        r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:&|and|-|–|—)?\s*(?:up|\+)(?!\d)",
        text,
        re.IGNORECASE,
    )
    if open_ended:
        minimum = Decimal(open_ended.group(1))
        if Decimal("0") <= minimum <= Decimal("99"):
            return minimum, None

    patterns = (
        r"\bages?\s*(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\b",
        r"(?<![\d/])(\d+(?:\.\d+)?)\s*(?:-|–|—)\s*(\d+(?:\.\d+)?)(?![\d/])",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        minimum = Decimal(match.group(1))
        maximum = Decimal(match.group(2))
        if Decimal("0") <= minimum <= maximum <= Decimal("99"):
            return minimum, maximum

    return None, None


def _studio_director_vocabulary_rules(studio):
    run = (
        VendorOnboardingRun.objects
        .filter(
            studio=studio,
            vendor="studio_director",
        )
        .first()
    )
    if run is None:
        return []

    state = run.step_state or {}
    vocabulary_state = state.get("import_vocabulary") or {}
    rules = vocabulary_state.get("rules") or []

    return [
        rule
        for rule in rules
        if isinstance(rule, dict)
        and str(rule.get("term") or "").strip()
    ]


def _vocabulary_term_matches(term, text):
    term = _clean_token(term)
    haystack = _clean_token(text)

    if not term or not haystack:
        return False

    normalized_term = re.sub(r"\s+", " ", term).strip()
    pattern = re.escape(normalized_term)
    pattern = pattern.replace(r"\ ", r"\s+")

    return bool(
        re.search(
            rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])",
            haystack,
            re.IGNORECASE,
        )
    )


def class_vocabulary_effects(studio, class_name, extra_rules=None):
    matched = []
    minimum = None
    maximum = None
    level_id = None
    class_type_id = None
    class_type_suffixes = []
    performance_values = []
    registration_values = []

    for rule in [*(_studio_director_vocabulary_rules(studio)), *(extra_rules or [])]:
        if not _vocabulary_term_matches(
            rule.get("term"),
            class_name,
        ):
            continue

        matched.append(rule)

        raw_minimum = str(
            rule.get("min_age") or ""
        ).strip()
        raw_maximum = str(
            rule.get("max_age") or ""
        ).strip()

        try:
            if raw_minimum:
                minimum = Decimal(raw_minimum)
        except InvalidOperation:
            pass

        try:
            if raw_maximum:
                maximum = Decimal(raw_maximum)
        except InvalidOperation:
            pass

        if str(rule.get("level_id") or "").isdigit():
            level_id = int(rule["level_id"])

        if str(rule.get("class_type_id") or "").isdigit():
            class_type_id = int(rule["class_type_id"])

        suffix = _clean_token(
            rule.get("class_type_suffix")
        )
        if suffix and suffix.lower() not in {
            item.lower()
            for item in class_type_suffixes
        }:
            class_type_suffixes.append(suffix)

        performance = str(
            rule.get("performance") or ""
        ).strip().lower()
        if performance in {"yes", "no"}:
            performance_values.append(
                performance == "yes"
            )

        registration = str(
            rule.get("registration") or ""
        ).strip().lower()
        if registration in {"open", "closed"}:
            registration_values.append(
                registration
            )

    performance = None
    performance_conflict = False
    if performance_values:
        unique = set(performance_values)
        if len(unique) == 1:
            performance = performance_values[-1]
        else:
            performance_conflict = True

    registration_open = None
    registration_conflict = False
    if registration_values:
        unique = set(registration_values)
        if len(unique) == 1:
            registration_open = (
                registration_values[-1] == "open"
            )
        else:
            registration_conflict = True
            registration_open = False

    return {
        "rules": matched,
        "min_age": minimum,
        "max_age": maximum,
        "level_id": level_id,
        "class_type_id": class_type_id,
        "class_type_suffixes": class_type_suffixes,
        "performance": performance,
        "performance_conflict": performance_conflict,
        "registration_open": registration_open,
        "registration_conflict": registration_conflict,
    }


def _standard_class_name(class_type_name, level_name):
    class_type_name = _clean_token(class_type_name)
    level_name = _clean_token(level_name)

    if class_type_name and level_name:
        return f"{class_type_name} - {level_name}"
    return class_type_name


def _class_type_by_name(studio, name):
    target = class_type_identity(name)
    if not target:
        return None

    for class_type in ClassType.objects.filter(
        studio=studio,
    ):
        if class_type_identity(class_type.name) == target:
            return class_type

    return None


def _resolved_class_type_with_vocabulary(
    studio,
    source_type,
    class_name,
    effects,
):
    if effects.get("class_type_id"):
        class_type = ClassType.objects.filter(
            studio=studio,
            pk=effects["class_type_id"],
        ).first()
        if class_type is not None:
            return class_type, class_type.name

    inferred_name, _source = infer_class_type(
        source_type,
        class_name,
    )

    if inferred_name and effects.get("class_type_suffixes"):
        inferred_name = (
            inferred_name
            + " - "
            + " - ".join(
                effects["class_type_suffixes"]
            )
        )

    return (
        _class_type_by_name(
            studio,
            inferred_name,
        ),
        inferred_name,
    )


def detect_multiple_class_types(
    studio,
    class_name,
    effects=None,
):
    haystack = _clean_token(class_name).lower()
    matches = []
    seen = set()

    # Recognize configured class types first.
    for class_type in ClassType.objects.filter(
        studio=studio,
    ):
        name = _clean_token(class_type.name)
        base = re.split(
            r"\s+-\s+",
            name,
            maxsplit=1,
        )[0]
        if (
            base
            and re.search(
                rf"(?<![a-z]){re.escape(base.lower())}(?![a-z])",
                haystack,
                re.IGNORECASE,
            )
        ):
            key = class_type_identity(base)
            if key not in seen:
                seen.add(key)
                matches.append(
                    {
                        "id": class_type.pk,
                        "name": base,
                    }
                )

    # Fall back to Encore's general style aliases.
    for alias, label in DANCE_STYLE_ALIASES:
        if re.search(
            rf"(?<![a-z]){re.escape(alias)}(?![a-z])",
            haystack,
            re.IGNORECASE,
        ):
            key = class_type_identity(label)
            if key in seen:
                continue
            seen.add(key)
            match = _class_type_by_name(
                studio,
                label,
            )
            matches.append(
                {
                    "id": match.pk if match else None,
                    "name": label,
                }
            )

    suffixes = (
        (effects or {}).get(
            "class_type_suffixes",
            [],
        )
    )
    if suffixes:
        suffix = " - ".join(suffixes)
        for item in matches:
            item["name"] = (
                f"{item['name']} - {suffix}"
            )
            resolved = _class_type_by_name(
                studio,
                item["name"],
            )
            item["id"] = (
                resolved.pk
                if resolved
                else None
            )

    return matches


def _level_token(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def resolve_class_level(studio, source_level, class_name):
    levels = list(ClassLevel.objects.filter(studio=studio, is_active=True).order_by("number", "name"))
    if not levels:
        return None, "No active Class Levels are configured; level was left blank."

    explicit = _clean_token(source_level)
    haystack = _clean_token(class_name)
    normalized_words = [_level_token(token) for token in re.findall(r"[A-Za-z]+\.?|\d+", haystack)]

    vocabulary_effects = class_vocabulary_effects(
        studio,
        class_name,
    )
    configured_non_level_tokens = {
        _level_token(rule.get("term"))
        for rule in vocabulary_effects.get("rules", [])
        if not str(rule.get("level_id") or "").isdigit()
    }

    matches = []
    for level in levels:
        aliases = [level.name, *(level.aliases or [])]
        alias_tokens = {_level_token(item) for item in aliases if _level_token(item)}
        if explicit:
            explicit_token = _level_token(explicit)
            if explicit_token == str(level.number) or explicit_token in alias_tokens:
                matches.append(level)
                continue
        # Do not treat arbitrary numbers in the class name as level aliases.
        # Times such as 4:25 / 5:20 previously caused false Level 4/5 matches.
        word_alias_tokens = {
            token
            for token in alias_tokens
            if not token.isdigit()
            and token not in configured_non_level_tokens
        }
        if any(token in word_alias_tokens for token in normalized_words):
            matches.append(level)

    # A number immediately after a recognizable dance style is treated as a level.
    # This catches "Ballet 1 - Toy Story Camp" without confusing age ranges such as 5-6.
    style_number = None
    lowered = haystack.lower()
    for alias, _label in DANCE_STYLE_ALIASES:
        match = re.search(
            rf"(?<![a-z]){re.escape(alias)}(?![a-z])\s+(?:level\s*)?(\d+)\b",
            lowered,
            re.IGNORECASE,
        )
        if match:
            style_number = int(match.group(1))
            break

    numeric = re.search(r"(?:\blevel\s*)?(\d+)\s*$", haystack, re.IGNORECASE)
    numeric_value = style_number or (int(numeric.group(1)) if numeric else None)
    if numeric_value is not None:
        level = next((item for item in levels if item.number == numeric_value), None)
        if level and level not in matches:
            matches.append(level)

    vocabulary_level = None
    if vocabulary_effects.get("level_id"):
        vocabulary_level = next(
            (
                item
                for item in levels
                if item.pk
                == vocabulary_effects["level_id"]
            ),
            None,
        )

    if vocabulary_level is not None:
        matches = [vocabulary_level]

    unique = {item.pk: item for item in matches}
    matches = list(unique.values())
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        return None, "Multiple configured Class Levels match this class name; review the level manually."
    return None, ""


_DAY_ALIASES = {
    "m": 0, "mon": 0, "monday": 0,
    "tu": 1, "tue": 1, "tues": 1, "tuesday": 1,
    "w": 2, "wed": 2, "wednesday": 2,
    "th": 3, "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "f": 4, "fri": 4, "friday": 4,
    "sa": 5, "sat": 5, "saturday": 5,
    "su": 6, "sun": 6, "sunday": 6,
}


def _day_token(value):
    return re.sub(r"[^a-z]", "", str(value or "").lower())


def parse_day_expression(value):
    """Return one or more weekday numbers from a title/day expression."""
    text = _clean_token(value)
    if not text:
        return []

    # Common compact ranges first: M-F, T-Th, Tues-Thurs, Mon-Wed, etc.
    token = r"(?:Monday|Mon|M|Tuesday|Tues|Tue|Tu|Wednesday|Wed|W|Thursday|Thurs|Thur|Thu|Th|Friday|Fri|F|Saturday|Sat|Sa|Sunday|Sun|Su)"
    range_match = re.search(rf"\b({token})\.?\s*(?:-|–|—|to|through)\s*({token})\.?\b", text, re.IGNORECASE)
    if range_match:
        start = _DAY_ALIASES.get(_day_token(range_match.group(1)))
        end = _DAY_ALIASES.get(_day_token(range_match.group(2)))
        if start is not None and end is not None:
            if start <= end:
                return list(range(start, end + 1))
            return list(range(start, 7)) + list(range(0, end + 1))

    # A single named weekday.
    single = re.search(rf"\b({token})\.?\b", text, re.IGNORECASE)
    if single:
        day = _DAY_ALIASES.get(_day_token(single.group(1)))
        return [day] if day is not None else []
    return []


def _time_from_parts(hour, minute, period):
    hour = int(hour)
    minute = int(minute or 0)
    period = (period or "").lower().replace(".", "")
    if period == "pm" and hour < 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0
    return time(hour, minute)


def parse_title_time_range(value):
    """Parse one start time or a start/end range from a class title."""
    text = _clean_token(value)
    clock = r"(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)?"
    range_match = re.search(rf"{clock}\s*(?:-|–|—|to)\s*{clock}", text, re.IGNORECASE)
    warning = ""
    if range_match:
        sh, sm, sp, eh, em, ep = range_match.groups()
        # "4:45-5:30pm" means both times are PM. Likewise for AM.
        if not sp and ep:
            sp = ep
        if not ep and sp:
            ep = sp
        if not sp and not ep:
            # Dance schedules without AM/PM are normally afternoon/evening when <=7.
            sp = ep = "pm" if int(sh) <= 7 else "am"
            warning = "Time range period was inferred from class-name shorthand."
        try:
            start = _time_from_parts(sh, sm, sp)
            end = _time_from_parts(eh, em, ep)
        except ValueError:
            return None, None, "", warning
        start_minutes = start.hour * 60 + start.minute
        end_minutes = end.hour * 60 + end.minute
        if end_minutes <= start_minutes:
            end_minutes += 24 * 60
        return start, max(1, end_minutes - start_minutes), range_match.group(0), warning

    single = re.search(clock, text, re.IGNORECASE)
    if not single:
        return None, None, "", ""
    hour, minute, period = single.groups()
    if not period:
        period = "pm" if int(hour) <= 7 else "am"
        warning = "Start time period was inferred from class-name shorthand."
    try:
        return _time_from_parts(hour, minute, period), None, single.group(0), warning
    except ValueError:
        return None, None, "", warning


def _source_year_for_month(source_season, month):
    start_year, end_year = _season_years(source_season)
    if start_year is None:
        return None
    if end_year is None:
        return start_year
    return start_year if month >= 7 else end_year


def parse_title_date_window(value, source_season=""):
    """Parse camp/session date ranges or explicit month/day lists from a title."""
    text = _clean_token(value)

    # 7/27-7/31st, 7/30-8/2, etc.
    numeric = re.search(
        r"(?<!\d)(\d{1,2})/(\d{1,2})(?:st|nd|rd|th)?\s*(?:-|–|—|to|through)\s*(?:(\d{1,2})/)?(\d{1,2})(?:st|nd|rd|th)?(?!\d)",
        text,
        re.IGNORECASE,
    )
    if numeric:
        sm, sd, em, ed = numeric.groups()
        sm, sd, ed = int(sm), int(sd), int(ed)
        em = int(em) if em else sm
        year = _source_year_for_month(source_season, sm)
        if year:
            end_year = year + 1 if em < sm else year
            try:
                start = date(year, sm, sd)
                end = date(end_year, em, ed)
                return {
                    "start_date": start,
                    "end_date": end,
                    "dates": [],
                    "raw": numeric.group(0),
                    "kind": "range",
                }
            except ValueError:
                pass

    # Aug 2 3 4 9 10 11 (explicit dates, not assumed to recur weekly).
    month_names = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    }
    month_pattern = "|".join(sorted(month_names, key=len, reverse=True))
    explicit = re.search(
        rf"\b({month_pattern})\.?\s+((?:\d{{1,2}}(?:st|nd|rd|th)?(?:\s+|,\s*))+\d{{1,2}}(?:st|nd|rd|th)?)\b",
        text,
        re.IGNORECASE,
    )
    if explicit:
        month = month_names[explicit.group(1).lower().rstrip(".")]
        year = _source_year_for_month(source_season, month)
        if year:
            days = [int(item) for item in re.findall(r"\d{1,2}", explicit.group(2))]
            parsed_dates = []
            for day_num in days:
                try:
                    parsed_dates.append(date(year, month, day_num))
                except ValueError:
                    continue
            if parsed_dates:
                return {
                    "start_date": min(parsed_dates),
                    "end_date": max(parsed_dates),
                    "dates": parsed_dates,
                    "raw": explicit.group(0),
                    "kind": "explicit",
                }

    return None


def _special_session_name(class_name, class_type_name, date_window):
    cleaned = clean_studio_director_class_display_name(class_name)
    theme = cleaned
    if class_type_name:
        theme = re.sub(
            rf"^\s*{re.escape(class_type_name)}\s*[-:/]?\s*",
            "",
            theme,
            flags=re.IGNORECASE,
        ).strip()
    theme = theme or cleaned or "Special Session"
    year = date_window["start_date"].year
    if date_window.get("kind") == "explicit" and "camp" not in theme.lower():
        return f"{theme} {year} Session"
    return f"{theme} {year}"


def special_session_for_row(row):
    class_name = _source_value(row, "Name", "Class Name")
    source_season = _source_value(row, "Season")
    window = parse_title_date_window(class_name, source_season)
    if not window:
        return None
    inferred_type, _ = infer_class_type(_source_value(row, "Type", "Class Type"), class_name)
    return {
        **window,
        "name": _special_session_name(class_name, inferred_type, window),
    }


def parse_schedule_from_class_name(value):
    text = _clean_token(value)
    days = parse_day_expression(text)
    start_time, derived_duration, matched_time, warning = parse_title_time_range(text)

    room = ""
    if matched_time:
        after = text[text.lower().find(matched_time.lower()) + len(matched_time):]
        room_match = re.match(r"\s*[-–—]\s*([A-Za-z][A-Za-z0-9 ]{0,20})\s*$", after)
        if room_match:
            room = _clean_token(room_match.group(1))

    return days, start_time, derived_duration, room, warning


def infer_season_name_from_class_name(value):
    text = _clean_token(value)
    match = re.search(r"\b((?:19|20|21)\d{2})\s*[-/]\s*(\d{2}|(?:19|20|21)\d{2})\b", text)
    if not match:
        return ""
    start = int(match.group(1))
    end_raw = match.group(2)
    if len(end_raw) == 2:
        end = (start // 100) * 100 + int(end_raw)
        if end < start:
            end += 100
    else:
        end = int(end_raw)
    return f"{start}-{end}"


def _class_identity(row):
    name = _source_value(row, "Name", "Class Name")
    season = _source_value(row, "Season") or infer_season_name_from_class_name(name)
    day = _source_value(row, "Day")
    start_time = _source_value(row, "Start Time", "Start")
    instructor = _source_value(row, "Instructor")
    location = _source_value(row, "Location")
    return "||".join(
        [
            str(season_identity(season)),
            name.strip().lower(),
            day.strip().lower(),
            start_time.strip().lower(),
            instructor.strip().lower(),
            location.strip().lower(),
        ]
    )


def class_id_for_vendor_row(studio, identity):
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10].upper()
    return f"SD-{digest}"


def discover_classes_and_meetings(studio, rows, extra_rules=None):
    grouped = {}

    for row_number, row in enumerate(rows, start=2):
        name = _source_value(
            row,
            "Name",
            "Class Name",
        )
        special = special_session_for_row(row)
        season_raw = (
            special["name"]
            if special
            else (
                _source_value(row, "Season")
                or infer_season_name_from_class_name(name)
            )
        )
        if not name or not season_raw:
            continue

        identity = _class_identity(row)
        if special:
            identity = (
                identity
                + "||special:"
                + special["name"].strip().lower()
            )

        item = grouped.setdefault(
            identity,
            {
                "identity": identity,
                "source_row_number": row_number,
                "source_row": row,
                "duplicate_rows": [],
            },
        )
        item["duplicate_rows"].append(row_number)

    proposals = []

    for identity, item in grouped.items():
        row = item["source_row"]
        source_class_name = _source_value(
            row,
            "Name",
            "Class Name",
        )
        special = special_session_for_row(row)

        season_raw = (
            special["name"]
            if special
            else (
                _source_value(row, "Season")
                or infer_season_name_from_class_name(
                    source_class_name
                )
            )
        )

        cleaned_source_name = (
            clean_studio_director_class_display_name(
                source_class_name
            )
        )

        source_type = _source_value(
            row,
            "Type",
            "Class Type",
        )
        source_level = _source_value(
            row,
            "Level",
            "Class Level",
        )
        instructor_raw = _source_value(
            row,
            "Instructor",
        )
        assistant_raw = _source_value(
            row,
            "Assistants",
            "Assistant",
        )
        room_raw = _source_value(
            row,
            "Location",
            "Room",
        )
        day_raw = _source_value(
            row,
            "Day",
        )
        time_raw = _source_value(
            row,
            "Start Time",
            "Start",
        )
        length_raw = _source_value(
            row,
            "Length",
            "Duration",
        )
        max_size_raw = _source_value(
            row,
            "Max Size",
            "Capacity",
        )
        allow_drop_raw = _source_value(
            row,
            "Allow Drop-ins",
            "Allow Drop Ins",
        )

        effects = class_vocabulary_effects(
            studio,
            source_class_name,
            extra_rules=extra_rules,
        )

        season = _match_season(
            studio,
            season_raw,
        )

        class_type, inferred_type_name = (
            _resolved_class_type_with_vocabulary(
                studio,
                source_type,
                source_class_name,
                effects,
            )
        )

        multiple_types = detect_multiple_class_types(
            studio,
            source_class_name,
            effects,
        )

        instructor, instructor_error = (
            resolve_instructor(
                studio,
                instructor_raw,
            )
        )

        assistant = None
        assistant_warning = ""
        if assistant_raw:
            assistant, assistant_warning = (
                resolve_instructor(
                    studio,
                    assistant_raw,
                )
            )

        room = (
            StudioRoom.objects
            .filter(
                studio=studio,
                name__iexact=room_raw,
            )
            .first()
            if room_raw
            else None
        )

        explicit_days = parse_day_expression(
            day_raw
        )
        start_time = parse_time(
            time_raw
        )

        explicit_duration = (
            parse_duration_minutes(length_raw)
            if length_raw
            else None
        )

        (
            parsed_days,
            parsed_time,
            title_duration,
            parsed_room,
            schedule_warning,
        ) = parse_schedule_from_class_name(
            source_class_name
        )

        meeting_days = (
            explicit_days
            or parsed_days
        )

        if (
            start_time is None
            and parsed_time is not None
        ):
            start_time = parsed_time

        duration = (
            explicit_duration
            or title_duration
            or 60
        )

        if not room_raw and parsed_room:
            room_raw = parsed_room
            room = (
                StudioRoom.objects
                .filter(
                    studio=studio,
                    name__iexact=room_raw,
                )
                .first()
            )

        explicit_min = _source_value(
            row,
            "Minimum Age",
            "Min Age",
        )
        explicit_max = _source_value(
            row,
            "Maximum Age",
            "Max Age",
        )

        inferred_min, inferred_max = (
            infer_class_age_range(
                source_class_name
            )
        )

        def parse_source_age(raw, fallback):
            if not raw:
                return fallback
            try:
                return Decimal(
                    str(raw).strip()
                )
            except (
                InvalidOperation,
                ValueError,
            ):
                return fallback

        min_age = parse_source_age(
            explicit_min,
            inferred_min,
        )
        max_age = parse_source_age(
            explicit_max,
            inferred_max,
        )

        # Studio vocabulary is only used when the source did not contain an
        # explicit numeric age range. Explicit source ages always win.
        if (
            not explicit_min
            and inferred_min is None
            and effects.get("min_age") is not None
        ):
            min_age = effects["min_age"]

        if (
            not explicit_max
            and inferred_max is None
            and effects.get("max_age") is not None
        ):
            max_age = effects["max_age"]

        level, level_note = resolve_class_level(
            studio,
            source_level,
            source_class_name,
        )

        instructor_candidates = (
            instructor_candidates_for_value(
                studio,
                instructor_raw,
            )
        )

        season_group = re.sub(
            r"[^a-z0-9]+",
            "-",
            _clean_token(
                season_raw
            ).lower(),
        ).strip("-") or "missing-season"

        instructor_group = re.sub(
            r"[^a-z0-9]+",
            "-",
            _clean_token(
                instructor_raw
            ).lower(),
        ).strip("-") or "blank-instructor"

        class_type_basis = (
            inferred_type_name
            or source_type
            or cleaned_source_name
        )

        class_type_group = re.sub(
            r"[^a-z0-9]+",
            "-",
            _clean_token(
                class_type_basis
            ).lower(),
        ).strip("-") or "missing-class-type"

        suggested_start = ""
        suggested_end = ""

        if special:
            suggested_start = (
                special["start_date"].isoformat()
            )
            suggested_end = (
                special["end_date"].isoformat()
            )
        else:
            (
                season_start,
                season_end,
                _season_warnings,
            ) = suggested_season_dates(
                season_raw
            )

            suggested_start = (
                season_start.isoformat()
                if season_start
                else ""
            )
            suggested_end = (
                season_end.isoformat()
                if season_end
                else ""
            )

        errors = []
        warnings = []

        if schedule_warning:
            warnings.append(
                schedule_warning
            )

        if level_note:
            warnings.append(
                level_note
            )

        if effects.get(
            "performance_conflict"
        ):
            warnings.append(
                "Studio vocabulary contains conflicting performance mappings "
                "for this class. Performance was left unconfirmed."
            )

        if effects.get(
            "registration_conflict"
        ):
            warnings.append(
                "Studio vocabulary contains conflicting registration mappings. "
                "Registration remains closed for safety."
            )

        if (
            special
            and special.get("kind")
            == "explicit"
        ):
            date_labels = ", ".join(
                value.strftime("%b %-d")
                for value
                in special.get("dates", [])
            )
            warnings.append(
                "Specific class dates detected"
                + (
                    f" ({date_labels})"
                    if date_labels
                    else ""
                )
                + ". Encore uses the session season range, but weekly "
                "ClassMeeting records cannot encode an irregular list of "
                "individual dates; verify this schedule manually."
            )

        if season is None:
            errors.append(
                f'Season "{season_raw}" could not be resolved. '
                "Re-run/finish the Seasons step first."
            )

        if class_type is None:
            errors.append(
                "Class type could not be resolved from "
                f'Type "{source_type}" / class name '
                f'"{source_class_name}".'
            )

        if len(multiple_types) > 1:
            errors.append(
                "Multiple class types were detected in this source class. "
                "Choose whether to split it into separate Encore classes "
                "or keep it as one class."
            )

        if instructor is None:
            errors.append(
                instructor_error
            )
        elif instructor_error:
            warnings.append(
                instructor_error
            )

        if room_raw and room is None:
            warnings.append(
                f'Room "{room_raw}" was not found; '
                "meeting will be created without a room."
            )

        if day_raw and not meeting_days:
            warnings.append(
                f'Day "{day_raw}" was not recognized; '
                "no meeting will be created."
            )

        if time_raw and start_time is None:
            warnings.append(
                f'Start time "{time_raw}" was not recognized; '
                "no meeting will be created."
            )

        if (
            assistant_raw
            and assistant is None
            and assistant_warning
        ):
            warnings.append(
                assistant_warning
            )

        class_id = class_id_for_vendor_row(
            studio,
            identity,
        )

        existing = (
            Class.objects
            .filter(
                studio=studio,
                class_id=class_id,
            )
            .first()
        )

        capacity = 20
        try:
            if max_size_raw:
                capacity = max(
                    1,
                    int(
                        float(
                            max_size_raw
                        )
                    ),
                )
        except (
            TypeError,
            ValueError,
        ):
            warnings.append(
                f'Max Size "{max_size_raw}" was not recognized; '
                "capacity defaults to 20."
            )

        allow_drop_ins = (
            allow_drop_raw
            .strip()
            .lower()
            in {
                "yes",
                "y",
                "true",
                "1",
                "on",
            }
        )

        is_historical = False
        if season is not None:
            is_historical = (
                season.end_date
                < date.today()
            )
        elif suggested_end:
            try:
                is_historical = (
                    datetime.fromisoformat(
                        suggested_end
                    ).date()
                    < date.today()
                )
            except ValueError:
                is_historical = False

        season_active = (
            not is_historical
        )

        registration_open = (
            effects.get(
                "registration_open"
            )
        )
        if registration_open is None:
            registration_open = False

        performance = effects.get(
            "performance"
        )

        standardized_name = (
            _standard_class_name(
                class_type.name
                if class_type
                else inferred_type_name,
                level.name
                if level
                else "",
            )
        )

        class_name = (
            source_class_name
            if is_historical
            else (
                standardized_name
                or cleaned_source_name
            )
        )

        meetings = []
        if start_time is not None:
            for meeting_day in meeting_days:
                meetings.append(
                    {
                        "day": meeting_day,
                        "day_name": (
                            ClassMeeting
                            .DayOfWeek(
                                meeting_day
                            )
                            .label
                        ),
                        "start_time": (
                            start_time
                            .strftime("%H:%M")
                        ),
                        "duration_minutes": duration,
                        "room_id": (
                            room.pk
                            if room
                            else None
                        ),
                        "room_name": (
                            room.name
                            if room
                            else room_raw
                        ),
                    }
                )

        first_meeting = (
            meetings[0]
            if meetings
            else {}
        )

        split_candidates = []
        split_group = ""
        if len(multiple_types) > 1:
            split_group = "split-" + "-".join(
                sorted(
                    class_type_identity(
                        candidate.get("name")
                    )
                    for candidate in multiple_types
                    if candidate.get("name")
                )
            )
            for index, candidate in enumerate(
                multiple_types,
                start=1,
            ):
                candidate_name = (
                    source_class_name
                    if is_historical
                    else (
                        _standard_class_name(
                            candidate["name"],
                            level.name
                            if level
                            else "",
                        )
                        or candidate["name"]
                    )
                )
                split_candidates.append(
                    {
                        "index": index,
                        "class_type_id": (
                            candidate.get("id")
                        ),
                        "class_type_name": (
                            candidate["name"]
                        ),
                        "name": candidate_name,
                        "start_time": (
                            start_time
                            .strftime("%H:%M")
                            if start_time
                            else ""
                        ),
                        "end_time": "",
                    }
                )

        proposal = {
            **item,
            "class_id": class_id,
            "source_name": source_class_name,
            "name": class_name,
            "standardized_name": standardized_name,
            "is_historical": is_historical,
            "name_standard_applied": (
                bool(
                    standardized_name
                )
                and not is_historical
            ),
            "season_raw": season_raw,
            "season_id": (
                season.pk
                if season
                else None
            ),
            "season_name": (
                season.name
                if season
                else ""
            ),
            "season_group": season_group,
            "season_suggested_start": suggested_start,
            "season_suggested_end": suggested_end,
            "special_session_start": (
                special["start_date"].isoformat()
                if special
                else ""
            ),
            "special_session_end": (
                special["end_date"].isoformat()
                if special
                else ""
            ),
            "specific_dates": [
                value.isoformat()
                for value
                in (
                    special.get("dates", [])
                    if special
                    else []
                )
            ],
            "class_type_id": (
                class_type.pk
                if class_type
                else None
            ),
            "class_type_name": (
                class_type.name
                if class_type
                else ""
            ),
            "class_type_group": class_type_group,
            "class_type_suggested_name": (
                inferred_type_name
                or ""
            ),
            "level_id": (
                level.pk
                if level
                else None
            ),
            "level_name": (
                level.name
                if level
                else ""
            ),
            "level_number": (
                level.number
                if level
                else None
            ),
            "min_age": min_age,
            "max_age": max_age,
            "is_performance_class": performance,
            "registration_open": registration_open,
            "matched_vocabulary": [
                rule.get("term")
                for rule
                in effects.get(
                    "rules",
                    [],
                )
            ],
            "split_candidates": split_candidates,
            "split_group": (
                split_group
                or class_type_group
            ),
            "requires_split_review": (
                len(split_candidates) > 1
            ),
            "instructor_id": (
                instructor.pk
                if instructor
                else None
            ),
            "instructor_name": (
                instructor.full_name
                if instructor
                else ""
            ),
            "instructor_raw": instructor_raw,
            "instructor_group": instructor_group,
            "instructor_candidates": [
                {
                    "id": candidate.pk,
                    "name": candidate.full_name,
                }
                for candidate
                in instructor_candidates
            ],
            "assistant_instructor_id": (
                assistant.pk
                if assistant
                else None
            ),
            "assistant_instructor_name": (
                assistant.full_name
                if assistant
                else ""
            ),
            "room_id": first_meeting.get(
                "room_id"
            ),
            "room_name": first_meeting.get(
                "room_name",
                room_raw,
            ),
            "day": first_meeting.get(
                "day"
            ),
            "day_name": first_meeting.get(
                "day_name",
                day_raw,
            ),
            "start_time": first_meeting.get(
                "start_time",
                (
                    start_time.strftime(
                        "%H:%M"
                    )
                    if start_time
                    else ""
                ),
            ),
            "duration_minutes": duration,
            "meetings": meetings,
            "capacity": capacity,
            "allow_drop_ins": allow_drop_ins,
            "is_active": season_active,
            "errors": errors,
            "warnings": warnings,
            "status": (
                "error"
                if errors
                else (
                    "update"
                    if existing
                    else "create"
                )
            ),
            "reason": (
                errors[0]
                if errors
                else (
                    "Existing Studio Director class offering "
                    "will be synchronized."
                    if existing
                    else "New scheduled class offering."
                )
            ),
            "existing_id": (
                existing.pk
                if existing
                else None
            ),
            "source_count": len(
                item["duplicate_rows"]
            ),
        }
        proposals.append(
            proposal
        )

    return sorted(
        proposals,
        key=lambda item: (
            (
                item["season_name"]
                or item["season_raw"]
            ),
            item["name"].lower(),
            (
                item["day"]
                if item["day"]
                is not None
                else 9
            ),
            item["start_time"],
        ),
    )


# -------------------------------------------------------------------
# Studio Director enrollment + drop-history discovery
# -------------------------------------------------------------------

def parse_studio_director_date(value):
    text = _clean_token(value)
    if not text:
        return None

    formats = (
        "%Y-%m-%d",
        "%Y-%b-%d",
        "%Y-%B-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%b %d %Y",
        "%B %d %Y",
        "%Y/%m/%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_studio_director_datetime(value):
    text = _clean_token(value)
    if not text:
        return None

    formats = (
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%y %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%b-%d %H:%M:%S",
        "%Y-%b-%d %I:%M %p",
        "%m/%d/%Y",
        "%m/%d/%y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    parsed_date = parse_studio_director_date(text)
    if parsed_date:
        return datetime.combine(parsed_date, time.min)
    return None


def normalize_enrollment_status(value):
    text = _clean_token(value).lower()

    if not text:
        return None, "Enrollment status is blank."

    if any(token in text for token in ("waitlist", "waiting")):
        return Enrollment.Status.WAITLISTED, ""

    if any(token in text for token in ("drop", "withdraw")):
        return Enrollment.Status.DROPPED, ""

    if any(token in text for token in ("complete", "finished")):
        return Enrollment.Status.COMPLETED, ""

    if any(token in text for token in ("cancel", "canceled", "cancelled")):
        return Enrollment.Status.CANCELLED, ""

    if text in {"enrolled", "active", "yes", "y", "true", "1", "registered", "current"}:
        return Enrollment.Status.ACTIVE, ""

    if text in {"no", "n", "false", "0", "not enrolled", "inactive"}:
        return None, (
            f'Studio Director status "{value}" does not identify whether the '
            "student was dropped, cancelled, completed, or never enrolled."
        )

    return None, f'Unrecognized Studio Director enrollment status "{value}".'


def resolve_student(studio, row):
    first = _source_value(row, "First Name", "Student First Name")
    last = _source_value(row, "Last Name", "Student Last Name")
    dob_raw = _source_value(row, "DOB", "Dob", "Birthday", "Student Birthday")
    dob = parse_studio_director_date(dob_raw)

    if not first or not last:
        return None, "Student first and last name are required."

    qs = Student.objects.filter(
        studio=studio,
        first_name__iexact=first,
        last_name__iexact=last,
    )

    if dob:
        exact = list(qs.filter(birthday=dob)[:3])
        if len(exact) == 1:
            return exact[0], ""
        if len(exact) > 1:
            return None, f'Multiple students match {first} {last} with birthday {dob}.'

    matches = list(qs[:4])
    if len(matches) == 1:
        warning = ""
        if dob_raw and dob is None:
            warning = f'Birthday "{dob_raw}" was not recognized; matched by unique student name.'
        return matches[0], warning

    if len(matches) > 1:
        return None, (
            f'Multiple students named "{first} {last}" exist. '
            "A valid birthday is needed to identify the correct student."
        )

    return None, f'No Encore student matches "{first} {last}".'


MEASUREMENT_NUMERIC_FIELDS = (
    "bust",
    "waist",
    "hips",
    "girth",
    "inseam",
    "outseam",
    "height",
)

MEASUREMENT_TEXT_FIELDS = (
    "clothing_size",
    "shoe_size",
    "other_size_info",
)

MEASUREMENT_SOURCE_COLUMNS = {
    "bust": ("Bust", "Bust / Chest", "Chest"),
    "waist": ("Waist",),
    "hips": ("Hips",),
    "girth": ("Girth",),
    "inseam": ("Inseam",),
    "outseam": ("Outseam",),
    "height": ("Height",),
    "clothing_size": ("Clothing Size", "Leotard / Costume Size", "Leotard Size"),
    "shoe_size": ("Shoe Size",),
    "other_size_info": ("Other Size Info",),
}


def _measurement_decimal(value):
    text = _clean_token(value)
    if not text:
        return None, ""
    try:
        from decimal import Decimal, InvalidOperation
        return Decimal(text), ""
    except (InvalidOperation, ValueError):
        return None, f'"{value}" is not a valid numeric measurement.'


def _measurement_existing_match(student, measured_at, normalized):
    qs = StudentMeasurementSet.objects.filter(student=student)
    if measured_at is not None:
        # Date Last Measured is the strongest identity for a measurement record.
        same_date = list(qs.filter(measured_at=measured_at).order_by("pk")[:3])
        if len(same_date) == 1:
            return same_date[0], "update"
        if len(same_date) > 1:
            return None, "ambiguous"

    # If the source has no date, only treat an exact value match as the same
    # record. This prevents a re-run from manufacturing duplicates while still
    # preserving a genuinely different undated historical measurement.
    for measurement in qs.order_by("-pk")[:25]:
        same = True
        for field in MEASUREMENT_NUMERIC_FIELDS:
            incoming = normalized.get(field)
            existing = getattr(measurement, field)
            if incoming is None and existing is None:
                continue
            if incoming is None or existing is None or incoming != existing:
                same = False
                break
        if same:
            for field in MEASUREMENT_TEXT_FIELDS:
                if (normalized.get(field) or "") != (getattr(measurement, field) or ""):
                    same = False
                    break
        if same:
            return measurement, "skip"

    return None, "create"


def discover_student_measurements(studio, rows):
    proposals = []
    seen = set()

    for row_number, row in enumerate(rows, start=2):
        student, student_note = resolve_student(studio, row)
        errors = []
        warnings = []

        if student is None:
            errors.append(student_note)
        elif student_note:
            warnings.append(student_note)

        normalized = {}
        for field, source_names in MEASUREMENT_SOURCE_COLUMNS.items():
            raw = _source_value(row, *source_names)
            if field in MEASUREMENT_NUMERIC_FIELDS:
                value, error = _measurement_decimal(raw)
                normalized[field] = value
                if error:
                    errors.append(f"{source_names[0]}: {error}")
            else:
                normalized[field] = _clean_token(raw)

        raw_measured_at = _source_value(row, "Measured at", "Measured At")
        raw_last_measured = _source_value(row, "Date Last Measured")
        measured_at = None
        if raw_measured_at:
            measured_at = parse_studio_director_datetime(raw_measured_at)
            if measured_at is None:
                errors.append(f'Measured at "{raw_measured_at}" was not recognized as a date/time.')
        elif raw_last_measured:
            measured_at = parse_studio_director_datetime(raw_last_measured)
            if measured_at is None:
                errors.append(
                    f'Date Last Measured "{raw_last_measured}" was not recognized as a date/time.'
                )

        # Preserve Studio Director costume-size fields even though Encore's
        # StudentMeasurementSet currently has no dedicated costume-size columns.
        costume_size_notes = []
        for number in range(1, 6):
            label = f"Costume {number} Size"
            value = _source_value(row, label)
            if value:
                costume_size_notes.append(f"{label}: {value}")

        has_measurement = any(
            normalized.get(field) is not None
            for field in MEASUREMENT_NUMERIC_FIELDS
        ) or any(
            bool(normalized.get(field))
            for field in MEASUREMENT_TEXT_FIELDS
        ) or bool(costume_size_notes)

        if not has_measurement and measured_at is None:
            # A worksheet row with no measurement values and no date is not a
            # measurement record to import.
            continue

        source_identity = (
            _clean_token(_source_value(row, "Student First Name", "First Name")).lower(),
            _clean_token(_source_value(row, "Student Last Name", "Last Name")).lower(),
            measured_at.isoformat() if measured_at else "",
            tuple(str(normalized.get(field) or "") for field in MEASUREMENT_NUMERIC_FIELDS),
            tuple(normalized.get(field) or "" for field in MEASUREMENT_TEXT_FIELDS),
            tuple(costume_size_notes),
        )
        if source_identity in seen:
            continue
        seen.add(source_identity)

        status = "error" if errors else "create"
        existing = None
        if student is not None and not errors:
            existing, match_status = _measurement_existing_match(
                student,
                measured_at,
                normalized,
            )
            if match_status == "ambiguous":
                errors.append(
                    "Multiple Encore measurement records use the same Measured at value for this student."
                )
                status = "error"
            else:
                status = match_status

        student_name = (
            f"{student.first_name} {student.last_name}"
            if student is not None
            else (
                f'{_source_value(row, "Student First Name", "First Name")} '
                f'{_source_value(row, "Student Last Name", "Last Name")} '
            ).strip()
        )

        reason = " | ".join(errors or warnings)
        proposals.append({
            "key": f"measurement-{row_number}",
            "row_number": row_number,
            "status": status,
            "reason": reason,
            "errors": errors,
            "warnings": warnings,
            "label": student_name,
            "student_id": student.pk if student is not None else None,
            "student_name": student_name,
            "existing_id": existing.pk if existing is not None else None,
            "measured_at": measured_at.isoformat() if measured_at else "",
            "date_last_measured": raw_last_measured,
            "is_complete": bool(has_measurement),
            "bust": str(normalized.get("bust") or ""),
            "waist": str(normalized.get("waist") or ""),
            "hips": str(normalized.get("hips") or ""),
            "girth": str(normalized.get("girth") or ""),
            "inseam": str(normalized.get("inseam") or ""),
            "outseam": str(normalized.get("outseam") or ""),
            "height": str(normalized.get("height") or ""),
            "clothing_size": normalized.get("clothing_size") or "",
            "shoe_size": normalized.get("shoe_size") or "",
            "other_size_info": normalized.get("other_size_info") or "",
            "costume_size_notes": costume_size_notes,
            "source_data": dict(row),
        })

    return proposals



def clean_studio_director_class_display_name(value):
    """Strip scheduling/age/level clutter while preserving the meaningful program name."""
    text = _clean_token(value)
    if not text:
        return ""

    text = text.replace("&amp;", "&")
    text = re.sub(r"[–—]", "-", text)

    # School-year prefix.
    text = re.sub(r"^\s*(?:19|20|21)?\d{2}\s*[-/]\s*\d{2,4}\s+", "", text)

    # Ages and studio age labels.
    text = re.sub(r"^\s*\d{1,2}\s*-\s*\d{1,2}\s*(?:yr\.?\s*olds?|years?\s*old)?\s*[;,:-]?\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*ages?\s*\d{1,2}\s*-\s*\d{1,2}\s*[;,:-]?\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*\d{1,2}\s*(?:&|and|-|–|—)?\s*(?:up|\+)\s*(?:yr\.?\s*olds?|years?\s*old)?\s*[;,:-]?\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*preschool\s+", "", text, flags=re.I)

    # Date/session expressions.
    text = re.sub(
        r"\b\d{1,2}/\d{1,2}(?:st|nd|rd|th)?\s*(?:-|to|through)\s*(?:\d{1,2}/)?\d{1,2}(?:st|nd|rd|th)?\b",
        " ", text, flags=re.I,
    )
    month_words = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    text = re.sub(rf"\b{month_words}\.?\s+(?:\d{{1,2}}(?:st|nd|rd|th)?[ ,]*){{2,}}", " ", text, flags=re.I)

    # Day/day-range expressions.
    day_token = r"(?:Monday|Mon|M|Tuesday|Tues|Tue|Tu|Wednesday|Wed|W|Thursday|Thurs|Thur|Thu|Th|Friday|Fri|F|Saturday|Sat|Sa|Sunday|Sun|Su)"

    # Remove a complete trailing schedule before stripping the pieces individually.
    # This handles names such as "Preschool - Tues 4:25" and "Tap - Thurs 6:15-C".
    clock = r"\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)?"
    text = re.sub(
        rf"\s*[-:/]?\s*{day_token}\.?\s+{clock}(?:\s*(?:-|to)\s*{clock})?(?:\s*-\s*[A-Za-z][A-Za-z0-9 ]{{0,20}})?\s*$",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(rf"\b{day_token}\.?\s*(?:-|to|through)\s*{day_token}\.?\b", " ", text, flags=re.I)
    text = re.sub(rf"\b(?:Monday|Mon|Tuesday|Tues|Tue|Wednesday|Wed|Thursday|Thurs|Thur|Thu|Friday|Fri|Saturday|Sat|Sunday|Sun)\.?\b", " ", text, flags=re.I)

    # Time range or single start time, plus a trailing room code such as -A / -C.
    text = re.sub(rf"\b{clock}\s*(?:-|to)\s*{clock}(?:\s*-\s*[A-Za-z][A-Za-z0-9 ]{{0,20}})?\s*$", " ", text, flags=re.I)
    text = re.sub(rf"\b{clock}(?:\s*-\s*[A-Za-z][A-Za-z0-9 ]{{0,20}})?\s*$", " ", text, flags=re.I)

    # Common level aliases. Numeric levels immediately following a known dance style are removed below.
    text = re.sub(r"\b(?:exp(?:erienced)?|beg(?:inner)?|basic(?:\s+skill)?|int(?:ermediate)?|comp(?:etitive)?|adv(?:anced)?|pro(?:fessional)?)\.?\b", " ", text, flags=re.I)
    for alias, _label in DANCE_STYLE_ALIASES:
        text = re.sub(
            rf"(?<![A-Za-z])({re.escape(alias)})(?![A-Za-z])\s+(?:level\s*)?\d+\b",
            r"\1",
            text,
            flags=re.I,
        )

    text = re.sub(r"\s*;\s*", " ", text)
    text = re.sub(r"\s*-\s*", " - ", text)
    text = re.sub(r"\s+", " ", text).strip(" -:/;,.")
    return text or _clean_token(value)



def normalize_studio_director_class_name(value):
    text = _clean_token(value).lower()
    if not text:
        return ""

    # Normalize punctuation / HTML-ish artifacts.
    text = text.replace("&amp;", "&")
    text = re.sub(r"[–—]", "-", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Student Class List sometimes appends meeting details to the class name.
    # The actual day/time are already separate columns, so strip obvious
    # trailing schedule phrases for identity matching.
    day_words = r"(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
    time_bits = r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"

    text = re.sub(
        rf"\s*[-:/]\s*{day_words}(?:\s+{time_bits})?\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"\s+{day_words}\s+{time_bits}\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Ignore punctuation/spacing for the final identity key.
    return re.sub(r"[^a-z0-9]+", "", text)


def _normalized_class_name_candidates(studio, season, class_name):
    target = normalize_studio_director_class_name(class_name)
    if not target:
        return []

    return [
        item
        for item in Class.objects.filter(studio=studio, season=season)
        .select_related("season", "class_type", "instructor")
        .prefetch_related("meeting_times", "meeting_times__room")
        if normalize_studio_director_class_name(item.name) == target
    ]

def _candidate_classes_for_source(studio, row):
    season_raw = _source_value(row, "Season")
    class_name = _source_value(row, "Class Name", "Name")
    if not season_raw or not class_name:
        return []

    season = _match_season(studio, season_raw)
    if season is None:
        return []

    # Prefer exact matching first.
    exact = list(
        Class.objects.filter(
            studio=studio,
            season=season,
            name__iexact=class_name,
        )
        .select_related("season", "class_type", "instructor")
        .prefetch_related("meeting_times", "meeting_times__room")[:30]
    )
    if exact:
        return exact

    # Fall back to Studio Director normalized-name matching. This handles
    # harmless differences like punctuation, spacing, or day/time text
    # included in one report but not the other.
    return _normalized_class_name_candidates(studio, season, class_name)[:30]


def resolve_class_for_student_list(studio, row):
    candidates = _candidate_classes_for_source(studio, row)
    season_raw = _source_value(row, "Season")
    class_name = _source_value(row, "Class Name", "Name")
    day_raw = _source_value(row, "Day")
    time_raw = _source_value(row, "Start Time", "Start")
    room_raw = _source_value(row, "Location", "Room")
    type_raw = _source_value(row, "Type", "Class Type")

    if not candidates:
        season = _match_season(studio, season_raw)
        if season is None:
            return None, f'Encore could not resolve season "{season_raw}".'
        return None, (
            f'Encore found season "{season.name}", but no imported class matched '
            f'Studio Director class "{class_name}".'
        )

    if len(candidates) == 1:
        return candidates[0], ""

    day = parse_day(day_raw) if day_raw else None
    start_time = parse_time(time_raw) if time_raw else None

    narrowed = candidates
    if day is not None or start_time is not None:
        schedule_matches = []
        for class_instance in narrowed:
            for meeting in class_instance.meeting_times.all():
                if day is not None and meeting.day_of_week != day:
                    continue
                if start_time is not None and meeting.start_time != start_time:
                    continue
                schedule_matches.append(class_instance)
                break
        if schedule_matches:
            narrowed = schedule_matches

    if room_raw and len(narrowed) > 1:
        room_matches = []
        for class_instance in narrowed:
            for meeting in class_instance.meeting_times.all():
                room_name = meeting.room.name if meeting.room_id else ""
                if room_name and room_name.strip().lower() == room_raw.strip().lower():
                    room_matches.append(class_instance)
                    break
        if room_matches:
            narrowed = room_matches

    if type_raw and len(narrowed) > 1:
        inferred, _source = infer_class_type(type_raw, class_name)
        target = class_type_identity(inferred) if inferred else ""
        if target:
            type_matches = [
                item for item in narrowed
                if item.class_type_id
                and class_type_identity(item.class_type.name) == target
            ]
            if type_matches:
                narrowed = type_matches

    unique = {item.pk: item for item in narrowed}
    narrowed = list(unique.values())

    if len(narrowed) == 1:
        return narrowed[0], ""

    details = []
    for item in narrowed[:5]:
        meeting_bits = []
        for meeting in list(item.meeting_times.all())[:2]:
            meeting_bits.append(
                f"{meeting.get_day_of_week_display()} {meeting.start_time.strftime('%H:%M')}"
            )
        details.append(f"{item.class_id} ({', '.join(meeting_bits) or 'no meeting'})")

    return None, (
        f'Multiple Encore classes match "{class_name}". '
        f'Use day/time/location to resolve it. Candidates: {", ".join(details)}'
    )


def resolve_class_for_drop_history(studio, row):
    candidates = _candidate_classes_for_source(studio, row)
    season_raw = _source_value(row, "Season")
    class_name = _source_value(row, "Class Name", "Name")

    if not candidates:
        season = _match_season(studio, season_raw)
        if season is None:
            return None, f'Encore could not resolve season "{season_raw}".'
        return None, (
            f'Encore found season "{season.name}", but no imported class matched '
            f'Studio Director class "{class_name}".'
        )

    if len(candidates) == 1:
        return candidates[0], ""

    instructor_raw = _source_value(row, "Instructor")
    if instructor_raw:
        instructor, error = resolve_instructor(studio, instructor_raw)
        if instructor and not error:
            matches = [
                item for item in candidates
                if item.instructor_id == instructor.pk
            ]
            if len(matches) == 1:
                return matches[0], ""
            if matches:
                candidates = matches

    if len(candidates) == 1:
        return candidates[0], ""

    return None, (
        f'Multiple Encore classes match dropped enrollment "{class_name}". '
        "The drop-history report does not contain enough scheduling information "
        "to identify the correct class automatically."
    )


def discover_enrollments(studio, rows):
    proposals = []
    seen_pairs = set()

    for row_number, row in enumerate(rows, start=2):
        # In Studio Director, a populated Student Class List row is itself the
        # evidence that the student/class relationship exists. The report's
        # Yes/No-style Status value is not reliable as Encore enrollment state.
        class_name_raw = _source_value(row, "Class Name", "Name")
        season_raw = _source_value(row, "Season")

        # Some Student Class List exports include student-only rows with no class.
        # Those are not enrollment records and should quietly skip instead of
        # flooding Needs Review.
        if not class_name_raw or not season_raw:
            continue

        student, student_note = resolve_student(studio, row)
        class_instance, class_note = resolve_class_for_student_list(studio, row)
        status_raw = _source_value(row, "Status", "Enrollment Status", "Enrolled")

        errors = []
        warnings = []

        if student is None:
            errors.append(student_note)
        elif student_note:
            warnings.append(student_note)

        if class_instance is None:
            errors.append(class_note)
        elif class_note:
            warnings.append(class_note)

        # Status comes from Encore's season context:
        # historical season -> Completed
        # current/future season -> Active
        status = Enrollment.Status.ACTIVE
        if class_instance is not None and class_instance.season.end_date < date.today():
            status = Enrollment.Status.COMPLETED

        # Preserve truly explicit vendor states if they ever appear, but do not
        # treat generic Yes/No values as enrollment status.
        status_text = _clean_token(status_raw).lower()
        if "waitlist" in status_text or "waiting" in status_text:
            status = Enrollment.Status.WAITLISTED
        elif "cancel" in status_text:
            status = Enrollment.Status.CANCELLED
        elif "drop" in status_text or "withdraw" in status_text:
            status = Enrollment.Status.DROPPED
        elif "complete" in status_text or "finished" in status_text:
            status = Enrollment.Status.COMPLETED

        if status_raw and status_text in {"yes", "no", "y", "n", "true", "false", "1", "0"}:
            warnings.append(
                f'Studio Director Status "{status_raw}" was ignored; the Student Class List row itself '
                "is treated as the enrollment relationship."
            )

        pair_key = None
        existing = None
        if student is not None and class_instance is not None:
            pair_key = f"{student.pk}:{class_instance.pk}"
            existing = Enrollment.objects.filter(
                student=student,
                class_instance=class_instance,
            ).first()

            if pair_key in seen_pairs:
                errors.append(
                    "This Student Class List contains a duplicate row for the same student and class."
                )
            else:
                seen_pairs.add(pair_key)

        proposal_key = pair_key or f"row-{row_number}"
        label = (
            f"{student.first_name} {student.last_name} → {class_instance.name}"
            if student and class_instance
            else f"CSV row {row_number}"
        )

        proposals.append(
            {
                "key": proposal_key,
                "row_number": row_number,
                "label": label,
                "student_id": student.pk if student else None,
                "student_name": str(student) if student else "",
                "class_id": class_instance.pk if class_instance else None,
                "class_name": class_instance.name if class_instance else _source_value(row, "Class Name", "Name"),
                "class_code": class_instance.class_id if class_instance else "",
                "season_name": class_instance.season.name if class_instance else _source_value(row, "Season"),
                "day": _source_value(row, "Day"),
                "start_time": _source_value(row, "Start Time", "Start"),
                "room": _source_value(row, "Location", "Room"),
                "status_value": status,
                "status_label": dict(Enrollment.Status.choices).get(status, status_raw),
                "source_status": status_raw,
                "errors": errors,
                "warnings": warnings,
                "existing_id": existing.pk if existing else None,
                "status": "error" if errors else ("update" if existing else "create"),
                "reason": (
                    errors[0]
                    if errors
                    else (
                        "Existing enrollment will be synchronized."
                        if existing
                        else "Student and scheduled class matched."
                    )
                ),
                "source_data": row,
            }
        )

    return proposals


def _drop_notes(row):
    reason = _source_value(row, "Drop Reason", "Reason")
    notes = _source_value(row, "Drop Notes", "Notes")
    dropped_by = _source_value(row, "Dropped By")
    days = _source_value(row, "Total Days Enrolled")

    parts = []
    if reason:
        parts.append(f"Studio Director drop reason: {reason}")
    if notes:
        parts.append(f"Drop notes: {notes}")
    if dropped_by:
        parts.append(f"Dropped by: {dropped_by}")
    if days:
        parts.append(f"Studio Director total days enrolled: {days}")
    return "\n".join(parts)


def discover_drop_history(studio, rows):
    proposals = []
    seen_pairs = set()

    for row_number, row in enumerate(rows, start=2):
        source_for_student = dict(row)
        if not _source_value(source_for_student, "First Name"):
            source_for_student["First Name"] = _source_value(
                row, "Student First Name", "Student"
            )
        if not _source_value(source_for_student, "Last Name"):
            source_for_student["Last Name"] = _source_value(
                row, "Student Last Name"
            )

        student, student_note = resolve_student(studio, source_for_student)
        class_instance, class_note = resolve_class_for_drop_history(studio, row)

        errors = []
        warnings = []

        if student is None:
            errors.append(student_note)
        elif student_note:
            warnings.append(student_note)

        if class_instance is None:
            errors.append(class_note)

        existing = None
        pair_key = None
        if student is not None and class_instance is not None:
            pair_key = f"{student.pk}:{class_instance.pk}"
            existing = Enrollment.objects.filter(
                student=student,
                class_instance=class_instance,
            ).first()

            if pair_key in seen_pairs:
                errors.append("Duplicate drop-history row for the same student and class.")
            else:
                seen_pairs.add(pair_key)

            if existing and existing.status == Enrollment.Status.ACTIVE:
                errors.append(
                    "Encore currently has this student actively enrolled in the class. "
                    "The drop-history record will not overwrite an active current enrollment."
                )

        dropped_at = parse_studio_director_datetime(
            _source_value(
                row,
                "Drop Classes Date",
                "Drop Date",
                "Dropped Date",
            )
        )
        enrolled_at = parse_studio_director_datetime(
            _source_value(
                row,
                "Signup Time",
                "Sign Up Time",
                "Enrollment Date",
            )
        )

        proposal_key = pair_key or f"drop-row-{row_number}"
        label = (
            f"{student.first_name} {student.last_name} → {class_instance.name}"
            if student and class_instance
            else f"CSV row {row_number}"
        )

        proposals.append(
            {
                "key": proposal_key,
                "row_number": row_number,
                "label": label,
                "student_id": student.pk if student else None,
                "student_name": str(student) if student else "",
                "class_id": class_instance.pk if class_instance else None,
                "class_name": class_instance.name if class_instance else _source_value(row, "Class Name", "Name"),
                "class_code": class_instance.class_id if class_instance else "",
                "season_name": class_instance.season.name if class_instance else _source_value(row, "Season"),
                "status_value": Enrollment.Status.DROPPED,
                "status_label": "Dropped",
                "drop_reason": _source_value(row, "Drop Reason", "Reason"),
                "drop_notes": _source_value(row, "Drop Notes", "Notes"),
                "notes": _drop_notes(row),
                "dropped_at": dropped_at.isoformat() if dropped_at else "",
                "enrolled_at": enrolled_at.isoformat() if enrolled_at else "",
                "errors": errors,
                "warnings": warnings,
                "existing_id": existing.pk if existing else None,
                "status": "error" if errors else ("update" if existing else "create"),
                "reason": (
                    errors[0]
                    if errors
                    else (
                        "Existing historical enrollment will be marked Dropped."
                        if existing
                        else "Dropped enrollment history matched."
                    )
                ),
                "source_data": row,
            }
        )

    return proposals
