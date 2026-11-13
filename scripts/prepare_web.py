"""Copy user-provided local assets to the ignored web asset directories."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    rows = json.loads((ROOT/'data/pilot_manifest.json').read_text())
    sources = [(r, ROOT/'data'/r['path']) for r in rows]
    for row, source in sources:
        if hashlib.sha256(source.read_bytes()).hexdigest() != row['image_sha256']:
            raise SystemExit(f"图片不匹配：{row['image_id']}")
    pdf = ROOT/'data/private/codebook.pdf'
    if not pdf.exists():
        raise SystemExit('请先放入 data/private/codebook.pdf')
    (ROOT/'web/images').mkdir(exist_ok=True)
    for row, source in sources:
        shutil.copyfile(source, ROOT/'web/images'/f"{row['image_id']}.jpg")
    shutil.copyfile(pdf, ROOT/'web/codebook.pdf')
    shutil.copyfile(ROOT/'results/pilot10/predictions.json', ROOT/'web/model-results.json')
    print('本地网页资料已就绪；新增的原图和 PDF 不会提交 Git。')

if __name__ == '__main__':
    main()
