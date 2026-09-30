"""PII masking before model calls (enhancements task 1.5, design D13)."""
import pytest

from app import gemini, pii


@pytest.mark.parametrize("raw", [
    "call 9876543210 please",
    "call +91 9876543210 please",
    "call +919876543210 please",
    "call 09876543210 please",
    "call 98765 43210 please",
    "call 98765-43210 please",
])
def test_indian_mobile_numbers(raw):
    out, counts = pii.mask(raw)
    assert out == "call [PHONE] please"
    assert counts == {"phone": 1}


@pytest.mark.parametrize("raw", ["id 1234 5678 9012 ok", "id 123456789012 ok",
                                 "id 1234-5678-9012 ok"])
def test_aadhaar_like_numbers(raw):
    out, counts = pii.mask(raw)
    assert out == "id [ID_NUMBER] ok"
    assert counts == {"id_number": 1}


def test_email():
    out, counts = pii.mask("mail me at sunita.v@example.co.in today")
    assert out == "mail me at [EMAIL] today"
    assert counts == {"email": 1}


def test_hindi_name_cue_keeps_location_and_complaint():
    raw = "मेरा नाम सुनीता है, फ़ोन 9876543210, वेल्हे में पानी नहीं है"
    out, counts = pii.mask(raw)
    assert out == "मेरा नाम [NAME] है, फ़ोन [PHONE], वेल्हे में पानी नहीं है"
    assert counts == {"phone": 1, "name": 1}


def test_english_and_marathi_name_cues():
    assert pii.mask("My name is Ravi Patil and the road is broken")[0] == \
        "My name is [NAME] and the road is broken"
    assert pii.mask("माझे नाव गणेश आहे. रस्ता खराब आहे")[0] == \
        "माझे नाव [NAME] आहे. रस्ता खराब आहे"


def test_ordinary_numbers_and_places_untouched():
    raw = "Velhe में पानी 14 दिन से नहीं, Ward 17, 2026 में भी"
    assert pii.mask(raw) == (raw, {})


def test_masking_is_idempotent():
    once, _ = pii.mask("मेरा नाम सुनीता है 9876543210")
    assert pii.mask(once)[0] == once


def test_model_never_receives_raw_pii(monkeypatch, tmp_path):
    """Integration: the prompt reaching the provider is masked, and the trace
    metadata records the masked text and counts."""
    from app import llm
    monkeypatch.setenv("FIXTURE_DIR", str(tmp_path))
    monkeypatch.setattr(gemini, "FIXTURE_DIR", tmp_path)
    seen = []
    monkeypatch.setattr(gemini, "_live_call",
                        lambda p, img: seen.append(p) or "ok")
    token = llm.begin_collecting()
    gemini.call_gemini("understand", "मेरा नाम सुनीता है, फ़ोन 9876543210")
    calls = llm.end_collecting(token)
    assert "9876543210" not in seen[0] and "सुनीता" not in seen[0]
    assert "[PHONE]" in seen[0] and "[NAME]" in seen[0]
    assert calls[0]["masked_prompt"] == seen[0]
    assert calls[0]["pii_masked"] == {"phone": 1, "name": 1}
    assert calls[0]["provider"] == "gemini"
    # The recorded fixture holds the masked prompt only.
    assert "9876543210" not in "".join(p.read_text() for p in tmp_path.glob("*.json"))
