"""Reconstruct the historical prompt from a locally supplied codebook."""
import argparse
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf', type=Path, default=ROOT/'data/private/codebook.pdf')
    parser.add_argument('--output', type=Path, default=ROOT/'data/private/prompt.txt')
    args = parser.parse_args()
    prefix = (ROOT/'prompts/pilot_prefix.txt').read_text()
    text = prefix + '\n'.join(p.extract_text() for p in PdfReader(args.pdf).pages)
    archived = json.loads((ROOT/'results/pilot10/run_manifest.json').read_text())
    digest = hashlib.sha256(text.encode()).hexdigest()
    if digest != archived['prompt_sha256']:
        raise SystemExit('Prompt 与历史试跑不一致：请检查 PDF 或提取器版本；未写入文件。')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding='utf-8')
    print('已生成完整本地 Prompt，哈希与历史试跑一致。')

if __name__ == '__main__':
    main()
