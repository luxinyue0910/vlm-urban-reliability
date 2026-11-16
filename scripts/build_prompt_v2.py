"""Prepare Base V2 from the new local codebook; never calls an API."""
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT/'data/private/base_v2_six_tasks'
EXPECTED_CODEBOOK_SHA256 = 'f5f365a9b5f275a476f7fd6f4b8748544b631b57a8f599796673d86ec9557b1a'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def main():
    pdf = PRIVATE/'codebook.pdf'
    if sha(pdf.read_bytes()) != EXPECTED_CODEBOOK_SHA256:
        raise SystemExit('Codebook differs from the reviewed six-task version.')
    prefix_path = ROOT/'prompts/base_v2_six_tasks_prefix.txt'
    schema_path = ROOT/'schemas/base_v2_six_tasks.schema.json'
    config_path = ROOT/'configs/base_v2_six_tasks.json'
    config = json.loads(config_path.read_text())
    if config != json.loads((ROOT/'configs/pilot.json').read_text()):
        raise SystemExit('API settings changed; expected the same settings as V1.')
    # Same extraction and concatenation method as V1; no prompt optimization.
    codebook = '\n'.join(page.extract_text() for page in PdfReader(pdf).pages)
    prompt = prefix_path.read_text() + codebook
    schema = json.loads(schema_path.read_text())
    tasks = schema['required']
    if len(tasks) != 6 or set(schema['properties']) != set(tasks):
        raise SystemExit('Expected exactly six task keys.')
    if 'bus_stop' in prompt or 'bicycle_lane' in prompt or '七类设施' in prompt:
        raise SystemExit('Legacy task list remains in the new prompt.')
    PRIVATE.mkdir(parents=True,exist_ok=True)
    (PRIVATE/'prompt.txt').write_text(prompt,encoding='utf-8')
    manifest = {
        'version':'base_v2_six_tasks', 'status':'prepared_not_run',
        'codebook_sha256':EXPECTED_CODEBOOK_SHA256,
        'prompt_sha256':sha(prompt.encode()),
        'schema_sha256':sha(schema_path.read_bytes()),
        'configuration':config, 'task_ids':tasks,
        'image_preprocessing':'none; original JPEG bytes',
        'planned_calls_per_image':1, 'calls_executed':0,
        'pdf_extraction':'pypdf default extract_text per page, joined with newline; same method as V1',
        'legacy_three_tasks_wording':'Preserved inside original codebook; six-task instruction in prefix overrides it.',
        'compatibility':'Use run_batch.py --version base_v2_six_tasks; default is local preflight. V1 reuse is rejected.'
    }
    (PRIVATE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'version':manifest['version'],'task_count':len(tasks),
        'prompt_sha256':manifest['prompt_sha256'],'settings_unchanged':True,'calls_executed':0},ensure_ascii=False))

if __name__ == '__main__':
    main()
