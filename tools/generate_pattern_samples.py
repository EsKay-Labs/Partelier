"""Regenerate local SVG samples from the same polygon planner as the add-in."""

from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Partelier.partelier.tools.patterns.settings import PatternSettings
from Partelier.partelier.tools.patterns.planner import build_layout
from Partelier.partelier.tools.patterns.tiles import TILED_PATTERNS


def generate():
    folder=ROOT/'Partelier/partelier/ui/pattern-previews'
    folder.mkdir(parents=True,exist_ok=True)
    for name in TILED_PATTERNS:
        settings=PatternSettings(pattern=name,layout_mode='fill',pitch_mm=13.5,web_mm=1.5,border_mm=3)
        layout=build_layout(settings,(0,120,0,80))
        paths=[]
        for cell in layout.cells:
            points=[(cell.center_mm[0]+x,cell.center_mm[1]+y) for x,y in cell.polygon_mm]
            paths.append('<path d="M'+'L'.join(f'{x:.5f},{y:.5f}' for x,y in points)+'Z"/>')
        svg=(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 122 82" role="img" aria-label="{name} polygon sample">'
             '<rect width="120" height="80" rx="2" fill="#8aafe0" stroke="#365f98" stroke-width=".5"/>'
             '<g fill="#f6f9fe" stroke="#416a9f" stroke-width=".2" stroke-linejoin="round">'
             +''.join(paths)+'</g></svg>\n')
        (folder/(name+'.svg')).write_text(svg,encoding='utf-8',newline='\n')
    print(f'Generated {len(TILED_PATTERNS)} polygon samples from real planner coordinates.')


if __name__=='__main__':generate()
