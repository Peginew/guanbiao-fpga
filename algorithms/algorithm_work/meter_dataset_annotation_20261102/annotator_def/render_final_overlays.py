"""Render annotation QA copies; source PNG bytes are never written."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

HERE=Path(__file__).resolve().parent
data=json.loads((HERE/'annotation.json').read_text(encoding='utf-8'))
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20)
for group in 'DEF':
    rows=[r for r in data['records'] if r['session_id']==group]
    for page in range(3):
        canvas=Image.new('RGB',(1600,1400),'#dddddd')
        draw=ImageDraw.Draw(canvas)
        for index,row in enumerate(rows[page*20:(page+1)*20]):
            im=Image.open(row['path']).convert('RGB')
            ink=ImageDraw.Draw(im)
            box=row['bbox_native_xyxy']
            if box:ink.rectangle(box,outline=(30,220,80),width=3)
            for name,color in [('hub','red'),('thin_terminal','blue')]:
                pt=row['keypoints'][name]
                if pt['xy'] is not None:
                    x,y=pt['xy'];ink.ellipse((x-4,y-4,x+4,y+4),outline=color,width=2)
            if box:
                patch=im.crop((max(0,box[0]-12),max(0,box[1]-12),min(1280,box[2]+12),min(720,box[3]+12)))
            else:patch=im
            patch.thumbnail((310,310))
            x=index%5*320;y=index//5*350
            canvas.paste(patch,(x,y+25))
            draw.text((x+3,y),f'{row["id"]} H={row["keypoints"]["hub"]["visibility"][:1]} N={row["keypoints"]["thin_terminal"]["visibility"][:1]}',fill='black',font=font)
        canvas.save(HERE/f'{group}_final_overlay_{page+1}.jpg',quality=95)
print('Final 9 overlay pages rendered')
