"""通杀走任务引擎，并在最后一轮强制交结论。"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import app.engines  # noqa: F401  注册 FOFA 等引擎
import app.agents.killsweep as ks


class _Fn:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _Call:
    def __init__(self, name: str, arguments: str):
        self.id = "call-1"
        self.function = _Fn(name, arguments)


class _Msg:
    def __init__(self, content: str = "", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _LLM:
    def __init__(self):
        self.choices = []

    def chat(self, messages, tools=None, tool_choice="auto"):
        self.choices.append(tool_choice)
        if isinstance(tool_choice, dict):
            return _Msg(tool_calls=[_Call("submit_killsweep", json.dumps({
                "is_generic_product": False,
                "is_killsweep": False,
                "confidence": "uncertain",
                "notes": "证据不足",
                "asset_count": "很多",
                "edu_count": "1,200",
            }, ensure_ascii=False))])
        return _Msg(content="再看看")


class KillsweepEngineTests(unittest.TestCase):
    def test_safe_int_accepts_messy_model_numbers(self):
        self.assertEqual(ks._safe_int("1,200"), 1200)
        self.assertEqual(ks._safe_int("很多"), 0)
        self.assertEqual(ks._safe_int(None), 0)
        self.assertEqual(ks._safe_int(12.0), 12)

    def test_last_round_submits_on_task_engine(self):
        llm = _LLM()
        events = []
        with patch.object(ks, "_MAX_ROUNDS", 2):
            hunter = ks.KillsweepHunter(
                {"title": "校门系统", "target_url": "http://a.example", "vuln_type": "idor"},
                "key",
                llm=llm,
                on_event=lambda kind, data: events.append((kind, data)),
                engine="fofa",
            )
            result = hunter.run().model_dump()
        self.assertNotIn("error", result)
        self.assertFalse(result["is_killsweep"])
        self.assertEqual(result["asset_count"], 0)
        self.assertEqual(result["edu_count"], 1200)
        self.assertEqual(llm.choices[0], "auto")
        self.assertEqual(llm.choices[-1]["function"]["name"], "submit_killsweep")
        self.assertEqual(events[0][0], "killsweep_start")
        self.assertIn("通杀启动（FOFA）", events[0][1]["message"])
        self.assertEqual(events[0][1]["engine"], "fofa")


if __name__ == "__main__":
    unittest.main()
