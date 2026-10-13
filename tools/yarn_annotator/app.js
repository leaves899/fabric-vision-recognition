"use strict";
const el=id=>document.getElementById(id);
const PRIORITY=["U20261013_01","U20261013_02","U20261013_03","U20261013_04","U20261013_05","U20261013_06","T001","T004","T005","T007","T006","P001","T002","H001","S001","X002","U001"];
const COLORS={reference:"#ff9a27",check_same:"#18d294",holdout_same:"#fff068",check_cross:"#72a9ff",check_cross_second:"#cf8cff"};
const LABELS={reference:"A第一根校准纱线",check_same:"A第二根校准纱线",holdout_same:"A第三根独立验收纱线",check_cross:"B第一根校准纱线",check_cross_second:"B第二根校准纱线"};
let all=[], visible=[], current=null, selected="reference", data=null, drawn=[];
function show(msg,good=true){el("message").textContent=msg;el("message").className=good?"good":"bad";}
function blank(row){return {schema_version:"1.0",sample_id:row.sample_id,image_path:row.image_path,annotation_target:/^U20261013_0[1-6]$/.test(row.sample_id)?"PHYSICAL_YARN_REFERENCE":"UNSPECIFIED",path_may_cross_occlusion:/^U20261013_0[1-6]$/.test(row.sample_id),visible_pixel_gt_confirmed:false,centerline_pixel_gt_confirmed:false,reference_confirmed:false,reference_family:"UNKNOWN",identity_confirmed:false,review_state:"DRAFT",eligibility:"UNREVIEWED",same_family_intervals:null,same_family_intervals_confirmed:false,cross_family_intervals:null,cross_family_intervals_confirmed:false,segments:{reference:null,check_same:null,holdout_same:null,check_cross:null,check_cross_second:null},notes:""};}
function axis(pts){if(!pts||pts.length!==2)return null;let a=pts[0],b=pts[1];return ((Math.atan2(b[1]-a[1],b[0]-a[0])*180/Math.PI)%180+180)%180;}
function activeList(){
  visible=el("subset").value==="focus"?all.filter(x=>PRIORITY.includes(x.sample_id)):all.slice();
  visible.sort((a,b)=>{
    let ia=PRIORITY.indexOf(a.sample_id),ib=PRIORITY.indexOf(b.sample_id);
    return (ia<0?1000:ia)-(ib<0?1000:ib)||a.sample_id.localeCompare(b.sample_id);
  });
  el("sample").replaceChildren(...visible.map(x=>{
    let option=document.createElement("option");
    option.value=x.sample_id;
    option.textContent=x.sample_id+(x.annotated?" ✓":"")+" | "+x.image_path.split("/").slice(-1)[0];
    return option;
  }));
}
function zoomImage(){
  const img=el("fabricImg"),canvas=el("layer");
  if(!img.naturalWidth)return;
  let pct=+el("zoom").value;
  const isNativeZoom=/^U20261013_0[1-6]$/.test(current?.sample_id||"");
  const baseWidth=isNativeZoom?img.naturalWidth:Math.min(img.naturalWidth,1000);
  let width=Math.max(200,Math.round(baseWidth*pct/100));
  img.style.width=width+"px";
  canvas.style.width=width+"px";
  canvas.style.height="auto";
  el("zoomText").textContent=pct+"%";
}
function redraw(){
  const img=el("fabricImg"),canvas=el("layer"),ctx=canvas.getContext("2d");
  if(!img.naturalWidth||!data)return;
  ctx.clearRect(0,0,canvas.width,canvas.height);
  let width=Math.max(3,canvas.width/350);
  Object.keys(LABELS).forEach(type=>{
    const pts=data.segments[type];
    if(!pts||!pts.length)return;
    ctx.strokeStyle=COLORS[type];ctx.fillStyle=COLORS[type];ctx.lineWidth=width;
    pts.forEach(p=>{ctx.beginPath();ctx.arc(p[0],p[1],width*1.9,0,2*Math.PI);ctx.fill();});
    if(pts.length===2){ctx.save();if(data.annotation_target==="PHYSICAL_YARN_REFERENCE")ctx.setLineDash([10,8]);ctx.beginPath();ctx.moveTo(...pts[0]);ctx.lineTo(...pts[1]);ctx.stroke();ctx.restore();}
  });
  el("angles").textContent=Object.keys(LABELS).map(type=>{
    let angle=axis(data.segments[type]);
    return LABELS[type]+": "+(angle===null?"未完成":angle.toFixed(2)+"°");
  }).join("\n");
}
function onPoint(ev){
  if(!data)return;
  let rect=el("layer").getBoundingClientRect(), img=el("fabricImg");
  let x=(ev.clientX-rect.left)*img.naturalWidth/rect.width;
  let y=(ev.clientY-rect.top)*img.naturalHeight/rect.height;
  x=Math.min(img.naturalWidth-0.001,Math.max(0,x));
  y=Math.min(img.naturalHeight-0.001,Math.max(0,y));
  let arr=data.segments[selected]||[];
  if(arr.length>=2)arr=[];
  arr.push([Number(x.toFixed(3)),Number(y.toFixed(3))]);
  data.segments[selected]=arr;
  if(selected==="reference")el("confirmRef").checked=false;
  el("reviewState").value="DRAFT";
  redraw();
}
function copyToInputs(){
  if(!data)return;
  el("eligibility").value=data.eligibility||"UNREVIEWED";
  el("confirmRef").checked=data.reference_confirmed===true;
  el("family").value=data.reference_family||"UNKNOWN";
  el("confirmIdentity").checked=data.identity_confirmed===true;
  el("reviewState").value=data.review_state||"DRAFT";
  el("notes").value=data.notes||"";
  el("aIntervals").value=data.same_family_intervals??"";
  el("aIntervalsConfirmed").checked=data.same_family_intervals_confirmed===true;
  el("bIntervals").value=data.cross_family_intervals??"";
  el("bIntervalsConfirmed").checked=data.cross_family_intervals_confirmed===true;
}
async function loadSample(sid){
  let row=all.find(x=>x.sample_id===sid);
  if(!row)return;
  current=row;
  const originalLink=el("originalPhotoLink");
  const zoomNative=/^U20261013_0[1-6]$/.test(sid);
  if(zoomNative) {
    originalLink.href="/datasets/user_contributed/2026-10-13-six-fabric-images/images/"+sid+".jpg";
    originalLink.hidden=false;
  } else {
    originalLink.removeAttribute("href");
    originalLink.hidden=true;
  }
  el("sample").value=sid;
  el("fabricImg").src="";
  show("读取 "+sid+" 当前标注照片和标注...");
  let response=await fetch("/api/annotation?id="+encodeURIComponent(sid),{cache:"no-store"});
  if(!response.ok){show("读取标注失败；检查后台",false);return;}
  let raw=await response.json();
  const staleSavedImage=!!(raw.image_path && raw.image_path!==row.image_path);
  data=Object.assign(blank(row),staleSavedImage?{}:raw);
  data.segments=Object.assign({reference:null,check_same:null,holdout_same:null,check_cross:null,check_cross_second:null},data.segments||{});
  if(data.annotation_target==="PHYSICAL_YARN_TRAJECTORY")data.annotation_target="PHYSICAL_YARN_REFERENCE";
  if(zoomNative){data.annotation_target="PHYSICAL_YARN_REFERENCE";data.annotation_semantics="PHYSICAL_YARN_REFERENCE";data.path_may_cross_occlusion=true;data.visible_pixel_gt_confirmed=false;data.centerline_pixel_gt_confirmed=false;}
  copyToInputs();
  let img=el("fabricImg");
  img.onload=()=>{
    let canvas=el("layer");
    canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
    zoomImage();
    el("meta").textContent=sid+" · "+img.naturalWidth+"×"+img.naturalHeight+
      (zoomNative?" · 2× 中心放大图原生像素坐标（不是原图坐标）":" · 当前图像原生像素坐标");
    redraw();
    show(staleSavedImage?"旧标注绑定的是另一张图，已清空当前画面草稿；请重新人工选点，避免坐标误用。":(zoomNative?"已加载：本组两点表示同一根真实物理纱线的推断连接轨迹，可以跨越遮挡区；虚线不是逐像素可见纱段。":"已加载：请按该样本标注说明人工确认。"),!staleSavedImage);
  };
  img.onerror=()=>show("无法加载图片，请确认仓库根目录启动了本地服务",false);
  img.src="/"+row.image_path.split("/").map(encodeURIComponent).join("/");
}
async function save(){
  if(!data)return;
  data.eligibility=el("eligibility").value;
  if(/^U20261013_0[1-6]$/.test(current.sample_id)){
    data.annotation_target="PHYSICAL_YARN_REFERENCE";data.annotation_semantics="PHYSICAL_YARN_REFERENCE";data.path_may_cross_occlusion=true;
    data.visible_pixel_gt_confirmed=false;data.centerline_pixel_gt_confirmed=false;
  }
  data.reference_confirmed=el("confirmRef").checked;
  data.reference_family=el("family").value;
  data.identity_confirmed=el("confirmIdentity").checked;
  data.review_state=el("reviewState").value;
  data.notes=el("notes").value;
  const countValue=id=>{
    const raw=el(id).value.trim();
    return raw===""?null:Number(raw);
  };
  data.same_family_intervals=countValue("aIntervals");
  data.same_family_intervals_confirmed=el("aIntervalsConfirmed").checked;
  data.cross_family_intervals=countValue("bIntervals");
  data.cross_family_intervals_confirmed=el("bIntervalsConfirmed").checked;
  for(const [numberField,checkField] of [
    ["same_family_intervals","same_family_intervals_confirmed"],
    ["cross_family_intervals","cross_family_intervals_confirmed"]]){
    const n=data[numberField];
    if(n!==null && (!Number.isInteger(n)||n<1||n>200||!data[checkField]))
      return show("必须填写1～200之间的真实纱距整数并勾选人工逐根确认，或清空该项",false);
    if(n===null&&data[checkField])
      return show("勾选确认前必须先填写完整真实纱距数",false);
  }
  if(data.review_state==="OPERATOR_REVIEWED"&&(!data.reference_confirmed||!data.segments.reference||data.segments.reference.length!==2)){
    return show("必须确认两点表示同一根真实物理纱线的连接轨迹（允许遮挡）",false);
  }
  show("正在校验并保存...");
  try{
    let r=await fetch("/api/annotation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    let out=await r.json();
    if(!r.ok)throw Error(out.error||"保存失败");
    current.annotated=true;
    activeList();el("sample").value=current.sample_id;
    show("保存成功 "+out.sample_id+" · "+out.status+" · 已校验标注图像 SHA-256");
  }catch(err){show(String(err),false);}
}
function updateMode(mode){
  selected=mode;
  document.querySelectorAll("[data-mode]").forEach(b=>b.classList.toggle("active",b.dataset.mode===mode));
}
function move(delta){
  let idx=visible.findIndex(x=>x.sample_id===current?.sample_id);
  if(idx<0||!visible.length)return;
  loadSample(visible[(idx+delta+visible.length)%visible.length].sample_id);
}
async function init(){
  try{
    let resp=await fetch("/api/items");
    if(!resp.ok)throw Error("本地标注服务未启动");
    all=(await resp.json()).items;
    activeList();
    if(!visible.length)throw Error("找不到对应照片");
    await loadSample(visible[0].sample_id);
  }catch(err){show("无法连接标注服务，请用 python -m benchmark.manual_annotation serve 启动。"+String(err),false);}
}
el("layer").addEventListener("pointerdown",onPoint);
el("zoom").addEventListener("input",()=>{zoomImage();redraw();});
el("sample").addEventListener("change",ev=>loadSample(ev.target.value));
el("subset").addEventListener("change",()=>{activeList();if(visible.length)loadSample(visible[0].sample_id);});
el("prev").addEventListener("click",()=>move(-1));
el("next").addEventListener("click",()=>move(1));
el("undo").addEventListener("click",()=>{
  if(!data)return;
  data.segments[selected]=null;
  if(selected==="reference")el("confirmRef").checked=false;
  el("reviewState").value="DRAFT";redraw();
});
document.querySelectorAll("[data-mode]").forEach(x=>x.addEventListener("click",()=>updateMode(x.dataset.mode)));
el("save").addEventListener("click",save);
init();