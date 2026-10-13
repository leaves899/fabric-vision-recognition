"use strict";
// Zero-dependency DOM smoke test for the simple three-task local annotation UI.
// It tests actual event callbacks, not just strings in the HTML.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class FakeElement {
  constructor(id="") {
    this.id=id;
    this.value="";
    this.textContent="";
    this.hidden=false;
    this.dataset={};
    this.listeners={};
    this.children=[];
    this.classes=new Set();
    this.classList={
      toggle:(cls,on)=>{
        if(on===undefined){on=!this.classes.has(cls)}
        if(on){this.classes.add(cls)}else{this.classes.delete(cls)}
      }
    };
    this.naturalWidth=200;
    this.naturalHeight=200;
  }
  addEventListener(event,callback){this.listeners[event]=callback}
  click(){this.listeners.click?.({preventDefault(){}})}
  replaceChildren(...items){this.children=[...items]}
  appendChild(child){this.children.push(child)}
  append(...children){this.children.push(...children)}
  getBoundingClientRect(){return {left:0,top:0,width:100,height:100}}
  setPointerCapture(){}
}
const cache=new Map();
const get=id=>{
  if(!cache.has(id))cache.set(id,new FakeElement(id));
  return cache.get(id);
};
get("localKind").value="APPARENT_VISIBLE_YARN";
get("localRelation").value="UNKNOWN";
get("localReviewState").value="DRAFT";
const kinds=[
 ["quickYarn","APPARENT_VISIBLE_YARN","line"],
 ["quickTexture","TWILL_PATTERN","line"],
 ["quickUnknown","UNCERTAIN","rect"]
];
for(const [id,kind,tool] of kinds){
  get(id).dataset={quickKind:kind,quickTool:tool};
}
for(const [id,tool] of [["toolRect","rect"],["toolLine","line"],
                        ["toolRelation","relation"],["toolDelete","delete"]]){
  get(id).dataset={localTool:tool};
}
const doc={
  getElementById:get,
  createElement:tag=>new FakeElement(tag),
  createTextNode:s=>({textContent:s}),
  querySelectorAll:selector=>{
    if(selector==="[data-quick-kind]")return kinds.map(([id])=>get(id));
    if(selector==="[data-local-tool]")
      return ["toolRect","toolLine","toolRelation","toolDelete"].map(get);
    return [];
  }
};
let redrawCalls=0;
const context={
  document:doc,window:{},console,Math,
  redraw:()=>{redrawCalls++;},
  fetch:async()=>{throw Error("Unexpected network access in UI smoke test")}
};
const file=path.join(__dirname,"local_review.js");
vm.runInNewContext(fs.readFileSync(file,"utf-8"),context,{filename:file});
const app=context.window.localEvidence;

assert.equal(app.active,true,"new easy local annotator should open by default");
assert.equal(app.tool,"line");
assert.equal(get("referencePanel").hidden,true);
assert.equal(get("localPanel").hidden,false);
assert.match(get("localGuide").textContent,/起点.*终点/);

app.data={regions:[],relations:[],review_state:"DRAFT"};
function point(x,y){return {clientX:x,clientY:y,pointerId:1,preventDefault(){}}}
app.pointerDown(point(12,20));
assert.equal(app.data.regions.length,0,"first click only starts a short line");
app.pointerDown(point(64,20));
assert.equal(app.data.regions.length,1);
assert.equal(app.data.regions[0].kind,"APPARENT_VISIBLE_YARN");
assert.equal(app.data.regions[0].geometry.type,"LINE");
assert.equal(app.data.regions[0].physical_identity_confirmed,undefined);

get("quickTexture").click();
assert.equal(get("localKind").value,"TWILL_PATTERN");
assert.equal(app.tool,"line");
assert.match(get("localGuide").textContent,/起点.*终点/);
app.pointerDown(point(20,35));
assert.equal(app.data.regions.length,1);
app.pointerDown(point(48,60));
assert.equal(app.data.regions.length,2);
assert.equal(app.data.regions[1].kind,"TWILL_PATTERN");
assert.equal(app.data.regions[1].geometry.type,"LINE");
// Advanced rectangle remains available for contextual TWILL_PATTERN regions.
get("toolRect").click();
app.pointerDown(point(50,70));
app.pointerMove(point(68,83));
app.pointerUp(point(68,83));
assert.equal(app.data.regions.length,3);
assert.equal(app.data.regions[2].kind,"TWILL_PATTERN");
assert.equal(app.data.regions[2].geometry.type,"RECT");

get("quickUnknown").click();
assert.equal(app.tool,"rect");
assert.match(get("localGuide").textContent,/看不清/);
app.pointerDown(point(51,52));
app.pointerMove(point(75,72));
app.pointerUp(point(75,72));
assert.equal(app.data.regions[3].kind,"UNCERTAIN");

// Advanced category picker remains operable without needing three-task buttons.
get("localKind").value="GAP";
get("localKind").listeners.change();
assert.equal(app.tool,"rect");

get("switchRefs").click();
assert.equal(app.active,false);
get("switchLocal").click();
assert.equal(app.active,true);
assert.ok(redrawCalls>0);
assert.equal(app.data.regions.length,4);
console.log("PASS guided UI: true-yarn line, twill-false line, legacy twill region, uncertain region and mode switching");
