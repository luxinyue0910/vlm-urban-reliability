"""Local-only overlap audit: bytes, decoded pixels, visual candidates and video IDs."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from PIL import Image, ImageOps

EXTENSIONS = {'.jpg', '.jpeg', '.png'}

def group(rows, key):
    groups = defaultdict(list)
    for row in rows:
        if row.get(key) is not None:
            groups[row[key]].append(row['filename'])
    return groups

def inspect_images(root):
    rows, errors = [], []
    for path in sorted(root.iterdir()):
        if path.suffix.lower() not in EXTENSIONS or not path.is_file():
            continue
        row = {'filename':path.name, 'file_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        match = re.fullmatch(r'(.+)_site_(\d+)\.[^.]+', path.name)
        if match:
            row.update(video_id=match[1], site_index=int(match[2]))
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert('RGB')
                row['dimensions'] = list(image.size)
                row['pixel_sha256'] = hashlib.sha256(
                    f'RGB:{image.width}x{image.height}:'.encode()+image.tobytes()).hexdigest()
                small = image.convert('L').resize((17,16),Image.Resampling.LANCZOS)
                pixels = list(small.tobytes())
                bits = 0
                for y in range(16):
                    for x in range(16):
                        bits = (bits << 1) | (pixels[y*17+x] > pixels[y*17+x+1])
                row['dhash256'] = f'{bits:064x}'
        except Exception as error:
            errors.append({'filename':path.name,'error':str(error)})
        rows.append(row)
    return rows, errors

def duplicates(rows, key):
    return [names for names in group(rows,key).values() if len(names)>1]

def audit(development, reference, max_distance=8):
    dev, dev_errors = inspect_images(development)
    ref, ref_errors = inspect_images(reference)
    matches = {}
    for key in ('filename','file_sha256','pixel_sha256'):
        lookup = group(ref,key)
        matches[key] = [
            {'development':row['filename'],'reference':lookup[row[key]]}
            for row in dev if row.get(key) is not None and row[key] in lookup]
    candidates = []
    for a in dev:
        if 'dhash256' not in a: continue
        for b in ref:
            if 'dhash256' not in b or a['pixel_sha256']==b['pixel_sha256']:continue
            distance = (int(a['dhash256'],16)^int(b['dhash256'],16)).bit_count()
            if distance<=max_distance:
                candidates.append({'development':a['filename'],'reference':b['filename'],
                    'dhash256_distance':distance,'same_filename_video':a.get('video_id')==b.get('video_id')})
    candidates.sort(key=lambda x:(x['dhash256_distance'],x['development'],x['reference']))
    dev_videos, ref_videos = group(dev,'video_id'), group(ref,'video_id')
    shared_videos = sorted(set(dev_videos)&set(ref_videos))
    proximity = []
    for a in dev:
        options = [b for b in ref if a.get('video_id') and b.get('video_id')==a['video_id']]
        if options:
            b = min(options,key=lambda b:abs(a['site_index']-b['site_index']))
            proximity.append({'development':a['filename'],'nearest_reference':b['filename'],
                'video_id':a['video_id'],'site_index_gap':abs(a['site_index']-b['site_index'])})
    summary = {'development_images':len(dev),'reference_images':len(ref),
        'cross_set_same_filename':len(matches['filename']),
        'cross_set_byte_identical':len(matches['file_sha256']),
        'cross_set_pixel_identical':len(matches['pixel_sha256']),
        'development_internal_byte_duplicate_groups':len(duplicates(dev,'file_sha256')),
        'development_internal_pixel_duplicate_groups':len(duplicates(dev,'pixel_sha256')),
        'reference_internal_byte_duplicate_groups':len(duplicates(ref,'file_sha256')),
        'reference_internal_pixel_duplicate_groups':len(duplicates(ref,'pixel_sha256')),
        'visual_candidate_pairs':len(candidates),'dhash256_max_distance':max_distance,
        'development_video_ids':len(dev_videos),'reference_video_ids':len(ref_videos),
        'shared_video_ids':len(shared_videos),
        'development_images_from_shared_videos':sum(len(dev_videos[v]) for v in shared_videos),
        'reference_images_from_shared_videos':sum(len(ref_videos[v]) for v in shared_videos),
        'same_video_site_index_gap_le5':sum(p['site_index_gap']<=5 for p in proximity),
        'decode_errors':len(dev_errors)+len(ref_errors)}
    return {'summary':summary,'matches':matches,'visual_candidates':candidates,
        'development_internal_pixel_duplicates':duplicates(dev,'pixel_sha256'),
        'shared_video_groups':[{'video_id':v,'development':dev_videos[v],'reference':ref_videos[v]} for v in shared_videos],
        'same_video_nearest_reference':proximity,
        'development_inventory':dev,'reference_inventory':ref,
        'errors':{'development':dev_errors,'reference':ref_errors},
        'limitations':[
            'dHash candidates are not confirmed duplicates; different viewpoints/crops may be missed.',
            'Matching filename video IDs indicate shared acquisition source, not proven geographic identity.',
            'Site index gaps are sequence numbers, not measured distance or time.',
            'No image is deleted, moved, excluded or sent to a model.']}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--development',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-distance',type=int,default=8)
    args=parser.parse_args()
    report=audit(args.development,args.reference,args.max_distance)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
