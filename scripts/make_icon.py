"""Draw the application icon with vector-like primitives for the Windows build."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.build-deps'))
from PIL import Image, ImageDraw

image = Image.new('RGBA',(256,256),(0,0,0,0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((0,0,255,255),radius=72,fill='#164d40')
color = '#d4f583'
for points in [[(68,100),(184,100)],[(148,64),(184,100),(148,136)],[(188,160),(72,160)],[(108,124),(72,160),(108,196)]]:
    draw.line(points,fill=color,width=18,joint='curve')
    for x,y in (points[0],points[-1]):
        draw.ellipse((x-9,y-9,x+9,y+9),fill=color)
(ROOT/'assets').mkdir(exist_ok=True)
image.save(ROOT/'assets'/'icon.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])

