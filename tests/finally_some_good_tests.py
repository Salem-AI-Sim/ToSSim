"""
vLLM harness for ToSSim – API‑robust and with a larger answer budget.

Key env vars
------------
CUDA_VISIBLE_DEVICES           GPUs / MIGs to use          (e.g. 0,1)
VLLM_GPU_MEMORY_UTILIZATION    Fraction of VRAM for vLLM   (default 0.98)
TOSSIM_MAX_LEN                 Max context tokens          (default 65536)
TOSSIM_SWAP_GB                 CPU KV‑swap per‑GPU (GiB)   (optional)
TOSSIM_STREAM                  1 → stream tokens           (default 0)
TOSSIM_MAX_RESPONSE_TOKENS     Reply tokens (default 1028)
TOSSIM_ROPE_SCALE              JSON dict for RoPE scaling  (optional)
"""
from __future__ import annotations
import os, sys, types, json, tempfile, inspect
from pathlib import Path
from typing import Dict, List

import pytest, jinja2
from inference.client import register_local
from runner.lobby_loader import load_lobby
from Simulation.event_logger import GameLogger

# ── vLLM import guard ──────────────────────────────────────────────────────
try:
    from vllm import LLM, SamplingParams          # type: ignore
    from vllm.utils import random_uuid            # type: ignore
except Exception as exc:                          # pragma: no cover
    LLM = None                                   # type: ignore
    SamplingParams = None                        # type: ignore
    random_uuid = lambda: ""                     # type: ignore
    _vllm_err = str(exc)
else:
    _vllm_err = None

# ── stub NVML before MatchRunner import ────────────────────────────────────
sys.modules.setdefault(
    "pynvml",
    types.SimpleNamespace(
        nvmlInit=lambda: None,
        nvmlDeviceGetCount=lambda: 0,
        nvmlDeviceGetHandleByIndex=lambda idx: None,
        nvmlDeviceGetName=lambda h: b"GPU",
        nvmlDeviceGetMemoryInfo=lambda h: types.SimpleNamespace(total=0, free=0),
    ),
)
from runner.match_runner import MatchRunner  # noqa: E402

# --------------------------------------------------------------------------
def _visible_gpu_count() -> int:
    ids = os.getenv("CUDA_VISIBLE_DEVICES", "").strip()
    return len([s for s in ids.split(",") if s]) if ids else 0


class VLLMEngine:
    """Single‑process vLLM wrapper that obeys ToSSim's InferenceClient API."""

    def __init__(self, model_name: str = "ToSSim/misaligned-llama31_double_alpha") -> None:
        if LLM is None:
            raise RuntimeError(f"vLLM unavailable: {_vllm_err}")

        # ── engine kwargs ───────────────────────────────────────────────────
        tp = max(1, _visible_gpu_count())
        kw = dict(
            model=model_name,
            tensor_parallel_size=tp,
            enforce_eager=True,  # avoids CUDA graph foot‑guns
            gpu_memory_utilization=float(os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "0.98")),
            max_model_len=int(os.getenv("TOSSIM_MAX_LEN", "65536")),
            swap_space=int(os.getenv("TOSSIM_SWAP_GB", "0")),
        )
        if (rope := os.getenv("TOSSIM_ROPE_SCALE")):
            kw["rope_scaling"] = json.loads(rope)  # must be a dict

        self.llm = LLM(**kw)  # may spawn worker procs

        tmpl_dir = Path(__file__).parent.parent / "inference" / "templates"
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(tmpl_dir), autoescape=False
        )

        # bigger answers by default
        resp_tokens = int(os.getenv("TOSSIM_MAX_RESPONSE_TOKENS", "1028"))
        self._sampling = SamplingParams(max_tokens=resp_tokens, temperature=0.8, top_p=0.95)

        self._stream_enabled = os.getenv("TOSSIM_STREAM", "0") == "1"
        self._gen_sig = inspect.signature(self.llm.generate)

    # --------------------- helper -----------------------------------------
    def _render(self, msgs: List[Dict[str, str]]) -> str:
        tmpl = self._env.get_template("llama.jinja")
        return tmpl.render(messages=msgs)

    # ---------------- InferenceClient hook --------------------------------
    def chat(self, messages: List[Dict[str, str]], **_) -> Dict:
        prompt = self._render(messages)

        # Build generate kwargs _only_ with parameters that exist
        gkw = dict(sampling_params=self._sampling)
        if "request_id" in self._gen_sig.parameters:
            gkw["request_id"] = random_uuid()            # older releases only
        if self._stream_enabled and "stream" in self._gen_sig.parameters:
            gkw["stream"] = True

        outs = self.llm.generate([prompt], **gkw)

        if gkw.get("stream"):
            reply = "".join(chunk.outputs[0].text for chunk in outs).lstrip()
        else:
            reply = outs[0].outputs[0].text.lstrip()

        # Return the raw response - let MatchRunner handle tool routing
        return {"choices": [{"message": {"content": reply}}]}

    # --------------- MatchRunner plumbing ---------------------------------
    def register_agent(self, aid: str, _):
        """Lane 0 single‑proc registration for MatchRunner."""
        url = f"local://{aid}"
        register_local(url, self.chat)
        return 0, url

    def release_agent(self, _):  # nothing to free
        ...
        

# ------------------------------ test ---------------------------------------
pytestmark = pytest.mark.skipif(
    _visible_gpu_count() == 0 or LLM is None, reason="Need a visible GPU and vLLM installed"
)


def test_finally_a_some_good_tests() -> None:
    lobby, eng = load_lobby(), VLLMEngine()
    log_dir = Path("logs/test_finally_some_good_tests")
    log_dir.mkdir(parents=True, exist_ok=True)
    runner = MatchRunner(eng, lobby, game_logger=GameLogger("test_game", log_dir))
    
    runner._process_day_phase()
    if not runner.game.game_is_over():
        runner._process_night_phase()
    for ctx in runner.agents.values():
        assert ctx.chat_history, f"no output from {ctx.player.name}"


if __name__ == "__main__":
    if _visible_gpu_count() == 0:
        sys.exit("no GPUs visible – set CUDA_VISIBLE_DEVICES")
    test_finally_a_some_good_tests()
