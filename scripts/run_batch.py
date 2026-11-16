"""Versioned batch inference. Local preflight by default; API calls require --execute."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
from run_pilot import TASKS, validate

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ('base_v2_six_tasks', 'pilot_v1')
PREPROCESSING = 'none; original JPEG bytes'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def save(path, value):
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)

def read(path):
    return json.loads(path.read_text())

def load_version(version):
    if version == 'base_v2_six_tasks':
        config_path = ROOT/'configs/base_v2_six_tasks.json'
        private = ROOT/'data/private/base_v2_six_tasks'
        schema_path = ROOT/'schemas/base_v2_six_tasks.schema.json'
        schema = read(schema_path)
        tasks = schema['required']
        item = schema['$defs']['prediction']; properties = item['properties']
        # The shared field validator implements this contract; do not silently
        # accept future schema changes that it cannot enforce.
        valid_contract = (
            schema['type']=='object' and schema['additionalProperties'] is False
            and len(tasks)==6 and len(set(tasks))==6 and set(tasks)==set(schema['properties'])
            and all(v=={'$ref':'#/$defs/prediction'} for v in schema['properties'].values())
            and item['type']=='object' and item['additionalProperties'] is False
            and set(item['required'])==set(properties)=={'label','confidence','evidence'}
            and properties['label']['type']=='string' and properties['label']['enum']==['1','0','NA']
            and properties['confidence']['type']=='integer'
            and properties['confidence']['minimum']==0 and properties['confidence']['maximum']==100
            and properties['evidence']['type']=='string' and properties['evidence']['minLength']==1
            and properties['evidence']['pattern']==r'\S')
        if not valid_contract:raise ValueError('Schema is incompatible with the batch field validator')
        prepared = read(private/'manifest.json'); schema_hash = sha(schema_path.read_bytes())
        if schema_hash != prepared['schema_sha256'] or tasks != prepared['task_ids']:
            raise ValueError('Schema differs from prepared V2; rebuild the prompt bundle')
    else:
        config_path = ROOT/'configs/pilot.json'; private = ROOT/'data/private'
        prepared = read(ROOT/'results/pilot10/run_manifest.json')
        tasks = sorted(TASKS); schema_hash = None
    config = read(config_path); prompt = (private/'prompt.txt').read_text()
    expected_config = prepared.get('configuration') or {
        'model':prepared['model_requested'],'endpoint':prepared['endpoint'],'parameters':prepared['parameters']}
    if config != expected_config or sha(prompt.encode()) != prepared['prompt_sha256']:
        raise ValueError('Prompt/configuration differs from the prepared version')
    if sha((private/'codebook.pdf').read_bytes()) != prepared['codebook_sha256']:
        raise ValueError('Codebook differs from the prepared version')
    return {'version':version,'configuration':config,'prompt':prompt,'task_ids':tasks,
        'schema_sha256':schema_hash,'codebook_sha256':prepared['codebook_sha256'],
        'prompt_sha256':sha(prompt.encode())}

def request_body(config, prompt, raw, mime):
    payload = {'model':config['model'],'messages':[{'role':'user','content':[
        {'type':'text','text':prompt},
        {'type':'image_url','image_url':{'url':f'data:{mime};base64,'+base64.b64encode(raw).decode()}}
    ]}],**config['parameters']}
    return json.dumps(payload,ensure_ascii=False).encode()

def enumerate_images(directory):
    entries = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() not in ('.jpg','.jpeg'):continue
        entries.append({'image_id':f'S{len(entries)+1:03}','original_filename':path.name,
            'image_sha256':sha(path.read_bytes()),
            'mime_type':'image/jpeg'})
    if not entries or len({e['image_sha256'] for e in entries}) != len(entries):
        raise ValueError('Empty input or duplicate image bytes; review the local audit first')
    return entries

def load_reuse(directory, profile):
    if directory is None:return {}
    manifest = read(directory/'run_manifest.json')
    config = manifest.get('configuration') or {
        'model':manifest.get('model_requested'),'endpoint':manifest.get('endpoint'),
        'parameters':manifest.get('parameters')}
    if (config != profile['configuration'] or manifest['prompt_sha256'] != profile['prompt_sha256']
        or manifest.get('codebook_sha256') != profile['codebook_sha256']
        or manifest.get('image_preprocessing') != PREPROCESSING):
        raise ValueError('Reuse mismatch: prompt/codebook/model/settings differ; V1 results cannot be reused for V2')
    if profile['schema_sha256'] is not None and manifest.get('schema_sha256') != profile['schema_sha256']:
        raise ValueError('Reuse schema mismatch')
    records_dir = directory/'records' if (directory/'records').is_dir() else directory
    prior = {}
    for path in sorted(records_dir.glob('*.json')):
        record = read(path)
        if not record.get('valid') or 'prediction' not in record:continue
        validate(record['prediction'],profile['task_ids'])
        if record['response']['model'] != profile['configuration']['model']:
            raise ValueError('Previous returned model mismatch')
        prior[record['image_sha256']] = record
    return prior

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',choices=VERSIONS,default='base_v2_six_tasks')
    parser.add_argument('--images',type=Path,required=True)
    parser.add_argument('--reuse',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=3,choices=range(1,5))
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run',action='store_true',help='Local preflight only (default)')
    mode.add_argument('--execute',action='store_true',help='Send images to the API; billable')
    args=parser.parse_args(argv)
    profile=load_version(args.version)
    config,prompt,tasks=profile['configuration'],profile['prompt'],profile['task_ids']
    entries=enumerate_images(args.images);prior=load_reuse(args.reuse,profile)
    identity={k:v for k,v in profile.items() if k!='prompt'}
    fingerprint=sha(json.dumps({'profile':identity,'images':entries},sort_keys=True).encode())
    records=args.output/'records';run_manifest=args.output/'run_manifest.json'
    if run_manifest.exists() and read(run_manifest).get('fingerprint') != fingerprint:
        raise ValueError('Existing output directory belongs to a different version/input set; use a new directory')
    if records.exists() and any(records.glob('*.json')) and not run_manifest.exists():
        raise ValueError('Unidentified existing records; use a new output directory')
    cached,reusable={},{}
    for entry in entries:
        dest=records/f"{entry['image_id']}.json"
        if dest.exists():
            record=read(dest)
            if record['image_sha256'] != entry['image_sha256'] or record.get('run_fingerprint') != fingerprint:
                raise ValueError('Existing record identity mismatch')
            if record.get('valid'):validate(record['prediction'],tasks)
            cached[entry['image_id']]=record
        elif entry['image_sha256'] in prior:
            previous=prior[entry['image_sha256']]
            body=request_body(config,prompt,(args.images/entry['original_filename']).read_bytes(),entry['mime_type'])
            if sha(body) != previous['request_sha256']:raise ValueError('Previous exact request payload mismatch')
            reusable[entry['image_id']]=previous
    preflight={**identity,'fingerprint':fingerprint,'mode':'execute' if args.execute else 'dry_run',
        'image_preprocessing':PREPROCESSING,'total_images':len(entries),'task_count':len(tasks),
        'expected_prediction_rows':len(entries)*len(tasks),'already_saved_images':len(cached),
        'reusable_images':len(reusable),'images_needing_api':len(entries)-len(cached)-len(reusable),
        'api_calls_this_preflight':0}
    args.output.mkdir(parents=True,exist_ok=True)
    save(args.output/'preflight.json',preflight);save(args.output/'images.json',entries)
    print(json.dumps(preflight,ensure_ascii=False,indent=2),flush=True)
    if not args.execute:return
    # No credential access or HTTP call occurs before the explicit execute gate.
    key=os.environ.get('DASHSCOPE_API_KEY')
    if not key:raise ValueError('Missing DASHSCOPE_API_KEY')
    records.mkdir(exist_ok=True)
    if not run_manifest.exists():
        save(run_manifest,{**identity,'fingerprint':fingerprint,'image_preprocessing':PREPROCESSING,
            'total_images':len(entries),'task_count':len(tasks),'started_at_utc':now(),
            'retry_policy':'HTTP 429/5xx only, maximum 3 attempts; invalid answers/timeouts are not automatically retried'})
        (args.output/'prompt.txt').write_text(prompt,encoding='utf-8')
    stop=threading.Event();executed=[]

    def run_one(entry):
        image_id=entry['image_id'];dest=records/f'{image_id}.json'
        if image_id in cached:return cached[image_id]
        raw=(args.images/entry['original_filename']).read_bytes()
        if sha(raw)!=entry['image_sha256']:raise ValueError('Image changed during run')
        body=request_body(config,prompt,raw,entry['mime_type'])
        if image_id in reusable:
            previous=reusable[image_id]
            record={**entry,'run_fingerprint':fingerprint,'source':'reused','valid':True,
                'previous_image_id':previous['image_id'],'previous_started_at_utc':previous.get('started_at_utc'),
                'reused_from_run':args.reuse.name,'request_sha256':sha(body),
                'model_requested':config['model'],'response':previous['response'],
                'prediction':previous['prediction'],'api_attempts':0,'attempts':[]}
            save(dest,record);return record
        record={**entry,'run_fingerprint':fingerprint,'source':'new_batch','valid':False,
            'model_requested':config['model'],'request_sha256':sha(body),
            'started_at_utc':now(),'api_attempts':0,'attempts':[]}
        if stop.is_set():
            record.update(error='Not attempted after authentication failure',unattempted=True)
            save(dest,record);return record
        start=time.monotonic()
        for attempt in range(1,4):
            log={'attempt':attempt,'started_at_utc':now()};tick=time.monotonic();retry=False
            try:
                request=urllib.request.Request(config['endpoint'],data=body,
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
                record['api_attempts']+=1;executed.append(image_id)
                with urllib.request.urlopen(request,timeout=150) as response:result=json.load(response)
                record['response']=result
                if result['model']!=config['model']:raise ValueError('Returned model differs from requested model')
                choice=result['choices'][0]
                if choice['finish_reason']!='stop':raise ValueError('Incomplete model output')
                prediction=json.loads(choice['message']['content']);validate(prediction,tasks)
                record.update(prediction=prediction,valid=True);log['status']='valid'
            except urllib.error.HTTPError as error:
                log.update(status='http_error',http_status=error.code,error=str(error).replace(key,'[REDACTED]'))
                record['error']=log['error']
                if error.code in (401,403):stop.set()
                retry=error.code==429 or 500<=error.code<600
            except Exception as error:
                log.update(status='failed',error=str(error).replace(key,'[REDACTED]'));record['error']=log['error']
            log['elapsed_seconds']=round(time.monotonic()-tick,3)
            record['attempts'].append(log);record['elapsed_seconds']=round(time.monotonic()-start,3)
            if record['valid']:record.pop('error',None)
            save(dest,record)
            if record['valid'] or not retry or attempt==3 or stop.is_set():break
            time.sleep(2**attempt)
        return record

    completed=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(run_one,entry) for entry in entries]
        for future in as_completed(futures):
            record=future.result();completed.append(record)
            print(json.dumps({'finished':len(completed),'total':len(entries),'image_id':record['image_id'],
                'source':record['source'],'valid':record['valid']},ensure_ascii=False),flush=True)
    completed.sort(key=lambda r:r['image_id'])
    rows=[{'image_id':r['image_id'],'original_filename':r['original_filename'],'source':r['source'],
           'task_id':task,**r['prediction'][task]} for r in completed if r['valid'] for task in tasks]
    failures=[{'image_id':r['image_id'],'error':r.get('error')} for r in completed if not r['valid']]
    usage={'new_run':{},'reused':{}}
    for record in completed:
        bucket=usage['reused' if record['source']=='reused' else 'new_run']
        for name,value in record.get('response',{}).get('usage',{}).items():
            if type(value) in (int,float):bucket[name]=bucket.get(name,0)+value
    summary={'version':args.version,'total_images':len(entries),'task_count':len(tasks),
        'valid_images':sum(r['valid'] for r in completed),'valid_predictions':len(rows),
        'reused_images':sum(r['source']=='reused' for r in completed),
        'api_calls_this_invocation':len(executed),'api_attempts_in_run':sum(r.get('api_attempts',0) for r in completed),
        'usage':usage,'failures':failures,'finished_at_utc':now(),
        'scope':'all supplied images; no manual scene-validity exclusion or human-label evaluation'}
    save(args.output/'predictions.json',{'version':args.version,'model':config['model'],
        'parameters':config['parameters'],'prompt_sha256':profile['prompt_sha256'],
        'schema_sha256':profile['schema_sha256'],'rows':rows,'failures':failures})
    save(args.output/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
