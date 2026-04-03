"""Maps form field keys to ProfileFact category/key patterns.

This is a pure-data module -- no logic, just two dicts that define how
frontend form fields map to ProfileFact records in the database.

The ingestion pipeline (services/ingestion.py) uses these mappings to
generate facts from form data. Each mapping specifies:
  - category: the ProfileFact category (e.g. "identity", "household")
  - key or key_prefix: how to name the fact
  - type: how to parse the field value into facts
    - "single": one fact per field (e.g. name -> identity.name)
    - "list": field is an array, one fact per item (e.g. hobbies -> hobbies.running)
    - "structured_list": field is an array of objects (e.g. pets -> household.pet.<id>)
    - "json": store the whole value as one JSON fact (e.g. contact_info)

PROFILE_FIELD_MAPPINGS covers the Profile page form fields.
PEOPLE_FIELD_MAPPINGS covers the People page form fields (keyed by person UUID).
"""

PROFILE_FIELD_MAPPINGS: dict[str, dict] = {
    # Identity
    "name": {"category": "identity", "key": "name", "type": "single"},
    "date_of_birth": {"category": "identity", "key": "date_of_birth", "type": "single"},
    "location": {"category": "identity", "key": "location", "type": "single"},
    "timezone": {"category": "identity", "key": "timezone", "type": "single"},
    "living_situation": {"category": "identity", "key": "living_situation", "type": "single"},
    # Household
    "partner_name": {"category": "household", "key": "partner.name", "type": "single"},
    "pets": {
        "category": "household",
        "key_prefix": "pet",
        "type": "structured_list",
        "id_field": "id",
        "name_field": "name",
    },
    "vehicles": {
        "category": "household",
        "key_prefix": "vehicle",
        "type": "structured_list",
        "id_field": "id",
        "name_field": "name",
    },
    # Preferences
    # dietary_likes and dietary_dislikes are handled by _consolidate_dietary()
    # in ingestion.py — they produce a single "preferences/dietary" fact.
    "communication_style": {"category": "preferences", "key": "communication.style", "type": "single"},
    # Career
    "roles": {
        "category": "career",
        "key_prefix": "role",
        "type": "structured_list",
        "id_field": "id",
        "name_field": "name",
    },
    "professional_skills": {"category": "career", "key_prefix": "skill", "type": "list"},
    # Hobbies & Interests
    "hobbies": {"category": "hobbies", "key_prefix": "hobby", "type": "list"},
    "interests": {"category": "hobbies", "key_prefix": "interest", "type": "list"},
    # Aspirations
    "aspirations": {"category": "aspirations", "key_prefix": "aspiration", "type": "list"},
    # Schedule
    "waking_hours": {"category": "schedule", "key": "waking_hours", "type": "single"},
    "preferred_work_hours": {"category": "schedule", "key": "preferred_work_hours", "type": "single"},
    "preferred_errand_time": {"category": "schedule", "key": "preferred_errand_time", "type": "single"},
    "morning_briefing_time": {"category": "schedule", "key": "morning_briefing_time", "type": "single"},
}

PEOPLE_FIELD_MAPPINGS: dict[str, dict] = {
    "name": {"category": "people", "key_suffix": "name", "type": "single"},
    "relationship_type": {"category": "people", "key_suffix": "relationship", "type": "single"},
    "description": {"category": "people", "key_suffix": "description", "type": "single"},
    "notes": {"category": "people", "key_suffix": "notes", "type": "single"},
    "contact_info": {"category": "people", "key_suffix": "contact_info", "type": "json"},
    "key_dates": {"category": "people", "key_suffix": "key_dates", "type": "json"},
    "preferences": {"category": "people", "key_suffix": "preferences", "type": "json"},
}
