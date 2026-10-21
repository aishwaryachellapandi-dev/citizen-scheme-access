from flask import Flask, render_template, request, redirect, url_for, session, jsonify

import mysql.connector

from mysql.connector import Error

from werkzeug.security import generate_password_hash, check_password_hash

from dotenv import load_dotenv

from groq import Groq

import os

import re

import json

import time



# ============================================================

# APP CONFIGURATION

# ============================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(

    "FLASK_SECRET_KEY",

    "citizen-guide-ai-secret-key"

)



# ============================================================

# GROQ CONFIGURATION

# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:

    print("WARNING: GROQ_API_KEY is not configured in .env")

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

GROQ_MODEL = "openai/gpt-oss-20b"



# ============================================================

# DATABASE CONFIGURATION

# ============================================================

DB_CONFIG = {

    "host": "localhost",

    "user": "root",

    "password": "CitizenGuide@123",

    "database": "citizen_guide_ai"

}



# ============================================================

# DATABASE CONNECTION

# ============================================================

def get_db_connection():

    try:

        connection = mysql.connector.connect(**DB_CONFIG)

        if connection.is_connected():

            return connection

    except Error as e:

        print("Database connection error:", e)

    return None



# ============================================================

# GENERAL HELPERS

# ============================================================

def normalize_text(text):

    if not text:

        return ""

    text = str(text).lower().strip()

    text = re.sub(r"\s+", " ", text)

    return text



def clean_display_text(text):

    if not text:

        return ""

    text = str(text)

    text = text.replace("```", "")

    text = text.replace("**", "")

    text = text.replace("__", "")

    text = text.replace("###", "")

    text = text.replace("##", "")

    text = text.replace("#", "")

    text = re.sub(r"\*{3,}\s*\n\s*\*{3,}", "\n\n", text)

    return text.strip()



def clean_voice_text(text):

    if not text:

        return ""

    text = str(text)

    # Remove URLs

    text = re.sub(

        r"https?://\S+|www.\S+",

        "",

        text,

        flags=re.IGNORECASE

    )

    # Remove code blocks

    text = re.sub(

        r"```.*?```",

        "",

        text,

        flags=re.DOTALL

    )

    # Markdown

    text = text.replace("**", "")

    text = text.replace("__", "")

    text = text.replace("`", "")

    text = text.replace("#", "")

    # Formatting

    text = text.replace("|", " ")

    text = text.replace("_", " ")

    text = text.replace("/", " ")

    text = text.replace("\\\\", " ")

    # Bullets

    text = re.sub(

        r"(?m)^\s*[-•*]\s*",

        "",

        text

    )

    # Numbered list markers

    text = re.sub(

        r"(?m)^\s*\d+[.)]\s*",

        "",

        text

    )

    # Table separators

    text = re.sub(

        r"(?m)^\s*[-: ]{3,}\s*$",

        "",

        text

    )

    # Brackets

    text = re.sub(

        r"[**\\[\\]**{}<>]",

        " ",

        text

    )

    # Extra spaces

    text = re.sub(

        r"\s+",

        " ",

        text

    )

    return text.strip()



def detect_language(text):

    if not text:

        return "en-IN"

    tamil_chars = sum(

        1

        for char in text

        if "\u0B80" <= char <= "\u0BFF"

    )

    if tamil_chars > 0:

        return "ta-IN"

    return "en-IN"



# ============================================================

# GREETING DETECTION

# ============================================================

def is_simple_greeting(message):

    text = normalize_text(message)

    greetings = {

        "hi",

        "hello",

        "hey",

        "hii",

        "hiii",

        "hai",

        "good morning",

        "good afternoon",

        "good evening",

        "vanakkam",

        "வணக்கம்"

    }

    return text in greetings



# ============================================================

# INTENT DETECTION

# ============================================================

def detect_question_intent(message):

    text = normalize_text(message)

    # Greeting

    if is_simple_greeting(text):

        return "GREETING"

    # Category detection

    is_scheme = any(

        word in text

        for word in [

            "scheme",

            "schemes",

            "thittam",

            "thittangal",

            "திட்டம்",

            "திட்டங்கள்"

        ]

    )

    is_scholarship = any(

        word in text

        for word in [

            "scholarship",

            "scholarships",

            "stipend",

            "kalvi uthavi",

            "கல்வி உதவி"

        ]

    )

    is_service = any(

        word in text

        for word in [

            "service",

            "services",

            "citizen service",

            "government service",

            "சேவை",

            "சேவைகள்"

        ]

    )

    # Eligibility

    if any(

        word in text

        for word in [

            "eligibility",

            "eligible",

            "qualification",

            "qualify",

            "who can apply",

            "yar apply",

            "யார் விண்ணப்பிக்க"

        ]

    ):

        return "ELIGIBILITY"

    # Benefits

    if any(

        word in text

        for word in [

            "benefit",

            "benefits",

            "benefits enna",

            "what do i get",

            "payangal",

            "பயன்",

            "பயன்கள்"

        ]

    ):

        return "BENEFITS"

    # Documents

    if any(

        word in text

        for word in [

            "document",

            "documents",

            "required document",

            "required documents",

            "proof",

            "papers",

            "enna documents",

            "என்ன ஆவணம்",

            "ஆவணங்கள்"

        ]

    ):

        return "DOCUMENTS"

    # Application

    if any(

        word in text

        for word in [

            "how to apply",

            "how can i apply",

            "application process",

            "apply process",

            "apply panna",

            "eppadi apply",

            "எப்படி apply",

            "எப்படி விண்ணப்பிக்க"

        ]

    ):

        return "APPLICATION_PROCESS"

    # Deadline

    if any(

        word in text

        for word in [

            "deadline",

            "last date",

            "closing date",

            "due date",

            "last date eppo",

            "கடைசி தேதி"

        ]

    ):

        return "DEADLINE"

    # Details

    detail_words = [

        "details",

        "detail",

        "full details",

        "complete details",

        "pathi sollu",

        "about",

        "explain",

        "விவரம்",

        "விவரங்கள்"

    ]

    has_details = any(

        word in text

        for word in detail_words

    )

    if has_details and is_scheme:

        return "SCHEME_DETAILS"

    if has_details and is_scholarship:

        return "SCHOLARSHIP_DETAILS"

    if has_details and is_service:

        return "SERVICE_DETAILS"

    # Lists

    list_words = [

        "list",

        "available",

        "what are",

        "which",

        "what schemes",

        "what scholarship",

        "what scholarships",

        "what services",

        "enna iruku",

        "enna schemes",

        "enna scholarship",

        "enna services",

        "கிடைக்கும்",

        "என்ன திட்டங்கள்"

    ]

    has_list_request = any(

        word in text

        for word in list_words

    )

    if is_scheme and has_list_request:

        return "SCHEME_LIST"

    if is_scholarship and has_list_request:

        return "SCHOLARSHIP_LIST"

    if is_service and has_list_request:

        return "SERVICE_LIST"

    # Category alone

    if is_scheme and not is_scholarship and not is_service:

        return "SCHEME_LIST"

    if is_scholarship and not is_scheme and not is_service:

        return "SCHOLARSHIP_LIST"

    if is_service and not is_scheme and not is_scholarship:

        return "SERVICE_LIST"

    return "GENERAL_PROJECT_QUESTION"



