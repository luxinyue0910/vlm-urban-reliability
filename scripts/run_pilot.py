"""Portable, single-pass API runner. No retries or overwriting existing runs."""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TASKS = {'road_surface_marking','traffic_signal','streetlight','sidewalk',
         'traffic_sign','bus_stop','bicycle_lane'}

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def validate(pred):
    if not isinstance(pred, dict) or set(pred) != TASKS:
        raise ValueError('Task keys differ')
    for value in pred.values():
        if not isinstance(value, dict) or set(value) != {'label','confidence','evidence'}:
            raise ValueError('Unexpected task fields')
        if value['label'] not in ('1','0','NA'):
            raise ValueError('Invalid label')
        if type(value['confidence']) is not int or not 0 <= value['confidence'] <= 100:
            raise ValueError('Invalid confidence')
        if not isinstance(value['evidence'], str) or not value['evidence'].strip():
            raise ValueError('Empty evidence')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT/'configs/pilot.json')
    parser.add_argument('--manifest', type=Path, default=ROOT/'data/pilot_manifest.json')
    parser.add_argument('--prompt', type=Path, default=ROOT/'data/private/prompt.txt')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    entries = json.loads(args.manifest.read_text())
    prompt = args.prompt.read_text()
    image_ids = [x['image_id'] for x in entries]
    if len(image_ids) != len(set(image_ids)) or any(Path(i).name != i or i in ('.','..') for i in image_ids):
        raise SystemExit('Invalid or duplicate image IDs')
    inputs = []
    for entry in entries:
        raw = (args.manifest.parent/entry['path']).read_bytes()
        if digest(raw) != entry['image_sha256']:
            raise SystemExit(f"Image hash mismatch: {entry['image_id']}")
        inputs.append((entry,raw))
    metadata = {**config, 'prompt_sha256':digest(prompt.encode()),
                'manifest_sha256':digest(args.manifest.read_bytes()),
                'image_preprocessing':'none; original JPEG bytes',
                'calls_per_image':1, 'automatic_retries':0,
                'confidence_definition':'self-reported confidence in selected label, not calibrated probability'}
    if args.dry_run:
        print(json.dumps({'dry_run':True,'images':len(inputs),**metadata}, ensure_ascii=False, indent=2))
        return
    if not args.output:
        parser.error('--output is required for an API run')
    key = os.environ.get('DASHSCOPE_API_KEY')
    if not key:
        raise SystemExit('Set DASHSCOPE_API_KEY in your environment first.')
    # A new output directory prevents silent reuse of a different prompt/model run.
    args.output.mkdir(parents=True, exist_ok=False)
    metadata['started_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save(args.output/'run_manifest.json', metadata)
    (args.output/'prompt.txt').write_text(prompt, encoding='utf-8')
    rows, failures, usage = [], [], {}
    for entry, raw in inputs:
        image_id = entry['image_id']
        payload = {'model':config['model'],'messages':[{'role':'user','content':[
            {'type':'text','text':prompt},
            {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(raw).decode()}}
        ]}], **config['parameters']}
        body = json.dumps(payload, ensure_ascii=False).encode()
        record = {'image_id':image_id,'image_sha256':digest(raw),'request_sha256':digest(body),
                  'model_requested':config['model'],'valid':False,
                  'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        start = time.monotonic()
        try:
            request = urllib.request.Request(config['endpoint'], data=body,
                headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.load(response)
            record['response'] = result
            for name,value in result.get('usage',{}).items():
                if type(value) in (int,float):
                    usage[name] = usage.get(name,0)+value
            choice = result['choices'][0]
            if choice['finish_reason'] != 'stop':
                raise ValueError('Incomplete output')
            prediction = json.loads(choice['message']['content'])
            validate(prediction)
            record.update(prediction=prediction, valid=True)
            rows.extend({'image_id':image_id,'task_id':task,**value} for task,value in prediction.items())
        except Exception as error:
            record['error'] = str(error).replace(key,'[REDACTED]')
            failures.append({'image_id':image_id,'error':record['error']})
        record['elapsed_seconds'] = round(time.monotonic()-start,3)
        save(args.output/f'{image_id}.json',record)
        print(f"{image_id}: {'valid' if record['valid'] else 'failed'}", flush=True)
        if record.get('error','').startswith(('HTTP Error 401','HTTP Error 403')):
            break
    completed = len(rows)//7
    save(args.output/'predictions.json', {'model':config['model'],'parameters':config['parameters'],
         'prompt_sha256':metadata['prompt_sha256'],'total_images':len(inputs),
         'completed_images':completed,'rows':rows,'failures':failures})
    attempted = completed+len(failures)
    save(args.output/'summary.json', {'total_images':len(inputs),'completed_images':completed,
         'valid_predictions':len(rows),'attempted_images':attempted,
         'unattempted_images':len(inputs)-attempted,'usage':usage,'failures':failures})
    if failures or attempted != len(inputs):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
