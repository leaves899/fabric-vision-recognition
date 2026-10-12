const $=(s)=>document.querySelector(s);
let currentFile=null,photo=new Image(),cornerPoints=[],referencePoints=[],clickMode='reference',analysis=null,visuals=null;
const canvas=$('#sourceCanvas'),ctx=canvas.getContext('2d');
const STATUS={CONFIRMED:['已人工确认','confirmed'],ESTIMATED:['视觉估计','estimated'],NEEDS_CONFIRMATION:['待核验','needs'],UNAVAILABLE:['数据不足','unavailable']};
const notes={roi:'已选 ROI。没有四角时仅分析照片中的视觉特征，不附带 5 cm 标定。',direction:'红色与绿色是冻结 V4 实际输出的纱线候选轨迹，仍需人工核验，不是 FFT / Gabor 方向参考网格。',transects:'红绿轨迹来自冻结 V4；白色截线统计与候选轨迹的交点，不能直接当作真实经纬密度。'};
const esc=(s)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function setMessage(txt,cls=''){$('#message').textContent=txt;$('#message').className='message '+cls;}
function referenceAxis(p,q){return (Math.atan2(q[1]-p[1],q[0]-p[0])*180/Math.PI+180)%180;}
function updateReady(){
  $('#analyzeButton').disabled=!currentFile||referencePoints.length!==2||!$('#confirmReference').checked;
}
function invalidateResults(){
  analysis=null;visuals=null;$('#resultSection').hidden=true;
  $('#previewResults').hidden=true;$('#previewEmpty').hidden=false;
}
function chooseMode(mode){
  clickMode=mode;
  $('#modeReference').classList.toggle('active',mode==='reference');
  $('#modeCorners').classList.toggle('active',mode==='corners');
  $('#modeReference').setAttribute('aria-pressed',String(mode==='reference'));
  $('#modeCorners').setAttribute('aria-pressed',String(mode==='corners'));
  drawCanvas();
}
function drawCanvas(){
  if(!photo.complete||!photo.naturalWidth)return;
  canvas.width=photo.naturalWidth;canvas.height=photo.naturalHeight;
  ctx.drawImage(photo,0,0);
  const labelSize=Math.max(16,photo.naturalWidth/65);
  if(cornerPoints.length){
    ctx.lineWidth=Math.max(2,photo.naturalWidth/480);ctx.strokeStyle='#27bf9a';ctx.lineCap='round';
    if(cornerPoints.length>=2){ctx.beginPath();ctx.moveTo(...cornerPoints[0]);cornerPoints.slice(1).forEach(p=>ctx.lineTo(...p));if(cornerPoints.length===4)ctx.closePath();ctx.stroke();}
    cornerPoints.forEach(([x,y],i)=>{
      ctx.beginPath();ctx.arc(x,y,Math.max(5,photo.naturalWidth/200),0,Math.PI*2);ctx.fillStyle='#17ba91';ctx.fill();
      ctx.font=`bold ${labelSize}px sans-serif`;ctx.fillStyle='#fff';ctx.fillText(['TL','TR','BR','BL'][i],x+14,y-12);
    });
  }
  if(referencePoints.length){
    ctx.lineWidth=Math.max(3,photo.naturalWidth/420);
    ctx.strokeStyle='#ffb020';ctx.lineCap='round';
    if(referencePoints.length===2){
      ctx.beginPath();ctx.moveTo(...referencePoints[0]);ctx.lineTo(...referencePoints[1]);ctx.stroke();
    }
    referencePoints.forEach(([x,y],i)=>{
      const radius=Math.max(8,photo.naturalWidth/155);
      ctx.beginPath();ctx.arc(x,y,radius,0,Math.PI*2);ctx.fillStyle='#ffae22';ctx.fill();
      ctx.strokeStyle='#202d30';ctx.lineWidth=Math.max(2,photo.naturalWidth/860);ctx.stroke();
      ctx.font=`bold ${labelSize}px sans-serif`;ctx.fillStyle='#fff';ctx.fillText(`P${i+1}`,x+16,y-12);
    });
  }
  $('#cornerStatus').innerHTML=cornerPoints.length===4?'<span class="dot"></span>4 个内角已标记，请核对后确认':`<span class="dot muted"></span>${cornerPoints.length}/4 个标定点（TL → TR → BR → BL）`;
  let status='请在同一根真实纱线的可见段上点击两点（不是斜纹带）。';
  if(referencePoints.length===1) status='已选 P1，请在同一根真实纱线上选择 P2。';
  if(referencePoints.length===2){
    const a=referenceAxis(referencePoints[0],referencePoints[1]);
    const d=Math.hypot(referencePoints[1][0]-referencePoints[0][0],referencePoints[1][1]-referencePoints[0][1]);
    status=`已选 2 点；原图参考轴 ${a.toFixed(2)}° · 间距 ${d.toFixed(1)} px。请核验后勾选确认。`;
  }
  $('#referenceStatus').textContent=status;
  $('#referenceAngle').textContent=referencePoints.length===2?`${referenceAxis(...referencePoints).toFixed(2)}°（原图）`:'尚未取点';
  $('#canvasHint').textContent=clickMode==='reference'?
    (referencePoints.length===2?'已选 P1、P2；重新点击可重新开始两点取样':'模式①：在同一根真实可见纱段上点击 P1、P2'):
    (cornerPoints.length===4?'实体框四角取点完成，切回模式①可选纱线方向':'模式②：依次点击实体框内角 TL → TR → BR → BL');
  updateReady();
}
function loadFile(file){
  if(!file)return;if(file.size>16*1024*1024){setMessage('图片文件不能超过 16MB','error');return;}
  currentFile=file;cornerPoints=[];referencePoints=[];$('#confirmCorners').checked=false;$('#confirmReference').checked=false;invalidateResults();chooseMode('reference');
  const url=URL.createObjectURL(file);photo=new Image();photo.onload=()=>{drawCanvas();URL.revokeObjectURL(url);$('#imageMeta').textContent=`${photo.naturalWidth} × ${photo.naturalHeight} px`;
    updateReady();$('#dropZone strong').textContent=file.name;setMessage('照片已加载：请选择同一根真实纱线的 P1、P2 两点并人工确认；四角标定可选。','ok');};
  photo.onerror=()=>{setMessage('无法读取图片','error');URL.revokeObjectURL(url);};photo.src=url;
}
$('#dropZone').addEventListener('click',()=>$('#fileInput').click());$('#dropZone').addEventListener('keydown',e=>{if(e.key==='Enter')$('#fileInput').click()});
$('#fileInput').addEventListener('change',e=>loadFile(e.target.files[0]));
for(const ev of ['dragenter','dragover'])$('#dropZone').addEventListener(ev,e=>{e.preventDefault();$('#dropZone').classList.add('drag')});
for(const ev of ['dragleave','drop'])$('#dropZone').addEventListener(ev,e=>{e.preventDefault();$('#dropZone').classList.remove('drag')});
$('#dropZone').addEventListener('drop',e=>loadFile(e.dataTransfer.files[0]));
for(let [id,path,name] of [['framedSample','/samples/有标定框_示例.jpg','有标定框_示例.jpg'],['plainSample','/samples/无标定框_示例.jpg','无标定框_示例.jpg']]){
  $('#'+id).addEventListener('click',async()=>{setMessage('正在加载示例照片…');try{let blob=await(await fetch(path)).blob();loadFile(new File([blob],name,{type:'image/jpeg'}));}catch(err){setMessage(String(err),'error');}});
}
$('#modeReference').addEventListener('click',()=>chooseMode('reference'));
$('#modeCorners').addEventListener('click',()=>chooseMode('corners'));
canvas.addEventListener('click',e=>{
  if(!currentFile||!photo.naturalWidth)return;
  const rect=canvas.getBoundingClientRect();
  const x=Math.max(0,Math.min(photo.naturalWidth-1,Math.round((e.clientX-rect.left)*photo.naturalWidth/rect.width)));
  const y=Math.max(0,Math.min(photo.naturalHeight-1,Math.round((e.clientY-rect.top)*photo.naturalHeight/rect.height)));
  invalidateResults();
  if(clickMode==='reference'){
    if(referencePoints.length===2)referencePoints=[];
    referencePoints.push([x,y]);$('#confirmReference').checked=false;
  }else{
    if(cornerPoints.length===4)cornerPoints=[];
    cornerPoints.push([x,y]);$('#confirmCorners').checked=false;
  }
  drawCanvas();
});
$('#resetCorners').addEventListener('click',()=>{cornerPoints=[];$('#confirmCorners').checked=false;invalidateResults();drawCanvas();});
$('#resetReference').addEventListener('click',()=>{referencePoints=[];$('#confirmReference').checked=false;invalidateResults();drawCanvas();});
$('#confirmReference').addEventListener('change',()=>{invalidateResults();updateReady();});
$('#confirmCorners').addEventListener('change',()=>{invalidateResults();updateReady();});
function fmt(num,d=1){return typeof num==='number'&&isFinite(num)?num.toFixed(d):'—';}
function renderValue(p){let v=p.value;if(v==null)return '暂无可用结果';
  if(p.id===1||p.id===2)return `${fmt(v,1)}° <small style="font-size:11px;font-weight:500;color:#889d91">方向候选</small>`;
  if(p.id===3||p.id===4)return esc(v.pattern_candidate||'未判定')+`<small style="font-size:11px;font-weight:500;color:#879990"> · CV ${fmt(v.spacing_cv,2)}</small>`;
  if(p.id===5||p.id===6){let a=v.visible_width_proxy_px;if(a==null)return '待确认';let mm=v.visible_width_proxy_mm;return `${fmt(a,2)} px${mm!=null?` <small style="font-size:12px;color:#749382">≈ ${fmt(mm,3)} mm</small>`:''}`;}
  if(p.id===7)return esc(v);
  if(p.id===8||p.id===9){if(v.candidate_per_cm!=null)return `${fmt(v.candidate_per_cm,1)} <small style="font-size:12px;font-weight:500">候选峰/cm</small>`;return '— <small style="font-size:12px;font-weight:500;color:#9aa6a0">未标定根/cm</small>';}
  if(p.id===10)return `${esc(v.dominant_colors?.[0]?.hex||'—')} <small style="font-size:11px;color:#7f9588;font-weight:500">主色候选</small>`;
  return esc(JSON.stringify(v));
}
function renderResults(){if(!analysis)return;$('#resultSection').hidden=false;for(const mod of ['A','B','C','D']){$('#module'+mod).innerHTML='';}
  for(const p of analysis.parameters){const [statusLabel,statusClass]=STATUS[p.status]||['未知','unavailable'];let card=document.createElement('article');card.className='parameter-card';
    let extra=p.id===10?`<div class="swatches">${(p.value?.dominant_colors||[]).map(c=>`<div class="swatch" style="background:${esc(c.hex)}" title="${esc(c.hex)} · ${Math.round(c.ratio*100)}%"></div>`).join('')}</div>`:'';
    card.innerHTML=`<div class="param-top"><span class="param-id">PARAM ${String(p.id).padStart(2,'0')}</span><span class="status ${statusClass}">${statusLabel}</span></div><h4>${esc(p.name)}</h4><div class="param-value ${[3,4,7].includes(p.id)?'desc':''}">${renderValue(p)}</div>${extra}<div class="param-sub">${esc(p.notes)}</div>`;
    $('#module'+p.module).append(card);}
  $('#availableCount').textContent=analysis.parameters.filter(p=>p.status!=='UNAVAILABLE').length+' / 10';
  $('#calibrationStatus').textContent=analysis.calibration.confirmed?'5 cm':'未确认';
  $('#warningCount').textContent=analysis.quality.warnings.length;
  $('#qualityRow').innerHTML=`<div><b>图像质量</b> · 锐度代理值 ${fmt(analysis.quality.sharpness_laplacian_variance,1)} · 灰度均值 ${fmt(analysis.quality.average_grayscale,1)}</div>`+
     analysis.quality.warnings.map(t=>`<div>• ${esc(t)}</div>`).join('');
  const r=analysis.manual_yarn_reference;
  $('#directionInfo').textContent=r?`人工参考轴：原图 ${fmt(r.reference_axis_image_deg,2)}°；V4 输入 ROI 轴 ${fmt(r.reference_axis_roi_deg,2)}°；V4 校正旋转 ${fmt(r.v4_adapter_rotation_deg,2)}°。经纬身份仍需另行确认。`:'未提供人工参考方向';
  $('#previewEmpty').hidden=true;$('#previewResults').hidden=false;
  $('[data-img="roi"]').click();
}
for(const tab of document.querySelectorAll('[data-img]'))tab.addEventListener('click',()=>{
  document.querySelectorAll('[data-img]').forEach(x=>x.classList.remove('active'));tab.classList.add('active');
  if(!visuals)return;let name=tab.dataset.img;$('#resultImage').src=visuals[name];$('#imageNote').textContent=notes[name];
});
$('#analyzeButton').addEventListener('click',async()=>{
  if(!currentFile)return;if(referencePoints.length!==2||!$('#confirmReference').checked){setMessage('请选完纱线参考两点，并人工确认同一根真实纱线','error');return;}let fd=new FormData();fd.append('image',currentFile);fd.append('corners',JSON.stringify(cornerPoints.length===4?cornerPoints:null));fd.append('confirm_corners',String($('#confirmCorners').checked&&cornerPoints.length===4));
  fd.append('reference_points',JSON.stringify(referencePoints.length===2?referencePoints:null));fd.append('confirm_reference',String($('#confirmReference').checked));fd.append('warp_family',$('#warpFamily').value);fd.append('weave_override',$('#weave').value);fd.append('confirm_weave',String($('#confirmWeave').checked));
  $('#analyzeButton').disabled=true;$('#buttonText').textContent='正在执行图像分析…';setMessage('分析中：正在运行冻结 V4，可能需要数十秒；结果为纱线候选轨迹…');
  try{let rsp=await fetch('/api/analyze',{method:'POST',body:fd});let body=await rsp.json();if(!rsp.ok)throw Error(body.detail||`HTTP ${rsp.status}`);
    analysis=body.result;visuals=body.visuals;renderResults();setMessage(`冻结 V4 检测完成：A组 ${analysis.v4?.family_a_candidate_lines??0} 条候选，B组 ${analysis.v4?.family_b_candidate_lines??0} 条候选。实际纱线准确率未经核验。`,'ok');$('#resultSection').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){setMessage('分析失败：'+e.message,'error');console.error(e);}finally{$('#analyzeButton').disabled=false;$('#buttonText').textContent='开始十项参数分析';}
});
function downloadData(uri,filename){let a=document.createElement('a');a.href=uri;a.download=filename;document.body.appendChild(a);a.click();a.remove();}
$('#downloadJson').addEventListener('click',()=>{if(!analysis)return;let blob=new Blob([JSON.stringify(analysis,null,2)],{type:'application/json'});let url=URL.createObjectURL(blob);downloadData(url,'textile_10_parameters_result.json');setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('#download3').addEventListener('click',()=>{if(visuals)downloadData(visuals.three_panel,'textile_three_panel.jpg');});