# ============================================================

# SEARCH TERM CREATION

# ============================================================

def create_search_terms(message):

    text = normalize_text(message)

    stop_words = {

        "i",

        "want",

        "need",

        "give",

        "show",

        "tell",

        "me",

        "please",

        "can",

        "you",

        "what",

        "which",

        "are",

        "is",

        "the",

        "for",

        "about",

        "details",

        "detail",

        "full",

        "complete",

        "information",

        "info",

        "list",

        "available",

        "currently",

        "there",

        "any",

        "have",

        "has",

        "and",

        "or",

        "to",

        "of",

        "in",

        "on",

        "from",

        "my",

        "how",

        "why",

        "when",

        "where",

        "who",

        "apply",

        "application",

        "process",

        "scheme",

        "schemes",

        "scholarship",

        "scholarships",

        "service",

        "services",

        "benefit",

        "benefits",

        "eligibility",

        "eligible",

        "qualification",

        "qualify",

        "document",

        "documents",

        "deadline",

        "last",

        "date",

        "students",

        "student",

        "college",

        "school",

        "job",

        "seeker",

        "seekers",

        "graduate",

        "graduates",

        "youth",

        "citizen",

        "citizens",

        "employee",

        "employees",

        "worker",

        "workers",

        "women",

        "woman",

        "men",

        "farmer",

        "farmers",

        "senior",

        "people",

        "person",

        "கல்வி",

        "திட்டம்",

        "திட்டங்கள்",

        "சேவை",

        "சேவைகள்",

        "ஆவணம்",

        "ஆவணங்கள்"

    }

    words = re.findall(

        r"[a-zA-Z0-9\u0B80-\u0BFF]+",

        text

    )

    terms = []

    for word in words:

        if len(word) <= 1:

            continue

        if word in stop_words:

            continue

        terms.append(word)

    unique_terms = []

    for term in terms:

        if term not in unique_terms:

            unique_terms.append(term)

    return unique_terms[:12]



# ============================================================

# GET ALL RECORDS

# ============================================================

def fetch_all_records():

    connection = get_db_connection()

    if not connection:

        return {

            "schemes": [],

            "scholarships": [],

            "services": []

        }

    cursor = connection.cursor(dictionary=True)

    data = {

        "schemes": [],

        "scholarships": [],

        "services": []

    }

    try:

        cursor.execute("""

            SELECT

                s.scheme_id,

                s.scheme_name,

                s.description,

                s.eligibility,

                s.benefits,

                s.required_documents,

                s.application_process,

                s.application_url,

                s.department

            FROM schemes s

            ORDER BY s.scheme_name

        """)

        data["schemes"] = cursor.fetchall()

        cursor.execute("""

            SELECT

                sc.scholarship_id,

                sc.scholarship_name,

                sc.provider,

                sc.education_level,

                sc.description,

                sc.eligibility,

                sc.benefits,

                sc.required_documents,

                sc.application_process,

                sc.application_url,

                sc.deadline

            FROM scholarships sc

            ORDER BY sc.scholarship_name

        """)

        data["scholarships"] = cursor.fetchall()

        cursor.execute("""

            SELECT

                sv.service_id,

                sv.service_name,

                sv.category,

                sv.description,

                sv.eligibility,

                sv.required_documents,

                sv.application_url,

                sv.department

            FROM services sv

            ORDER BY sv.service_name

        """)

        data["services"] = cursor.fetchall()
        for service in data["services"]:
            service.setdefault("application_process", None)

    except Error as e:

        print("Error fetching all records:", e)

    finally:

        cursor.close()

        connection.close()

    return data



# ============================================================

# GET STAGE-LINKED RECORDS

# ============================================================

def fetch_stage_records(stage_id):

    if not stage_id:

        return {

            "schemes": [],

            "scholarships": [],

            "services": []

        }

    connection = get_db_connection()

    if not connection:

        return {

            "schemes": [],

            "scholarships": [],

            "services": []

        }

    cursor = connection.cursor(dictionary=True)

    result = {

        "schemes": [],

        "scholarships": [],

        "services": []

    }

    try:

        cursor.execute("""

            SELECT

                s.scheme_id,

                s.scheme_name,

                s.description,

                s.eligibility,

                s.benefits,

                s.required_documents,

                s.application_process,

                s.application_url,

                s.department

            FROM schemes s

            INNER JOIN scheme_stages ss

                ON s.scheme_id = ss.scheme_id

            WHERE ss.stage_id = %s

            ORDER BY s.scheme_name

        """, (stage_id,))

        result["schemes"] = cursor.fetchall()

        cursor.execute("""

            SELECT

                sc.scholarship_id,

                sc.scholarship_name,

                sc.provider,

                sc.education_level,

                sc.description,

                sc.eligibility,

                sc.benefits,

                sc.required_documents,

                sc.application_process,

                sc.application_url,

                sc.deadline

            FROM scholarships sc

            INNER JOIN scholarship_stages sst

                ON sc.scholarship_id = sst.scholarship_id

            WHERE sst.stage_id = %s

            ORDER BY sc.scholarship_name

        """, (stage_id,))

        result["scholarships"] = cursor.fetchall()

        cursor.execute("""

            SELECT

                sv.service_id,

                sv.service_name,

                sv.category,

                sv.description,

                sv.eligibility,

                sv.required_documents,

                sv.application_url,

                sv.department

            FROM services sv

            INNER JOIN service_stages ssv

                ON sv.service_id = ssv.service_id

            WHERE ssv.stage_id = %s

            ORDER BY sv.service_name

        """, (stage_id,))

        result["services"] = cursor.fetchall()
        for service in result["services"]:
            service.setdefault("application_process", None)

    except Error as e:

        print("Stage record error:", e)

    finally:

        cursor.close()

        connection.close()

    return result



