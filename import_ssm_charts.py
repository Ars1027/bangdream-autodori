"""Import extracted BanG BMS charts from a local SSM GUI release."""

import argparse
from collections import Counter
from pathlib import Path
import shutil


DEFAULT_DESTINATION = Path(__file__).resolve().parent / "data" / "ssm" / "charts"


def import_charts(source, destination=DEFAULT_DESTINATION):
    source = Path(source).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    candidates = (source / "assets/star/forassetbundle/startapp/musicscore", source)
    for chart_root in candidates:
        charts = sorted(chart_root.glob("musicscore*/*/*.txt"))
        if charts:
            break
    else:
        raise FileNotFoundError("没有找到 SSM GUI 已解包的 BanG BMS 谱面: %s" % source)

    imported = []
    for chart in charts:
        target = destination / chart.relative_to(chart_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(chart, target)
        imported.append(target)
    return imported


def main():
    parser = argparse.ArgumentParser(description="导入 SSM GUI release 中已保存的 BanG BMS 谱面")
    parser.add_argument("source", type=Path, help="SSM GUI release 目录，或其 musicscore 目录")
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    imported = import_charts(args.source, args.destination)
    difficulties = Counter(path.stem.rsplit("_", 1)[-1] for path in imported)
    songs = len({path.parent.name for path in imported})
    print("已导入 %s 首歌、%s 张 BMS 谱面到 %s" % (songs, len(imported), args.destination))
    print("难度: " + ", ".join("%s=%s" % item for item in sorted(difficulties.items())))


if __name__ == "__main__":
    main()
