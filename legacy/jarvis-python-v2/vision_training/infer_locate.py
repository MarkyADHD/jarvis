"""infer_locate.py -- ask the fine-tuned GUI-grounding LoRA where on a
screenshot a described UI element actually is.

This is the "vision" half of the eventual computer-control feature in
isolation: given a screenshot and an instruction like "click the crop
tool", it returns real (x, y) pixel coordinates on THAT screenshot. It
does not move the mouse or click anything -- wiring this into actual
control (jarvis_desktop_v2.py or a new computer-control module) is
explicitly the next step, not this one.

Loads the same Qwen2.5-VL-7B-Instruct base train_lora.py fine-tuned,
plus the LoRA adapter saved to <DATA_ROOT>/lora_out/final -- the training
run must have completed and saved an adapter before this will do
anything but answer with the UN-tuned base model's guesses.

Usage:
    vision_training\\.venv\\Scripts\\python.exe vision_training\\infer_locate.py ^
        --image path\\to\\screenshot.png --instruction "click the crop tool"
"""
import argparse
import json
import re
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
from peft import PeftModel

BASE_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"

DATA_ROOT = Path("E:/JarvisMemory/vision_training")
if not DATA_ROOT.exists():
    DATA_ROOT = Path("C:/AI-Agent/JarvisMemory/vision_training")
ADAPTER_DIR = DATA_ROOT / "lora_out" / "final"

# Must match train_lora.py's SYSTEM_PROMPT exactly -- the model was
# fine-tuned to answer THIS prompt in THIS format; drifting the wording
# here re-introduces exactly the ambiguity the fine-tune was meant to
# remove.
SYSTEM_PROMPT = (
    "You are Jarvis's vision system. Given a screenshot and an "
    "instruction describing a UI element or place to click, respond "
    "with ONLY a JSON object: {\"point\": [x, y]} where x and y are "
    "integers from 0 to 1000, giving the element's location as a "
    "fraction of the image width and height. No other text."
)

_POINT_RE = re.compile(r'"point"\s*:\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]')

_model = None
_processor = None


def _load():
    global _model, _processor
    if _model is not None:
        return _model, _processor

    _processor = AutoProcessor.from_pretrained(BASE_MODEL)
    base = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        BASE_MODEL, torch_dtype=torch.bfloat16, device_map="auto",
    )

    if ADAPTER_DIR.exists():
        _model = PeftModel.from_pretrained(base, str(ADAPTER_DIR))
        print(f"[infer_locate] loaded fine-tuned adapter from {ADAPTER_DIR}")
    else:
        _model = base
        print(
            f"[infer_locate] WARNING: no adapter at {ADAPTER_DIR} -- "
            f"answering with the UN-tuned base model. Run train_lora.py "
            f"first for real results."
        )

    _model.eval()
    return _model, _processor


def locate(image: Image.Image, instruction: str):
    """Returns (x, y) real pixel coordinates on `image` for the UI
    element `instruction` describes, or None if the model's answer
    couldn't be parsed as a point."""
    model, processor = _load()
    width, height = image.size

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": instruction},
            ],
        },
    ]

    prompt_text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
    )
    inputs = processor(text=[prompt_text], images=[image], return_tensors="pt")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        generated = model.generate(**inputs, max_new_tokens=64, do_sample=False)

    output_ids = generated[0][inputs["input_ids"].shape[1]:]
    raw_answer = processor.tokenizer.decode(output_ids, skip_special_tokens=True)

    match = _POINT_RE.search(raw_answer)
    if not match:
        print(f"[infer_locate] could not parse a point from: {raw_answer!r}")
        return None

    x_norm, y_norm = int(match.group(1)), int(match.group(2))
    x = round(x_norm / 1000 * width)
    y = round(y_norm / 1000 * height)
    return x, y


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--instruction", required=True)
    args = parser.parse_args()

    image = Image.open(args.image).convert("RGB")
    result = locate(image, args.instruction)
    print(json.dumps({"instruction": args.instruction, "point": result}))


if __name__ == "__main__":
    main()