# ============================================================

# RECORD SEARCH

# ============================================================

def record_matches(record, terms):

    if not terms:

        return True

    searchable_fields = []

    for key, value in record.items():

        if value is None:

            continue

        searchable_fields.append(str(value))

    searchable_text = normalize_text(

        " ".join(searchable_fields)

    )

    matched = 0

    for term in terms:

        if normalize_text(term) in searchable_text:

            matched += 1

    return matched > 0



def score_record(record, terms):

    if not terms:

        return 0

    score = 0

    name_fields = [

        "scheme_name",

        "scholarship_name",

        "service_name"

    ]

    for field in name_fields:

        value = normalize_text(

            record.get(field, "")

        )

        if not value:

            continue

        for term in terms:

            if term in value:

                score += 5

    all_text = normalize_text(

        " ".join(

            str(value)

            for value in record.values()

            if value is not None

        )

    )

    for term in terms:

        if term in all_text:

            score += 1

    return score



def find_matching_records(records, terms, limit=5):

    if not records:

        return []

    if not terms:

        return records[:limit]

    scored_records = []

    for record in records:

        if record_matches(record, terms):

            score = score_record(

                record,

                terms

            )

            scored_records.append(

                (score, record)

            )

    scored_records.sort(

        key=lambda item: item[0],

        reverse=True

    )

    return [

        record

        for score, record

        in scored_records[:limit]

    ]



# ============================================================

# COMPACT DATABASE RECORD

# ============================================================

def compact_record(record, intent):

    result = {}

    if "scheme_name" in record:

        result["name"] = record.get("scheme_name")

        result["description"] = record.get("description")

        if intent in [

            "SCHEME_DETAILS",

            "ELIGIBILITY",

            "BENEFITS",

            "DOCUMENTS",

            "APPLICATION_PROCESS",

            "DEADLINE",

            "GENERAL_PROJECT_QUESTION"

        ]:

            result["eligibility"] = record.get("eligibility")

            result["benefits"] = record.get("benefits")

            result["required_documents"] = record.get(

                "required_documents"

            )

            result["application_process"] = record.get(

                "application_process"

            )

            result["application_url"] = record.get(

                "application_url"

            )

            result["department"] = record.get("department")

    elif "scholarship_name" in record:

        result["name"] = record.get("scholarship_name")

        result["provider"] = record.get("provider")

        result["education_level"] = record.get(

            "education_level"

        )

        result["description"] = record.get("description")

        if intent in [

            "SCHOLARSHIP_DETAILS",

            "ELIGIBILITY",

            "BENEFITS",

            "DOCUMENTS",

            "APPLICATION_PROCESS",

            "DEADLINE",

            "GENERAL_PROJECT_QUESTION"

        ]:

            result["eligibility"] = record.get("eligibility")

            result["benefits"] = record.get("benefits")

            result["required_documents"] = record.get(

                "required_documents"

            )

            result["application_process"] = record.get(

                "application_process"

            )

            result["application_url"] = record.get(

                "application_url"

            )

            result["deadline"] = record.get("deadline")

    elif "service_name" in record:

        result["name"] = record.get("service_name")

        result["category"] = record.get("category")

        result["description"] = record.get("description")

        if intent in [

            "SERVICE_DETAILS",

            "ELIGIBILITY",

            "BENEFITS",

            "DOCUMENTS",

            "APPLICATION_PROCESS",

            "DEADLINE",

            "GENERAL_PROJECT_QUESTION"

        ]:

            result["eligibility"] = record.get("eligibility")

            result["required_documents"] = record.get(

                "required_documents"

            )

            result["application_process"] = record.get(

                "application_process"

            )

            result["application_url"] = record.get(

                "application_url"

            )

            result["department"] = record.get("department")

    return result



# ============================================================

# GET CURRENT USER

# ============================================================

def get_current_user():

    user_id = session.get("user_id")

    if not user_id:

        return None

    connection = get_db_connection()

    if not connection:

        return None

    cursor = connection.cursor(dictionary=True)

    user = None

    try:

        cursor.execute("""

            SELECT *

            FROM users

            WHERE user_id = %s

        """, (user_id,))

        user = cursor.fetchone()

    except Error as e:

        print("User fetch error:", e)

    finally:

        cursor.close()

        connection.close()

    return user



# ============================================================

# GET USER STAGE

# ============================================================

def get_user_stage():

    user_id = session.get("user_id")

    if not user_id:

        return None

    connection = get_db_connection()

    if not connection:

        return None

    cursor = connection.cursor(dictionary=True)

    stage = None

    try:

        cursor.execute("""

            SELECT

                u.stage_id,

                s.stage_name

            FROM users u

            LEFT JOIN stages s

                ON u.stage_id = s.stage_id

            WHERE u.user_id = %s

        """, (user_id,))

        stage = cursor.fetchone()

    except Error as e:

        print("Stage fetch error:", e)

    finally:

        cursor.close()

        connection.close()

    return stage



# ============================================================

# ASSISTANT NAVIGATION / STAGE HELPERS

# ============================================================

def get_all_stages():
    connection = get_db_connection()
    if not connection:
        return []

    cursor = connection.cursor(dictionary=True)
    stages = []
    try:
        cursor.execute("""
            SELECT stage_id, stage_name
            FROM stages
            ORDER BY stage_id
        """)
        stages = cursor.fetchall()
    except Error as e:
        print("Stage catalog error:", e)
    finally:
        cursor.close()
        connection.close()
    return stages


def stage_keyword_aliases():
    return {
        "college": ["college", "college student", "college students", "degree", "ug", "pg", "university", "கல்லூரி"],
        "school": ["school", "school student", "school students", "10th", "11th", "12th", "higher secondary", "பள்ளி"],
        "job": ["job seeker", "job seekers", "job", "employment", "unemployed", "graduate", "graduates", "career", "வேலை", "வேலை தேடுபவர்"],
        "parent": ["parent", "parents", "mother", "father", "பெற்றோர்", "தாய்", "தந்தை"],
        "farmer": ["farmer", "farmers", "agriculture", "விவசாயி", "விவசாயிகள்"],
        "student": ["student", "students", "மாணவர்", "மாணவர்கள்"]
    }


