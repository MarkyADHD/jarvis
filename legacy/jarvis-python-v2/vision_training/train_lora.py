"""train_lora.py -- fine-tune our own GUI-grounding LoRA on top of
Qwen2.5-VL-7B-Instruct, using the dataset collect_ui_data.py builds.

WHY THIS BASE MODEL: Jarvis already runs Qwen2.5-VL-7B locally (via
Ollama, for the existing "what's on my screen" Q&A) and it already has
native grounding ability in its training -- it was taught to output
coordinates for described image regions, just not specifically tuned on
YOUR apps (Paint.net/DaVinci/Premiere/CapCut) or to this project's exact
answer format. A LoRA adapter on top of it, trained on real examples of
those specific apps, is what turns "a vision model" into "OUR vision
model" without needing to train a foundation model from nothing -- that
would need internet-scale data and a data-center's worth of GPUs neither
of which exist here.

WHY 4-BIT QLORA: the RTX 4070 in this machine has 12GB of VRAM. A 7B
vision-language model in full precision does not fit alongside training
activations and optimizer state in that budget. Loading the frozen base
model in 4-bit (bitsandbytes NF4) and training only small LoRA adapter
weights on top brings the whole job comfortably inside 12GB.

WHAT GETS TRAINED: LoRA adapters on the language-model attention/MLP
projections only. The vision encoder stays frozen -- it already sees
images fine; what it doesn't know yet is what YOUR specific toolbars and
icons mean, and that's a language-model-side (instruction -> coordinate)
mapping problem, not a "see better" problem. Freezing the vision tower
also uses less VRAM and trains faster.

ANSWER FORMAT: every training target is exactly
    {"point": [x, y]}
where x and y are 0-1000 integers, normalized against the ORIGINAL
screenshot's width/height (not the model's internal resized image) --
Qwen2-family grounding models were themselves trained on this 0-1000
convention, so it fine-tunes fast, and it makes every trained example
resolution-independent (a 1920x1080 click and a 2560x1440 click at "the
same relative spot" land on the same trained numbers). infer_locate.py
converts back to real pixel coordinates for whatever screenshot it's
actually given.

Run with the isolated training venv, not Jarvis's main one:
    vision_training\\.venv\\Scripts\\python.exe vision_training\\train_lora.py
"""
import argparse
import json
import random
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import Dataset
from transformers import (
    AutoProcessor,
    BitsAndBytesConfig,
    Qwen2_5_VLForConditionalGeneration,
    Trainer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model

BASE_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"

DATA_ROOT = Path("E:/JarvisMemory/vision_training")
if not DATA_ROOT.exists():
    DATA_ROOT = Path("C:/AI-Agent/JarvisMemory/vision_training")
MANIFEST_PATH = DATA_ROOT / "manifest.jsonl"

OUTPUT_DIR = DATA_ROOT / "lora_out"

SYSTEM_PROMPT = (
    "You are Jarvis's vision system. Given a screenshot and an "
    "instruction describing a UI element or place to click, respond "
    "with ONLY a JSON object: {\"point\": [x, y]} where x and y are "
    "integers from 0 to 1000, giving the element's location as a "
    "fraction of the image width and height. No other text."
)

# Held out from every training run so eval loss actually means something
# rather than measuring memorisation -- fixed seed so which examples end
# up in eval doesn't change between runs on the same dataset.
EVAL_FRACTION = 0.1
SEED = 42


def load_examples():
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"No dataset at {MANIFEST_PATH}. Run collect_ui_data.py "
            f"first and label some examples."
        )
    examples = []
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def split_examples(examples):
    rng = random.Random(SEED)
    shuffled = examples[:]
    rng.shuffle(shuffled)
    n_eval = max(1, int(len(shuffled) * EVAL_FRACTION)) if len(shuffled) >= 10 else 0
    return shuffled[n_eval:], shuffled[:n_eval]


