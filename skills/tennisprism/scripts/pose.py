#!/usr/bin/env python3
"""Optional real pose inference. Never supplies a score or guessed skeleton."""
from pathlib import Path
import argparse
import json
import sys
import time
import uuid

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    infer=sub.add_parser('infer');infer.add_argument('--workspace',required=True);infer.add_argument('--run',required=True);infer.add_argument('--model',required=True);infer.add_argument('--roi',type=float,nargs=4,required=True,metavar=('LEFT','TOP','RIGHT','BOTTOM'))
    approve=sub.add_parser('approve');approve.add_argument('--workspace',required=True);approve.add_argument('--run',required=True);approve.add_argument('--candidate',required=True)
    args=p.parse_args()
    from tennis_runtime.store import Store
    from tennis_runtime.h5 import sha
    from coach import workspace
    store=Store(workspace(args.workspace));r=store.get('runs',args.run);folder=store.path('runs',r['id']);v=store.get('videos',r['video_id']);preview=store.path('videos',v['id'])/'media/preview.mp4'
    if args.command=='approve':
        candidate=Path(args.candidate).resolve();data=json.loads(candidate.read_text(encoding='utf-8'))
        if not candidate.is_relative_to((folder/'pose-candidates').resolve()) or not (candidate.parent/'review.jpg').exists():raise ValueError('Review this run’s generated candidate and contact sheet first')
        if data['preview_sha256']!=sha(preview) or data['target']!=r['target']:raise ValueError('Pose identity does not match this run')
        data['reviewed']=True;data['review_method']='Host Agent visually reviewed contact sheet; not an accuracy benchmark'
        with (folder/'pose.json').open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False)
        print(json.dumps({'pose':str(folder/'pose.json'),'reviewed':True}));return
    x0,y0,x1,y1=args.roi
    if not all(0<=x<=1 for x in args.roi) or x1<=x0 or y1<=y0:raise ValueError('ROI must be normalized left top right bottom within 0..1')
    import av
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    from PIL import Image,ImageDraw,ImageFont
    model=Path(args.model).expanduser().resolve(strict=True)
    options=vision.PoseLandmarkerOptions(base_options=python.BaseOptions(model_asset_path=str(model),delegate=python.BaseOptions.Delegate.CPU),running_mode=vision.RunningMode.VIDEO,num_poses=1,min_pose_detection_confidence=.5,min_pose_presence_confidence=.5,min_tracking_confidence=.5)
    anchors=[e['timestamp'] for group in ('strengths','priorities') for f in (r.get('report') or {}).get(group,[]) for e in f['evidence']]
    duration=v['metadata']['duration'];windows=[(0,duration)] if duration<=120 else [(max(0,t-2),min(duration,t+2)) for t in anchors]
    if not windows:raise ValueError('Long videos require a completed report with evidence windows before pose inference')
    unique_anchors=sorted(set(anchors))
    chosen=[unique_anchors[round(i*(len(unique_anchors)-1)/3)] for i in range(4)] if len(unique_anchors)>4 else unique_anchors
    review_times=sorted(set([0,*chosen,max(0,duration-.1)])) if duration<=120 and chosen else ([max(0,duration-.1)*i/5 for i in range(6)] if duration<=120 else chosen)
    samples=[];rows=[];started=time.monotonic();last_ms=-1;review_index=0
    with av.open(str(preview)) as c,vision.PoseLandmarker.create_from_options(options) as landmarker:
        stream=c.streams.video[0];origin=float(stream.start_time*stream.time_base) if stream.start_time else 0
        W,H=stream.codec_context.width,stream.codec_context.height
        roi=(int(x0*W),int(y0*H),int(x1*W),int(y1*H));a,b,d,e=roi
        for i,frame in enumerate(c.decode(stream)):
            if frame.pts is None:raise ValueError('Preview frame has no timestamp')
            t=float(frame.pts*frame.time_base)-origin;row={'index':i,'time':t,'landmarks':None}
            if any(start<=t<=end for start,end in windows):
                rgb=frame.to_ndarray(format='rgb24');crop=np.ascontiguousarray(rgb[b:e,a:d]);ms=max(last_ms+1,round(t*1000));last_ms=ms
                prediction=landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,data=crop),ms)
                if prediction.pose_landmarks:
                    pts=[[q.x*(d-a)+a,q.y*(e-b)+b,q.visibility,q.presence] for q in prediction.pose_landmarks[0]]
                    good=lambda q:q[2]>=.65 and q[3]>=.65 and 0<=q[0]<=W and 0<=q[1]<=H
                    if sum(good(q) for q in pts)>10 and all(good(pts[j]) for j in [11,12,23,24]):row['landmarks']=pts
                if review_index<len(review_times) and t>=review_times[review_index]:
                    samples.append((t,Image.fromarray(rgb),row['landmarks']))
                    while review_index<len(review_times) and t>=review_times[review_index]:review_index+=1
            rows.append(row)
    out=folder/'pose-candidates'/uuid.uuid4().hex[:12];out.mkdir(parents=True)
    data={'model':'MediaPipe Pose Landmarker','version':mp.__version__,'model_sha256':sha(model),'preview_sha256':sha(preview),'target':r['target'],'roi':list(roi),'windows':windows,'frames':rows,'detected_frames':sum(bool(f['landmarks']) for f in rows),'elapsed_seconds':round(time.monotonic()-started,3),'reviewed':False,'notes':['Agent-selected ROI; visual identity review is required.','Only real predictions; visibility AND presence >=0.65; no gap interpolation.','For videos over 120 seconds, inference covers only cited evidence windows.','Detection coverage is not pose accuracy. No automatic rating or joint-angle diagnosis.']}
    (out/'pose.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    sheet=Image.new('RGB',(960,3*300),'#193023');draw=ImageDraw.Draw(sheet);lines=[(11,12),(11,13),(13,15),(12,14),(14,16),(11,23),(12,24),(23,24),(23,25),(25,27),(24,26),(26,28)]
    for n,(t,picture,pts) in enumerate(samples):
        painter=ImageDraw.Draw(picture)
        if pts:
            for j,k in lines:
                if min(pts[j][2:])>=.65 and min(pts[k][2:])>=.65:painter.line((pts[j][0],pts[j][1],pts[k][0],pts[k][1]),fill='#d2ff72',width=3)
        picture.thumbnail((480,270));xx=(n%2)*480;yy=(n//2)*300;sheet.paste(picture,(xx,yy));draw.text((xx+10,yy+275),f'{t:.3f}s | actual model prediction',font=ImageFont.load_default(size=15),fill='white')
    sheet.save(out/'review.jpg')
    print(json.dumps({'candidate':str(out/'pose.json'),'review_image':str(out/'review.jpg'),'detected_frames':data['detected_frames'],'total_frames':len(rows),'reviewed':False},ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception as exc:print(json.dumps({'error':str(exc)},ensure_ascii=False));sys.exit(1)
