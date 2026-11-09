#!/usr/bin/env python3
"""Train a small font encoder on rendered local fonts and export it to ONNX.

Training uses two augmented views per face, with identical text across the
batch. Hard negative metric learning therefore has to distinguish fonts.
Only this training command requires torch and onnx.
"""
import argparse
import json
import random
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from match_fonts import (INPUT_HEIGHT, INPUT_WIDTH, FontMatcher, load_index,
                         model_input, render_text, supports)

TRAIN_CJK = "智慧校园核心模块统一数据平台课程教学管理服务学生教师资源共享安全建设发展方案数字技术创新实践项目学习成果展示"
TRAIN_LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
VALIDATION_TEXTS = ["教育信息化应用", "科学研究与交流", "数字资源中心",
                    "Quarterly Report", "Campus AI 2026", "Project Overview"]


class FontEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.AdaptiveAvgPool2d((3, 8)), nn.Flatten(), nn.Linear(64 * 3 * 8, 64))

    def forward(self, ink):
        return F.normalize(self.features(ink), dim=1)


def augment(mask, rng):
    scale = rng.uniform(0.55, 1.15)
    width = max(1, int(round(mask.shape[1] * scale)))
    height = max(1, int(round(mask.shape[0] * scale)))
    result = cv2.resize(mask, (width, height), interpolation=cv2.INTER_AREA)
    if rng.random() < 0.4:
        result = cv2.GaussianBlur(result, (3, 3), rng.uniform(0.2, 0.65))
    # Real extraction supplies binary masks, so include that representation.
    if rng.random() < 0.5:
        result = (result > rng.uniform(70, 160)).astype(np.uint8) * 255
    return result


def train(fonts, steps, seed):
    rng = random.Random(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    encoder = FontEncoder()
    classifier = nn.Linear(64, len(fonts))
    optimizer = torch.optim.AdamW([*encoder.parameters(), *classifier.parameters()], lr=0.001)
    # A fixed synthetic corpus limits rendering overhead while varying text
    # independently of font identity. Validation uses separate phrases below.
    phrases = []
    for alphabet in (TRAIN_CJK, TRAIN_LATIN):
        for _ in range(40):
            text = "".join(rng.choices(alphabet, k=rng.randint(4, 10)))
            eligible = [i for i, font in enumerate(fonts) if supports(font, text)]
            if len(eligible) >= 2:
                phrases.append((text, eligible))
    covered = set(i for _, indices in phrases for i in indices)
    if len(covered) != len(fonts):
        raise ValueError("some indexed fonts cannot render the training corpus; use a text-font index")
    cache = {}
    started = time.monotonic()
    for step in range(steps):
        text, eligible = rng.choice(phrases)
        selected = rng.sample(eligible, min(16, len(eligible)))
        inputs, labels = [], []
        for index in selected:
            key = (index, text)
            if key not in cache:
                cache[key] = render_text(fonts[index], text, 48)
            for _ in range(2):
                inputs.append(model_input(augment(cache[key], rng)))
                labels.append(index)
        batch = torch.from_numpy(np.stack(inputs))
        targets = torch.tensor(labels)
        embeddings = encoder(batch)
        similarities = embeddings @ embeddings.T
        same = targets[:, None] == targets[None, :]
        diagonal = torch.eye(len(targets), dtype=torch.bool)
        positive = similarities.masked_fill(~same | diagonal, float("inf")).min(dim=1).values
        negative = similarities.masked_fill(same, -float("inf")).max(dim=1).values
        metric_loss = F.relu(negative - positive + 0.15).mean()
        class_loss = F.cross_entropy(classifier(embeddings) * 8, targets)
        loss = metric_loss + 0.25 * class_loss
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        if step == 0 or (step + 1) % 50 == 0:
            print(f"step {step + 1}/{steps} loss={loss.item():.4f} "
                  f"elapsed={time.monotonic() - started:.1f}s", flush=True)
    return encoder.eval()


def export_model(encoder, fonts, path, steps, seed):
    import onnx

    temporary = path.with_suffix(".tmp.onnx")
    sample = torch.zeros(1, 1, INPUT_HEIGHT, INPUT_WIDTH)
    torch.onnx.export(encoder, sample, str(temporary), input_names=["ink"],
                      output_names=["embedding"], dynamic_axes={"ink": {0: "batch"},
                                                               "embedding": {0: "batch"}},
                      opset_version=17, dynamo=False)
    model = onnx.load(temporary)
    onnx.helper.set_model_props(model, {
        "slide_alchemy_font_encoder": "1", "steps": str(steps), "seed": str(seed),
        "trained_faces": json.dumps([f'{f["sha256"]}:{f["index"]}' for f in fonts])})
    onnx.checker.check_model(model)
    onnx.save(model, temporary)
    temporary.replace(path)


def evaluate(index_path, model_path, samples_per_font=1):
    matcher = FontMatcher(index_path, model_path)
    rng = random.Random(20261108)
    results = []
    for font in matcher.fonts:
        phrases = [t for t in VALIDATION_TEXTS if supports(font, t)]
        for sample in range(samples_per_font):
            text = phrases[sample % len(phrases)] if phrases else "0123456789"
            if not supports(font, text):
                continue
            mask = augment(render_text(font, text, rng.randint(24, 64)), rng)
            result = matcher.match(mask, text)
            expected = (font["path"], font["index"])
            candidates = result["candidates"]
            found = any((c["path"], c["index"]) == expected for c in candidates)
            best = candidates[0]
            correct = (best["path"], best["index"]) == expected
            results.append({"family": font["family"], "style": font["style"], "text": text,
                            "top10": found, "top1": correct, "best": best["family"],
                            "best_style": best["style"], "shape_error": best["shape_error"]})
    count = len(results)
    return {"kind": "held_out_text_synthetic", "samples": count,
            "top10_recall": sum(r["top10"] for r in results) / count if count else None,
            "top1_accuracy": sum(r["top1"] for r in results) / count if count else None,
            "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-index", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--steps", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--eval-only", action="store_true")
    parser.add_argument("--samples-per-font", type=int, default=1)
    args = parser.parse_args()
    fonts = load_index(args.font_index)
    if len(fonts) < 2 or args.steps < 1 or args.samples_per_font < 1:
        parser.error("need >= 2 fonts, >= 1 training step and >= 1 sample per font")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not args.eval_only:
        encoder = train(fonts, args.steps, args.seed)
        export_model(encoder, fonts, args.out, args.steps, args.seed)
    report = evaluate(args.font_index, args.out, args.samples_per_font)
    report_path = args.out.with_suffix(".evaluation.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}), flush=True)


if __name__ == "__main__":
    main()
