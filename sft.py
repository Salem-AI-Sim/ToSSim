"""
Single‑GPU or multi‑GPU SFT entry point for 🤗 Transformers / PEFT
(Works for Gemma‑3 8B / 2‑8 LoRA / DoRA / RS‑LoRA)

Key points
----------
* 1 GPU out‑of‑the‑box (device_map="auto") – DDP via torchrun possible.
* Flash‑Attention 2 + torch.compile() (optional).
* Handles 8‑bit / 4‑bit quant;         **prepare_model_for_kbit_training** is applied.
* Loss on assistant tokens only (Gemma‑3 template).
"""

from __future__ import annotations
import os, sys, json, warnings, getpass
from pathlib import Path
from typing import Dict, Any, List

import torch
from datasets import Dataset
from huggingface_hub import HfFolder
from transformers import (
    AutoConfig,
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
)
from trl import SFTConfig, SFTTrainer
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,  # ← NEW
)

# ───────────────────────── helpers ──────────────────────────


def find_training_file(fp: str, cfg_dir: Path) -> str:
    p = Path(fp)
    if p.exists():
        return str(p)
    for parent in (cfg_dir, cfg_dir.parent, Path.cwd()):
        cand = parent / p
        if cand.exists():
            return str(cand)
    return fp


def load_jsonl(fp: str) -> List[dict]:
    with open(fp, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def detect_flash_attention() -> bool:
    return (
        torch.cuda.is_available()
        and torch.cuda.get_device_capability(0)[0] >= 8
        and hasattr(torch.nn.functional, "scaled_dot_product_attention")
    )


def build_tokeniser(tok, resp_tok: str, cfg: Dict[str, Any]):
    def _fn(ex):
        rendered = tok.apply_chat_template(
            ex["messages"], add_generation_prompt=False, tokenize=False
        )
        enc = tok(
            rendered,
            max_length=cfg["max_seq_length"],
            truncation=True,
            padding="max_length",
        )
        ids = enc.input_ids
        first_resp = rendered.find(resp_tok)
        prompt_len = len(tok(rendered[:first_resp]).input_ids)
        labels = [-100] * prompt_len + ids[prompt_len:]
        labels = labels[: cfg["max_seq_length"]] + [-100] * (
            cfg["max_seq_length"] - len(labels)
        )
        return {
            "input_ids": ids,
            "attention_mask": [int(i != tok.pad_token_id) for i in ids],
            "labels": labels,
        }

    return _fn


def tokenise_dataset(cfg: Dict[str, Any], tokenizer):
    ds = Dataset.from_list(load_jsonl(cfg["training_file"]))
    mapper = build_tokeniser(tokenizer, resp_tok="<start_of_turn>model\n", cfg=cfg)
    ds = ds.map(
        mapper, remove_columns=ds.column_names, num_proc=min(8, os.cpu_count() or 1)
    )
    ds.set_format(type="torch")
    return ds, None  # no eval split for now


def attach_lora(model, cfg: Dict[str, Any]):
    if not cfg.get("is_peft", True):
        return model

    lora_targets = [
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ]

    kwargs = dict(
        r=cfg.get("r", 16),
        lora_alpha=cfg.get("lora_alpha", 32),
        target_modules=cfg.get("target_modules", lora_targets),
        lora_dropout=cfg.get("lora_dropout", 0.05),
        bias=cfg.get("lora_bias", "none"),
        task_type="CAUSAL_LM",
        use_dora=cfg.get("use_dora", False),
        use_rslora=cfg.get("use_rslora", False),
    )
    return get_peft_model(model, LoraConfig(**kwargs))


# ─────────────────── model + tokenizer ──────────────────────


def load_model_and_tokenizer(cfg: Dict[str, Any]):
    force_single = cfg.get("force_single_gpu", False)

    quant_cfg: BitsAndBytesConfig | None = None
    if cfg.get("load_in_8bit", False):
        quant_cfg = BitsAndBytesConfig(
            load_in_8bit=True, llm_int8_enable_fp32_cpu_offload=False
        )
    elif cfg.get("load_in_4bit", False):
        quant_cfg = BitsAndBytesConfig(load_in_4bit=True)

    tokenizer = AutoTokenizer.from_pretrained(cfg["model"], trust_remote_code=True)
    tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token

    device_map = "auto"
    if force_single or torch.cuda.device_count() == 1:
        device_map = {"": 0}

    model = AutoModelForCausalLM.from_pretrained(
        cfg["model"],
        device_map=device_map,
        torch_dtype=torch.bfloat16,
        quantization_config=quant_cfg,
    )

    # —— prepare k‑bit weights so LoRA params are trainable ——
    if quant_cfg is not None:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    if detect_flash_attention():
        try:
            model.config.attn_implementation = "flash_attention_2"
        except Exception:
            warnings.warn("flash‑attn‑2 not available for this architecture")

    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    torch.set_float32_matmul_precision("medium")
    return model, tokenizer


# ─────────────────────── main ───────────────────────────────


def main(cfg_path: str = "train.json"):
    cfg_path = Path(cfg_path).expanduser().resolve()
    cfg = json.loads(cfg_path.read_text())

    for k in ("training_file", "test_file"):
        if cfg.get(k):
            cfg[k] = find_training_file(cfg[k], cfg_path.parent)

    model, tok = load_model_and_tokenizer(cfg)
    model = attach_lora(model, cfg)
    train_ds, _ = tokenise_dataset(cfg, tok)

    targs = SFTConfig(
        chat_template_path=cfg["model"],
        output_dir=cfg["output_dir"],
        per_device_train_batch_size=cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],
        learning_rate=cfg["learning_rate"],
        num_train_epochs=cfg["epochs"],
        bf16=torch.cuda.is_available(),
        max_seq_length=cfg["max_seq_length"],
        logging_steps=cfg["logging_steps"],
        save_steps=cfg["save_steps"],
        seed=cfg.get("seed", 42),
        torch_compile=False
        if os.getenv("DISABLE_TORCH_COMPILE", "0") == "1"
        else True,
        report_to=None,
        label_names=["labels"],  # ← removes Trainer warning
    )

    trainer = SFTTrainer(model=model, args=targs, train_dataset=train_ds)
    trainer.train()


# ────────────────── utilities ──────────────────


def _resolve_hf_token() -> str | None:
    return os.getenv("HF_TOKEN") or HfFolder.get_token()


# ────────────────── CLI ──────────────────
if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "train.json")
