"""Recompute agreement; initial annotations are not adjudicated ground truth."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description='Local agreement check; human labels are not included in the public repository.')
    parser.add_argument('--human', type=Path, required=True, help='Annotation JSON exported by the web app')
    parser.add_argument('--predictions', type=Path, default=ROOT/'results/pilot10/predictions.json')
    args = parser.parse_args()
    human = json.loads(args.human.read_text())
    rows = json.loads(args.predictions.read_text())['rows']
    pairs, excluded = [], 0
    for row in rows:
        annotation = human['images'][row['image_id']]
        if annotation['validity'] == '无效':
            excluded += 1
            continue
        label = annotation['tasks'][row['task_id']]['label']
        if annotation['validity'] != '有效' or label not in ('0','1','NA'):
            raise ValueError('Human annotations are incomplete')
        if row['label'] not in ('0','1','NA'):
            raise ValueError('Invalid model label')
        pairs.append((row, label))
    if len({(r['image_id'], r['task_id']) for r in rows}) != len(rows):
        raise ValueError('Duplicate predictions')
    agreement = sum(r['label'] == h for r,h in pairs)
    opposite = sum(r['label'] in ('0','1') and h in ('0','1') and r['label'] != h for r,h in pairs)
    result = {'reference':'user-supplied annotations; agreement does not establish accuracy',
              'total':len(pairs), 'excluded_invalid_image_judgments':excluded,
              'agreement':agreement, 'disagreements':len(pairs)-agreement,
              'opposite_binary':opposite, 'model_na':sum(r['label']=='NA' for r,h in pairs),
              'human_na':sum(h=='NA' for r,h in pairs)}
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