def detect_stage_from_question(message):
    text = normalize_text(message)
    aliases = stage_keyword_aliases()
    detected = []

    for stage_type, keywords in aliases.items():
        if any(keyword in text for keyword in keywords):
            detected.append(stage_type)

    specific = [x for x in detected if x != "student"]
    if len(specific) == 1:
        return specific[0]
    if not specific and "student" in detected:
        return "student"
    return None


def get_stage_id_by_keyword(stage_keyword):
    if not stage_keyword:
        return None

    stages = get_all_stages()
    aliases = stage_keyword_aliases().get(stage_keyword, [stage_keyword])

    for stage in stages:
        stage_name = normalize_text(stage.get("stage_name", ""))
        for alias in aliases:
            alias_text = normalize_text(alias)
            if alias_text and (
                stage_name == alias_text
                or alias_text in stage_name
                or stage_name in alias_text
            ):
                return stage.get("stage_id")

    return None


def find_specific_record(message):
    text = normalize_text(message)
    records = fetch_all_records()
    candidates = []

    for record in records["schemes"]:
        name = normalize_text(record.get("scheme_name", ""))
        if name and name in text:
            candidates.append((len(name), "scheme", record.get("scheme_id"), record.get("scheme_name")))

    for record in records["scholarships"]:
        name = normalize_text(record.get("scholarship_name", ""))
        if name and name in text:
            candidates.append((len(name), "scholarship", record.get("scholarship_id"), record.get("scholarship_name")))

    for record in records["services"]:
        name = normalize_text(record.get("service_name", ""))
        if name and name in text:
            candidates.append((len(name), "service", record.get("service_id"), record.get("service_name")))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    _, record_type, record_id, record_name = candidates[0]

    if record_type == "scheme":
        target_url = url_for("scheme_details", scheme_id=record_id)
    elif record_type == "scholarship":
        target_url = url_for("scholarship_details", scholarship_id=record_id)
    else:
        target_url = url_for("service_details", service_id=record_id)

    return {"type": record_type, "id": record_id, "name": record_name, "target_url": target_url}


def is_stage_overview_question(message, intent):
    text = normalize_text(message)
    category_words = ["scheme", "schemes", "scholarship", "scholarships", "service", "services", "thittam", "thittangal", "சேவை", "திட்டம்"]
    stage_words = ["student", "students", "college", "school", "job seeker", "parent", "parents", "farmer", "graduate", "வேலை", "கல்லூரி", "பள்ளி", "பெற்றோர்", "விவசாயி"]
    return any(word in text for word in category_words) and any(word in text for word in stage_words) and intent in {"GENERAL_PROJECT_QUESTION", "SCHEME_LIST", "SCHOLARSHIP_LIST", "SERVICE_LIST", "ELIGIBILITY"}


def is_stage_only_message(message):
    text = normalize_text(message)
    aliases = stage_keyword_aliases()
    for stage_type, keywords in aliases.items():
        for keyword in keywords:
            if text == normalize_text(keyword):
                return stage_type
    return None


def needs_stage_clarification(message, intent):
    text = normalize_text(message)
    has_category = any(word in text for word in [
        "scheme", "schemes", "scholarship", "scholarships",
        "service", "services", "திட்டம்", "திட்டங்கள்", "சேவை", "சேவைகள்"
    ])
    has_eligibility = intent == "ELIGIBILITY"
    detected_stage = detect_stage_from_question(message)
    return has_category and has_eligibility and detected_stage is None


def stage_clarification_reply(language):
    if language.startswith("ta"):
        return "உங்களுக்கு சரியான guidance கொடுக்க, நீங்கள் school student-aa, college student-aa, job seeker-aa, parent-aa அல்லது farmer-aa என்று சொல்லுங்கள்."
    return "To give you the right guidance, please tell me your stage: school student, college student, job seeker, parent, or farmer."


def navigation_reply(language, destination_name):
    if language.startswith("ta"):
        return f"சரி. {destination_name} தொடர்பான தகவலுக்கு அந்த page-ஐ திறக்கிறேன்."
    return f"Sure. I’ll open the page for {destination_name}."


# ============================================================

# PREPARE DATABASE CONTEXT

# ============================================================

def get_relevant_database_context(

    message,

    intent,

    user_stage

):

    terms = create_search_terms(message)

    all_records = fetch_all_records()

    scheme_records = all_records["schemes"]

    scholarship_records = all_records["scholarships"]

    service_records = all_records["services"]

    detected_stage = detect_stage_from_question(message)

    detected_stage_id = get_stage_id_by_keyword(

        detected_stage

    )

    # Explicit stage mentioned

    if detected_stage_id:

        detected_stage_records = fetch_stage_records(

            detected_stage_id

        )

        scheme_records = detected_stage_records["schemes"]

        scholarship_records = detected_stage_records[

            "scholarships"

        ]

        service_records = detected_stage_records[

            "services"

        ]

    # No explicit stage

    elif user_stage and user_stage.get("stage_id"):

        selected_stage_records = fetch_stage_records(

            user_stage.get("stage_id")

        )

        if not scheme_records:

            scheme_records = selected_stage_records["schemes"]

        if not scholarship_records:

            scholarship_records = selected_stage_records[

                "scholarships"

            ]

        if not service_records:

            service_records = selected_stage_records[

                "services"

            ]

    context = {

        "query": message,

        "intent": intent,

        "mentioned_stage": detected_stage,

        "schemes": [],

        "scholarships": [],

        "services": []

    }

    # Scheme

    if intent in [

        "SCHEME_LIST",

        "SCHEME_DETAILS"

    ]:

        matched = find_matching_records(

            scheme_records,

            terms,

            5

        )

        if not matched and not terms:

            matched = scheme_records[:5]

        context["schemes"] = [

            compact_record(record, intent)

            for record in matched

        ]

    # Scholarship

    elif intent in [

        "SCHOLARSHIP_LIST",

        "SCHOLARSHIP_DETAILS"

    ]:

        matched = find_matching_records(

            scholarship_records,

            terms,

            5

        )

        if not matched and not terms:

            matched = scholarship_records[:5]

        context["scholarships"] = [

            compact_record(record, intent)

            for record in matched

        ]

    # Service

    elif intent in [

        "SERVICE_LIST",

        "SERVICE_DETAILS"

    ]:

        matched = find_matching_records(

            service_records,

            terms,

            5

        )

        if not matched and not terms:

            matched = service_records[:5]

        context["services"] = [

            compact_record(record, intent)

            for record in matched

        ]

    # Other questions

    else:

        context["schemes"] = [

            compact_record(record, intent)

            for record in find_matching_records(

                scheme_records,

                terms,

                3

            )

        ]

        context["scholarships"] = [

            compact_record(record, intent)

            for record in find_matching_records(

                scholarship_records,

                terms,

                3

            )

        ]

        context["services"] = [

            compact_record(record, intent)

            for record in find_matching_records(

                service_records,

                terms,

                3

            )

        ]

        # Fallback

        if (

            not context["schemes"]

            and not context["scholarships"]

            and not context["services"]

        ):

            fallback_stage = None

            if detected_stage_id:

                fallback_stage = fetch_stage_records(

                    detected_stage_id

                )

            elif (

                user_stage

                and user_stage.get("stage_id")

            ):

                fallback_stage = fetch_stage_records(

                    user_stage.get("stage_id")

                )

            if fallback_stage:

                context["schemes"] = [

                    compact_record(record, intent)

                    for record in fallback_stage["schemes"][:3]

                ]

                context["scholarships"] = [

                    compact_record(record, intent)

                    for record in fallback_stage["scholarships"][:3]

                ]

                context["services"] = [

                    compact_record(record, intent)

                    for record in fallback_stage["services"][:3]

                ]

    return context



