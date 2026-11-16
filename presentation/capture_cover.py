from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,math
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent
import argparse
parser=argparse.ArgumentParser(description='Refresh the high-resolution MODIS LST cover without changing scientific figures.')
parser.add_argument('--base-url',default='https://earth-atlas.tail969737.ts.net')
args=parser.parse_args()
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 page=b.new_page(viewport={'width':1600,'height':1100},device_scale_factor=2,reduced_motion='reduce')
 page.goto(args.base_url.rstrip('/')+'/?lang=en',wait_until='domcontentloaded',timeout=60000)
 page.wait_for_function("typeof G !== 'undefined' && G.map && G.map.isStyleLoaded()",timeout=90000)
 if page.locator('#gVar').input_value() != 'lst_day': page.locator('#gVar').select_option('lst_day')
 page.wait_for_function("G.var==='lst_day' && G.monthly && G.map.isStyleLoaded()",timeout=90000)
 page.add_style_tag(content='#globe > :not(#globeMap),.atlas-tour-welcome,.maplibregl-control-container{visibility:hidden!important}')
 box=page.locator('#globeMap').bounding_box();side=math.floor(min(box['width'],box['height'])-24)
 page.evaluate("side=>{G.spin=false;G.map.jumpTo({center:[20,15],zoom:Math.log2(side*.91*Math.PI/512),padding:{top:0,bottom:0,left:0,right:0}});}",side)
 page.wait_for_timeout(5000)
 page.wait_for_function('G.map.areTilesLoaded()',timeout=90000)
 state=page.evaluate('({variable:G.var,monthly:G.monthly,year:G.year,month:G.imgMonth,imagery:G.imagery,center:G.map.getCenter(),zoom:G.map.getZoom()})')
 page.screenshot(path=str(root/'assets/globe-cover.png'),clip={'x':box['x']+(box['width']-side)/2,'y':box['y']+(box['height']-side)/2,'width':side,'height':side})
 b.close()
from PIL import Image,ImageDraw,ImageChops
cover=Image.open(root/'assets/globe-cover.png').convert('RGB');W,H=cover.size
probe=cover.copy();ImageDraw.Draw(probe).rectangle([int(W*.75),int(H*.94),W,H],fill=(0,0,0))
x0,y0,x1,y1=probe.convert('L').point(lambda v:255 if v*3>60 else 0).getbbox()
cx,cy,r=(x0+x1)/2,(y0+y1)/2,(x1-x0+y1-y0)/4-2;k=4
mask=Image.new('L',(W*k,H*k),0);ImageDraw.Draw(mask).ellipse([(cx-r)*k,(cy-r)*k,(cx+r)*k,(cy+r)*k],fill=255)
cover.putalpha(mask.resize((W,H),Image.LANCZOS));cover.save(root/'assets/globe-cover.png',optimize=True)
record=json.loads((root/'capture-validation.json').read_text())
record['assets_sha256']['globe-cover.png']=hashlib.sha256((root/'assets/globe-cover.png').read_bytes()).hexdigest()
record['cover_refresh']={'captured_at':datetime.now(ZoneInfo('Europe/Warsaw')).isoformat(timespec='seconds'),'base_url':args.base_url,'state':state,'device_scale_factor':2,'note':'Read-only capture of the actual map; controls hidden and camera framed for the cover; background cut out to a transparent circle so the globe sits on the slide colour. Scientific evidence and other figures unchanged.'}
(root/'capture-validation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(state),flush=True)
