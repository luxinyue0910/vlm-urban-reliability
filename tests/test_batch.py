"""Offline tests. Every HTTP entry point is replaced; no model calls are possible."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_batch
from run_pilot import validate

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.images=self.root/'images';self.images.mkdir()
        (self.images/'a.jpg').write_bytes(b'local test image a')
        (self.images/'b.jpg').write_bytes(b'local test image b')
        self.output=self.root/'output'
        schema=run_batch.read(run_batch.ROOT/'schemas/base_v2_six_tasks.schema.json')
        self.tasks=schema['required']
        self.profile={'version':'base_v2_six_tasks','configuration':{
            'model':'test-model','endpoint':'https://test.invalid/completions',
            'parameters':{'temperature':0,'enable_thinking':False,'max_tokens':1800,
                          'response_format':{'type':'json_object'}}},
            'prompt':'test prompt','prompt_sha256':run_batch.sha(b'test prompt'),
            'task_ids':self.tasks,'schema_sha256':'test-schema','codebook_sha256':'test-codebook'}
        self.prediction={t:{'label':'NA','confidence':50,'evidence':'Synthetic test only.'} for t in self.tasks}
        self.args=['--images',str(self.images),'--output',str(self.output),'--workers','1']

    def tearDown(self):self.tmp.cleanup()

    def response(self,*args,**kwargs):
        payload=json.loads(args[0].data)
        self.assertEqual(payload['model'],'test-model')
        self.assertEqual(payload['temperature'],0)
        self.assertEqual(payload['messages'][0]['content'][0]['text'],'test prompt')
        return io.BytesIO(json.dumps({'model':'test-model','choices':[{
            'finish_reason':'stop','message':{'content':json.dumps(self.prediction)}}],
            'usage':{'total_tokens':10}}).encode())

    def invoke(self,extra=(),transport=None,profile=None):
        with patch.object(run_batch,'load_version',return_value=profile or self.profile), \
             patch('urllib.request.urlopen',side_effect=transport or AssertionError('Network forbidden')) as http, \
             patch.dict(os.environ,{'DASHSCOPE_API_KEY':'synthetic-test-key'},clear=True), \
             contextlib.redirect_stdout(io.StringIO()):
            run_batch.main(self.args+list(extra))
            return http.call_count

    def test_default_is_local_six_task_preflight(self):
        self.assertEqual(self.invoke(),0)
        p=run_batch.read(self.output/'preflight.json')
        self.assertEqual((p['total_images'],p['task_count'],p['expected_prediction_rows']),(2,6,12))
        self.assertFalse((self.output/'records').exists())
        self.assertFalse((self.output/'run_manifest.json').exists())

    def test_six_task_execution_and_resume_without_new_calls(self):
        self.assertEqual(self.invoke(['--execute'],self.response),2)
        rows=run_batch.read(self.output/'predictions.json')['rows']
        self.assertEqual(len(rows),12)
        self.assertEqual(set(r['task_id'] for r in rows),set(self.tasks))
        self.assertEqual(self.invoke(['--execute']),0)
        self.assertEqual(run_batch.read(self.output/'summary.json')['api_calls_this_invocation'],0)

    def test_invalid_seven_task_answers_are_preserved_not_retried(self):
        self.prediction['bus_stop']={'label':'0','confidence':50,'evidence':'Synthetic test only.'}
        with self.assertRaises(SystemExit):self.invoke(['--execute'],self.response)
        summary=run_batch.read(self.output/'summary.json')
        self.assertEqual(summary['api_calls_this_invocation'],2)
        self.assertEqual(summary['valid_predictions'],0)
        self.assertEqual(len(summary['failures']),2)
        with self.assertRaises(SystemExit):self.invoke(['--execute'])
        self.assertEqual(run_batch.read(self.output/'summary.json')['api_calls_this_invocation'],0)

    def test_changed_version_cannot_overwrite_existing_run(self):
        self.invoke(['--execute'],self.response)
        changed=copy.deepcopy(self.profile);changed['prompt']='changed';changed['prompt_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'different version/input'):self.invoke(profile=changed)

    def test_reuse_checks_exact_payload_and_avoids_new_calls(self):
        self.invoke(['--execute'],self.response)
        original=self.output;self.output=self.root/'reuse-output'
        self.args=['--images',str(self.images),'--output',str(self.output),'--workers','1']
        self.assertEqual(self.invoke(['--execute','--reuse',str(original)]),0)
        self.assertEqual(run_batch.read(self.output/'summary.json')['reused_images'],2)

    def test_seven_task_version_reuse_is_rejected(self):
        reuse=self.root/'old';reuse.mkdir()
        run_batch.save(reuse/'run_manifest.json',{'configuration':self.profile['configuration'],
            'prompt_sha256':'old-seven-task-prompt','codebook_sha256':'old-codebook',
            'image_preprocessing':run_batch.PREPROCESSING})
        with self.assertRaisesRegex(ValueError,'V1 results cannot be reused for V2'):
            self.invoke(['--reuse',str(reuse)])

    def test_strict_fields_and_missing_tasks(self):
        validate(self.prediction,self.tasks)
        variants=[]
        for field,value in [('label',1),('confidence',True),('confidence',101),('evidence','  ')]:
            p=copy.deepcopy(self.prediction);p[self.tasks[0]][field]=value;variants.append(p)
        p=copy.deepcopy(self.prediction);p.pop(self.tasks[0]);variants.append(p)
        for p in variants:
            with self.assertRaises(ValueError):validate(p,self.tasks)

if __name__=='__main__':unittest.main()
