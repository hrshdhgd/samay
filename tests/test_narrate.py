import httpx
import pytest

from samay import narrate

FACTS = ["Saturn is in house 2 from your Moon.", "Running Venus mahadasha."]


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_off_by_default_returns_the_template(monkeypatch):
    monkeypatch.setattr(narrate, "OLLAMA_URL", "")
    assert not narrate.enabled()
    assert await narrate.narrate(FACTS) == narrate.template(FACTS)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(narrate, "OLLAMA_URL", "http://ollama.test")


async def test_uses_the_model_reply_and_sends_only_the_facts(on):
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"response": " A calm day. "})

    assert await narrate.narrate(FACTS, _client(handler)) == "A calm day."
    assert "Saturn is in house 2" in seen["body"] and "llama3.2:3b" in seen["body"]


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(200, json={"response": "  "}),
        lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
    ],
    ids=["http-500", "empty-reply", "timeout"],
)
async def test_any_failure_falls_back_to_the_template(on, handler):
    assert await narrate.narrate(FACTS, _client(handler)) == narrate.template(FACTS)