# ============================================================

# GROQ SYSTEM PROMPT

# ============================================================

SYSTEM_PROMPT = """

You are Citizen Guide AI, a simple government guidance assistant.

Your job is to answer questions about:

- Government schemes

- Scholarships

- Citizen services

- Eligibility

- Benefits

- Required documents

- Application process

- Deadlines

- Career-related government guidance when database information exists

IMPORTANT DATABASE RULE:

The supplied database context is the ONLY source of truth for government

scheme, scholarship and service records.

Never invent:

- Scheme names

- Scholarship names

- Benefits

- Eligibility

- Documents

- Deadlines

- Application procedures

- URLs

- Departments

- Amounts

If the requested information is not present in the supplied database context,

clearly say that the information is currently unavailable.

VERY IMPORTANT STAGE RULE:

The user's selected stage is NOT a restriction.

A user may select College Student but ask about Job Seekers.

A user may select School Student but ask about College Students.

A user may select Job Seeker but ask about School Students.

Always answer according to the user's CURRENT QUESTION.

If the user explicitly mentions a stage, prioritize that stage's records.

If no stage is mentioned, the selected stage can be used as context.

LANGUAGE:

- English question -> English answer.

- Tamil question -> Tamil answer.

- Tanglish question -> natural simple Tanglish answer.

- Mixed Tamil + English -> natural mixed Tamil + English answer.

STYLE:

- Keep answers SHORT and clear.

- Normally 2 to 5 short sentences.

- Use simple words.

- Directly answer the question.

- Do not give unnecessary explanations.

- Do not dump the database.

- Do not use Markdown tables.

- Do not use long separator lines.

- Avoid unnecessary symbols.

- Do not use underscores as formatting.

- Do not use pipe characters.

- Do not write raw JSON.

- Do not repeat the user's question.

LIST QUESTIONS:

If the user asks what schemes, scholarships or services are available,

give the relevant names from the database in a short list.

DETAIL QUESTIONS:

Give the most useful details from the supplied database record.

FIELD QUESTIONS:

If the user asks about eligibility, benefits, documents, application process

or deadline, answer only from the supplied database information.

If a requested field is missing, say that particular information is not

currently available in the database.

GREETING:

Reply naturally and briefly.

GENERAL PROJECT QUESTIONS:

Answer based on Citizen Guide AI functionality when the question is about

the project.

Never claim that something exists in the database unless it is present in

the supplied context.

"""



# ============================================================

# GROQ REQUEST

# ============================================================

def ask_groq(

    user_message,

    database_context,

    intent,

    language

):

    if not groq_client:

        return "AI service is not configured right now."

    language_name = (

        "Tamil"

        if language.startswith("ta")

        else "English"

    )

    prompt = f"""

User question:

{user_message}

Detected intent:

{intent}

Response language:

{language_name}

Database context:

{json.dumps(

    database_context,

    ensure_ascii=False,

    default=str

)}

Answer the user's question directly.

Remember:

1. Database context is the source of truth.

2. Do not invent missing information.

3. User's selected stage is NOT a restriction.

4. If another stage is mentioned in the question, answer for that stage.

5. Keep the answer short and simple.

6. Do not use Markdown tables.

7. Do not use underscore formatting.

8. Do not use pipe characters.

9. Do not include unnecessary symbols.

"""

    max_retries = 3

    for attempt in range(max_retries):

        try:

            response = groq_client.chat.completions.create(

                model=GROQ_MODEL,

                messages=[

                    {

                        "role": "system",

                        "content": SYSTEM_PROMPT

                    },

                    {

                        "role": "user",

                        "content": prompt

                    }

                ],

                temperature=0.2,

                max_tokens=500

            )

            answer = response.choices[0].message.content

            if answer:

                return clean_display_text(answer)

            return "Sorry, I could not generate a response right now."

        except Exception as e:

            error_text = str(e).lower()

            print(

                f"Groq error attempt {attempt + 1}:",

                e

            )

            retryable = any(

                code in error_text

                for code in [

                    "429",

                    "500",

                    "502",

                    "503",

                    "timeout",

                    "temporarily unavailable",

                    "rate limit"

                ]

            )

            if (

                retryable

                and attempt < max_retries - 1

            ):

                time.sleep(

                    2 * (attempt + 1)

                )

                continue

            return (

                "Sorry, AI service is temporarily "

                "unavailable. Please try again."

            )

    return "Sorry, I could not process your request."



# ============================================================

# HOME

# ============================================================

@app.route("/")

@app.route("/home")

def home():

    return render_template("index.html")



# ============================================================

# LOGIN

# ============================================================

@app.route("/login", methods=["GET", "POST"])

