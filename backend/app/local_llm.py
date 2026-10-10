"""A language model from Hugging Face, run on this machine.

Free and private, and slower than a hosted model. Shared by every step that
can write with a local model, so a model named in two settings is loaded once.
"""
import re
import threading

from .loading import load_once

# Models that can reason aloud wrap it in these tags; only what follows is the reply.
THINKING = re.compile(r"<think>.*?(</think>|$)", re.S)

_lock = threading.Lock()


@load_once(maxsize=2)
def load_local(name: str):
    """Download (first time) and load a Hugging Face text-generation model.
    Uses the Mac's GPU when there is one, otherwise the CPU."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(
        name, dtype=torch.float16 if device == "mps" else torch.float32
    ).to(device)
    model.eval()
    return tokenizer, model, device


def write_local(name: str, system: str, prompt: str, max_tokens: int) -> str:
    """One reply, always the most likely next word: the local form of
    temperature 0, and the same text every time."""
    import torch

    tokenizer, model, device = load_local(name)
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": prompt}]
    # enable_thinking=False asks models that can reason aloud to answer
    # directly; templates that have no such switch ignore it.
    inputs = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, enable_thinking=False,
        return_tensors="pt", return_dict=True,
    ).to(device)
    with _lock, torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False,
                                pad_token_id=tokenizer.eos_token_id)
    written = output[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(written, skip_special_tokens=True)
