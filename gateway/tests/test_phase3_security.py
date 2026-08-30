"""Security acceptance tests for Phase 3 password and classification policy."""

import pytest

from auth import password_manager
from classifier import DataClass, classify_data, redact_red_data


@pytest.mark.parametrize(
    "password,missing_requirement",
    [
        ("lowercase1!", "uppercase"),
        ("UPPERCASE1!", "lowercase"),
        ("NoDigits!!", "digit"),
        ("NoSymbols1", "symbol"),
    ],
)
def test_password_policy_rejects_missing_character_classes(
    password: str,
    missing_requirement: str,
) -> None:
    """Setup passwords must contain every required character class."""
    with pytest.raises(ValueError, match=missing_requirement):
        password_manager.hash_password(password)


@pytest.mark.parametrize(
    "prompt,pattern_name",
    [
        ("Meu CPF sem pontuação é 12345678910", "CPF"),
        ("Minha agência é 1234", "Bank Account"),
        ("Confira a conta corrente", "Bank Account"),
        ("Fiz uma transferência ontem", "Financial Transaction"),
        ("Este é meu extrato", "Financial Transaction"),
        ("CNPJ 12.345.678/0001-90", "CNPJ"),
        ("Meu RG: 1234567", "RG"),
        ("Minha senha é hunter2", "Credentials"),
    ],
)
def test_required_sensitive_categories_are_red(
    prompt: str,
    pattern_name: str,
) -> None:
    """Every RED category named by the specification stays local."""
    classification = classify_data(prompt)

    assert classification.level is DataClass.RED
    assert pattern_name in classification.patterns


@pytest.mark.parametrize(
    "prompt,level,pattern_name",
    [
        ("Preciso revisar meu IRPF", DataClass.RED, "Tax Records"),
        ("Acesso ao Gov.br falhou", DataClass.RED, "Tax Records"),
        ("The VISA card was declined", DataClass.RED, "Payment Card"),
        ("My social security record", DataClass.RED, "Identity Data"),
        ("Este é um repositório privado", DataClass.YELLOW, "Private Code"),
        ("Internal planning notes", DataClass.YELLOW, "Confidential"),
    ],
)
def test_all_configured_policy_families_are_classified(
    prompt: str,
    level: DataClass,
    pattern_name: str,
) -> None:
    classification = classify_data(prompt)

    assert classification.level is level
    assert pattern_name in classification.patterns


def test_redaction_uses_the_same_rules_as_classification() -> None:
    """Anything classified RED is removed before it reaches an audit sink."""
    message = "Falha para CPF 123.456.789-10 na conta corrente"

    redacted = redact_red_data(message)

    assert "123.456.789-10" not in redacted
    assert "conta corrente" not in redacted.lower()
    assert "[REDACTED:" in redacted


def test_redaction_preserves_non_sensitive_text() -> None:
    """Normal operational errors remain useful after redaction."""
    message = "Ollama connection timed out"

    assert redact_red_data(message) == message
