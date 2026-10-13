"use strict";
/* Local PHONE-IMAGE evidence editor; separate from PHYSICAL_YARN_REFERENCE.
 * Coordinates are native image pixels, even when screen zoom is changed.
 * Nothing here creates independent physical identity ground truth.
 */
(function(){
  const byId=id=>document.getElementById(id);
  const colors={
    APPARENT_VISIBLE_YARN:"#18ba65",GAP:"#fc6c63",
    TWILL_PATTERN:"#ffc247",COLOR_STRIPE:"#df89ff",
    SHADOW:"#7ca6f6",OCCLUSION:"#00c8c8",UNCERTAIN:"#dedede"
  };
  const labels={
    APPARENT_VISIBLE_YARN:"可见纱线候选",
    GAP:"纱线间隙",TWILL_PATTERN:"斜纹视觉带",
    COLOR_STRIPE:"染色条带",SHADOW:"阴影/反光",
    OCCLUSION:"交织遮挡",UNCERTAIN:"无法判断"
  };
  const api={active:false,dirty:false,data:null,tool:"line",
             dragStart:null,preview:null,partialLine:null,relationFirst:null};
  const notify=(msg,good=true)=>{
    byId("localMessage").textContent=msg;
    byId("localMessage").className=good?"good":"bad";
  };
  const markDirty=()=>{
    api.dirty=true;
    byId("localStatus").textContent="局部证据：有未保存修改";
    if(api.data)api.data.review_state="DRAFT";
    byId("localReviewState").value="DRAFT";
  };
  const savedState=()=>{
    api.dirty=false;
    byId("localStatus").textContent="局部证据："+(api.data?.regions?.length||0)+"个区域 / "+(api.data?.relations?.length||0)+"对关系（已保存）";
  };
  const coordinates=ev=>{
    const rect=byId("layer").getBoundingClientRect();
    const img=byId("fabricImg");
    const x=(ev.clientX-rect.left)*img.naturalWidth/rect.width;
    const y=(ev.clientY-rect.top)*img.naturalHeight/rect.height;
    return [Number(Math.max(0,Math.min(img.naturalWidth-.001,x)).toFixed(3)),
            Number(Math.max(0,Math.min(img.naturalHeight-.001,y)).toFixed(3))];
  };
  function nextId(){
    const used=new Set(api.data.regions.map(x=>x.id));
    let n=1;
    while(used.has("r"+String(n).padStart(4,"0")))n++;
    return "r"+String(n).padStart(4,"0");
  }
  function center(g){
    if(g.type==="RECT"){
      const a=g.bbox;
      return [(a[0]+a[2])/2,(a[1]+a[3])/2];
    }
    const pts=g.points;
    return [(pts[0][0]+pts[1][0])/2,(pts[0][1]+pts[1][1])/2];
  }
  function nearestRegion(p){
    for(const region of [...api.data.regions].reverse()){
      const g=region.geometry;
      if(g.type==="RECT"){
        const b=g.bbox;
        if(p[0]>=b[0] && p[0]<=b[2] && p[1]>=b[1] && p[1]<=b[3])return region;
      }else{
        const a=g.points[0],b=g.points[1];
        const len=(b[0]-a[0])**2+(b[1]-a[1])**2;
        const t=Math.max(0,Math.min(1,((p[0]-a[0])*(b[0]-a[0])+(p[1]-a[1])*(b[1]-a[1]))/len));
        if(Math.hypot(p[0]-(a[0]+t*(b[0]-a[0])),p[1]-(a[1]+t*(b[1]-a[1])))<=
           Math.max(8,byId("fabricImg").naturalWidth/130))return region;
      }
    }
    return null;
  }
  function drawStroke(ctx,geometry,color,width,dotted=false){
    ctx.save();ctx.strokeStyle=color;ctx.lineWidth=width;
    if(dotted)ctx.setLineDash([width*2,width*1.5]);
    ctx.beginPath();
    if(geometry.type==="RECT"){
      const b=geometry.bbox;
      ctx.rect(b[0],b[1],b[2]-b[0],b[3]-b[1]);
    }else{
      ctx.moveTo(...geometry.points[0]);ctx.lineTo(...geometry.points[1]);
    }
    ctx.stroke();ctx.restore();
  }
  function repaint(ctx){
    if(!api.data)return;
    const width=Math.max(2,byId("fabricImg").naturalWidth/440);
    ctx.save();
    for(const region of api.data.regions){
      const color=colors[region.kind]||"#fff";
      drawStroke(ctx,region.geometry,color,width,region.kind==="TWILL_PATTERN"&&region.geometry.type==="LINE");
      const p=center(region.geometry);
      ctx.font=Math.max(12,width*5)+"px sans-serif";
      ctx.fillStyle="#080e18";
      ctx.fillText(region.id,p[0]+4,p[1]+5);
      ctx.fillStyle=color;
      ctx.fillText(region.id,p[0]+3,p[1]+4);
    }
    for(const link of api.data.relations){
      const a=api.data.regions.find(x=>x.id===link.a);
      const b=api.data.regions.find(x=>x.id===link.b);
      if(!a||!b)continue;
      const sign=link.relation==="SAME_PHYSICAL_YARN"?"#3ae88f":
        link.relation==="DIFFERENT_PHYSICAL_YARN"?"#ff4f6b":"#9ca3af";
      drawStroke(ctx,{type:"LINE",points:[center(a.geometry),center(b.geometry)]},
                 sign,width,link.relation!=="SAME_PHYSICAL_YARN");
    }
    if(api.preview){
      drawStroke(ctx,api.preview,"#ffffff",width*1.5,true);
    }
    if(api.partialLine){
      ctx.fillStyle="#ffffff";
      ctx.beginPath();ctx.arc(...api.partialLine,width*3,0,Math.PI*2);ctx.fill();
    }
    if(api.relationFirst){
      const r=api.data.regions.find(x=>x.id===api.relationFirst);
      if(r)drawStroke(ctx,r.geometry,"#ffffff",width*2,true);
    }
    ctx.restore();
  }
  api.render=repaint;
  function updateList(){
    const container=byId("localList");
    container.replaceChildren();
    for(const row of api.data?.regions||[]){
      const d=document.createElement("div");
      d.textContent=row.id+" · "+(labels[row.kind]||row.kind)+
        " · "+(row.geometry.type==="RECT"?"框选区域":(row.kind==="TWILL_PATTERN"?"斜纹假线":"可见短线"))+
        (row.note?" · "+row.note:"");
      container.appendChild(d);
    }
    if(!container.children.length)container.textContent="本张尚无区域；在照片上拖动框选即可开始。";
    const rels=byId("localRelationList");
    rels.replaceChildren();
    for(const rel of api.data?.relations||[]){
      const line=document.createElement("div");
      const button=document.createElement("button");
      button.type="button";button.textContent="删除";
      button.addEventListener("click",()=>{
        api.data.relations=api.data.relations.filter(x=>x!==rel);
        markDirty();updateList();redraw();
      });
      line.append(document.createTextNode(rel.a+" ↔ "+rel.b+" · "+rel.relation+"  "),button);
      rels.appendChild(line);
    }
    if(!rels.children.length)rels.textContent="尚无两区域关系。";
    byId("relationPending").textContent=api.relationFirst?
      "已选 "+api.relationFirst+"，请点第二个区域（不能同一个）":"尚未选择两区域关系的第一处";
  }
  function updateGuide(){
    const kind=byId("localKind").value;
    const tool=api.tool;
    let message;
    if(tool==="relation"){
      message="先点击第一块已经标过的区域，再点击另一块，最后选择同根/不同根/未知。这个步骤可不做。";
    }else if(tool==="delete"){
      message="单击左侧照片里已经画出的短线或框，就能删除该标注。";
    }else if(tool==="line" && kind==="TWILL_PATTERN"){
      message="② 在左侧照片上：沿着疑似斜纹视觉带，先点击短段起点，再点击终点。画的是容易误认为同一根纱线的视觉假线，不是这块区域里没有纱线；无法确认则选择③。";
    }else if(tool==="line"){
      message="① 在左侧照片上：先点真正可见的纱线短段起点，再点终点。只画局部，不跨遮挡。";
    }else if(kind==="UNCERTAIN"){
      message="在左侧照片上：鼠标按住拖动，框住看不清是不是纱线的区域。不要猜测；框完可以继续标其他位置。";
    }else if(kind==="TWILL_PATTERN"){
      message="高级框选模式：框出斜纹视觉带周围的纹理区域。若要和真实纱线一一对比，请用②沿斜纹画短线。";
    }else{
      message="在左侧照片上：按住鼠标拖动，框住当前类别的局部范围。看不清时可切换③无法判断。";
    }
    byId("localGuide").textContent=message;
    document.querySelectorAll("[data-quick-kind]").forEach(b=>{
      b.classList.toggle("active",b.dataset.quickKind===kind&&b.dataset.quickTool===tool);
    });
  }
  function addRegion(geometry){
    const item={id:nextId(),kind:byId("localKind").value,geometry,
      note:byId("localRegionNote").value.trim()};
    api.data.regions.push(item);
    byId("localRegionNote").value="";
    markDirty();updateList();redraw();
    notify("已记录 "+item.id+"（"+labels[item.kind]+"），继续标其它局部；完成后点击「保存本张局部标注」。");
  }
  function handleRelation(p){
    const found=nearestRegion(p);
    if(!found)return notify("请选择已画好的一个区域或短线；可以切换缩放后再点。",false);
    if(!api.relationFirst){
      api.relationFirst=found.id;
      updateList();redraw();return;
    }
    if(found.id===api.relationFirst)return notify("必须点两个不同的区域。",false);
    const a=api.relationFirst,b=found.id;
    if(api.data.relations.some(x=>(x.a===a&&x.b===b)||(x.a===b&&x.b===a))){
      api.relationFirst=null;updateList();redraw();
      return notify("这两个区域已经有关系；请先在下方删除原关系再重新添加。",false);
    }
    api.data.relations.push({a,b,relation:byId("localRelation").value});
    api.relationFirst=null;markDirty();updateList();redraw();
  }
  api.pointerDown=function(ev){
    if(!api.active||!api.data)return;
    ev.preventDefault();
    const p=coordinates(ev);
    if(api.tool==="relation"){handleRelation(p);return;}
    if(api.tool==="delete"){
      const r=nearestRegion(p);
      if(!r){notify("点击已标记的区域或短线以删除。",false);return;}
      api.data.regions=api.data.regions.filter(x=>x.id!==r.id);
      api.data.relations=api.data.relations.filter(x=>x.a!==r.id&&x.b!==r.id);
      markDirty();updateList();redraw();return;
    }
    if(api.tool==="line"){
      if(!["APPARENT_VISIBLE_YARN","TWILL_PATTERN","UNCERTAIN"].includes(byId("localKind").value)){
        notify("短线仅用于可见纱线、斜纹假线或无法判断；其他类别请框选。",false);return;
      }
      if(api.partialLine){
        const a=api.partialLine;
        if(Math.hypot(p[0]-a[0],p[1]-a[1])<4)return notify("两点过近，请重新选择第二点。",false);
        api.partialLine=null;api.preview=null;
        addRegion({type:"LINE",points:[a,p]});
      }else{api.partialLine=p;redraw();}
      return;
    }
    api.dragStart=p;
    api.preview={type:"RECT",bbox:[p[0],p[1],p[0]+.1,p[1]+.1]};
    byId("layer").setPointerCapture?.(ev.pointerId);
  };
  api.pointerMove=function(ev){
    if(!api.active||!api.data)return;
    if(api.dragStart){
      const p=coordinates(ev),a=api.dragStart;
      api.preview={type:"RECT",bbox:[Math.min(a[0],p[0]),Math.min(a[1],p[1]),
                                     Math.max(a[0],p[0]),Math.max(a[1],p[1])]};
      redraw();
    }else if(api.partialLine){
      api.preview={type:"LINE",points:[api.partialLine,coordinates(ev)]};
      redraw();
    }
  };
  api.pointerUp=function(ev){
    if(!api.active||!api.dragStart)return;
    const a=api.dragStart,b=coordinates(ev);
    api.dragStart=null;api.preview=null;
    const rect=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),
                Math.max(a[0],b[0]),Math.max(a[1],b[1])];
    if(rect[2]-rect[0]>=4 && rect[3]-rect[1]>=4)
      addRegion({type:"RECT",bbox:rect});
    else{redraw();notify("框选区域太小，请按住鼠标拖动形成矩形。",false);}
  };
  api.cancel=function(){
    api.dragStart=null;api.partialLine=null;api.relationFirst=null;api.preview=null;
    if(api.data)updateList();redraw();
  };
  api.load=async sid=>{
    api.cancel();
    const response=await fetch("/api/local-review?id="+encodeURIComponent(sid),{cache:"no-store"});
    const payload=await response.json();
    if(!response.ok)throw Error(payload.error||"无法读取局部标注");
    api.data=payload;
    byId("localNotes").value=payload.notes||"";
    byId("localReviewState").value=payload.review_state||"DRAFT";
    savedState();updateList();redraw();updateGuide();
    notify("已读取 "+sid+" 的局部标注。先在左侧照片画一小段真正可见的纱线；如果看不清，点③。");
  };
  // An updated browser page can stay open while an old Python process keeps
  // serving the old validator. Refuse to POST unless the server advertises
  // support for every class of LINE currently in this unsaved draft.
  async function assertServerCompatible(){
    const fix="本地 Python 标注服务版本过旧。请保持当前网页打开（不要刷新或关闭，以免丢失未保存标注），在运行服务的 PowerShell 按 Ctrl+C 停止旧服务，git pull 更新后重新执行 .\\启动本地标注.bat。然后回到本页直接点击「保存本张局部标注」。";
    let response;
    try{
      response=await fetch("/api/local-review-capabilities",{cache:"no-store"});
      if(!response.ok)throw Error("missing capability endpoint");
      const info=await response.json();
      if(info.protocol_version!==2 || !Array.isArray(info.supported_line_kinds)){
        throw Error("old protocol");
      }
      const lineKinds=new Set((api.data?.regions||[])
        .filter(item=>item.geometry?.type==="LINE")
        .map(item=>item.kind));
      for(const kind of lineKinds){
        if(!info.supported_line_kinds.includes(kind))
          throw Error("unsupported local line kind: "+kind);
      }
    }catch(err){
      throw Error(fix);
    }
  }
  api.save=async ()=>{
    if(!api.data)return notify("尚未加载局部标注。",false);
    api.data.notes=byId("localNotes").value;
    api.data.review_state=byId("localReviewState").value;
    api.data.independent_physical_gt=false;
    api.data.annotation_source="PHONE_IMAGE_OPERATOR_REVIEW";
    notify("正在保存局部 JSON...");
    try{
      await assertServerCompatible();
      const response=await fetch("/api/local-review",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify(api.data)});
      const result=await response.json();
      if(!response.ok){
        if(/short line is only for apparent yarn or unknown/i.test(result.error||""))
          throw Error("旧版 Python 进程拒绝斜纹短线。请不要刷新或关闭当前网页；按 Ctrl+C 停掉旧标注服务、重新运行启动本地标注.bat，再点击保存。");
        throw Error(result.error||"保存失败");
      }
      savedState();
      notify("已写入 "+result.path+"（"+result.regions+"个区域、"+
             result.relations+"对关系）。请在 PowerShell 执行 git add / commit / push。");
    }catch(err){notify(String(err),false);}
  };
  function selectTool(name){
    api.cancel();
    api.tool=name;
    document.querySelectorAll("[data-local-tool]").forEach(b=>
      b.classList.toggle("active",b.dataset.localTool===name));
    updateGuide();
    notify(name==="rect"?"按住鼠标拖动，框住局部区域。":
      name==="line"?(byId("localKind").value==="TWILL_PATTERN"?"沿疑似斜纹假线依次点起点、终点。":"沿实际可见的纱线短段依次点起点、终点。"):
      name==="relation"?"依次点两个已有区域；不确定就选 UNKNOWN。":"单击已标区域删除。");
  }
  function selectPanel(local){
    if(local===api.active)return;
    api.active=local;api.cancel();
    byId("referencePanel").hidden=local;
    byId("localPanel").hidden=!local;
    byId("switchRefs").classList.toggle("primary",!local);
    byId("switchLocal").classList.toggle("primary",local);
    redraw();
  }
  document.querySelectorAll("[data-quick-kind]").forEach(button=>{
    button.addEventListener("click",()=>{
      byId("localKind").value=button.dataset.quickKind;
      selectTool(button.dataset.quickTool);
    });
  });
  byId("localKind").addEventListener("change",()=>{
    const kind=byId("localKind").value;
    selectTool(["APPARENT_VISIBLE_YARN","TWILL_PATTERN"].includes(kind)?"line":"rect");
  });
  byId("switchRefs").addEventListener("click",()=>selectPanel(false));
  byId("switchLocal").addEventListener("click",()=>selectPanel(true));
  document.querySelectorAll("[data-local-tool]").forEach(b=>b.addEventListener("click",()=>selectTool(b.dataset.localTool)));
  byId("layer").addEventListener("pointermove",ev=>api.pointerMove(ev));
  byId("layer").addEventListener("pointerup",ev=>api.pointerUp(ev));
  byId("layer").addEventListener("pointercancel",()=>api.cancel());
  byId("localUndo").addEventListener("click",()=>{
    if(!api.data?.regions?.length)return;
    const removed=api.data.regions.pop();
    api.data.relations=api.data.relations.filter(x=>x.a!==removed.id&&x.b!==removed.id);
    markDirty();updateList();redraw();
  });
  byId("localClearPending").addEventListener("click",()=>api.cancel());
  byId("localReviewState").addEventListener("change",()=>{api.dirty=true;});
  byId("localNotes").addEventListener("input",()=>{api.dirty=true;byId("localStatus").textContent="局部证据：有未保存修改";});
  byId("saveLocal").addEventListener("click",()=>api.save());
  updateGuide();
  window.localEvidence=api;
  // New evidence-review workflow is the default; legacy A1/A2/A3 is one click away.
  selectPanel(true);
})();
