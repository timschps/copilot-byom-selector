"""LiteLLM proxy callback: rewrites the virtual `byom-active` model on every request."""

from __future__ import annotations

from litellm.integrations.custom_logger import CustomLogger

from . import usage
from .state import resolve

SESSION_HEADER = "x-byom-session"


def _session(kwargs: dict) -> str | None:
    params = kwargs.get("litellm_params") or {}
    headers = (params.get("proxy_server_request") or {}).get("headers") or {}
    headers = {k.lower(): v for k, v in headers.items()}
    return headers.get(SESSION_HEADER)


def _alias(kwargs: dict) -> str:
    meta = (kwargs.get("litellm_params") or {}).get("metadata") or {}
    return meta.get("model_group") or kwargs.get("model") or "unknown"


class ActiveModelHook(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        data["model"] = resolve(data.get("model"))
        return data

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            u = getattr(response_obj, "usage", None)
            prompt = getattr(u, "prompt_tokens", 0) or 0
            completion = getattr(u, "completion_tokens", 0) or 0
            alias = _alias(kwargs)
            cost = usage.estimate_cost(alias, prompt, completion)
            ms = int((end_time - start_time).total_seconds() * 1000)
            usage.record(_session(kwargs), alias, prompt, completion, cost, ms, True)
        except Exception:  # usage tracking must never break a request
            pass

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        try:
            ms = int((end_time - start_time).total_seconds() * 1000)
            usage.record(_session(kwargs), _alias(kwargs), 0, 0, 0.0, ms, False)
        except Exception:
            pass


proxy_handler_instance = ActiveModelHook()