def login():

    if request.method == "GET":

        return render_template("login.html")

    # --------------------------------------------------------

    # GET FORM VALUES

    # --------------------------------------------------------

    username = request.form.get(

        "username",

        ""

    ).strip()

    email = request.form.get(

        "email",

        ""

    ).strip()

    password = request.form.get(

        "password",

        ""

    )

    # --------------------------------------------------------

    # VALIDATION

    # --------------------------------------------------------

    if not username or not email or not password:

        return render_template(

            "login.html",

            error="Please enter username, email and password."

        )

    connection = get_db_connection()

    if not connection:

        return render_template(

            "login.html",

            error="Database connection failed."

        )

    cursor = connection.cursor(

        dictionary=True

    )

    try:

        # ----------------------------------------------------

        # CHECK USERS TABLE COLUMNS

        # ----------------------------------------------------

        cursor.execute(

            "SHOW COLUMNS FROM users"

        )

        columns = [

            row["Field"]

            for row in cursor.fetchall()

        ]

        print(

            "Users table columns:",

            columns

        )

        has_email = "email" in columns

        has_password_hash = "password_hash" in columns

        has_full_name = "full_name" in columns

        print(

            "Email column exists:",

            has_email

        )

        # ----------------------------------------------------

        # FIND EXISTING USER

        # ----------------------------------------------------

        if has_email:

            cursor.execute("""

                SELECT *

                FROM users

                WHERE username = %s

                   OR email = %s

                LIMIT 1

            """, (

                username,

                email

            ))

        else:

            cursor.execute("""

                SELECT *

                FROM users

                WHERE username = %s

                LIMIT 1

            """, (

                username,

            ))

        user = cursor.fetchone()

        # ====================================================

        # EXISTING USER

        # ====================================================

        if user:

            print(

                "Existing user found:",

                user.get("user_id")

            )

            stored_password = user.get(

                "password_hash"

            )

            if not stored_password:

                return render_template(

                    "login.html",

                    error="Password information is missing."

                )

            # ------------------------------------------------

            # CHECK HASHED PASSWORD

            # ------------------------------------------------

            valid_password = False

            try:

                valid_password = check_password_hash(

                    stored_password,

                    password

                )

            except Exception as e:

                print(

                    "Password hash check error:",

                    e

                )

                valid_password = False

            # ------------------------------------------------

            # SUPPORT OLD PLAIN PASSWORD

            # ------------------------------------------------

            if not valid_password:

                valid_password = (

                    stored_password == password

                )

            # ------------------------------------------------

            # INVALID PASSWORD

            # ------------------------------------------------

            if not valid_password:

                return render_template(

                    "login.html",

                    error="Invalid username, email or password."

                )

            # ------------------------------------------------

            # LOGIN SUCCESS

            # ------------------------------------------------

            session.clear()

            session["user_id"] = user["user_id"]

            session["username"] = user.get(

                "username",

                username

            )

            print(

                "LOGIN SUCCESS - User ID:",

                user["user_id"]

            )

            print(

                "Redirecting to /stage"

            )

            return redirect(

                url_for("stage")

            )

        # ====================================================

        # NEW USER

        # ====================================================

        print(

            "No existing user found."

        )

        hashed_password = generate_password_hash(

            password

        )

        # ----------------------------------------------------

        # INSERT NEW USER

        # ----------------------------------------------------

        if has_full_name and has_email:

            cursor.execute("""

                INSERT INTO users

                (

                    full_name,

                    username,

                    email,

                    password_hash

                )

                VALUES

                (

                    %s,

                    %s,

                    %s,

                    %s

                )

            """, (

                username,

                username,

                email,

                hashed_password

            ))

        elif has_email:

            cursor.execute("""

                INSERT INTO users

                (

                    username,

                    email,

                    password_hash

                )

                VALUES

                (

                    %s,

                    %s,

                    %s

                )

            """, (

                username,

                email,

                hashed_password

            ))

        else:

            cursor.execute("""

                INSERT INTO users

                (

                    username,

                    password_hash

                )

                VALUES

                (

                    %s,

                    %s

                )

            """, (

                username,

                hashed_password

            ))

        connection.commit()

        user_id = cursor.lastrowid

        # ----------------------------------------------------

        # SAVE SESSION

        # ----------------------------------------------------

        session.clear()

        session["user_id"] = user_id

        session["username"] = username

        print(

            "NEW USER CREATED - User ID:",

            user_id

        )

        print(

            "Redirecting new user to /stage"

        )

        # ----------------------------------------------------

        # LOGIN -> STAGE

        # ----------------------------------------------------

        return redirect(

            url_for("stage")

        )

    except Error as e:

        connection.rollback()

        print(

            "LOGIN DATABASE ERROR:",

            e

        )

        return render_template(

            "login.html",

            error=f"Login database error: {e}"

        )

    except Exception as e:

        connection.rollback()

        print(

            "LOGIN ERROR:",

            e

        )

        return render_template(

            "login.html",

            error=f"Login error: {e}"

        )

    finally:

        cursor.close()

        connection.close()



# ============================================================

# STAGE SELECTION

# ============================================================

@app.route("/stage", methods=["GET", "POST"])

