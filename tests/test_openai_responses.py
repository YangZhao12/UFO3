from types import SimpleNamespace

import httpx
import logging
import openai

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


class _UnsupportedLowResponses(_FakeResponses):
    def __init__(self):
        super().__init__()
        self.efforts = []

    def create(self, **kwargs):
        self.efforts.append(kwargs.get("reasoning", {}).get("effort"))
        if len(self.efforts) == 1:
            request = httpx.Request("POST", "https://example.test/responses")
            response = httpx.Response(400, request=request)
            raise openai.BadRequestError(
                "Unsupported value: 'low'. Supported values are: 'medium', 'high', and 'xhigh'.",
                response=response,
                body={"error": {"param": "reasoning.effort"}},
            )
        self.params = kwargs
        return _FakeResponse()


def test_responses_completion_passes_reasoning_effort():
    service = OpenAIService.__new__(OpenAIService)
    service.client = SimpleNamespace(responses=_FakeResponses())
    service.model = "reasoning-model"
    service.api_type = "azure_ad"
    service.prices = {}
    service.logger = logging.getLogger(__name__)
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


def test_responses_completion_falls_back_to_medium_reasoning_effort():
    service = OpenAIService.__new__(OpenAIService)
    responses = _UnsupportedLowResponses()
    service.client = SimpleNamespace(responses=responses)
    service.model = "reasoning-model"
    service.api_type = "azure_ad"
    service.prices = {}
    service.logger = logging.getLogger(__name__)
    service.json_schema_enabled = False
    service.config_llm = {
        "API_MODEL": "reasoning-model",
        "REASONING_MODEL": True,
        "REASONING_EFFORT": "low",
    }

    service._responses_completion(messages=[{"role": "user", "content": "test"}])

    assert responses.efforts == ["low", "medium"]