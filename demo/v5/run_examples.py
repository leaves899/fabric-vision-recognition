"""Explicit human reference coordinates for offline smoke or operator-confirmed examples.

Usage:
python run_examples.py --image samples/无标定框_示例.jpg --points 600,850,850,795 --confirm

Do not treat --confirm as proof the coordinates truly mark one physical yarn.
"""
import argparse, base64, json
from pathlib import Path
from v4_analysis import analyze

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',required=True,type=Path)
    parser.add_argument('--points',required=True,help='原图坐标 x1,y1,x2,y2')
    parser.add_argument('--confirm',action='store_true',help='操作员已确认两点属于同一根真实纱线')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'outputs')
    args=parser.parse_args()
    vals=[float(t) for t in args.points.split(',')]
    if len(vals)!=4:parser.error('--points 需要 4 个数 x1,y1,x2,y2')
    result,visuals=analyze(args.image.read_bytes(),reference_points=[vals[:2],vals[2:]],confirm_reference=args.confirm)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'v5_result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    (args.output_dir/'v5_three_panel.jpg').write_bytes(base64.b64decode(visuals['three_panel'].partition(',')[2]))
    print('Done:',args.output_dir)
    print('V4 rotation:',result['manual_yarn_reference']['v4_adapter_rotation_deg'])

if __name__=='__main__':main()