class UIGroundingDataset(Dataset):
    """One example = one (screenshot, instruction) -> {"point": [x, y]}
    target, formatted as a Qwen2.5-VL chat conversation with the prompt
    tokens masked out of the loss (label = -100) so training only
    penalises getting the coordinate answer wrong, not re-learning to
    reproduce the fixed system/user prompt text."""

    def __init__(self, examples, processor):
        self.examples = examples
        self.processor = processor

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        ex = self.examples[idx]
        image_path = DATA_ROOT / ex["image"]
        image = Image.open(image_path).convert("RGB")
        width, height = ex.get("screen_size", image.size)
        x, y = ex["point"]
        x_norm = round(1000 * x / width)
        y_norm = round(1000 * y / height)
        answer = json.dumps({"point": [x_norm, y_norm]})

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": ex["instruction"]},
                ],
            },
        ]

        prompt_text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
        full_text = prompt_text + answer

        prompt_inputs = self.processor(
            text=[prompt_text], images=[image], return_tensors="pt",
        )
        full_inputs = self.processor(
            text=[full_text], images=[image], return_tensors="pt",
        )

        input_ids = full_inputs["input_ids"][0]
        labels = input_ids.clone()
        prompt_len = prompt_inputs["input_ids"].shape[1]
        labels[:prompt_len] = -100

        item = {
            "input_ids": input_ids,
            "attention_mask": full_inputs["attention_mask"][0],
            "labels": labels,
            "pixel_values": full_inputs["pixel_values"],
            "image_grid_thw": full_inputs["image_grid_thw"][0],
        }
        return item


def make_collate_fn(pad_token_id):
    def collate(batch):
        max_len = max(item["input_ids"].shape[0] for item in batch)

        def pad(tensor, value):
            pad_len = max_len - tensor.shape[0]
            if pad_len == 0:
                return tensor
            padding = torch.full((pad_len,), value, dtype=tensor.dtype)
            return torch.cat([tensor, padding])

        input_ids = torch.stack([pad(b["input_ids"], pad_token_id) for b in batch])
        attention_mask = torch.stack([pad(b["attention_mask"], 0) for b in batch])
        labels = torch.stack([pad(b["labels"], -100) for b in batch])
        pixel_values = torch.cat([b["pixel_values"] for b in batch], dim=0)
        image_grid_thw = torch.stack([b["image_grid_thw"] for b in batch])

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
            "pixel_values": pixel_values,
            "image_grid_thw": image_grid_thw,
        }

    return collate


def build_model_and_processor():
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    processor = AutoProcessor.from_pretrained(BASE_MODEL)

    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    model.config.use_cache = False

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        # Language-model attention + MLP projections only -- the vision
        # tower and the vision-language merger are left frozen so the
        # model keeps seeing images exactly as well as it always did;
        # only the instruction -> coordinate mapping is being taught.
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    return model, processor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()

    examples = load_examples()
    print(f"[train_lora] {len(examples)} labelled examples found in {MANIFEST_PATH}")
    if len(examples) < 20:
        print(
            "[train_lora] WARNING: fewer than 20 examples. This will train "
            "without error, but a GUI-grounding LoRA that actually "
            "generalises needs hundreds of examples spread across the "
            "apps and UI states you want Jarvis to control. Treat an "
            "early run like this as a pipeline smoke test, not a real "
            "training run."
        )

    train_examples, eval_examples = split_examples(examples)
    print(f"[train_lora] {len(train_examples)} train / {len(eval_examples)} eval")

    model, processor = build_model_and_processor()

    train_dataset = UIGroundingDataset(train_examples, processor)
    eval_dataset = UIGroundingDataset(eval_examples, processor) if eval_examples else None
    collate_fn = make_collate_fn(processor.tokenizer.pad_token_id)

    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        learning_rate=args.lr,
        bf16=True,
        logging_steps=5,
        save_strategy="epoch",
        eval_strategy="epoch" if eval_dataset else "no",
        report_to=[],
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=collate_fn,
    )

    trainer.train()

    final_dir = OUTPUT_DIR / "final"
    model.save_pretrained(str(final_dir))
    processor.save_pretrained(str(final_dir))
    print(f"[train_lora] LoRA adapter saved to {final_dir}")


if __name__ == "__main__":
    main()
