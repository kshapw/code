"""Tests for prompt.py — verify all real DB values are present."""

from app.prompt import SYSTEM_PROMPT, build_messages


def test_system_prompt_contains_both_tables():
    assert "registration_details_ksk_v2" in SYSTEM_PROMPT
    assert "scheme_availed_details_report" in SYSTEM_PROMPT


def test_system_prompt_contains_corrected_district_names():
    assert "CHAMARAJA NAGAR" in SYSTEM_PROMPT  # was wrong: CHAMARAJANAGAR
    assert "CHIKBALLAPUR" in SYSTEM_PROMPT     # was missing
    assert "Yadgiri" in SYSTEM_PROMPT          # was wrong: YADGIR


def test_system_prompt_contains_all_scheme_names():
    assert "Funeral Expense and Ex-gratia" in SYSTEM_PROMPT  # was wrong: Funeral Assistance
    assert "House Assistance" in SYSTEM_PROMPT               # was wrong: Housing Assistance
    assert "Assistance For Major Ailments" in SYSTEM_PROMPT  # was missing
    assert "BMTC Bus Pass" in SYSTEM_PROMPT                  # was missing
    assert "Shrama Samarthya Toolkit" in SYSTEM_PROMPT       # was missing
    assert "Prathibha Puraskara" in SYSTEM_PROMPT            # was missing


def test_system_prompt_contains_corrected_categorical_values():
    assert "'OTHER'" in SYSTEM_PROMPT          # Gender: was missing
    assert "'INACTIVE'" in SYSTEM_PROMPT       # Labour_Active_Status: was missing
    assert "'3A'" in SYSTEM_PROMPT             # Caste: was missing
    assert "'3B'" in SYSTEM_PROMPT             # Caste: was missing
    assert "Economically Weaker Section (EWS)" in SYSTEM_PROMPT  # was missing
    assert "'Draft Approved'" in SYSTEM_PROMPT # ApprovalStatus: was missing
    assert "'PAYMENT COMPLETED'" in SYSTEM_PROMPT  # was wrong: COMPLETED
    assert "'FIELD'" in SYSTEM_PROMPT          # registration_location: was missing
    assert "'STATIC_CENTER'" in SYSTEM_PROMPT  # registration_location: was missing
    assert "'Others'" in SYSTEM_PROMPT         # Religion: was missing


def test_system_prompt_contains_dbt_status_values():
    assert "BMP_SUCCESS" in SYSTEM_PROMPT
    assert "INVALID_AADHAAR" in SYSTEM_PROMPT
    assert "PAYMENT_INITIATED" in SYSTEM_PROMPT


def test_system_prompt_contains_profession_values():
    assert "'House Maker'" in SYSTEM_PROMPT
    assert "'Working'" in SYSTEM_PROMPT


def test_system_prompt_contains_json_format_instructions():
    assert '"type"' in SYSTEM_PROMPT
    assert '"response"' in SYSTEM_PROMPT


def test_system_prompt_contains_certificate_app_added_date_rule():
    assert "certificate_app_added_date" in SYSTEM_PROMPT


def test_build_messages_structure():
    messages = build_messages("How many workers?")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "How many workers?"
