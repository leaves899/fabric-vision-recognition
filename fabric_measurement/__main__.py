"""Command-line entry with the same validated input contract as the web app."""
import argparse
from datetime import datetime
import json
from pathlib import Path

from .service import AnalysisOptions, execute, summary


def main():
    parser = argparse.ArgumentParser(description='织物图像识别：报告技术路线')
    parser.add_argument('--reflection', required=True, type=Path)
    parser.add_argument('--transmission', type=Path)
    parser.add_argument('--options', type=Path, help='AnalysisOptions JSON; mm_per_px refers to the final ROI')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    options = AnalysisOptions.model_validate_json(args.options.read_text(encoding='utf-8-sig')) if args.options else AnalysisOptions()
    output = args.output or Path('experiments') / ('report-system-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    result = execute(args.reflection.read_bytes(), args.transmission.read_bytes() if args.transmission else None,
                     options, output, names=[p.name for p in (args.reflection, args.transmission) if p])
    print(json.dumps(summary(result), ensure_ascii=False, indent=2, allow_nan=False))
    print('Review:', (output / 'review.html').resolve())


if __name__ == '__main__':
    main()
