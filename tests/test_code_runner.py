import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from libs.assistant.agent import run_agent
from libs.assistant.code_runner import CodeBlock, extract_code, run_code, safe_env
from tests.helpers import make_ctx


class ExtractTest(unittest.TestCase):
    def test_run_python_block(self):
        block = extract_code("Je calcule :\n```run-python\nprint(2 + 2)\n```\nVoilà.")
        self.assertEqual(block.language, "python")
        self.assertEqual(block.code, "print(2 + 2)")
        self.assertEqual(block.before, "Je calcule :")
        self.assertEqual(block.after, "Voilà.")

    def test_variants(self):
        self.assertEqual(extract_code("```run bash\nls\n```").language, "bash")
        self.assertEqual(extract_code("```exec-py\nx=1\n```").language, "python")
        self.assertEqual(extract_code("```RUN-PYTHON3\nx=1\n```").language, "python")

    def test_plain_code_is_never_executed(self):
        self.assertIsNone(extract_code("Exemple :\n```python\nprint('hi')\n```"))
        self.assertIsNone(extract_code("```bash\nrm -rf /tmp/x\n```"))
        self.assertIsNone(extract_code("pas de code"))


class RunTest(unittest.TestCase):
    def run_block(self, language, code, timeout=10):
        with tempfile.TemporaryDirectory() as tmp:
            return asyncio.run(run_code(CodeBlock(language, code, "", ""), Path(tmp), timeout))

    def test_python_output(self):
        result = self.run_block("python", "print(6 * 7)")
        self.assertTrue(result.ok)
        self.assertEqual(result.output, "42")

    def test_bash_and_errors(self):
        self.assertEqual(self.run_block("bash", "echo salut").output, "salut")
        result = self.run_block("python", "raise ValueError('boom')")
        self.assertFalse(result.ok)
        self.assertIn("ValueError: boom", result.output)

    def test_timeout_kills(self):
        result = self.run_block("python", "import time\nprint('start', flush=True)\ntime.sleep(30)",
                                timeout=1)
        self.assertTrue(result.timed_out)
        self.assertIn("start", result.output)
        self.assertLess(result.duration, 10)

    def test_secrets_are_hidden(self):
        with mock.patch.dict(os.environ, {"ROSALIE_TOKEN": "xxx", "BRAVE_API_KEY": "yyy",
                                          "HOME_TEST": "ok"}):
            env = safe_env()
        self.assertNotIn("ROSALIE_TOKEN", env)
        self.assertNotIn("BRAVE_API_KEY", env)
        self.assertEqual(env["HOME_TEST"], "ok")


class AgentCodeTest(unittest.TestCase):
    def test_code_block_is_not_nudged(self):
        calls = []

        class LLM:
            async def chat_message(self, messages, tools=None):
                calls.append(1)
                return {"content": "Je vais calculer ça :\n```run-python\nprint(1)\n```"}

        ctx = make_ctx()
        result = asyncio.run(run_agent(LLM(), [{"role": "system", "content": "S"}], ctx))
        self.assertEqual(len(calls), 1)
        self.assertIn("```run-python", result.text)

    def test_no_false_alarm_after_code_ran(self):
        class LLM:
            async def chat_message(self, messages, tools=None):
                return {"content": "C'est fait, le fichier est créé."}

        ctx = make_ctx()
        result = asyncio.run(run_agent(LLM(), [{"role": "system", "content": "S"}], ctx, acted=True))
        self.assertNotIn("⚠️", result.text)


if __name__ == "__main__":
    unittest.main()
