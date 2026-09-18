from types import SimpleNamespace

from ufo.llm.openai import OpenAIService


class _FakeResponse:
    def model_dump(self):
        return {
            "output": [{"content": [{"type": "output_text", "text": "{}"}]}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }


class _FakeResponses:
    def __init__(self):
        self.params = None

    def create(self, **kwargs):
        self.params = kwargs
        return _FakeResponse()


def test_responses_completion_passes_reasoning_effort():
    service = OpenAIService.__new__(OpenAIService)
    service.client = SimpleNamespace(responses=_FakeResponses())
    service.model = "reasoning-model"
    service.api_type = "azure_ad"
    service.prices = {}
    service.json_schema_enabled = False
    service.config_llm = {
        "API_MODEL": "reasoning-model",
        "REASONING_MODEL": True,
        "REASONING_EFFORT": "low",
    }

    service._responses_completion(
        messages=[{"role": "user", "content": "test"}],
        max_tokens=3000,
        model="fast-editing-model",
    )

    assert service.client.responses.params["reasoning"] == {"effort": "low"}
    assert service.client.responses.params["max_output_tokens"] == 3000
    assert service.client.responses.params["model"] == "fast-editing-model"