def stage():

    user_id = session.get("user_id")

    print(

        "STAGE ROUTE - Session user_id:",

        user_id

    )

    if not user_id:

        print(

            "No session user_id. Redirecting to login."

        )

        return redirect(

            url_for("login")

        )

    # ========================================================

    # POST - STAGE SELECTED

    # ========================================================

    if request.method == "POST":

        stage_id = request.form.get(

            "stage_id"

        )

        # ----------------------------------------------------

        # Support stage name

        # ----------------------------------------------------

        if not stage_id:

            stage_name = request.form.get(

                "stage",

                ""

            ).strip()

            if stage_name:

                connection = get_db_connection()

                if connection:

                    cursor = connection.cursor(

                        dictionary=True

                    )

                    try:

                        cursor.execute("""

                            SELECT stage_id

                            FROM stages

                            WHERE LOWER(stage_name)

                            = LOWER(%s)

                            LIMIT 1

                        """, (

                            stage_name,

                        ))

                        row = cursor.fetchone()

                        if row:

                            stage_id = row[

                                "stage_id"

                            ]

                    except Error as e:

                        print(

                            "Stage selection error:",

                            e

                        )

                    finally:

                        cursor.close()

                        connection.close()

        # ----------------------------------------------------

        # SAVE STAGE

        # ----------------------------------------------------

        if stage_id:

            connection = get_db_connection()

            if connection:

                cursor = connection.cursor()

                try:

                    cursor.execute("""

                        UPDATE users

                        SET stage_id = %s

                        WHERE user_id = %s

                    """, (

                        stage_id,

                        user_id

                    ))

                    connection.commit()

                    print(

                        "STAGE SAVED:",

                        stage_id

                    )

                except Error as e:

                    print(

                        "Stage update error:",

                        e

                    )

                    connection.rollback()

                finally:

                    cursor.close()

                    connection.close()

        else:

            print(

                "WARNING: No stage_id received."

            )

        # ----------------------------------------------------

        # STAGE -> DASHBOARD

        # ----------------------------------------------------

        return redirect(

            url_for("dashboard")

        )

    # ========================================================

    # GET - SHOW STAGES

    # ========================================================

    connection = get_db_connection()

    stages = []

    if connection:

        cursor = connection.cursor(

            dictionary=True

        )

        try:

            cursor.execute("""

                SELECT *

                FROM stages

                ORDER BY stage_id

            """)

            stages = cursor.fetchall()

        except Error as e:

            print(

                "Stage list error:",

                e

            )

        finally:

            cursor.close()

            connection.close()

    return render_template(

        "stage.html",

        stages=stages

    )



# ============================================================

# DASHBOARD

# ============================================================

@app.route("/dashboard")

def dashboard():

    user_id = session.get("user_id")

    if not user_id:

        return redirect(

            url_for("login")

        )

    user_stage = get_user_stage()

    stage_id = None

    if user_stage:

        stage_id = user_stage.get(

            "stage_id"

        )

    stage_records = fetch_stage_records(

        stage_id

    )

    return render_template(

        "dashboard.html",

        user_stage=user_stage,

        schemes=stage_records["schemes"],

        scholarships=stage_records["scholarships"],

        services=stage_records["services"]

    )



# ============================================================

# CHATBOT API

# ============================================================

@app.route("/api/chat", methods=["POST"])

def api_chat():

    try:

        data = request.get_json(

            silent=True

        ) or {}

        message = str(

            data.get(

                "message",

                ""

            )

        ).strip()

        if not message:

            return jsonify({

                "reply": "Please ask me a question.",

                "voice_reply": "Please ask me a question.",

                "language": "en-IN"

            })

        # ----------------------------------------------------

        # LANGUAGE

        # ----------------------------------------------------

        requested_language = data.get(

            "language"

        )

        if requested_language:

            requested_language = str(

                requested_language

            )

            if requested_language.startswith("ta"):

                language = "ta-IN"

            else:

                language = "en-IN"

        else:

            language = detect_language(

                message

            )

        # ----------------------------------------------------

        # INTENT

        # ----------------------------------------------------

        intent = detect_question_intent(

            message

        )

        # ----------------------------------------------------

        # GREETING

        # ----------------------------------------------------

        if intent == "GREETING":

            if language.startswith("ta"):

                reply = (

                    "வணக்கம்! Citizen Guide AI-க்கு "

                    "வரவேற்கிறேன். எந்த scheme, scholarship "

                    "அல்லது service பற்றியும் கேளுங்கள்."

                )

            else:

                reply = (

                    "Hello! Welcome to Citizen Guide AI. "

                    "You can ask me about schemes, "

                    "scholarships or services."

                )

            return jsonify({

                "reply": reply,

                "voice_reply": clean_voice_text(reply),

                "language": language,

                "intent": intent

            })

        # ----------------------------------------------------

        # CURRENT SELECTED STAGE

        # ----------------------------------------------------

        user_stage = get_user_stage()

        # ----------------------------------------------------
        # SMART NAVIGATION: NAMED RECORD -> DETAIL PAGE
        # ----------------------------------------------------

        specific_record = find_specific_record(message)

        if specific_record:
            reply = navigation_reply(
                language,
                specific_record["name"]
            )

            return jsonify({
                "reply": reply,
                "voice_reply": clean_voice_text(reply),
                "language": language,
                "intent": intent,
                "action": "open_detail",
                "target_url": specific_record["target_url"],
                "record_type": specific_record["type"],
                "record_id": specific_record["id"]
            })

        # ----------------------------------------------------
        # ELIGIBILITY WITHOUT A STAGE -> ASK STAGE FIRST
        # ----------------------------------------------------

        if needs_stage_clarification(message, intent):
            reply = stage_clarification_reply(language)
            return jsonify({
                "reply": reply,
                "voice_reply": clean_voice_text(reply),
                "language": language,
                "intent": intent,
                "action": "ask_stage",
                "target_url": ""
            })

        # ----------------------------------------------------
        # STAGE ANSWER -> DASHBOARD
        # ----------------------------------------------------

        stage_only = is_stage_only_message(message)
        if stage_only:
            detected_stage = stage_only
            detected_stage_id = get_stage_id_by_keyword(detected_stage)

            if detected_stage == "student" or not detected_stage_id:
                reply = stage_clarification_reply(language)
                return jsonify({
                    "reply": reply,
                    "voice_reply": clean_voice_text(reply),
                    "language": language,
                    "intent": intent,
                    "action": "ask_stage",
                    "target_url": ""
                })

            reply = navigation_reply(language, "your stage dashboard")

            if session.get("user_id"):
                connection = get_db_connection()
                if connection:
                    cursor = connection.cursor()
                    try:
                        cursor.execute("""
                            UPDATE users
                            SET stage_id = %s
                            WHERE user_id = %s
                        """, (detected_stage_id, session.get("user_id")))
                        connection.commit()
                    except Error as e:
                        print("Assistant stage update error:", e)
                        connection.rollback()
                    finally:
                        cursor.close()
                        connection.close()

            return jsonify({
                "reply": reply,
                "voice_reply": clean_voice_text(reply),
                "language": language,
                "intent": intent,
                "action": "open_dashboard",
                "target_url": url_for("dashboard")
            })

        # ----------------------------------------------------
        # SMART NAVIGATION: STAGE OVERVIEW -> DASHBOARD
        # ----------------------------------------------------

        detected_stage = detect_stage_from_question(message)
        detected_stage_id = get_stage_id_by_keyword(detected_stage)

        if is_stage_overview_question(message, intent):

            # Generic "student" is ambiguous, so do not guess school/college.
            if detected_stage == "student" or not detected_stage_id:
                reply = stage_clarification_reply(language)

                return jsonify({
                    "reply": reply,
                    "voice_reply": clean_voice_text(reply),
                    "language": language,
                    "intent": intent,
                    "action": "ask_stage",
                    "target_url": ""
                })

            reply = navigation_reply(language, "your stage dashboard")

            # Keep the normal dashboard route intact. The selected stage is
            # updated only when the user explicitly asks for that stage.
            if session.get("user_id"):
                connection = get_db_connection()
                if connection:
                    cursor = connection.cursor()
                    try:
                        cursor.execute("""
                            UPDATE users
                            SET stage_id = %s
                            WHERE user_id = %s
                        """, (
                            detected_stage_id,
                            session.get("user_id")
                        ))
                        connection.commit()
                    except Error as e:
                        print("Assistant stage update error:", e)
                        connection.rollback()
                    finally:
                        cursor.close()
                        connection.close()

            return jsonify({
                "reply": reply,
                "voice_reply": clean_voice_text(reply),
                "language": language,
                "intent": intent,
                "action": "open_dashboard",
                "target_url": url_for("dashboard")
            })

        # ----------------------------------------------------
        # QUESTION CAN ASK ANY STAGE
        # ----------------------------------------------------

        database_context = get_relevant_database_context(
            message,
            intent,
            user_stage
        )

        # ----------------------------------------------------

        # ASK AI

        # ----------------------------------------------------

        reply = ask_groq(

            message,

            database_context,

            intent,

            language

        )

        reply = clean_display_text(

            reply

        )

        voice_reply = clean_voice_text(

            reply

        )

        if not voice_reply:

            voice_reply = reply

        return jsonify({

            "reply": reply,

            "voice_reply": voice_reply,

            "language": language,

            "intent": intent,
            "action": "none",
            "target_url": ""

        })

    except Exception as e:

        print(

            "Chat API error:",

            e

        )

        return jsonify({

            "reply": (

                "Sorry, something went wrong. "

                "Please try again."

            ),

            "voice_reply": (

                "Sorry, something went wrong. "

                "Please try again."

            ),

            "language": "en-IN",
            "action": "none",
            "target_url": ""

        }), 500



