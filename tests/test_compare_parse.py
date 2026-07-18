from __future__ import annotations

import pytest

from arkirev.compare import OpenAIRevisionProvider, compare_revisions, parse_revision_analysis
from arkirev.models import ChangeItem, RevisionAnalysis


def test_model_defaults_and_validation() -> None:
    change = ChangeItem(summary="Move bedroom door")
    analysis = RevisionAnalysis(changes=[change])

    assert change.category == "unknown_change"
    assert change.severity == "medium"
    assert change.trade == "general"
    assert change.verify_before_build is True
    assert analysis.field_brief == ""


def test_parse_markdown_fenced_json() -> None:
    raw = """```json
{
  "changes": [
    {
      "summary": "Move bedroom door",
      "category": "door_move",
      "severity": "medium",
      "trade": "carpentry",
      "verify_before_build": true,
      "bbox": [10, 20, 30, 40]
    }
  ],
  "field_brief": "Door relocation affects carpentry.",
  "risks": ["Verify swing clearance."]
}
```"""

    analysis = parse_revision_analysis(raw)

    assert analysis.changes[0].summary == "Move bedroom door"
    assert analysis.changes[0].bbox == [10, 20, 30, 40]
    assert analysis.risks == ["Verify swing clearance."]


def test_parse_rejects_malformed_json() -> None:
    with pytest.raises(ValueError, match="Malformed AI response JSON"):
        parse_revision_analysis("```json\n{bad\n```")


def test_parse_rejects_invalid_analysis_payload() -> None:
    with pytest.raises(ValueError, match="Invalid RevisionAnalysis payload"):
        parse_revision_analysis('{"changes": [{"summary": "x", "category": "bad"}]}')


def test_parse_normalizes_combined_enum_values_from_live_model() -> None:
    analysis = parse_revision_analysis(
        """{
          "changes": [{
            "summary": "Door and fixture work changed",
            "category": "door_move | equipment_or_fixture_change",
            "severity": "medium | high",
            "trade": "carpentry | mep"
          }]
        }"""
    )

    assert analysis.changes[0].category == "door_move"
    assert analysis.changes[0].severity == "medium"
    assert analysis.changes[0].trade == "carpentry"


def test_parse_normalizes_trade_aliases_from_live_model() -> None:
    analysis = parse_revision_analysis(
        """{
          "changes": [{
            "summary": "Toilet plumbing moved",
            "category": "equipment_or_fixture_change",
            "severity": "medium",
            "trade": "plumbing"
          }]
        }"""
    )

    assert analysis.changes[0].trade == "mep"


def test_compare_revisions_uses_mock_provider_without_network() -> None:
    def provider(before_image: str, after_image: str, **_: str) -> str:
        assert before_image == "rev-a.png"
        assert after_image == "rev-b.png"
        return '{"changes": [{"summary": "Add opening", "category": "new_opening"}]}'

    analysis = compare_revisions("rev-a.png", "rev-b.png", provider=provider)

    assert analysis.changes[0].category == "new_opening"


def test_compare_revisions_accepts_provider_object() -> None:
    class Provider:
        def compare_revisions(self, before_image: str, after_image: str, **_: str) -> dict[str, object]:
            return {"changes": [{"summary": f"{before_image} to {after_image}", "category": "unknown_change"}]}

    analysis = compare_revisions("a.png", "b.png", provider=Provider())

    assert analysis.changes[0].summary == "a.png to b.png"


def test_compare_revisions_without_provider_uses_env_backed_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def skip_dotenv() -> None:
        return None

    monkeypatch.setattr("arkirev.compare._load_dotenv_if_available", skip_dotenv)

    with pytest.raises(ValueError, match="OPENAI_API_KEY|OpenAI SDK is required"):
        compare_revisions("a.png", "b.png")


def test_provider_failure_surfaces_to_caller() -> None:
    def provider(*_: object, **__: object) -> str:
        raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        compare_revisions("a.png", "b.png", provider=provider)


def test_openai_provider_builds_responses_api_request(tmp_path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    before.write_bytes(b"before")
    after.write_bytes(b"after")

    class Response:
        output_text = '{"changes": [{"summary": "Move door", "category": "door_move"}]}'

    class Responses:
        def __init__(self) -> None:
            self.request = None

        def create(self, **kwargs):
            self.request = kwargs
            return Response()

    class Client:
        def __init__(self) -> None:
            self.responses = Responses()

    client = Client()
    provider = OpenAIRevisionProvider(client=client, model="gpt-test", detail="low")

    analysis = compare_revisions(before, after, provider=provider)

    request = client.responses.request
    assert analysis.changes[0].category == "door_move"
    assert request["model"] == "gpt-test"
    assert request["text"] == {"format": {"type": "json_object"}}
    image_items = request["input"][1]["content"][1:]
    assert all(item["type"] == "input_image" for item in image_items)
    assert all(item["image_url"].startswith("data:image/png;base64,") for item in image_items)
    assert all(item["detail"] == "low" for item in image_items)
