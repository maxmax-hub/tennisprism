'use strict';
(()=>{
const D=window.TENNIS_REPORT,R=D.report,P=D.pose,$=id=>document.getElementById(id),v=$('video'),W=D.video.width,H=D.video.height,stamps=D.timestamps;
const ctx=$('overlay').getContext('2d'),zc=$('zoom-canvas'),zx=zc.getContext('2d');$('overlay').width=W;$('overlay').height=H;document.querySelector('.video-stage').style.aspectRatio=W+'/'+H;
let selected=D.events[0]||null,loop=false,pending=null;const confidence={low:'低',medium:'中',high:'高'},kind={observed:'本次重点',potential:'先验证',development:'可选拓展'},roles={focus:'本次重点',trial:'先验证',optional:'可选拓展'};
const roleOf=p=>p.selection?.role||({observed:'focus',potential:'trial',development:'optional'}[p.kind]);
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function time(t){return String(Math.floor(t/60)).padStart(2,'0')+':'+(t%60).toFixed(3).padStart(6,'0');}
function nearest(t){let l=0,r=stamps.length-1;while(l<r){const m=(l+r)>>1;if(stamps[m]<t)l=m+1;else r=m;}return l&&Math.abs(stamps[l-1]-t)<Math.abs(stamps[l]-t)?l-1:l;}
function seek(t){v.pause();pending=nearest(t);v.currentTime=Math.min(D.video.duration-.001,stamps[pending]+.002);render(stamps[pending]);}
function choose(e,scroll=false){selected=e;loop=false;$('loop').textContent='循环看这一段';$('moment-title').textContent=e.title;$('moment-caption').textContent=e.observation;$('moment-time').textContent=time(e.time)+' · '+e.frame_id;seek(e.time);document.querySelectorAll('[data-event]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.event===e.id)));if(scroll)$('review').scrollIntoView({behavior:'smooth',block:'start'});}
const lines=[[11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],[23,24],[23,25],[25,27],[24,26],[26,28],[27,29],[29,31],[28,30],[30,32]];
const valid=p=>p&&p[2]>=.65&&p[3]>=.65&&p[0]>=0&&p[0]<=W&&p[1]>=0&&p[1]<=H;
function draw(context,pts,tx=0,ty=0,s=1){context.save();context.lineWidth=2.5;context.strokeStyle='#d3ff84';context.fillStyle='#edffd8';context.lineCap='round';for(const [a,b] of lines){if(!valid(pts[a])||!valid(pts[b]))continue;context.beginPath();context.moveTo((pts[a][0]-tx)*s,(pts[a][1]-ty)*s);context.lineTo((pts[b][0]-tx)*s,(pts[b][1]-ty)*s);context.stroke();}for(let n=11;n<33;n++){if(!valid(pts[n]))continue;context.beginPath();context.arc((pts[n][0]-tx)*s,(pts[n][1]-ty)*s,2.5,0,Math.PI*2);context.fill();}context.restore();}
function render(t){const i=nearest(t),row=P.frames[i],pts=row&&Math.abs(row.time-t)<.075?row.landmarks:null;$('clock').textContent=time(Math.min(t,D.video.duration));$('frame-label').textContent='预览第 '+(i+1)+' / '+stamps.length+' 帧';ctx.clearRect(0,0,W,H);if($('skeleton').checked&&pts)draw(ctx,pts);$('zoom-box').hidden=!$('zoom').checked;if($('zoom').checked&&v.readyState>=2){const points=(pts||[]).filter(valid);if(points.length>10){const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);const h=Math.min(H,W*.75,Math.max(H*.3,(maxy-miny)*1.3,(maxx-minx)*.95)),w=h*4/3,x=Math.max(0,Math.min(W-w,(minx+maxx-w)/2)),y=Math.max(0,Math.min(H-h,(miny+maxy-h)/2));zx.drawImage(v,x,y,w,h,0,0,320,240);if($('skeleton').checked)draw(zx,pts,x,y,320/w);}else{zx.fillStyle='#2e4e3d';zx.fillRect(0,0,320,240);zx.fillStyle='#cbd7be';zx.font='14px sans-serif';zx.textAlign='center';zx.fillText('本帧没有可靠人体位置',160,120);}}if(loop&&selected&&!v.paused&&t>=Math.min(D.video.duration,selected.time+1.3))v.currentTime=Math.max(0,selected.time-1.3);}
$('subtitle').textContent=D.video.filename+' · '+R.player.description;$('player').textContent=R.player.description;$('rating').textContent=Number(R.assessment.rating).toFixed(1);$('rating-confidence').textContent='等级置信度 · '+confidence[R.assessment.confidence];$('summary').textContent=R.summary;$('basis').textContent=R.assessment.basis;R.assessment.not_observed.forEach(s=>$('not-observed').append(node('li',s)));R.limitations.forEach(s=>$('limits').append(node('li',s)));
const hasPose=P.reviewed&&P.frames.some(f=>f.landmarks);for(const id of ['skeleton','zoom']){$(id).disabled=!hasPose;$(id).checked=!!hasPose;$(id).addEventListener('change',()=>render(v.currentTime));}$('pose-note').textContent=hasPose?'真实本地姿态预测 · 低可见节点隐藏 · 遮挡不补画。姿态可在文字报告完成后生成，仅作回看辅助。':'未运行或未通过复核的姿态不显示骨架；逐帧回看仍可使用。';$('provenance').textContent=(P.notes||[]).join(' ')+' '+(D.provenance.model||'当前 Agent 基于真实画面撰写。');
D.events.forEach(e=>{const b=node('button',undefined,'keyframe');b.dataset.event=e.id;const img=node('img');img.src=e.image;img.alt=e.title+' '+time(e.time);b.append(img,node('small',time(e.time)),node('strong',e.title));b.addEventListener('click',()=>choose(e));$('keyframes').append(b);const f=node('button',undefined,'finding');f.append(node('strong',e.title),node('p',e.interpretation),node('small',(roles[e.role]||kind[e.kind]||'已有基础')+' · 判断置信度'+confidence[e.confidence]));f.addEventListener('click',()=>choose(e,true));$('findings').append(f);});
function evidenceLinks(refs,title){
  const links=node('div',undefined,'evidence-links');
  refs.forEach(ref=>{const b=node('button','↗ 回看 '+time(ref.timestamp),'text-button');b.addEventListener('click',()=>choose({id:'ref',time:ref.timestamp,frame_id:ref.frame_id,title,observation:ref.description},true));links.append(b);});
  return links;
}
function trainingCard(p){
  const d=p.drill,s=p.selection,card=node('article',undefined,'drill-card'+(roleOf(p)==='trial'?' potential':''));
  card.append(node('h3',d.title),node('p',s?s.why_this_player:p.interpretation));
  card.append(evidenceLinks(p.evidence,p.title));
  if(s){
    card.append(node('p','适用来球：'+s.situation),node('p','继续保留：'+s.preserve));
    const basis=node('details',undefined,'report-details');
    basis.append(node('summary','为什么给我这项建议'),node('p','观察：'+p.observation),node('p','解释：'+p.interpretation),node('p','其他解释：'+p.alternative));
    for(const [key,label] of [['comparison','对照与反例'],['outcome','回球或后续影响']]){
      basis.append(node('h4',label),node('p',s[key].note),evidenceLinks(s[key].evidence,p.title+' · '+label));
    }
    basis.append(node('small','判断置信度：'+confidence[p.confidence],'small-note'));card.append(basis);
  }else if(p.kind==='potential'){
    const note=node('div',undefined,'hypothesis');note.append(node('strong','潜在问题备注'),node('p','直接观察：'+p.observation),node('p','其他解释：'+p.alternative));card.append(note);
  }
  if(d.test_variable)card.append(node('p','本次只检验：'+d.test_variable,'setup'));
  card.append(node('p','准备：'+d.setup,'setup'),node('small','建议安排：'+d.duration,'small-note'));
  const ol=node('ol');d.steps.forEach(step=>ol.append(node('li',step)));card.append(ol,node('blockquote',d.cue));
  const measure=node('div',undefined,'measure');measure.append(node('strong','练完怎么判断'),node('p',d.success_criterion),node('p','有帮助时：'+d.supports),node('p','没有帮助时：'+d.against));card.append(measure);
  const details=node('details',undefined,'report-details');details.append(node('summary','难度调整与方法出处'),node('p','简单一点：'+d.easier),node('p','进阶：'+d.harder),node('p',d.source_kind==='authored'?'本报告设计的练习，未验证个人训练效果。':'参考练习；根据本次视频调整。'));
  d.sources.forEach(source=>{const a=node('a',source.title+' ↗');a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';details.append(a);});details.append(node('p',d.adaptation));card.append(details);
  return card;
}
const trainingGroups=['focus','trial','optional'].map(role=>({role,items:R.priorities.filter(p=>roleOf(p)===role)}));
const hasFocus=trainingGroups[0].items.length>0,hasTrial=trainingGroups[1].items.length>0;
$('training-intro').textContent=hasFocus?'先练已反复出现并影响击球的重点，再用录像复查。':hasTrial?'本片尚未确认需要优先纠正的短板。先用下面的练习检验一个具体问题。':'本片没有足够依据选出个人纠正重点，先保留已有动作。';
trainingGroups.forEach(({role,items})=>{
  if(!items.length)return;
  const group=node(role==='optional'?'details':'section',undefined,'training-group');group.dataset.role=role;
  group.append(node(role==='optional'?'summary':'h3',roles[role]));items.forEach(p=>group.append(trainingCard(p)));$('drills').append(group);
});
for(const finding of R.strengths.concat(R.priorities)){
  const row=node('div',undefined,'evidence-row');row.append(node('h4',finding.title),node('p','观察：'+finding.observation),node('p','判断：'+finding.interpretation));
  const refs=[...finding.evidence,...(finding.selection?.comparison.evidence||[]),...(finding.selection?.outcome.evidence||[])];
  refs.forEach(ref=>row.append(node('p',ref.frame_id+' · '+time(ref.timestamp)+' · '+ref.description,'small-note')));$('evidence-list').append(row);
}
function step(delta){loop=false;const i=pending===null?nearest(v.currentTime):pending;seek(stamps[Math.max(0,Math.min(stamps.length-1,i+delta))]);}
function showShotData(){
  const data=D.shots;if(!data||!Array.isArray(data.shots)||!data.summary)return;
  const shots=data.shots,summary=data.summary;
  const labels={
    stroke:{forehand:'正手',backhand:'反手',serve:'发球',volley:'截击',overhead:'高压',unknown:'动作未判定'},
    contact_height:{below_hip:'髋部以下',hip_to_shoulder:'髋部至肩部',above_shoulder:'肩部以上',unknown:'高度未判定'},
    incoming_depth:{short:'浅来球',mid:'中等深度来球',deep:'深来球',unknown:'来球深度未判定'},
    outgoing_depth:{short:'回球浅区',mid:'回球中区',deep:'回球深区',unknown:'回球深度未判定'},
    split_step:{observed:'看到分腿垫步',not_observed:'完整窗口内未见',unknown:'分腿垫步未判定'}
  };
  const titles={contact_height:'击球高度',incoming_depth:'来球深度',outgoing_depth:'回球深度',split_step:'分腿垫步'};
  const metricKeys=['preparation_to_contact_s','contact_to_recovery_s','wrist_height_torso_2d','stance_shoulder_ratio_2d','elbow_angle_2d_deg'];
  const metricNames={preparation_to_contact_s:'准备至触球',contact_to_recovery_s:'触球至回位',wrist_height_torso_2d:'手腕高度 / 躯干垂直跨度（2D）',stance_shoulder_ratio_2d:'脚踝间距 / 肩宽（2D）',elbow_angle_2d_deg:'肘部投影角（2D）'};
  const displayValue=(key,value)=>Number.isFinite(value)?(key==='elbow_angle_2d_deg'?value.toFixed(1)+'°':value.toFixed(2)+(key.endsWith('_s')?' 秒':'')):'未计算';
  const known=(field,value)=>labels[field][value]||labels[field].unknown;
  $('shot-analysis').hidden=false;
  $('shot-scope').textContent='共记录 '+summary.shot_count+' 个抽样击球；以下统计只覆盖这些记录，不代表整场。击球高度按身体部位分档。';
  for(const [value,label] of Object.entries(labels.stroke)){
    const count=summary.stroke_counts[value];if(count>0)$('stroke-counts').append(node('span',label+' '+count,'stroke-count'));
  }
  for(const [field,title] of Object.entries(titles)){
    const stat=summary[field];if(!stat)continue;
    const card=node('article',undefined,'shot-distribution');
    card.append(node('h3',title),node('p','可判定 '+stat.valid+' / '+stat.total+' 拍','sample-count'));
    if(!stat.valid)card.append(node('p','暂无可判定样本','metric-empty'));
    else for(const [value,label] of Object.entries(labels[field])){
      const count=stat.counts[value];if(value==='unknown'||!count)continue;
      const row=node('div',undefined,'distribution-row'),bar=node('div',undefined,'distribution-bar'),fill=node('span');
      fill.style.width=(100*count/stat.valid)+'%';bar.setAttribute('aria-hidden','true');bar.append(fill);
      row.append(node('span',label),node('strong',count+' 拍'),bar);card.append(row);
    }
    $('shot-distributions').append(card);
    $('shot-methods').append(node('p',title+'：可判定 '+stat.valid+' / '+stat.total+' 拍；推测 '+stat.estimated+' 拍，未判定 '+stat.unknown+' 拍。推测与未判定不计入可判定分布。'));
  }
  for(const key of metricKeys){
    const stat=(summary.metrics||{})[key],definition=(data.metric_definitions||{})[key];
    if(stat&&stat.valid>0&&Number.isFinite(stat.median)){
      const card=node('article',undefined,'shot-metric');card.append(node('h4',metricNames[key]),node('strong',displayValue(key,stat.median)),node('p','有效 '+stat.valid+' / '+stat.total+' 拍','sample-count'));
      if(stat.valid>1)card.append(node('small','范围 '+displayValue(key,stat.min)+' — '+displayValue(key,stat.max)));
      $('shot-metric-cards').append(card);$('shot-measurements').hidden=false;
    }
    if(definition)$('shot-methods').append(node('p',metricNames[key]+'：'+definition.description+(stat?' 有效 '+stat.valid+' / '+stat.total+' 拍，未计算 '+stat.unknown+' 拍。':'')));
  }
  (data.notes||[]).forEach(note=>$('shot-methods').append(node('p',note)));
  const filters={stroke:'all',incoming_depth:'all',outgoing_depth:'all'};
  for(const [field,label] of [['stroke','动作'],['incoming_depth','来球'],['outgoing_depth','回球']]){
    const wrapper=node('label',label),select=node('select');select.setAttribute('aria-label','筛选逐拍记录：'+label);select.dataset.shotFilter=field;
    const all=node('option','全部');all.value='all';select.append(all);
    for(const [value,text] of Object.entries(labels[field]))if(shots.some(shot=>shot[field]===value)){const option=node('option',text);option.value=value;select.append(option);}
    select.addEventListener('change',()=>{filters[field]=select.value;renderRecords();});wrapper.append(select);$('shot-filters').append(wrapper);
  }
  function renderRecords(){
    const visible=shots.filter(shot=>Object.entries(filters).every(([field,value])=>value==='all'||shot[field]===value));
    $('shot-filter-count').textContent='显示 '+visible.length+' / '+shots.length+' 条记录 · 筛选仅影响下方回看列表。';$('shot-list').replaceChildren();
    if(!visible.length){$('shot-list').append(node('p','没有同时符合这些条件的已记录击球。','metric-empty'));return;}
    for(const shot of visible){
      const row=node('article',undefined,'shot-record'),heading=node('div',undefined,'shot-record-heading'),button=node('button','↗ '+time(shot.time),'text-button');
      button.setAttribute('aria-label','回看 '+known('stroke',shot.stroke)+' '+time(shot.time));
      button.addEventListener('click',()=>{choose({id:'shot-'+shot.id,time:shot.time,frame_id:shot.phases.contact||shot.evidence[0].frame_id,title:known('stroke',shot.stroke),observation:shot.note},true);$('loop').disabled=false;});
      heading.append(node('strong',known('stroke',shot.stroke)),button);
      const height=known('contact_height',shot.contact_height)+(shot.contact_basis==='estimated'&&shot.contact_height!=='unknown'?'（推测）':'');
      row.append(heading,node('p',[height,known('incoming_depth',shot.incoming_depth),known('outgoing_depth',shot.outgoing_depth)].join(' · '),'shot-record-context'),node('p',shot.note));
      const details=node('details',undefined,'shot-record-details');details.append(node('summary','查看依据与单拍数据'));
      details.append(node('p','判断置信度：'+confidence[shot.confidence]+' · '+({visible:'触球可见',estimated:'触球为推测时刻',unknown:'触球未确认'}[shot.contact_basis])+' · '+known('split_step',shot.split_step)));
      const metrics=node('dl',undefined,'shot-values');
      for(const key of metricKeys)if(Number.isFinite((shot.metrics||{})[key]))metrics.append(node('dt',metricNames[key]),node('dd',displayValue(key,shot.metrics[key])));
      if(metrics.children.length)details.append(metrics);
      else details.append(node('p','本拍没有满足计算条件的数值。','small-note'));
      shot.evidence.forEach(ref=>{const evidenceButton=node('button',ref.frame_id+' · '+time(ref.timestamp)+' · '+ref.description,'shot-evidence-link');evidenceButton.addEventListener('click',()=>{choose({id:'shot-ref',time:ref.timestamp,frame_id:ref.frame_id,title:known('stroke',shot.stroke)+' · 画面依据',observation:ref.description},true);$('loop').disabled=false;});details.append(evidenceButton);});
      row.append(details);$('shot-list').append(row);
    }
  }
  renderRecords();
}
showShotData();
$('prev').addEventListener('click',()=>step(-1));$('next').addEventListener('click',()=>step(1));$('speed').addEventListener('change',e=>v.playbackRate=Number(e.target.value));$('loop').disabled=!selected;$('loop').addEventListener('click',()=>{loop=!loop;$('loop').textContent=loop?'停止循环':'循环看这一段';if(loop){seek(Math.max(0,selected.time-1.3));v.play().catch(()=>{});}else v.pause();});v.addEventListener('seeked',()=>{pending=null;render(v.currentTime);});v.addEventListener('loadeddata',()=>selected?choose(selected):render(0));v.addEventListener('timeupdate',()=>{if(!v.requestVideoFrameCallback)render(v.currentTime);});if(v.requestVideoFrameCallback){const cb=(_,m)=>{render(m.mediaTime);v.requestVideoFrameCallback(cb);};v.requestVideoFrameCallback(cb);}if(v.readyState>=2){if(selected)choose(selected);else render(0);}render(0);
})();