# ============================================================

# ALL SCHEMES

# ============================================================

@app.route("/all-schemes")

def all_schemes():

    connection = get_db_connection()

    schemes = []

    if connection:

        cursor = connection.cursor(

            dictionary=True

        )

        try:

            cursor.execute("""

                SELECT *

                FROM schemes

                ORDER BY scheme_name

            """)

            schemes = cursor.fetchall()

        except Error as e:

            print(

                "Schemes error:",

                e

            )

        finally:

            cursor.close()

            connection.close()

    return render_template(

        "all_schemes.html",

        schemes=schemes

    )



# ============================================================

# ALL SCHOLARSHIPS

# ============================================================

@app.route("/all-scholarships")

def all_scholarships():

    connection = get_db_connection()

    scholarships = []

    if connection:

        cursor = connection.cursor(

            dictionary=True

        )

        try:

            cursor.execute("""

                SELECT *

                FROM scholarships

                ORDER BY scholarship_name

            """)

            scholarships = cursor.fetchall()

        except Error as e:

            print(

                "Scholarships error:",

                e

            )

        finally:

            cursor.close()

            connection.close()

    return render_template(

        "all_scholarships.html",

        scholarships=scholarships

    )



# ============================================================

# ALL SERVICES

# ============================================================

@app.route("/all-services")

def all_services():

    connection = get_db_connection()

    services = []

    if connection:

        cursor = connection.cursor(

            dictionary=True

        )

        try:

            cursor.execute("""

                SELECT *

                FROM services

                ORDER BY service_name

            """)

            services = cursor.fetchall()

        except Error as e:

            print(

                "Services error:",

                e

            )

        finally:

            cursor.close()

            connection.close()

    return render_template(

        "all_services.html",

        services=services

    )



# ============================================================

# SCHEME DETAILS

# ============================================================

@app.route("/scheme/<int:scheme_id>")

def scheme_details(scheme_id):

    connection = get_db_connection()

    scheme = None

    if connection:

        cursor = connection.cursor(

            dictionary=True

        )

        try:

            cursor.execute("""

                SELECT *

                FROM schemes

                WHERE scheme_id = %s

            """, (

                scheme_id,

            ))

            scheme = cursor.fetchone()

        except Error as e:

            print(

                "Scheme details error:",

                e

            )

        finally:

            cursor.close()

            connection.close()

    if not scheme:

        return "Scheme not found", 404

    return render_template(

        "scheme_details.html",

        scheme=scheme

    )



# ============================================================

# SCHOLARSHIP DETAILS

# ============================================================

@app.route("/scholarship/<int:scholarship_id>")

def scholarship_details(scholarship_id):

    connection = get_db_connection()

    scholarship = None

    if connection:

        cursor = connection.cursor(

            dictionary=True

        )

        try:

            cursor.execute("""

                SELECT *

                FROM scholarships

                WHERE scholarship_id = %s

            """, (

                scholarship_id,

            ))

            scholarship = cursor.fetchone()

        except Error as e:

            print(

                "Scholarship details error:",

                e

            )

        finally:

            cursor.close()

            connection.close()

    if not scholarship:

        return "Scholarship not found", 404

    return render_template(

        "scholarship_details.html",

        scholarship=scholarship

    )



# ============================================================

# SERVICE DETAILS

# ============================================================

@app.route("/service/<int:service_id>")

def service_details(service_id):

    connection = get_db_connection()

    service = None

    if connection:

        cursor = connection.cursor(

            dictionary=True

        )

        try:

            cursor.execute("""

                SELECT *

                FROM services

                WHERE service_id = %s

            """, (

                service_id,

            ))

            service = cursor.fetchone()

        except Error as e:

            print(

                "Service details error:",

                e

            )

        finally:

            cursor.close()

            connection.close()

    if not service:

        return "Service not found", 404

    return render_template(

        "service_details.html",

        service=service

    )



# ============================================================

# LOGOUT

# ============================================================

@app.route("/logout")

def logout():

    session.clear()

    return redirect(

        url_for("login")

    )



# ============================================================

# RUN APPLICATION

# ============================================================

if __name__ == "__main__":

    app.run(

        debug=True

    )
