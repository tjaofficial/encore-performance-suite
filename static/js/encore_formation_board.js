(() => {
const app=document.getElementById("formation-board-app");if(!app)return;
const stage=document.getElementById("formation-stage"),stageViewport=document.getElementById("drawing-stage-viewport"),stageZoomContent=document.getElementById("drawing-stage-zoom-content"),stageZoomOut=document.getElementById("stage-zoom-out"),stageZoomIn=document.getElementById("stage-zoom-in"),stageZoomReset=document.getElementById("stage-zoom-reset"),stageZoomValue=document.getElementById("stage-zoom-value"),layer=document.getElementById("marker-layer"),assignmentList=document.getElementById("assignment-list"),assignmentSort=document.getElementById("assignment-sort"),tooltip=document.getElementById("marker-tooltip"),status=document.getElementById("formation-status"),saveButton=document.getElementById("save-formation"),titleInput=document.getElementById("board-title"),songMinutes=document.getElementById("song-minutes"),songSeconds=document.getElementById("song-seconds"),showWings=document.getElementById("show-offstage-wings"),apronStageGrid=document.getElementById("apron-stage-grid"),tabs=document.getElementById("formation-tabs"),addFormationButton=document.getElementById("add-formation"),collapsePanelButton=document.getElementById("collapse-drawing-panel"),expandPanelButton=document.getElementById("expand-drawing-panel"),modal=document.getElementById("formation-modal"),modalClose=document.getElementById("close-formation-modal"),modalCancel=document.getElementById("cancel-formation-modal"),modalSave=document.getElementById("save-new-formation"),modalName=document.getElementById("new-formation-name"),modalMinute=document.getElementById("new-formation-minute"),modalSecond=document.getElementById("new-formation-second"),modalCopy=document.getElementById("copy-current-formation"),modalError=document.getElementById("formation-modal-error"),formatTitle=document.getElementById("format-marker-title"),formatHelp=document.getElementById("format-marker-help"),formatControls=document.getElementById("marker-format-controls"),customColor=document.getElementById("marker-custom-color");
const titleDisplay=document.getElementById("board-title-display"),danceDisplay=document.getElementById("board-dance-display"),danceSelect=document.getElementById("board-dance-select"),songSelect=document.getElementById("board-song-select"),createDanceButton=document.getElementById("create-dance-button"),addSongButton=document.getElementById("add-song-button"),songLengthHelp=document.getElementById("song-length-help"),danceModal=document.getElementById("dance-modal"),danceModalClose=document.getElementById("close-dance-modal"),danceModalCancel=document.getElementById("cancel-dance-modal"),danceSave=document.getElementById("save-dance"),danceTitle=document.getElementById("dance-title"),danceSongTitle=document.getElementById("dance-song-title"),danceArtist=document.getElementById("dance-artist"),danceChoreo=document.getElementById("dance-choreography-notes"),danceTeacherNotes=document.getElementById("dance-teacher-notes"),dancePerformanceNotes=document.getElementById("dance-performance-notes"),danceError=document.getElementById("dance-modal-error"),songModal=document.getElementById("song-modal"),songModalClose=document.getElementById("close-song-modal"),songModalCancel=document.getElementById("cancel-song-modal"),songSave=document.getElementById("save-song"),newSongTitle=document.getElementById("new-song-title"),newSongArtist=document.getElementById("new-song-artist"),newSongFile=document.getElementById("new-song-file"),newSongUrl=document.getElementById("new-song-url"),newSongMinutes=document.getElementById("new-song-minutes"),newSongSeconds=document.getElementById("new-song-seconds"),newSongDescription=document.getElementById("new-song-description"),songError=document.getElementById("song-modal-error");
const transitionTab=document.getElementById("transition-panel-tab"),transitionName=document.getElementById("transition-name"),transitionTime=document.getElementById("transition-time"),addMovementButton=document.getElementById("add-movement-path"),movementInstruction=document.getElementById("movement-instruction"),movementEditor=document.getElementById("movement-editor"),transitionMarkerName=document.getElementById("transition-marker-name"),customPathInstruction=document.getElementById("custom-path-instruction"),removeMovementButton=document.getElementById("remove-movement-path"),showTransitionPaths=document.getElementById("show-transition-paths"),transitionPathsGroup=document.getElementById("transition-paths"),customPathPreview=document.getElementById("custom-path-preview");const timingTab=document.getElementById("timing-panel-tab"),timingTransitionName=document.getElementById("timing-transition-name"),timingTransitionTime=document.getElementById("timing-transition-time"),timingFormationLabel=document.getElementById("timing-formation-label"),formationHoldMinutes=document.getElementById("formation-hold-minutes"),formationHoldSeconds=document.getElementById("formation-hold-seconds"),transitionDurationMinutes=document.getElementById("transition-duration-minutes"),transitionDurationSeconds=document.getElementById("transition-duration-seconds"),transitionTimingExampleText=document.getElementById("transition-timing-example-text"),controlPointSetting=document.getElementById("control-point-setting"),controlPointLabel=document.getElementById("control-point-label"),controlPointCount=document.getElementById("control-point-count"),decreaseControlPoints=document.getElementById("decrease-control-points"),increaseControlPoints=document.getElementById("increase-control-points"),autoPreview=document.getElementById("movement-auto-preview"),previewMovementButton=document.getElementById("preview-movement"),previewStatus=document.getElementById("movement-preview-status"),transitionPreviewFooter=document.getElementById("transition-preview-footer"),playMusicWithPlayback=document.getElementById("play-music-with-playback"),drawingBoardAudio=document.getElementById("drawing-board-audio"),selectedFormationName=document.getElementById("selected-formation-name"),selectedFormationStartTime=document.getElementById("selected-formation-start-time"),selectedFormationHoldMinutes=document.getElementById("selected-formation-hold-minutes"),selectedFormationHoldSeconds=document.getElementById("selected-formation-hold-seconds");const playbackToggle=document.getElementById("playback-toggle"),playbackRestart=document.getElementById("playback-restart"),playbackScrubber=document.getElementById("playback-scrubber"),playbackCurrentTime=document.getElementById("playback-current-time"),playbackTotalTime=document.getElementById("playback-total-time"),playbackFormationMarkers=document.getElementById("playback-formation-markers"),playbackExit=document.getElementById("playback-exit");
const saveUrl=app.dataset.saveUrl,addFormationUrl=app.dataset.addFormationUrl,deleteUrlTemplate=app.dataset.deleteUrlTemplate,informationSaveUrl=app.dataset.informationSaveUrl,danceAddUrl=app.dataset.danceAddUrl,songAddUrl=app.dataset.songAddUrl;const deleteModal=document.getElementById("delete-formation-modal"),deleteModalClose=document.getElementById("close-delete-formation-modal"),deleteModalCancel=document.getElementById("cancel-delete-formation"),deleteModalConfirm=document.getElementById("confirm-delete-formation"),deleteModalName=document.getElementById("delete-formation-name"),deleteModalError=document.getElementById("delete-formation-error");let pendingDeleteFormationId=null;let data={students:[],assignments:[],formations:[],active_formation_id:null,show_offstage_wings:false,apron_stage_grid:false,stage_drawings:[],song_duration_seconds:0,board_title:"",selected_dance_id:null,selected_song_id:null,dances:[],songs:[],transitions:[],lighting_cues:[],lighting_fixtures:[],active_lighting_cue_id:null};try{const dataScript=document.getElementById("drawing-board-data");data={...data,...JSON.parse(dataScript?dataScript.textContent:"{}")}}catch(e){console.error(e)}
const studentMap=new Map(data.students.map(s=>[Number(s.id),s]));let assignments=new Map();data.assignments.forEach(i=>{const id=i.student_id==null?null:Number(i.student_id);assignments.set(Number(i.marker),{marker:Number(i.marker),student_id:id!==null&&studentMap.has(id)?id:null,shape:i.shape||"circle",color:i.color||"#2E3CF1"})});let formations=data.formations.map((f,index)=>({...f,id:Number(f.id),sequence_order:Number(f.sequence_order||index+1),time_seconds:Number(f.time_seconds||0),hold_duration_seconds:Math.max(0,Number(f.hold_duration_seconds??8)),positions:(f.positions||[]).map(p=>({marker:Number(p.marker),x:Number(p.x),y:Number(p.y)}))}));function normalizeMovement(m){let type=m.path_type||"straight";if(type==="curve_left"||type==="curve_right")type="curve";if(type==="zigzag")type="angled";const points=(m.points||[]).map(p=>({x:Number(p.x),y:Number(p.y)}));return{marker:Number(m.marker),path_type:type,points,control_point_count:Math.max(1,Math.min(8,Number(m.control_point_count||points.length||1)))}}let transitions=(data.transitions||[]).map(t=>({id:t.id==null?null:Number(t.id),from_formation_id:Number(t.from_formation_id),to_formation_id:Number(t.to_formation_id),duration_seconds:Math.max(1,Number(t.duration_seconds??3)),movements:(t.movements||[]).map(normalizeMovement)}));
let activeFormationId=Number(data.active_formation_id),selectedMarker=null,draggedStudentId=null,stageZoom=1,dirty=false,saveTimer=null,saveInFlight=false,saveQueued=false,activeTransitionKey=null,selectedTransitionMarker=null,movementSelectMode=false,customPathMode=false,customDrawing=false,customPoints=[],transitionEditorMode="movement",previewFrame=null,previewTimer=null,previewRunning=false,playbackMode=false,playbackPlaying=false,playbackTime=0,playbackStartedAt=0,playbackStartedFrom=0,playbackFrame=null;
function csrf(){const c=document.cookie.split(";").map(x=>x.trim()).find(x=>x.startsWith("csrftoken="));return c?decodeURIComponent(c.split("=")[1]):""}function fmt(t){t=Math.max(0,Number(t)||0);return `${Math.floor(t/60)}:${String(t%60).padStart(2,"0")}`}function songLen(){return(Math.max(0,Number(songMinutes.value)||0)*60)+Math.max(0,Math.min(59,Number(songSeconds.value)||0))}function setSong(t){t=Math.max(0,Number(t)||0);songMinutes.value=Math.floor(t/60);songSeconds.value=String(t%60).padStart(2,"0")}function active(){return formations.find(f=>f.id===activeFormationId)||null}function markerCount(){return assignments.size?Math.max(data.students.length,...assignments.keys()):data.students.length}function ensureAssignments(){for(let i=1;i<=markerCount();i++)if(!assignments.has(i))assignments.set(i,{marker:i,student_id:null,shape:"circle",color:"#2E3CF1"})}
function defaults(count){if(!count)return[];const cols=Math.min(8,Math.max(4,count)),rows=Math.ceil(count/cols),out=[];for(let i=0;i<count;i++){const r=Math.floor(i/cols),c=i%cols,rc=Math.min(cols,count-r*cols),x=((c+1)/(rc+1))*100,y=rows===1?66:72-((r/Math.max(rows-1,1))*34);out.push({marker:i+1,x,y})}return out}function ensurePos(f){if(!f.positions||!f.positions.length)f.positions=defaults(markerCount())}function posMap(f){ensurePos(f);return new Map(f.positions.map(p=>[Number(p.marker),p]))}function assignFor(n){return assignments.get(Number(n))||{marker:Number(n),student_id:null,shape:"circle",color:"#2E3CF1"}}function studentFor(a){return a&&a.student_id?studentMap.get(Number(a.student_id))||null:null}
function markDirty(msg="Unsaved changes"){dirty=true;status.textContent=msg;status.className="formation-status dirty";clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveBoard(false),850)}function markSaved(){dirty=false;status.textContent="✓ Saved";status.className="formation-status saved"}function markSaving(){status.textContent="Saving…";status.className="formation-status saving"}function markError(m){status.textContent=`⚠ ${m}`;status.className="formation-status error"}function payload(){return{title:titleInput.value.trim(),song_duration_seconds:songLen(),show_offstage_wings:showWings.checked,apron_stage_grid:Boolean(apronStageGrid?.checked),stage_drawings:(window.EncoreStageDrawing&&window.EncoreStageDrawing.serialize?window.EncoreStageDrawing.serialize():data.stage_drawings||[]),active_roster_ids:data.students.map(s=>Number(s.id)),marker_count:markerCount(),assignments:Array.from(assignments.values()),formations:formations.map(f=>({id:f.id,name:String(f.name||"").trim(),hold_duration_seconds:Math.max(0,Number(f.hold_duration_seconds)||0),positions:f.positions||[]})),transitions:transitions.map(t=>({id:t.id,from_formation_id:t.from_formation_id,to_formation_id:t.to_formation_id,duration_seconds:Math.max(1,Number(t.duration_seconds)||3),movements:t.movements||[]})),lighting_cues:(window.EncoreLighting&&window.EncoreLighting.serialize?window.EncoreLighting.serialize():data.lighting_cues||[]),lighting_fixtures:(window.EncoreLighting&&window.EncoreLighting.serializeFixtures?window.EncoreLighting.serializeFixtures():data.lighting_fixtures||[])}}
async function saveBoard(manual=false){clearTimeout(saveTimer);if(saveInFlight){saveQueued=true;return}if(!dirty&&!manual)return;saveInFlight=true;saveQueued=false;markSaving();if(manual){saveButton.disabled=true;saveButton.textContent="Saving…"}try{const r=await fetch(saveUrl,{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":csrf()},body:JSON.stringify(payload())}),j=await r.json();if(!r.ok||!j.ok){if(j.roster_changed){clearTimeout(saveTimer);saveQueued=false;markError(j.error||"Class roster changed. Refresh this page.");return}throw new Error(j.error||"Could not save.")}markSaved()}catch(e){console.error(e);dirty=true;markError(e.message||"Not saved")}finally{saveInFlight=false;if(manual){saveButton.disabled=false;saveButton.textContent="Save"}if(saveQueued){saveQueued=false;clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveBoard(false),850)}}}
const STAGE_ZOOM_MIN=.5,STAGE_ZOOM_MAX=2.5,STAGE_ZOOM_STEP=.1;
function clampStageZoom(value){return Math.max(STAGE_ZOOM_MIN,Math.min(STAGE_ZOOM_MAX,Math.round(Number(value||1)*100)/100))}
function updateStageZoomDisplay(){if(stageZoomValue)stageZoomValue.textContent=`${Math.round(stageZoom*100)}%`}
function applyStageZoom(preserveCenter=true){if(!stageViewport||!stageZoomContent)return;let centerX=.5,centerY=.5;if(preserveCenter&&stageViewport.scrollWidth>0&&stageViewport.scrollHeight>0){centerX=(stageViewport.scrollLeft+stageViewport.clientWidth/2)/stageViewport.scrollWidth;centerY=(stageViewport.scrollTop+stageViewport.clientHeight/2)/stageViewport.scrollHeight}stageZoomContent.style.setProperty("--stage-zoom",String(stageZoom));updateStageZoomDisplay();requestAnimationFrame(()=>{if(!preserveCenter)return;stageViewport.scrollLeft=Math.max(0,centerX*stageViewport.scrollWidth-stageViewport.clientWidth/2);stageViewport.scrollTop=Math.max(0,centerY*stageViewport.scrollHeight-stageViewport.clientHeight/2)})}
function setStageZoom(value,preserveCenter=true){stageZoom=clampStageZoom(value);applyStageZoom(preserveCenter)}
function centerStageView(){if(!stageViewport)return;stageViewport.scrollLeft=Math.max(0,(stageViewport.scrollWidth-stageViewport.clientWidth)/2);stageViewport.scrollTop=Math.max(0,(stageViewport.scrollHeight-stageViewport.clientHeight)/2)}
function resetStageView(){stageZoom=1;applyStageZoom(false);requestAnimationFrame(centerStageView)}
function applyWings(){stage.classList.toggle("show-wings",showWings.checked);stage.classList.toggle("apron-stage-grid",Boolean(apronStageGrid?.checked))}function setPos(el,p){el.style.left=`${p.x}%`;el.style.top=`${p.y}%`}function pointerPct(x,y){const r=stage.getBoundingClientRect();return{x:Math.max(0,Math.min(100,((x-r.left)/r.width)*100)),y:Math.max(0,Math.min(100,((y-r.top)/r.height)*100))}}function label(n){const a=assignFor(n),s=studentFor(a);return s?`${n} · ${s.name}`:`${n} · Unassigned`}function positionTip(el){const sr=stage.getBoundingClientRect(),mr=el.getBoundingClientRect();tooltip.style.left=`${Math.min(Math.max(8,mr.right-sr.left+8),stage.clientWidth-190)}px`;tooltip.style.top=`${Math.max(8,Math.min(mr.top-sr.top+mr.height/2-14,stage.clientHeight-34))}px`}function showTip(el,n){tooltip.textContent=label(n);tooltip.hidden=false;positionTip(el)}function hideTip(el=null){if(el&&el.classList.contains("dragging"))return;tooltip.hidden=true}
function selectMarker(n,switchTab=false){selectedMarker=Number(n);layer.querySelectorAll(".board-marker").forEach(m=>m.classList.toggle("selected",Number(m.dataset.marker)===selectedMarker));updateFormat();if(switchTab)activateTab("assignments")}
function dragMarker(el,n,p){let on=false;el.addEventListener("pointerdown",e=>{if(e.button!==0)return;on=true;el.setPointerCapture(e.pointerId);el.classList.add("dragging");selectMarker(n,false);showTip(el,n);e.preventDefault()});el.addEventListener("pointermove",e=>{if(!on)return;const q=pointerPct(e.clientX,e.clientY);p.x=q.x;p.y=q.y;setPos(el,p);showTip(el,n);markDirty("Marker moved")});const end=e=>{if(!on)return;on=false;try{el.releasePointerCapture(e.pointerId)}catch{}el.classList.remove("dragging");if(el.matches(":hover"))showTip(el,n);else hideTip()};el.addEventListener("pointerup",end);el.addEventListener("pointercancel",end)}
function assignStudent(marker,studentId){studentId=Number(studentId);const s=studentMap.get(studentId);if(!s)return;assignments.forEach(a=>{if(a.student_id===studentId)a.student_id=null});const a=assignFor(marker);a.student_id=studentId;assignments.set(Number(marker),a);renderAssignments();renderStage();updateFormat();markDirty(`${s.name} assigned to marker ${marker}`)}function unassignStudent(marker){const a=assignFor(marker),student=studentFor(a);if(!a||a.student_id==null)return;a.student_id=null;assignments.set(Number(marker),a);if(selectedMarker===Number(marker))selectedMarker=null;renderAssignments();renderStage();updateFormat();markDirty(student?`${student.name} unassigned from marker ${marker}`:`Marker ${marker} unassigned`)}
function transitionKey(fromId,toId){return `${Number(fromId)}:${Number(toId)}`}
function transitionByKey(key){if(!key)return null;const [fromId,toId]=key.split(":").map(Number);return transitions.find(t=>t.from_formation_id===fromId&&t.to_formation_id===toId)||null}
function ensureTransition(fromFormation,toFormation){const key=transitionKey(fromFormation.id,toFormation.id);let t=transitionByKey(key);if(!t){t={id:null,from_formation_id:fromFormation.id,to_formation_id:toFormation.id,duration_seconds:3,movements:[]};transitions.push(t)}return t}
function activeTransition(){return transitionByKey(activeTransitionKey)}
function transitionFormations(){const t=activeTransition();if(!t)return{from:null,to:null};return{from:formations.find(f=>f.id===t.from_formation_id)||null,to:formations.find(f=>f.id===t.to_formation_id)||null}}
function movementForMarker(t,n){return(t?.movements||[]).find(m=>Number(m.marker)===Number(n))||null}
function ensureMovement(t,n){let m=movementForMarker(t,n);if(!m){m=normalizeMovement({marker:Number(n),path_type:"straight",points:[],control_point_count:1});t.movements.push(m)}return m}
function defaultControlPoints(start,end,count){const out=[],amount=Math.max(1,Math.min(8,Number(count)||1));for(let i=1;i<=amount;i++){const q=i/(amount+1);out.push({x:start.x+(end.x-start.x)*q,y:start.y+(end.y-start.y)*q})}return out}
function ensureControlPoints(m,start,end){if(!m||!['curve','angled'].includes(m.path_type))return;const count=Math.max(1,Math.min(8,Number(m.control_point_count)||1));m.control_point_count=count;if(!Array.isArray(m.points))m.points=[];if(m.points.length!==count)m.points=defaultControlPoints(start,end,count)}
function catmullRom(points,steps=18){if(points.length<3)return points.slice();const out=[],at=i=>points[Math.max(0,Math.min(points.length-1,i))];for(let i=0;i<points.length-1;i++){const p0=at(i-1),p1=at(i),p2=at(i+1),p3=at(i+2);for(let j=0;j<steps;j++){const t=j/steps,t2=t*t,t3=t2*t;out.push({x:.5*(2*p1.x+(-p0.x+p2.x)*t+(2*p0.x-5*p1.x+4*p2.x-p3.x)*t2+(-p0.x+3*p1.x-3*p2.x+p3.x)*t3),y:.5*(2*p1.y+(-p0.y+p2.y)*t+(2*p0.y-5*p1.y+4*p2.y-p3.y)*t2+(-p0.y+3*p1.y-3*p2.y+p3.y)*t3)})}}out.push(points[points.length-1]);return out}
function movementPolyline(m,start,end){if(m?.path_type==="custom"&&m.points?.length)return[start,...m.points,end];if(m?.path_type==="curve"){ensureControlPoints(m,start,end);return catmullRom([start,...m.points,end])}if(m?.path_type==="angled"){ensureControlPoints(m,start,end);return[start,...m.points,end]}return[start,end]}
function createBoardMarker(n,p,ghost=false,startMarker=false){const a=assignFor(n),el=document.createElement("div");el.className=`board-marker shape-${a.shape||"circle"}`;el.dataset.marker=n;el.style.setProperty("--marker-color",a.color||"#2E3CF1");if(ghost)el.classList.add("transition-ghost-marker");if(startMarker)el.classList.add("transition-start-marker");const num=document.createElement("span");num.textContent=n;el.appendChild(num);setPos(el,p);return el}
function movementPathD(m,start,end){return movementPolyline(m,start,end).map((p,i)=>`${i?"L":"M"} ${p.x} ${p.y}`).join(" ")}
function renderTransitionPaths(t,fromMap,toMap){transitionPathsGroup.innerHTML="";if(!showTransitionPaths.checked)return;(t.movements||[]).forEach(m=>{const start=fromMap.get(Number(m.marker)),end=toMap.get(Number(m.marker));if(!start||!end)return;const path=document.createElementNS("http://www.w3.org/2000/svg","path");path.setAttribute("d",movementPathD(m,start,end));path.setAttribute("class","transition-path"+(Number(m.marker)===Number(selectedTransitionMarker)?" selected":""));transitionPathsGroup.appendChild(path)})}
function renderControlHandles(m,start,end){if(!m||!["curve","angled"].includes(m.path_type))return;ensureControlPoints(m,start,end);m.points.forEach((point,index)=>{const h=document.createElement("button");h.type="button";h.className="transition-control-handle";h.dataset.index=String(index+1);setPos(h,point);let dragging=false;h.addEventListener("pointerdown",e=>{if(e.button!==0)return;dragging=true;h.classList.add("dragging");h.setPointerCapture(e.pointerId);e.stopPropagation();e.preventDefault()});h.addEventListener("pointermove",e=>{if(!dragging)return;const q=pointerPct(e.clientX,e.clientY);point.x=q.x;point.y=q.y;setPos(h,point);const t=activeTransition(),pair=transitionFormations();if(t&&pair.from&&pair.to)renderTransitionPaths(t,posMap(pair.from),posMap(pair.to));markDirty("Movement path adjusted")});const done=e=>{if(!dragging)return;dragging=false;h.classList.remove("dragging");try{h.releasePointerCapture(e.pointerId)}catch{}renderStage();maybeAutoPreview()};h.addEventListener("pointerup",done);h.addEventListener("pointercancel",done);layer.appendChild(h)})}
function handleTransitionMarkerClick(n){const t=activeTransition();if(!t)return;selectedTransitionMarker=Number(n);if(movementSelectMode){ensureMovement(t,n);movementSelectMode=false;movementInstruction.hidden=true;stage.classList.remove("transition-select-mode");markDirty(`Movement added for marker ${n}`)}customPathMode=false;customDrawing=false;customPoints=[];stage.classList.remove("custom-path-mode");updateTransitionPanel();renderStage()}
function renderTransitionStage(){const t=activeTransition(),pair=transitionFormations();if(!t||!pair.from||!pair.to)return;ensurePos(pair.from);ensurePos(pair.to);const fm=posMap(pair.from),tm=posMap(pair.to);renderTransitionPaths(t,fm,tm);for(let n=1;n<=markerCount();n++){const start=fm.get(n),end=tm.get(n);if(!start||!end)continue;const ghost=createBoardMarker(n,end,true,false);layer.appendChild(ghost);const el=createBoardMarker(n,start,false,true);if(Number(selectedTransitionMarker)===n)el.classList.add("selected");el.addEventListener("click",()=>handleTransitionMarkerClick(n));el.addEventListener("mouseenter",()=>showTip(el,n));el.addEventListener("mouseleave",()=>hideTip(el));layer.appendChild(el)}if(selectedTransitionMarker){const m=movementForMarker(t,selectedTransitionMarker),start=fm.get(Number(selectedTransitionMarker)),end=tm.get(Number(selectedTransitionMarker));if(m&&start&&end)renderControlHandles(m,start,end)}}
function renderStage(){layer.innerHTML="";transitionPathsGroup.innerHTML="";customPathPreview.hidden=true;customPathPreview.setAttribute("d","");if(playbackMode){renderPlaybackStage();return}if(activeTransitionKey){renderTransitionStage();return}const f=active();if(!f)return;ensurePos(f);const pm=posMap(f),fallback=defaults(markerCount());for(let n=1;n<=markerCount();n++){let p=pm.get(n);if(!p){const q=fallback[n-1];p={marker:n,x:q.x,y:q.y};f.positions.push(p)}const a=assignFor(n),el=document.createElement("div");el.className=`board-marker shape-${a.shape||"circle"}`;el.dataset.marker=n;el.style.setProperty("--marker-color",a.color||"#2E3CF1");const num=document.createElement("span");num.textContent=n;el.appendChild(num);if(selectedMarker===n)el.classList.add("selected");setPos(el,p);dragMarker(el,n,p);el.addEventListener("click",()=>selectMarker(n,true));el.addEventListener("mouseenter",()=>showTip(el,n));el.addEventListener("mouseleave",()=>hideTip(el));el.addEventListener("dragover",e=>{if(draggedStudentId==null)return;e.preventDefault();el.classList.add("assignment-drop-target")});el.addEventListener("dragleave",()=>el.classList.remove("assignment-drop-target"));el.addEventListener("drop",e=>{e.preventDefault();el.classList.remove("assignment-drop-target");const sid=Number(e.dataTransfer.getData("text/student-id")||draggedStudentId);draggedStudentId=null;assignStudent(n,sid)});layer.appendChild(el)}}
function assignmentStudentsForDisplay(){const rows=data.students.map(s=>({student:s,assignment:Array.from(assignments.values()).find(a=>Number(a.student_id)===Number(s.id))||null})),mode=assignmentSort?.value||"alphabetical";if(mode==="marker"){return rows.sort((left,right)=>{const la=left.assignment,ra=right.assignment;if(la&&ra)return Number(la.marker)-Number(ra.marker);if(la)return-1;if(ra)return 1;return left.student.name.localeCompare(right.student.name,undefined,{sensitivity:"base"})})}return rows.sort((left,right)=>left.student.name.localeCompare(right.student.name,undefined,{sensitivity:"base"}))}
function renderAssignments(){assignmentList.innerHTML="";assignmentStudentsForDisplay().forEach(({student:s,assignment:a})=>{const row=document.createElement("div");row.className="assignment-student-row";if(!a){row.classList.add("unassigned");row.draggable=true;row.addEventListener("dragstart",e=>{draggedStudentId=Number(s.id);e.dataTransfer.setData("text/student-id",String(s.id));e.dataTransfer.effectAllowed="move"});row.addEventListener("dragend",()=>draggedStudentId=null)}const av=document.createElement("span");av.className="assignment-avatar";av.textContent=s.initials||s.name.slice(0,2).toUpperCase();const copy=document.createElement("span");copy.className="assignment-student-copy";const name=document.createElement("strong");name.textContent=s.name;const hint=document.createElement("span");hint.textContent=a?`Assigned to marker ${a.marker}`:"Drag onto a marker";copy.append(name,hint);row.append(av,copy);const actions=document.createElement("span");actions.className="assignment-row-actions";if(a){const b=document.createElement("button");b.type="button";b.className=`assignment-marker-badge shape-${a.shape||"circle"}`;b.style.setProperty("--marker-color",a.color||"#2E3CF1");b.title=`Go to marker ${a.marker}`;const n=document.createElement("span");n.textContent=a.marker;b.appendChild(n);b.addEventListener("click",()=>selectMarker(a.marker,true));const remove=document.createElement("button");remove.type="button";remove.className="assignment-unassign-button";remove.textContent="×";remove.title=`Unassign ${s.name} from marker ${a.marker}`;remove.setAttribute("aria-label",`Unassign ${s.name} from marker ${a.marker}`);remove.addEventListener("click",()=>unassignStudent(a.marker));actions.append(b,remove)}else{const available=document.createElement("span");available.className="assignment-available-label";available.textContent="Available";actions.appendChild(available)}row.appendChild(actions);assignmentList.appendChild(row)})}
function syncTransitions(){formations.sort((a,b)=>a.sequence_order-b.sequence_order||a.id-b.id);const valid=new Set();for(let i=0;i<formations.length-1;i++){const from=formations[i],to=formations[i+1],key=transitionKey(from.id,to.id);valid.add(key);ensureTransition(from,to)}transitions=transitions.filter(t=>valid.has(transitionKey(t.from_formation_id,t.to_formation_id)));if(activeTransitionKey&&!valid.has(activeTransitionKey))exitTransitionMode()}
function durationFromInputs(minutesInput,secondsInput,minSeconds=0){const minutes=Math.max(0,Number(minutesInput?.value)||0),seconds=Math.max(0,Math.min(59,Number(secondsInput?.value)||0));return Math.max(minSeconds,minutes*60+seconds)}
function setDurationInputs(minutesInput,secondsInput,total){const safe=Math.max(0,Number(total)||0);if(minutesInput)minutesInput.value=String(Math.floor(safe/60));if(secondsInput)secondsInput.value=String(Math.floor(safe%60)).padStart(2,"0")}
function updateSelectedFormationDurationUI(){const f=active();if(!f)return;if(selectedFormationName)selectedFormationName.value=f.name||"";if(selectedFormationStartTime)selectedFormationStartTime.textContent=formatFormationStart(formationStartSeconds(f.id));setDurationInputs(selectedFormationHoldMinutes,selectedFormationHoldSeconds,f.hold_duration_seconds)}
function updateSelectedFormationNameFromUI(){const f=active();if(!f||!selectedFormationName)return;const next=selectedFormationName.value.trim();f.name=next||`Formation ${f.sequence_order||1}`;selectedFormationName.value=f.name;renderTabs();markDirty("Formation name changed")}function updateSelectedFormationDurationFromUI(){const f=active();if(!f)return;f.hold_duration_seconds=durationFromInputs(selectedFormationHoldMinutes,selectedFormationHoldSeconds,0);markDirty("Formation length changed");renderTabs();renderPlaybackTicks();updateSelectedFormationDurationUI()}
function updateTransitionDurationFromUI(){const t=activeTransition(),pair=transitionFormations();if(!t||!pair.from)return;pair.from.hold_duration_seconds=durationFromInputs(formationHoldMinutes,formationHoldSeconds,0);t.duration_seconds=durationFromInputs(transitionDurationMinutes,transitionDurationSeconds,1);updateSelectedFormationDurationUI();updateTransitionPanel();markDirty("Transition timing changed");renderTabs();renderPlaybackTicks();maybeAutoPreview()}
function updateTransitionPanel(){const t=activeTransition(),pair=transitionFormations();if(!t||!pair.from||!pair.to)return;transitionName.textContent=`${pair.from.name} → ${pair.to.name}`;transitionTime.textContent=`Hold ${fmt(pair.from.hold_duration_seconds)} · Move ${fmt(t.duration_seconds)}`;timingTransitionName.textContent=`${pair.from.name} → ${pair.to.name}`;timingTransitionTime.textContent=`Hold ${fmt(pair.from.hold_duration_seconds)} · Move ${fmt(t.duration_seconds)}`;timingFormationLabel.textContent=pair.from.name;setDurationInputs(formationHoldMinutes,formationHoldSeconds,pair.from.hold_duration_seconds);setDurationInputs(transitionDurationMinutes,transitionDurationSeconds,t.duration_seconds);transitionTimingExampleText.textContent=`Hold ${pair.from.name} for ${fmt(pair.from.hold_duration_seconds)} → Move for ${fmt(t.duration_seconds)} → ${pair.to.name}`;if(!selectedTransitionMarker){movementEditor.hidden=true;return}const a=assignFor(selectedTransitionMarker),student=studentFor(a),m=movementForMarker(t,selectedTransitionMarker);transitionMarkerName.textContent=student?`Marker ${selectedTransitionMarker} · ${student.name}`:`Marker ${selectedTransitionMarker} · Unassigned`;movementEditor.hidden=false;document.querySelectorAll("[data-path-type]").forEach(b=>b.classList.toggle("active",!!m&&b.dataset.pathType===m.path_type));const adjustable=!!m&&["curve","angled"].includes(m.path_type);controlPointSetting.hidden=!adjustable;if(adjustable){controlPointLabel.textContent=m.path_type==="curve"?"Curve Points":"Angle Points";controlPointCount.textContent=String(m.control_point_count||1)}customPathInstruction.hidden=!customPathMode}
function enterTransitionMode(from,to){
    ensureTransition(from,to);
    activeTransitionKey=transitionKey(from.id,to.id);
    activeFormationId=from.id;
    selectedMarker=null;
    selectedTransitionMarker=null;
    movementSelectMode=false;
    customPathMode=false;
    customDrawing=false;
    customPoints=[];

    app.classList.add("transition-mode");if(transitionPreviewFooter)transitionPreviewFooter.hidden=false;
    transitionTab.hidden=false;
    timingTab.hidden=false;

    movementInstruction.hidden=true;
    movementEditor.hidden=true;
    
    
    customPathInstruction.hidden=true;

    stage.classList.remove(
        "transition-select-mode",
        "custom-path-mode"
    );

    activateTab("transition");
    updateTransitionPanel();
    renderTabs();
    renderStage();
}

function exitTransitionMode(){
    activeTransitionKey=null;
    selectedTransitionMarker=null;
    movementSelectMode=false;
    customPathMode=false;
    customDrawing=false;
    customPoints=[];

    stopPreview();

    app.classList.remove("transition-mode");if(transitionPreviewFooter)transitionPreviewFooter.hidden=true;
    stage.classList.remove(
        "transition-select-mode",
        "custom-path-mode"
    );

    transitionTab.hidden=true;
    timingTab.hidden=true;
    movementInstruction.hidden=true;
    movementEditor.hidden=true;
    
    
    customPathInstruction.hidden=true;
    customPathPreview.hidden=true;
    customPathPreview.setAttribute("d","");

    if(
        document.querySelector('[data-panel-tab="transition"].active')
        ||document.querySelector('[data-panel-tab="timing"].active')
    ){
        activateTab("information");
    }
}
function beginMovementSelection(){if(!activeTransitionKey)return;movementSelectMode=true;customPathMode=false;selectedTransitionMarker=null;movementInstruction.hidden=false;movementEditor.hidden=true;customPathInstruction.hidden=true;stage.classList.add("transition-select-mode");stage.classList.remove("custom-path-mode");renderStage()}
function setMovementPathType(type){const t=activeTransition();if(!t||!selectedTransitionMarker)return;const m=ensureMovement(t,selectedTransitionMarker),pair=transitionFormations(),start=pair.from?posMap(pair.from).get(Number(selectedTransitionMarker)):null,end=pair.to?posMap(pair.to).get(Number(selectedTransitionMarker)):null;m.path_type=type;if(["curve","angled"].includes(type)&&start&&end){m.control_point_count=Math.max(1,Number(m.control_point_count)||1);m.points=[];ensureControlPoints(m,start,end)}if(type==="straight"){m.points=[];customPathMode=false;stage.classList.remove("custom-path-mode");customPathInstruction.hidden=true}else if(type==="custom"){m.points=[];customPathMode=true;customPoints=[];stage.classList.add("custom-path-mode");customPathInstruction.hidden=false}else{customPathMode=false;stage.classList.remove("custom-path-mode");customPathInstruction.hidden=true}updateTransitionPanel();renderStage();markDirty("Movement path changed");maybeAutoPreview()}
function changeControlPointCount(delta){const t=activeTransition(),m=t&&selectedTransitionMarker?movementForMarker(t,selectedTransitionMarker):null,pair=transitionFormations();if(!m||!["curve","angled"].includes(m.path_type)||!pair.from||!pair.to)return;const start=posMap(pair.from).get(Number(selectedTransitionMarker)),end=posMap(pair.to).get(Number(selectedTransitionMarker));if(!start||!end)return;m.control_point_count=Math.max(1,Math.min(8,Number(m.control_point_count||1)+delta));m.points=defaultControlPoints(start,end,m.control_point_count);updateTransitionPanel();renderStage();markDirty("Control points changed");maybeAutoPreview()}
function removeMovement(){const t=activeTransition();if(!t||!selectedTransitionMarker)return;t.movements=(t.movements||[]).filter(m=>Number(m.marker)!==Number(selectedTransitionMarker));customPathMode=false;stage.classList.remove("custom-path-mode");customPathInstruction.hidden=true;updateTransitionPanel();renderTabs();renderStage();markDirty("Movement path removed")}
function customD(points){return(points||[]).map((p,i)=>`${i?"L":"M"} ${p.x} ${p.y}`).join(" ")}
function customStart(e){if(!customPathMode||!activeTransitionKey||!selectedTransitionMarker||e.button!==0)return;customDrawing=true;customPoints=[pointerPct(e.clientX,e.clientY)];customPathPreview.hidden=false;customPathPreview.setAttribute("d",customD(customPoints));stage.setPointerCapture(e.pointerId);e.preventDefault()}
function customMove(e){if(!customDrawing)return;const p=pointerPct(e.clientX,e.clientY),last=customPoints[customPoints.length-1];if(Math.abs(p.x-last.x)+Math.abs(p.y-last.y)<.7)return;customPoints.push(p);customPathPreview.setAttribute("d",customD(customPoints))}
function customEnd(e){if(!customDrawing)return;customDrawing=false;try{stage.releasePointerCapture(e.pointerId)}catch{}const t=activeTransition();if(t&&selectedTransitionMarker&&customPoints.length>1){const m=ensureMovement(t,selectedTransitionMarker);m.path_type="custom";m.points=customPoints.slice(1,-1).filter((_,i)=>i%2===0).slice(0,250);markDirty("Custom movement path drawn")}customPoints=[];customPathPreview.hidden=true;customPathPreview.setAttribute("d","");customPathMode=false;stage.classList.remove("custom-path-mode");customPathInstruction.hidden=true;updateTransitionPanel();renderTabs();renderStage()}
function formationStartSeconds(formationId){const schedule=choreographySchedule(),segment=schedule.segments.find(row=>row.type==="hold"&&Number(row.formation.id)===Number(formationId));return segment?Math.max(0,Number(segment.start)||0):0}
function formatFormationStart(seconds){seconds=Math.max(0,Math.floor(Number(seconds)||0));const minutes=Math.floor(seconds/60),secs=seconds%60;return`${minutes}:${String(secs).padStart(2,"0")}`}
function renderTabs(){
    tabs.innerHTML="";
    syncTransitions();

    formations.forEach((f,index)=>{
        const w=document.createElement("div");
        w.className="formation-tab-wrap";

        const b=document.createElement("button");
        b.type="button";
        b.dataset.formationId=String(f.id);
        b.className="formation-tab"
            +(!activeTransitionKey&&!playbackMode&&f.id===activeFormationId
                ?" active"
                :"");

        const n=document.createElement("strong");
        n.textContent=f.name;

        const tm=document.createElement("span");
        tm.textContent=`Start ${formatFormationStart(formationStartSeconds(f.id))}`;

        b.append(n,tm);

        b.addEventListener("click",()=>{
            if(playbackMode)exitPlayback();
            exitTransitionMode();
            activeFormationId=f.id;
            selectedMarker=null;
            activateTab("options");
            renderTabs();
            renderStage();
            updateFormat();
            updateSelectedFormationDurationUI();
        });

        w.appendChild(b);

        if(formations.length>1){
            const x=document.createElement("button");
            x.type="button";
            x.className="formation-tab-delete";
            x.textContent="×";
            x.title=`Delete ${f.name}`;

            x.addEventListener("click",e=>{
                e.stopPropagation();
                openDeleteModal(f);
            });

            w.appendChild(x);
        }

        tabs.appendChild(w);

        if(index<formations.length-1){
            const next=formations[index+1],
                key=transitionKey(f.id,next.id),
                tr=transitionByKey(key),
                tb=document.createElement("button");

            tb.type="button";
            tb.className="transition-tab-button"
                +(activeTransitionKey===key?" active":"")
                +(tr?.movements?.length?" has-movements":"");

            tb.textContent="↝";
            tb.title=`Transition: ${f.name} → ${next.name}`;

            tb.addEventListener("click",()=>{
                if(playbackMode)exitPlayback();
                enterTransitionMode(f,next);
            });

            tabs.appendChild(tb);
        }
    });
}
function openDeleteModal(f){pendingDeleteFormationId=f.id;deleteModalName.textContent=f.name;deleteModalError.hidden=true;deleteModal.hidden=false}function closeDeleteModal(){pendingDeleteFormationId=null;deleteModal.hidden=true}async function deleteFormation(){if(pendingDeleteFormationId===null)return;const id=pendingDeleteFormationId,url=deleteUrlTemplate.replace("999999",String(id));deleteModalConfirm.disabled=true;deleteModalConfirm.textContent="Deleting…";try{const r=await fetch(url,{method:"POST",headers:{"X-CSRFToken":csrf()}}),j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||"Could not delete formation.");formations=formations.filter(f=>f.id!==id).sort((a,b)=>a.time_seconds-b.time_seconds||a.id-b.id);if(activeFormationId===id)activeFormationId=formations[0]?.id||null;closeDeleteModal();exitTransitionMode();renderTabs();renderStage();updateFormat();markDirty("Formation deleted")}catch(e){deleteModalError.textContent=e.message;deleteModalError.hidden=false}finally{deleteModalConfirm.disabled=false;deleteModalConfirm.textContent="Delete Formation"}}
function updateFormat(){if(!selectedMarker){formatTitle.textContent="Select a marker";formatHelp.textContent="Click a stage marker to change its shape or color.";formatControls.hidden=true;return}const a=assignFor(selectedMarker),s=studentFor(a);formatTitle.textContent=s?`Marker ${selectedMarker} · ${s.name}`:`Marker ${selectedMarker} · Unassigned`;formatHelp.textContent="Formatting stays with this marker through every formation.";formatControls.hidden=false;document.querySelectorAll("[data-shape]").forEach(b=>b.classList.toggle("active",b.dataset.shape===a.shape));document.querySelectorAll("[data-color]").forEach(b=>b.classList.toggle("active",b.dataset.color.toUpperCase()===a.color.toUpperCase()));customColor.value=a.color||"#2E3CF1"}
function setShape(shape){if(!selectedMarker)return;const a=assignFor(selectedMarker);a.shape=shape;assignments.set(selectedMarker,a);renderStage();renderAssignments();updateFormat();markDirty("Marker format changed")}function setColor(color){if(!selectedMarker||!/^#[0-9A-Fa-f]{6}$/.test(color))return;const a=assignFor(selectedMarker);a.color=color.toUpperCase();assignments.set(selectedMarker,a);renderStage();renderAssignments();updateFormat();markDirty("Marker color changed")}
function activateTab(name){document.querySelectorAll("[data-panel-tab]").forEach(b=>b.classList.toggle("active",b.dataset.panelTab===name));document.querySelectorAll("[data-panel-content]").forEach(c=>c.hidden=c.dataset.panelContent!==name)
;if(window.EncoreStageDrawing&&window.EncoreStageDrawing.setPanelActive){window.EncoreStageDrawing.setPanelActive(name==="draw")}
}
function renderDanceOptions(){
    danceSelect.innerHTML="";
    const none=document.createElement("option");
    none.value="";
    none.textContent="No Dance Assigned";
    danceSelect.appendChild(none);
    data.dances.forEach(d=>{
        const option=document.createElement("option");
        option.value=String(d.id);
        option.textContent=d.title;
        danceSelect.appendChild(option);
    });
    danceSelect.value=data.selected_dance_id?String(data.selected_dance_id):"";
}
function renderSongOptions(){
    songSelect.innerHTML="";
    const none=document.createElement("option");
    none.value="";
    none.textContent="No Music Yet";
    songSelect.appendChild(none);
    data.songs.forEach(s=>{
        const option=document.createElement("option");
        option.value=String(s.id);
        option.textContent=s.artist?`${s.title} · ${s.artist}`:s.title;
        songSelect.appendChild(option);
    });
    songSelect.value=data.selected_song_id?String(data.selected_song_id):"";
    addSongButton.disabled=!data.selected_dance_id;
}
function selectedDance(){
    return data.dances.find(d=>Number(d.id)===Number(data.selected_dance_id))||null;
}
function selectedSong(){
    return data.songs.find(s=>Number(s.id)===Number(data.selected_song_id))||null;
}
function refreshSongLengthState(){
    const song=selectedSong();
    const locked=Boolean(song&&Number(song.duration_seconds)>0);
    songMinutes.disabled=locked;
    songSeconds.disabled=locked;
    songLengthHelp.textContent=locked
        ?"Song length is coming from the selected uploaded song."
        :"With no timed music selected, enter the song length manually.";
}
function syncDanceToSong(){
    const dance=selectedDance();
    data.selected_song_id=dance&&dance.song_id?Number(dance.song_id):null;
    if(dance&&Number(dance.song_duration_seconds)>0){
        setSong(Number(dance.song_duration_seconds));
    }
    renderSongOptions();
    refreshSongLengthState();
    danceDisplay.textContent=dance?dance.title:"No Dance Assigned";
}
async function saveInformation(){
    const body={
        title:titleInput.value.trim(),
        dance_id:data.selected_dance_id||null,
        song_id:data.selected_song_id||null,
        song_duration_seconds:songLen()
    };
    try{
        const r=await fetch(informationSaveUrl,{
            method:"POST",
            headers:{"Content-Type":"application/json","X-CSRFToken":csrf()},
            body:JSON.stringify(body)
        });
        const j=await r.json();
        if(!r.ok||!j.ok)throw new Error(j.error||"Could not save information.");
        titleDisplay.textContent=j.board.title;
        data.selected_dance_id=j.board.dance_id;
        data.selected_song_id=j.board.song_id;
        setSong(j.board.song_duration_seconds||0);
        renderDanceOptions();
        renderSongOptions();
        refreshSongLengthState();
        markSaved();
    }catch(e){
        markError(e.message||"Information not saved");
    }
}
function openDanceModal(){
    danceError.hidden=true;
    danceError.textContent="";
    danceTitle.value="";
    danceSongTitle.value="";
    danceArtist.value="";
    danceChoreo.value="";
    danceTeacherNotes.value="";
    dancePerformanceNotes.value="";
    danceModal.hidden=false;
    setTimeout(()=>danceTitle.focus(),30);
}
function closeDanceModal(){danceModal.hidden=true}
async function createDance(){
    danceError.hidden=true;
    danceSave.disabled=true;
    danceSave.textContent="Saving…";
    try{
        const r=await fetch(danceAddUrl,{
            method:"POST",
            headers:{"Content-Type":"application/json","X-CSRFToken":csrf()},
            body:JSON.stringify({
                title:danceTitle.value.trim(),
                song_title:danceSongTitle.value.trim(),
                artist:danceArtist.value.trim(),
                choreography_notes:danceChoreo.value.trim(),
                teacher_notes:danceTeacherNotes.value.trim(),
                performance_notes:dancePerformanceNotes.value.trim()
            })
        });
        const j=await r.json();
        if(!r.ok||!j.ok)throw new Error(j.error||"Could not create Dance.");
        data.dances.push(j.dance);
        data.selected_dance_id=Number(j.dance.id);
        data.selected_song_id=null;
        closeDanceModal();
        renderDanceOptions();
        syncDanceToSong();
        markDirty("Dance created");
        await saveInformation();
    }catch(e){
        danceError.textContent=e.message;
        danceError.hidden=false;
    }finally{
        danceSave.disabled=false;
        danceSave.textContent="Save Dance";
    }
}
function openSongModal(){
    if(!data.selected_dance_id)return;
    songError.hidden=true;
    songError.textContent="";
    newSongTitle.value="";
    newSongArtist.value="";
    newSongFile.value="";
    newSongUrl.value="";
    newSongMinutes.value="0";
    newSongSeconds.value="00";
    newSongDescription.value="";
    songModal.hidden=false;
    setTimeout(()=>newSongTitle.focus(),30);
}
function closeSongModal(){songModal.hidden=true}
async function createSong(){
    songError.hidden=true;
    songSave.disabled=true;
    songSave.textContent="Saving…";
    try{
        const fd=new FormData();
        fd.append("title",newSongTitle.value.trim());
        fd.append("artist",newSongArtist.value.trim());
        fd.append("external_url",newSongUrl.value.trim());
        fd.append("duration_minutes",String(Math.max(0,Number(newSongMinutes.value)||0)));
        fd.append("duration_seconds",String(Math.max(0,Math.min(59,Number(newSongSeconds.value)||0))));
        fd.append("description",newSongDescription.value.trim());
        if(newSongFile.files[0])fd.append("file",newSongFile.files[0]);
        const r=await fetch(songAddUrl,{
            method:"POST",
            headers:{"X-CSRFToken":csrf()},
            body:fd
        });
        const j=await r.json();
        if(!r.ok||!j.ok)throw new Error(j.error||"Could not add song.");
        data.songs.push(j.song);
        data.selected_song_id=Number(j.song.id);
        const dance=selectedDance();
        if(dance){
            dance.song_id=Number(j.song.id);
            dance.song_title=j.song.title;
            dance.song_duration_seconds=Number(j.song.duration_seconds)||0;
        }
        if(Number(j.song.duration_seconds)>0)setSong(Number(j.song.duration_seconds));
        closeSongModal();
        renderSongOptions();
        refreshSongLengthState();
        markDirty("Song added");
        await saveInformation();
    }catch(e){
        songError.textContent=e.message;
        songError.hidden=false;
    }finally{
        songSave.disabled=false;
        songSave.textContent="Save Song";
    }
}

function selectedTransitionMovement(){const t=activeTransition();return t&&selectedTransitionMarker?movementForMarker(t,selectedTransitionMarker):null}
function stopPreview(){previewRunning=false;if(previewFrame){cancelAnimationFrame(previewFrame);previewFrame=null}if(previewTimer){clearTimeout(previewTimer);previewTimer=null}app.classList.remove("preview-mode");previewStatus.hidden=true}
function previewSelectedMovement(){stopPreview();const t=activeTransition(),pair=transitionFormations();if(!t||!pair.from||!pair.to)return;renderStage();const duration=Math.max(1,Number(t.duration_seconds)||3)*1000,started=performance.now();app.classList.add("preview-mode");previewStatus.hidden=false;previewRunning=true;const fm=posMap(pair.from),tm=posMap(pair.to),previewMarkers=new Map();for(let marker=1;marker<=markerCount();marker++){const el=Array.from(layer.querySelectorAll(".board-marker.transition-start-marker")).find(x=>Number(x.dataset.marker)===marker);if(el){el.classList.add("preview-marker");previewMarkers.set(marker,el)}}const frame=now=>{if(!previewRunning)return;const progress=Math.min(1,(now-started)/duration);for(const [marker,el] of previewMarkers){const start=fm.get(marker),end=tm.get(marker)||start;if(!start||!end)continue;const movement=movementForPlayback(t,marker);setPos(el,playbackPoint(movement,start,end,progress))}if(progress>=1){previewRunning=false;previewFrame=null;previewTimer=setTimeout(()=>{app.classList.remove("preview-mode");previewStatus.hidden=true;renderStage()},300);return}previewFrame=requestAnimationFrame(frame)};previewFrame=requestAnimationFrame(frame)}
function maybeAutoPreview(){if(!autoPreview.checked)return;if(previewTimer)clearTimeout(previewTimer);previewTimer=setTimeout(previewSelectedMovement,120)}
function sortedFormations(){return formations.slice().sort((a,b)=>a.sequence_order-b.sequence_order||a.id-b.id)}
function transitionForPair(fromId,toId){return transitions.find(tr=>Number(tr.from_formation_id)===Number(fromId)&&Number(tr.to_formation_id)===Number(toId))||{from_formation_id:Number(fromId),to_formation_id:Number(toId),duration_seconds:3,movements:[]}}
function movementForPlayback(tr,marker){return(tr.movements||[]).find(m=>Number(m.marker)===Number(marker))||normalizeMovement({marker:Number(marker),path_type:"straight",points:[],control_point_count:1})}
function lerp(a,b,t){return a+(b-a)*t}
function pointAlongPolyline(points,t){if(!points.length)return{x:0,y:0};if(points.length===1)return points[0];const lengths=[];let total=0;for(let i=0;i<points.length-1;i++){const dx=points[i+1].x-points[i].x,dy=points[i+1].y-points[i].y,len=Math.sqrt(dx*dx+dy*dy);lengths.push(len);total+=len}if(total<=0)return points[points.length-1];let target=Math.max(0,Math.min(1,t))*total;for(let i=0;i<lengths.length;i++){if(target<=lengths[i]||i===lengths.length-1){const local=lengths[i]?target/lengths[i]:0;return{x:lerp(points[i].x,points[i+1].x,local),y:lerp(points[i].y,points[i+1].y,local)}}target-=lengths[i]}return points[points.length-1]}
function playbackPoint(movement,start,end,t){return pointAlongPolyline(movementPolyline(movement,start,end),Math.max(0,Math.min(1,t)))}
function choreographySchedule(){const fs=sortedFormations(),segments=[];let cursor=0;if(!fs.length)return{segments,total:0,formations:[]};for(let i=0;i<fs.length;i++){const formation=fs[i],hold=Math.max(0,Number(formation.hold_duration_seconds)||0),holdStart=cursor,holdEnd=cursor+hold;segments.push({type:"hold",formation,start:holdStart,end:holdEnd});cursor=holdEnd;if(i<fs.length-1){const next=fs[i+1],transition=transitionForPair(formation.id,next.id),move=Math.max(1,Number(transition.duration_seconds)||3),moveStart=cursor,moveEnd=cursor+move;segments.push({type:"transition",from:formation,to:next,transition,start:moveStart,end:moveEnd});cursor=moveEnd}}return{segments,total:cursor,formations:fs}}
function playbackDuration(){const schedule=choreographySchedule(),configured=songLen();return Math.max(schedule.total,configured,1)}
function playbackSegment(time){const schedule=choreographySchedule();if(!schedule.formations.length)return null;for(const segment of schedule.segments){if(time>=segment.start&&time<segment.end){if(segment.type==="hold")return{type:"hold",from:segment.formation,to:segment.formation,progress:0,segment};const span=Math.max(.001,segment.end-segment.start);return{type:"transition",from:segment.from,to:segment.to,progress:(time-segment.start)/span,segment}}}const last=schedule.formations[schedule.formations.length-1];return{type:"hold",from:last,to:last,progress:0,segment:null}}
function renderPlaybackStage(){layer.innerHTML="";transitionPathsGroup.innerHTML="";const seg=playbackSegment(playbackTime);if(!seg)return;ensurePos(seg.from);ensurePos(seg.to);const fm=posMap(seg.from),tm=posMap(seg.to),tr=transitionForPair(seg.from.id,seg.to.id);for(let marker=1;marker<=markerCount();marker++){const start=fm.get(marker),end=tm.get(marker)||start;if(!start||!end)continue;const movement=movementForPlayback(tr,marker),point=seg.from.id===seg.to.id?start:playbackPoint(movement,start,end,seg.progress),a=assignFor(marker),el=document.createElement("div");el.className=`board-marker shape-${a.shape||"circle"} playback-marker`;el.dataset.marker=marker;el.style.setProperty("--marker-color",a.color||"#2E3CF1");const num=document.createElement("span");num.textContent=marker;el.appendChild(num);setPos(el,point);el.addEventListener("mouseenter",()=>showTip(el,marker));el.addEventListener("mouseleave",()=>hideTip(el));layer.appendChild(el)}document.querySelectorAll(".formation-tab-wrap").forEach(w=>w.classList.remove("playback-active-formation"));const activeId=seg.progress>=.999?seg.to.id:seg.from.id;tabs.querySelectorAll(".formation-tab").forEach(b=>{if(Number(b.dataset.formationId)===Number(activeId))b.parentElement.classList.add("playback-active-formation")})}
function updatePlaybackUI(){if(window.EncoreLighting&&window.EncoreLighting.onPlaybackTime)window.EncoreLighting.onPlaybackTime(playbackTime,playbackMode);const duration=playbackDuration();playbackTime=Math.max(0,Math.min(duration,playbackTime));playbackScrubber.max=String(duration);playbackScrubber.value=String(playbackTime);playbackCurrentTime.textContent=fmt(playbackTime);playbackTotalTime.textContent=fmt(duration);playbackToggle.textContent=playbackPlaying?"❚❚":"▶";playbackToggle.setAttribute("aria-label",playbackPlaying?"Pause choreography":"Play choreography");if(playbackMode)renderPlaybackStage()}
function renderPlaybackTicks(){playbackFormationMarkers.innerHTML="";const duration=playbackDuration(),schedule=choreographySchedule();let cursor=0;schedule.formations.forEach((f,index)=>{const tick=document.createElement("span");tick.className="playback-formation-tick";tick.style.left=`${Math.max(0,Math.min(100,(cursor/duration)*100))}%`;tick.dataset.label=`${f.name} · ${fmt(cursor)}`;playbackFormationMarkers.appendChild(tick);cursor+=Math.max(0,Number(f.hold_duration_seconds)||0);if(index<schedule.formations.length-1){const tr=transitionForPair(f.id,schedule.formations[index+1].id);cursor+=Math.max(1,Number(tr.duration_seconds)||3)}});playbackScrubber.max=String(duration);playbackTotalTime.textContent=fmt(duration)}
function selectedPlaybackSong(){return selectedSong()}
function syncAudioSource(){const song=selectedPlaybackSong(),url=song?.playback_url||"";if(!url){if(drawingBoardAudio.getAttribute("src")){drawingBoardAudio.pause();drawingBoardAudio.removeAttribute("src");drawingBoardAudio.load()}return false}if(drawingBoardAudio.getAttribute("src")!==url){drawingBoardAudio.pause();drawingBoardAudio.src=url;drawingBoardAudio.load()}return true}
function musicPlaybackEnabled(){return Boolean(playMusicWithPlayback?.checked&&syncAudioSource())}
function setAudioTime(time){if(!drawingBoardAudio.getAttribute("src"))return;try{drawingBoardAudio.currentTime=Math.max(0,Number(time)||0)}catch{}}
function playbackLoop(now){if(!playbackPlaying)return;if(musicPlaybackEnabled()&&!drawingBoardAudio.paused&&!Number.isNaN(drawingBoardAudio.currentTime)){playbackTime=drawingBoardAudio.currentTime}else{playbackTime=playbackStartedFrom+(now-playbackStartedAt)/1000}const duration=playbackDuration();if(playbackTime>=duration){playbackTime=duration;playbackPlaying=false;playbackFrame=null;drawingBoardAudio.pause();updatePlaybackUI();return}updatePlaybackUI();playbackFrame=requestAnimationFrame(playbackLoop)}
function enterPlayback(){if(activeTransitionKey)exitTransitionMode();playbackMode=true;app.classList.add("playback-mode");playbackExit.hidden=false;renderTabs();renderPlaybackTicks();updatePlaybackUI()}
function pausePlayback(){playbackPlaying=false;if(playbackFrame){cancelAnimationFrame(playbackFrame);playbackFrame=null}drawingBoardAudio.pause();updatePlaybackUI()}
function pausePlaybackForEditing(){if(!playbackMode&&!playbackPlaying)return;pausePlayback();playbackMode=false;app.classList.remove("playback-mode");playbackExit.hidden=true;renderTabs();renderStage();updateFormat();if(window.EncoreLighting&&window.EncoreLighting.onPlaybackTime)window.EncoreLighting.onPlaybackTime(playbackTime,false)}
async function playPlayback(){if(!playbackMode)enterPlayback();const duration=playbackDuration();if(playbackTime>=duration)playbackTime=0;playbackPlaying=true;playbackStartedFrom=playbackTime;playbackStartedAt=performance.now();if(musicPlaybackEnabled()){setAudioTime(playbackTime);try{await drawingBoardAudio.play();playbackStartedAt=performance.now();playbackStartedFrom=playbackTime}catch(error){console.warn("Music playback could not start.",error);drawingBoardAudio.pause();playbackStartedAt=performance.now();playbackStartedFrom=playbackTime}}updatePlaybackUI();playbackFrame=requestAnimationFrame(playbackLoop)}
function togglePlayback(){if(playbackPlaying)pausePlaybackForEditing();else playPlayback()}
function exitPlayback(){pausePlaybackForEditing()}
function openModal(){modalError.hidden=true;modalError.textContent="";modalName.value="";modalMinute.value="0";modalSecond.value="08";modal.hidden=false;setTimeout(()=>modalName.focus(),30)}function closeModal(){modal.hidden=true}
async function addFormation(){modalError.hidden=true;const holdDuration=(Math.max(0,Number(modalMinute.value)||0)*60)+Math.max(0,Math.min(59,Number(modalSecond.value)||0));modalSave.disabled=true;modalSave.textContent="Adding…";try{const r=await fetch(addFormationUrl,{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":csrf()},body:JSON.stringify({name:modalName.value.trim(),hold_duration_seconds:holdDuration,copy_from:modalCopy.checked&&active()?active().id:null})}),j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||"Could not add formation.");const f={...j.formation,id:Number(j.formation.id),sequence_order:formations.length+1,time_seconds:Number(j.formation.time_seconds||0),hold_duration_seconds:Math.max(0,Number(j.formation.hold_duration_seconds??8)),positions:(j.formation.positions||[]).map(p=>({marker:Number(p.marker),x:Number(p.x),y:Number(p.y)}))};if(!f.positions.length)f.positions=defaults(markerCount());formations.push(f);activeFormationId=f.id;selectedMarker=null;closeModal();renderTabs();renderStage();updateFormat();updateSelectedFormationDurationUI();renderPlaybackTicks();markDirty("Formation added")}catch(e){modalError.textContent=e.message;modalError.hidden=false}finally{modalSave.disabled=false;modalSave.textContent="Add Formation"}}

decreaseControlPoints.addEventListener("click",()=>changeControlPointCount(-1));increaseControlPoints.addEventListener("click",()=>changeControlPointCount(1));formationHoldMinutes.addEventListener("change",updateTransitionDurationFromUI);formationHoldSeconds.addEventListener("change",updateTransitionDurationFromUI);transitionDurationMinutes.addEventListener("change",updateTransitionDurationFromUI);transitionDurationSeconds.addEventListener("change",updateTransitionDurationFromUI);if(selectedFormationName){selectedFormationName.addEventListener("input",()=>{const f=active();if(!f)return;f.name=selectedFormationName.value;renderTabs();markDirty("Formation name changed")});selectedFormationName.addEventListener("change",updateSelectedFormationNameFromUI);}selectedFormationHoldMinutes.addEventListener("change",updateSelectedFormationDurationFromUI);selectedFormationHoldSeconds.addEventListener("change",updateSelectedFormationDurationFromUI);previewMovementButton.addEventListener("click",previewSelectedMovement);playMusicWithPlayback.addEventListener("change",()=>{if(!playMusicWithPlayback.checked)drawingBoardAudio.pause();else syncAudioSource()});document.querySelectorAll("[data-path-type]").forEach(b=>b.addEventListener("click",()=>setMovementPathType(b.dataset.pathType)));addMovementButton.addEventListener("click",beginMovementSelection);removeMovementButton.addEventListener("click",removeMovement);showTransitionPaths.addEventListener("change",renderStage);stage.addEventListener("pointerdown",customStart);stage.addEventListener("pointermove",customMove);stage.addEventListener("pointerup",customEnd);stage.addEventListener("pointercancel",customEnd);playbackToggle.addEventListener("click",togglePlayback);playbackRestart.addEventListener("click",()=>{if(!playbackMode)enterPlayback();pausePlayback();playbackTime=0;setAudioTime(0);updatePlaybackUI()});playbackScrubber.addEventListener("input",()=>{if(!playbackMode)enterPlayback();pausePlayback();playbackTime=Number(playbackScrubber.value)||0;setAudioTime(playbackTime);updatePlaybackUI()});playbackExit.addEventListener("click",exitPlayback);deleteModalClose.addEventListener("click",closeDeleteModal);deleteModalCancel.addEventListener("click",closeDeleteModal);deleteModalConfirm.addEventListener("click",deleteFormation);deleteModal.addEventListener("click",e=>{if(e.target===deleteModal)closeDeleteModal()});
document.querySelectorAll("[data-panel-tab]").forEach(b=>b.addEventListener("click",()=>activateTab(b.dataset.panelTab)));document.querySelectorAll("[data-shape]").forEach(b=>b.addEventListener("click",()=>setShape(b.dataset.shape)));document.querySelectorAll("[data-color]").forEach(b=>b.addEventListener("click",()=>setColor(b.dataset.color)));customColor.addEventListener("input",()=>setColor(customColor.value));showWings.checked=Boolean(data.show_offstage_wings);if(assignmentSort){const savedAssignmentSort=window.localStorage.getItem("encoreDrawingBoardAssignmentSort");if(savedAssignmentSort==="marker"||savedAssignmentSort==="alphabetical")assignmentSort.value=savedAssignmentSort;assignmentSort.addEventListener("change",()=>{window.localStorage.setItem("encoreDrawingBoardAssignmentSort",assignmentSort.value);renderAssignments()})}showWings.addEventListener("change",()=>{applyWings();markDirty("Stage options changed")});if(apronStageGrid){apronStageGrid.checked=Boolean(data.apron_stage_grid);apronStageGrid.addEventListener("change",()=>{applyWings();markDirty("Stage grid changed")});}titleInput.addEventListener("input",()=>{titleDisplay.textContent=titleInput.value.trim()||"Untitled Drawing Board";markDirty("Board name changed")});danceSelect.addEventListener("change",()=>{data.selected_dance_id=danceSelect.value?Number(danceSelect.value):null;syncDanceToSong();markDirty("Dance changed");saveInformation()});songSelect.addEventListener("change",()=>{data.selected_song_id=songSelect.value?Number(songSelect.value):null;const song=selectedSong();if(song&&Number(song.duration_seconds)>0)setSong(Number(song.duration_seconds));refreshSongLengthState();syncAudioSource();markDirty("Song changed");saveInformation()});[songMinutes,songSeconds].forEach(i=>i.addEventListener("change",()=>{setSong(songLen());markDirty("Song length changed");saveInformation()}));createDanceButton.addEventListener("click",openDanceModal);danceModalClose.addEventListener("click",closeDanceModal);danceModalCancel.addEventListener("click",closeDanceModal);danceSave.addEventListener("click",createDance);addSongButton.addEventListener("click",openSongModal);songModalClose.addEventListener("click",closeSongModal);songModalCancel.addEventListener("click",closeSongModal);songSave.addEventListener("click",createSong);collapsePanelButton.addEventListener("click",()=>{app.classList.add("panel-collapsed");expandPanelButton.hidden=false});expandPanelButton.addEventListener("click",()=>{app.classList.remove("panel-collapsed");expandPanelButton.hidden=true});addFormationButton.addEventListener("click",openModal);modalClose.addEventListener("click",closeModal);modalCancel.addEventListener("click",closeModal);modalSave.addEventListener("click",addFormation);modal.addEventListener("click",e=>{if(e.target===modal)closeModal()});document.addEventListener("keydown",e=>{if(e.key!=="Escape")return;if(playbackMode){exitPlayback();return}if(customPathMode){customPathMode=false;customDrawing=false;customPoints=[];stage.classList.remove("custom-path-mode");customPathInstruction.hidden=true;customPathPreview.hidden=true;customPathPreview.setAttribute("d","");updateTransitionPanel();return}if(movementSelectMode){movementSelectMode=false;movementInstruction.hidden=true;stage.classList.remove("transition-select-mode");renderStage();return}if(!modal.hidden){closeModal();return}if(!danceModal.hidden){closeDanceModal();return}if(!songModal.hidden){closeSongModal();return}if(activeTransitionKey){exitTransitionMode();renderTabs();renderStage();return}});document.addEventListener("pointerdown",event=>{if(!playbackPlaying)return;const target=event.target;if(!(target instanceof Element))return;if(target.closest("#playback-toggle,#playback-restart,#playback-scrubber,#playback-exit,.drawing-playback-bar"))return;if(!target.closest("#formation-board-app"))return;pausePlaybackForEditing()},true);if(stageZoomOut)stageZoomOut.addEventListener("click",()=>setStageZoom(stageZoom-STAGE_ZOOM_STEP));
if(stageZoomIn)stageZoomIn.addEventListener("click",()=>setStageZoom(stageZoom+STAGE_ZOOM_STEP));
if(stageZoomReset)stageZoomReset.addEventListener("click",resetStageView);
if(stageViewport){stageViewport.addEventListener("wheel",event=>{if(!(event.ctrlKey||event.metaKey))return;event.preventDefault();setStageZoom(stageZoom+(event.deltaY<0?STAGE_ZOOM_STEP:-STAGE_ZOOM_STEP))},{passive:false})}
saveButton.addEventListener("click",()=>saveBoard(true));document.addEventListener("focusin",event=>{if(!playbackPlaying)return;const target=event.target;if(!(target instanceof Element))return;if(!target.closest("#formation-board-app"))return;if(target.closest(".drawing-playback-bar"))return;pausePlaybackForEditing()},true);window.addEventListener("beforeunload",e=>{if(!dirty)return;e.preventDefault();e.returnValue=""});
ensureAssignments();formations.forEach(ensurePos);syncTransitions();setSong(data.song_duration_seconds);titleInput.value=data.board_title||titleInput.value;titleDisplay.textContent=titleInput.value;renderDanceOptions();renderSongOptions();syncDanceToSong();refreshSongLengthState();applyWings();renderAssignments();renderTabs();renderPlaybackTicks();renderStage();updateFormat();updateSelectedFormationDurationUI();syncAudioSource();resetStageView();playbackTime=0;updatePlaybackUI();markSaved();

/* ================================
   Encore Lighting Design V1
   ================================ */
(() => {
    const lightingLayer = document.getElementById("lighting-layer");
    const lightingToggle = document.getElementById("lighting-mode-toggle");
    const simpleModeButton = document.getElementById("lighting-simple-mode");
    const proModeButton = document.getElementById("lighting-pro-mode");
    const simpleLightingControls = document.getElementById("simple-lighting-controls");
    const proLightingControls = document.getElementById("pro-lighting-controls");
    const proFixtureList = document.getElementById("pro-fixture-list");
    const fixtureAddUrl = app.dataset.lightingFixtureAddUrl;
    const fixtureDeleteUrlTemplate = app.dataset.lightingFixtureDeleteUrlTemplate;
    const lookTab = document.getElementById("lighting-look-tab");
    const cueTab = document.getElementById("lighting-cue-tab");
    const outputTab = document.getElementById("lighting-output-tab");
    const cueTabsShell = document.getElementById("lighting-cue-tabs-shell");
    const cueTabs = document.getElementById("lighting-cue-tabs");
    const addCueButton = document.getElementById("add-lighting-cue");

    const addFocusButton = document.getElementById("add-focus-area");
    const blackoutShortcut = document.getElementById("add-blackout-cue-shortcut");
    const focusList = document.getElementById("lighting-focus-list");
    const focusEditor = document.getElementById("lighting-focus-editor");
    const focusName = document.getElementById("lighting-focus-name");
    const focusColor = document.getElementById("lighting-focus-color");
    const focusIntensity = document.getElementById("lighting-focus-intensity");
    const intensityValue = document.getElementById("lighting-intensity-value");
    const focusSoftness = document.getElementById("lighting-focus-softness");
    const softnessValue = document.getElementById("lighting-softness-value");
    const focusShape = document.getElementById("lighting-focus-shape");
    const focusWidth = document.getElementById("lighting-focus-width");
    const widthValue = document.getElementById("lighting-width-value");
    const focusHeight = document.getElementById("lighting-focus-height");
    const heightValue = document.getElementById("lighting-height-value");
    const removeFocusButton = document.getElementById("remove-focus-area");

    const addFollowButton = document.getElementById("add-follow-spot");
    const followList = document.getElementById("lighting-follow-list");
    const followEditor = document.getElementById("lighting-follow-editor");
    const followName = document.getElementById("lighting-follow-name");
    const followTargetType = document.getElementById("lighting-follow-target-type");
    const followMarkerWrap = document.getElementById("lighting-follow-marker-wrap");
    const followMarker = document.getElementById("lighting-follow-marker");
    const followPositionHelp = document.getElementById("lighting-follow-position-help");
    const followColor = document.getElementById("lighting-follow-color");
    const followIntensity = document.getElementById("lighting-follow-intensity");
    const followIntensityValue = document.getElementById("lighting-follow-intensity-value");
    const followSize = document.getElementById("lighting-follow-size");
    const followSizeValue = document.getElementById("lighting-follow-size-value");
    const followSoftness = document.getElementById("lighting-follow-softness");
    const followSoftnessValue = document.getElementById("lighting-follow-softness-value");
    const removeFollowButton = document.getElementById("remove-follow-spot");

    const cueName = document.getElementById("lighting-cue-name");
    const cueMinute = document.getElementById("lighting-cue-minute");
    const cueSecond = document.getElementById("lighting-cue-second");
    const cueFade = document.getElementById("lighting-cue-fade");
    const cueBlackout = document.getElementById("lighting-cue-blackout");
    const cueNotes = document.getElementById("lighting-cue-notes");
    const cueSummaryName = document.getElementById("lighting-cue-summary-name");
    const cueSummaryTime = document.getElementById("lighting-cue-summary-time");

    const outputSheet = document.getElementById("lighting-output-sheet");
    const copyOutputButton = document.getElementById("copy-lighting-output");

    const lightingModal = document.getElementById("lighting-cue-modal");
    const lightingModalClose = document.getElementById("close-lighting-cue-modal");
    const lightingModalCancel = document.getElementById("cancel-lighting-cue-modal");
    const lightingModalSave = document.getElementById("save-lighting-cue");
    const lightingModalName = document.getElementById("new-lighting-cue-name");
    const lightingModalMinute = document.getElementById("new-lighting-cue-minute");
    const lightingModalSecond = document.getElementById("new-lighting-cue-second");
    const lightingModalFade = document.getElementById("new-lighting-cue-fade");
    const lightingModalCopy = document.getElementById("new-lighting-cue-copy-look");
    const lightingModalError = document.getElementById("lighting-cue-modal-error");

    const addLightingUrl = app.dataset.lightingAddUrl;
    const deleteLightingUrlTemplate = app.dataset.lightingDeleteUrlTemplate;

    const boardDataScript = document.getElementById("drawing-board-data");
    let lightingRaw = {};

    try {
        lightingRaw = JSON.parse(
            boardDataScript
                ? boardDataScript.textContent
                : "{}"
        );
    } catch (error) {
        console.error("Lighting data parse failed.", error);
    }

    const makeId = () => (
        window.crypto && crypto.randomUUID
            ? crypto.randomUUID()
            : `focus-${Date.now()}-${Math.random().toString(16).slice(2)}`
    );

    let lightingCues = (
        lightingRaw.lighting_cues || []
    ).map((cue) => ({
        id: Number(cue.id),
        cue_number: Number(cue.cue_number || 1),
        name: cue.name || `Cue ${cue.cue_number || 1}`,
        time_seconds: Math.max(
            0,
            Number(cue.time_seconds || 0)
        ),
        fade_seconds: Math.max(
            0,
            Number(cue.fade_seconds || 0)
        ),
        is_blackout: Boolean(cue.is_blackout),
        notes: cue.notes || "",
        focus_areas: (cue.focus_areas || []).map((area) => ({
            id: String(area.id || makeId()),
            label: String(area.label || "A").toUpperCase(),
            x: Number(area.x ?? 50),
            y: Number(area.y ?? 50),
            width: Number(area.width ?? 24),
            height: Number(area.height ?? area.width ?? 24),
            color: area.color || "#FFFFFF",
            intensity: Number(area.intensity ?? 70),
            softness: Number(area.softness ?? 70),
            shape: area.shape === "ellipse"
                ? "ellipse"
                : "circle",
        })),
        follow_spots: (cue.follow_spots || []).map((spot,index) => ({
            id: String(spot.id || makeId()),
            label: spot.label || `Follow Spot ${index + 1}`,
            target_type: spot.target_type === "position" ? "position" : "marker",
            marker: Math.max(1, Number(spot.marker || 1)),
            x: Number(spot.x ?? 50),
            y: Number(spot.y ?? 50),
            size: Number(spot.size ?? 18),
            color: spot.color || "#FFFFFF",
            intensity: Number(spot.intensity ?? 80),
            softness: Number(spot.softness ?? 55),
        })),
        fixture_states: (cue.fixture_states || []).map((state) => ({
            fixture_id: Number(state.fixture_id),
            is_on: Boolean(state.is_on),
            intensity: Math.max(0, Math.min(100, Number(state.intensity || 0))),
            color: state.color || "#FFFFFF",
            angle_degrees: Number(state.angle_degrees ?? 90),
            beam_size: Math.max(4, Math.min(60, Number(state.beam_size ?? 18))),
        })),
    }));

    let lightingFixtures = (
        lightingRaw.lighting_fixtures
        || []
    ).map((fixture) => ({
        id: Number(fixture.id),
        fixture_number: Number(fixture.fixture_number || 1),
        label: fixture.label || `Fixture ${fixture.fixture_number || 1}`,
        fixture_type: fixture.fixture_type || "par",
        fixture_type_label: fixture.fixture_type_label || fixture.fixture_type || "PAR",
        x: Number(fixture.x ?? 50),
        y: Number(fixture.y ?? 10),
        notes: fixture.notes || "",
    }));

    const fixtureTypeMeta = {
        par: { label: "PAR", icon: "◉" },
        ellipsoidal: { label: "Ellipsoidal / Profile", icon: "▰" },
        fresnel: { label: "Fresnel", icon: "◎" },
        cyc: { label: "Cyc / Strip", icon: "▥" },
        follow_spot: { label: "Follow Spot", icon: "◈" },
    };

    let activeLightingCueId = Number(
        lightingRaw.active_lighting_cue_id
        || lightingCues[0]?.id
        || 0
    );

    let lightingMode = false;
    let lightingDesignMode = "simple";
    let selectedLightingFocusId = null;
    let selectedFollowSpotId = null;
    let selectedFixtureId = null;
    let lightingPlaybackTime = 0;
    let lightingPlaybackEnabled = false;

    function lightingCsrf() {
        const cookie = document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith("csrftoken="));

        return cookie
            ? decodeURIComponent(
                cookie.split("=")[1]
            )
            : "";
    }

    function lightingFmt(seconds) {
        const total = Math.max(
            0,
            Math.floor(
                Number(seconds) || 0
            )
        );

        return (
            `${Math.floor(total / 60)}:`
            + `${String(total % 60).padStart(2, "0")}`
        );
    }

    function activeLightingCue() {
        return lightingCues.find(
            (cue) => cue.id === activeLightingCueId
        ) || lightingCues[0] || null;
    }

    function sortedLightingCues() {
        return lightingCues
            .slice()
            .sort(
                (a, b) => (
                    a.time_seconds - b.time_seconds
                    || a.cue_number - b.cue_number
                    || a.id - b.id
                )
            );
    }

    function selectedLightingFocus() {
        const cue = activeLightingCue();

        if (!cue) return null;

        return cue.focus_areas.find(
            (area) => (
                area.id === selectedLightingFocusId
            )
        ) || null;
    }

    function nextFocusLabel(cue) {
        const used = new Set(
            cue.focus_areas.map(
                (area) => area.label
            )
        );

        for (
            let code = 65;
            code <= 90;
            code += 1
        ) {
            const label = String.fromCharCode(code);

            if (!used.has(label)) {
                return label;
            }
        }

        return String(
            cue.focus_areas.length + 1
        );
    }

    function hexToRgb(hex) {
        const value = String(
            hex || "#FFFFFF"
        ).replace("#", "");

        const safe = /^[0-9A-Fa-f]{6}$/.test(value)
            ? value
            : "FFFFFF";

        return {
            r: parseInt(safe.slice(0, 2), 16),
            g: parseInt(safe.slice(2, 4), 16),
            b: parseInt(safe.slice(4, 6), 16),
        };
    }

    function lightingStageRegion(area) {
        const horizontal = (
            area.x < 33
                ? "Stage Right"
                : (
                    area.x > 67
                        ? "Stage Left"
                        : "Center"
                )
        );

        const vertical = (
            area.y < 33
                ? "Upstage"
                : (
                    area.y > 67
                        ? "Downstage"
                        : "Midstage"
                )
        );

        return horizontal === "Center"
            ? `${vertical} Center`
            : `${vertical} ${horizontal}`;
    }

    function activateLightingPanel(name) {
        document.querySelectorAll(
            "[data-panel-tab]"
        ).forEach((button) => {
            button.classList.toggle(
                "active",
                button.dataset.panelTab === name
            );
        });

        document.querySelectorAll(
            "[data-panel-content]"
        ).forEach((content) => {
            content.hidden = (
                content.dataset.panelContent !== name
            );
        });
    }

    function lightingMarkDirty(message) {
        markDirty(
            message || "Lighting changed"
        );
    }

    function selectedFollowSpot() {
        const cue = activeLightingCue();
        if (!cue) return null;

        return (cue.follow_spots || []).find(
            (spot) => spot.id === selectedFollowSpotId
        ) || null;
    }

    function markerName(markerNumber) {
        const assignment = assignments.get(Number(markerNumber));
        const student = assignment ? studentFor(assignment) : null;

        return student
            ? `Marker ${markerNumber} · ${student.name}`
            : `Marker ${markerNumber}`;
    }

    function markerStagePoint(markerNumber) {
        const candidates = Array.from(
            layer.querySelectorAll(".board-marker")
        ).filter(
            (element) => (
                Number(element.dataset.marker) === Number(markerNumber)
                && !element.classList.contains("transition-ghost-marker")
            )
        );

        const element = (
            candidates.find((item) => item.classList.contains("playback-marker"))
            || candidates.find((item) => item.classList.contains("transition-start-marker"))
            || candidates[0]
        );

        if (!element) return null;

        return {
            x: parseFloat(element.style.left) || 50,
            y: parseFloat(element.style.top) || 50,
        };
    }

    function buildFollowCardDrawer(spot) {
        const drawer = document.createElement("div");
        drawer.className = "lighting-card-drawer";

        const heading = document.createElement("div");
        heading.className = "transition-selected-marker";

        const headingLabel = document.createElement("span");
        headingLabel.textContent = "Selected Follow Spot";

        const headingName = document.createElement("strong");
        headingName.textContent = spot.label;

        heading.append(headingLabel, headingName);

        const targetLabel = document.createElement("label");
        targetLabel.className = "board-info-field";

        const targetTitle = document.createElement("span");
        targetTitle.textContent = "Target";

        const targetSelect = document.createElement("select");
        targetSelect.className = "encore-input";

        [
            ["marker", "Dancer Marker"],
            ["position", "Fixed Position"],
        ].forEach(([value, label]) => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = label;
            targetSelect.appendChild(option);
        });

        targetSelect.value = spot.target_type;
        targetLabel.append(targetTitle, targetSelect);

        const markerLabel = document.createElement("label");
        markerLabel.className = "board-info-field";

        const markerTitle = document.createElement("span");
        markerTitle.textContent = "Dancer Marker";

        const markerSelect = document.createElement("select");
        markerSelect.className = "encore-input";

        for (
            let marker = 1;
            marker <= markerCount();
            marker += 1
        ) {
            const option = document.createElement("option");
            option.value = String(marker);
            option.textContent = markerName(marker);
            markerSelect.appendChild(option);
        }

        markerSelect.value = String(spot.marker);
        markerLabel.append(markerTitle, markerSelect);

        const positionHelp = document.createElement("div");
        positionHelp.className = "movement-instruction";
        positionHelp.textContent = (
            "Drag the follow spot directly on the stage to set its fixed position."
        );

        const colorLabel = document.createElement("label");
        colorLabel.className = "board-info-field";

        const colorTitle = document.createElement("span");
        colorTitle.textContent = "Color";

        const colorInput = document.createElement("input");
        colorInput.type = "color";
        colorInput.value = spot.color;

        colorLabel.append(colorTitle, colorInput);

        const makeRange = (label, value, min, max) => {
            const field = document.createElement("label");
            field.className = "lighting-range-field";

            const top = document.createElement("span");
            const title = document.createElement("strong");
            title.textContent = label;

            const output = document.createElement("b");
            output.textContent = `${Math.round(value)}%`;

            top.append(title, output);

            const input = document.createElement("input");
            input.type = "range";
            input.min = String(min);
            input.max = String(max);
            input.step = "1";
            input.value = String(value);

            field.append(top, input);

            return { field, input, output };
        };

        const intensity = makeRange(
            "Intensity",
            spot.intensity,
            0,
            100
        );

        const size = makeRange(
            "Beam Size",
            spot.size,
            4,
            60
        );

        const softness = makeRange(
            "Softness",
            spot.softness,
            0,
            100
        );

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "transition-remove-path";
        remove.textContent = "Remove Follow Spot";

        const updateVisibility = () => {
            markerLabel.hidden = targetSelect.value !== "marker";
            positionHelp.hidden = targetSelect.value !== "position";
        };

        const update = () => {
            spot.target_type = (
                targetSelect.value === "position"
                    ? "position"
                    : "marker"
            );
            spot.marker = Math.max(
                1,
                Number(markerSelect.value || 1)
            );
            spot.color = colorInput.value.toUpperCase();
            spot.intensity = Number(intensity.input.value);
            spot.size = Number(size.input.value);
            spot.softness = Number(softness.input.value);

            intensity.output.textContent = `${Math.round(spot.intensity)}%`;
            size.output.textContent = `${Math.round(spot.size)}%`;
            softness.output.textContent = `${Math.round(spot.softness)}%`;

            updateVisibility();
            lightingMarkDirty("Follow spot changed");
            renderLightingLook();
            renderLightingOutput();
        };

        targetSelect.addEventListener("change", () => {
            update();
            renderLightingAll();
        });

        markerSelect.addEventListener("change", update);
        colorInput.addEventListener("input", update);
        intensity.input.addEventListener("input", update);
        size.input.addEventListener("input", update);
        softness.input.addEventListener("input", update);

        remove.addEventListener("click", () => {
            const cue = activeLightingCue();
            if (!cue) return;

            cue.follow_spots = (
                cue.follow_spots || []
            ).filter(
                (item) => item.id !== spot.id
            );

            selectedFollowSpotId = null;

            renderLightingAll();
            lightingMarkDirty("Follow spot removed");
        });

        updateVisibility();

        drawer.append(
            heading,
            targetLabel,
            markerLabel,
            positionHelp,
            colorLabel,
            intensity.field,
            size.field,
            softness.field,
            remove
        );

        return drawer;
    }

    function renderFollowList() {
        const cue = activeLightingCue();

        followList.innerHTML = "";

        if (!cue) return;

        (cue.follow_spots || []).forEach((spot) => {
            const wrapper = document.createElement("div");
            wrapper.className = (
                "lighting-accordion-card"
                + (
                    spot.id === selectedFollowSpotId
                        ? " open"
                        : ""
                )
            );

            const row = document.createElement("button");
            row.type = "button";
            row.className = (
                "lighting-follow-row"
                + (
                    spot.id === selectedFollowSpotId
                        ? " active"
                        : ""
                )
            );

            const icon = document.createElement("span");
            icon.className = "lighting-follow-icon";
            icon.textContent = "🔦";

            const copy = document.createElement("span");
            copy.className = "lighting-follow-copy";

            const title = document.createElement("strong");
            title.textContent = spot.label;

            const detail = document.createElement("span");
            detail.textContent = (
                spot.target_type === "marker"
                    ? markerName(spot.marker)
                    : `${lightingStageRegion(spot)} · Fixed`
            );

            copy.append(title, detail);

            const right = document.createElement("span");
            right.className = "lighting-card-row-right";

            const intensity = document.createElement("small");
            intensity.textContent = `${spot.intensity}%`;

            const chevron = document.createElement("span");
            chevron.className = "lighting-drawer-chevron";
            chevron.textContent = (
                spot.id === selectedFollowSpotId
                    ? "⌃"
                    : "⌄"
            );

            right.append(intensity, chevron);
            row.append(icon, copy, right);

            row.addEventListener("click", () => {
                selectedLightingFocusId = null;

                selectedFollowSpotId = (
                    selectedFollowSpotId === spot.id
                        ? null
                        : spot.id
                );

                renderLightingAll();
            });

            wrapper.appendChild(row);

            if (
                spot.id === selectedFollowSpotId
            ) {
                wrapper.appendChild(
                    buildFollowCardDrawer(spot)
                );
            }

            followList.appendChild(wrapper);
        });
    }

    function renderFollowEditor() {
        followEditor.hidden = true;
    }

    function updateFollowFromControls() {
        const spot = selectedFollowSpot();
        if (!spot) return;

        spot.target_type = (
            followTargetType.value === "position"
                ? "position"
                : "marker"
        );
        spot.marker = Math.max(1, Number(followMarker.value || 1));
        spot.color = followColor.value.toUpperCase();
        spot.intensity = Number(followIntensity.value);
        spot.size = Number(followSize.value);
        spot.softness = Number(followSoftness.value);

        lightingMarkDirty("Follow spot changed");
        renderLightingAll();
    }

    function createFollowSpotElement(spot, playback=false) {
        let point = { x: spot.x, y: spot.y };

        if (spot.target_type === "marker") {
            point = markerStagePoint(spot.marker) || point;
        }

        const element = document.createElement("div");
        element.className = (
            "lighting-follow-spot"
            + (
                spot.id === selectedFollowSpotId && !playback
                    ? " selected"
                    : ""
            )
            + (
                spot.target_type === "marker"
                    ? " marker-target"
                    : ""
            )
            + (playback ? " playback-light" : "")
        );

        element.dataset.label = spot.label;

        const rgb = hexToRgb(spot.color);

        element.style.left = `${point.x}%`;
        element.style.top = `${point.y}%`;
        element.style.width = `${spot.size}%`;
        element.style.setProperty(
            "--follow-rgb",
            `${rgb.r}, ${rgb.g}, ${rgb.b}`
        );
        element.style.setProperty(
            "--follow-alpha",
            String(Math.max(0, Math.min(1, spot.intensity / 100)))
        );
        element.style.setProperty(
            "--follow-softness",
            String(spot.softness)
        );

        if (!playback && spot.target_type === "position") {
            let dragging = false;

            element.addEventListener("pointerdown", (event) => {
                if (event.button !== 0) return;

                dragging = true;
                selectedFollowSpotId = spot.id;
                selectedLightingFocusId = null;
                element.setPointerCapture(event.pointerId);
                event.preventDefault();
            });

            element.addEventListener("pointermove", (event) => {
                if (!dragging) return;

                const rect = stage.getBoundingClientRect();

                spot.x = Math.max(
                    0,
                    Math.min(
                        100,
                        ((event.clientX - rect.left) / rect.width) * 100
                    )
                );

                spot.y = Math.max(
                    0,
                    Math.min(
                        100,
                        ((event.clientY - rect.top) / rect.height) * 100
                    )
                );

                element.style.left = `${spot.x}%`;
                element.style.top = `${spot.y}%`;

                lightingMarkDirty("Follow spot moved");
            });

            const end = (event) => {
                if (!dragging) return;
                dragging = false;

                try {
                    element.releasePointerCapture(event.pointerId);
                } catch {}

                renderLightingAll();
            };

            element.addEventListener("pointerup", end);
            element.addEventListener("pointercancel", end);
        }

        return element;
    }


    function fixtureMeta(fixture) {
        return fixtureTypeMeta[fixture.fixture_type] || fixtureTypeMeta.par;
    }

    function fixtureState(cue, fixtureId, create=false) {
        if (!cue) return null;
        cue.fixture_states = cue.fixture_states || [];
        let state = cue.fixture_states.find(
            (item) => Number(item.fixture_id) === Number(fixtureId)
        ) || null;

        if (!state && create) {
            state = {
                fixture_id: Number(fixtureId),
                is_on: false,
                intensity: 0,
                color: "#FFFFFF",
                angle_degrees: 90,
                beam_size: 18,
            };
            cue.fixture_states.push(state);
        }
        return state;
    }

    function fixtureTargetPoint(fixture, state) {
        const radians = (Number(state?.angle_degrees ?? 90) * Math.PI) / 180;
        const distance = 34;
        return {
            x: Math.max(0, Math.min(100, fixture.x + Math.cos(radians) * distance)),
            y: Math.max(0, Math.min(100, fixture.y + Math.sin(radians) * distance)),
        };
    }

    async function createProFixture(fixtureType, point={x:50,y:12}) {
        const meta = fixtureTypeMeta[fixtureType];
        if (!meta) return;

        const response = await fetch(
            fixtureAddUrl,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": lightingCsrf(),
                },
                body: JSON.stringify({
                    fixture_type: fixtureType,
                    x: point.x,
                    y: point.y,
                }),
            }
        );

        const result = await response.json();
        if (!response.ok || !result.ok) {
            throw new Error(result.error || "Could not add fixture.");
        }

        const fixture = {
            ...result.fixture,
            id: Number(result.fixture.id),
            fixture_number: Number(result.fixture.fixture_number),
            x: Number(result.fixture.x),
            y: Number(result.fixture.y),
        };

        lightingFixtures.push(fixture);
        selectedFixtureId = fixture.id;
        selectedLightingFocusId = null;
        selectedFollowSpotId = null;
        renderLightingAll();
        lightingMarkDirty(`${meta.label} added`);
    }

    function createProStageFixtureElement(fixture, playback=false) {
        const meta = fixtureMeta(fixture);
        const element = document.createElement("div");

        element.className = (
            "pro-fixture-stage-icon"
            + (
                fixture.id === selectedFixtureId && !playback
                    ? " selected"
                    : ""
            )
        );
        element.style.left = `${fixture.x}%`;
        element.style.top = `${fixture.y}%`;
        element.dataset.fixtureId = String(fixture.id);
        element.title = `${fixture.label} · ${meta.label}`;
        element.textContent = meta.icon;

        const badge = document.createElement("span");
        badge.className = "pro-fixture-number";
        badge.textContent = fixture.fixture_number;
        element.appendChild(badge);

        if (!playback) {
            let dragging = false;

            element.addEventListener("pointerdown", (event) => {
                if (event.button !== 0) return;
                dragging = true;
                selectedFixtureId = fixture.id;
                element.setPointerCapture(event.pointerId);
                event.preventDefault();
                event.stopPropagation();
            });

            element.addEventListener("pointermove", (event) => {
                if (!dragging) return;
                const point = pointerPct(event.clientX, event.clientY);
                fixture.x = point.x;
                fixture.y = point.y;
                element.style.left = `${fixture.x}%`;
                element.style.top = `${fixture.y}%`;
                lightingMarkDirty("Fixture moved");
            });

            const end = (event) => {
                if (!dragging) return;
                dragging = false;
                try {
                    element.releasePointerCapture(event.pointerId);
                } catch {}
                renderLightingAll();
            };

            element.addEventListener("pointerup", end);
            element.addEventListener("pointercancel", end);
            element.addEventListener("click", (event) => {
                selectedFixtureId = fixture.id;
                selectedLightingFocusId = null;
                selectedFollowSpotId = null;
                renderLightingAll();
                event.stopPropagation();
            });
        }

        return element;
    }

    function renderProBeam(fixture, state, opacity=1) {
        if (!state || !state.is_on || Number(state.intensity) <= 0) return;

        const target = fixtureTargetPoint(fixture, state);
        const rgb = hexToRgb(state.color);
        const stageRect = stage.getBoundingClientRect();
        const dxPx = ((target.x - fixture.x) / 100) * stageRect.width;
        const dyPx = ((target.y - fixture.y) / 100) * stageRect.height;
        const lengthPx = Math.sqrt(dxPx * dxPx + dyPx * dyPx);
        const angle = Math.atan2(dyPx, dxPx) * 180 / Math.PI;

        const line = document.createElement("div");
        line.className = "pro-light-beam-line";
        line.style.left = `${fixture.x}%`;
        line.style.top = `${fixture.y}%`;
        line.style.width = `${lengthPx}px`;
        line.style.transform = `rotate(${angle}deg)`;
        line.style.opacity = String(opacity);
        line.style.setProperty("--beam-rgb", `${rgb.r}, ${rgb.g}, ${rgb.b}`);

        const pool = document.createElement("div");
        pool.className = "pro-light-pool";
        pool.style.left = `${target.x}%`;
        pool.style.top = `${target.y}%`;
        pool.style.width = `${state.beam_size}%`;
        pool.style.opacity = String(opacity);
        pool.style.setProperty("--beam-rgb", `${rgb.r}, ${rgb.g}, ${rgb.b}`);
        pool.style.setProperty(
            "--beam-alpha",
            String(Math.max(0, Math.min(1, Number(state.intensity) / 100)))
        );

        lightingLayer.append(line, pool);
    }

    function renderProRig(cue=activeLightingCue(), playback=false, opacity=1, append=false) {
        if (!append) lightingLayer.innerHTML = "";

        if (cue && !cue.is_blackout) {
            lightingFixtures.forEach((fixture) => {
                renderProBeam(
                    fixture,
                    fixtureState(cue, fixture.id, false),
                    opacity
                );
            });
        }

        if (!playback) {
            lightingFixtures.forEach((fixture) => {
                lightingLayer.appendChild(
                    createProStageFixtureElement(fixture, false)
                );
            });
        }
    }

    function makeProRange(title, value, min, max, suffix="%") {
        const field = document.createElement("label");
        field.className = "lighting-range-field";

        const top = document.createElement("span");
        const strong = document.createElement("strong");
        strong.textContent = title;
        const output = document.createElement("b");
        output.textContent = `${Math.round(value)}${suffix}`;
        top.append(strong, output);

        const input = document.createElement("input");
        input.type = "range";
        input.min = String(min);
        input.max = String(max);
        input.step = "1";
        input.value = String(value);

        field.append(top, input);
        return { field, input, output };
    }

    function buildFixtureDrawer(fixture) {
        const drawer = document.createElement("div");
        drawer.className = "pro-fixture-drawer";
        const meta = fixtureMeta(fixture);

        const rigTitle = document.createElement("div");
        rigTitle.className = "pro-fixture-section-title";
        rigTitle.innerHTML = "<strong>Rig Setup</strong><span>Persistent across all cues</span>";

        const labelField = document.createElement("label");
        labelField.className = "board-info-field";
        const labelTitle = document.createElement("span");
        labelTitle.textContent = "Fixture Name";
        const labelInput = document.createElement("input");
        labelInput.className = "encore-input";
        labelInput.type = "text";
        labelInput.maxLength = 100;
        labelInput.value = fixture.label;
        labelField.append(labelTitle, labelInput);

        const typeCard = document.createElement("div");
        typeCard.className = "transition-info-card";
        typeCard.innerHTML = (
            `<span>Instrument</span><strong>${meta.label}</strong>`
            + `<small>${lightingStageRegion(fixture)}</small>`
        );

        const notesField = document.createElement("label");
        notesField.className = "board-info-field";
        const notesTitle = document.createElement("span");
        notesTitle.textContent = "Rig Notes";
        const notesInput = document.createElement("textarea");
        notesInput.className = "encore-input lighting-notes";
        notesInput.rows = 2;
        notesInput.value = fixture.notes || "";
        notesField.append(notesTitle, notesInput);

        const cueTitle = document.createElement("div");
        cueTitle.className = "pro-fixture-section-title";
        cueTitle.innerHTML = "<strong>Current Cue</strong><span>Resets on a new cue</span>";

        const cue = activeLightingCue();
        const state = fixtureState(cue, fixture.id, true);

        const enabledField = document.createElement("label");
        enabledField.className = "pro-fixture-toggle";
        const enabledInput = document.createElement("input");
        enabledInput.type = "checkbox";
        enabledInput.checked = state.is_on;
        const enabledCopy = document.createElement("span");
        enabledCopy.innerHTML = "<strong>Fixture On</strong><small>Include this fixture in this cue.</small>";
        enabledField.append(enabledInput, enabledCopy);

        const colorField = document.createElement("label");
        colorField.className = "board-info-field";
        const colorTitle = document.createElement("span");
        colorTitle.textContent = "Color";
        const colorInput = document.createElement("input");
        colorInput.type = "color";
        colorInput.value = state.color;
        colorField.append(colorTitle, colorInput);

        const intensity = makeProRange("Intensity", state.intensity, 0, 100);
        const angle = makeProRange("Angle", state.angle_degrees, 0, 359, "°");
        const beam = makeProRange("Beam Size", state.beam_size, 4, 60);

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "transition-remove-path";
        remove.textContent = "Remove Fixture";

        const saveRig = () => {
            fixture.label = labelInput.value.trim() || `Fixture ${fixture.fixture_number}`;
            fixture.notes = notesInput.value.trim();
            lightingMarkDirty("Fixture setup changed");
            renderProRig();
            renderLightingOutput();
        };

        labelInput.addEventListener("input", saveRig);
        notesInput.addEventListener("input", saveRig);

        const updateState = () => {
            state.is_on = enabledInput.checked;
            state.intensity = Number(intensity.input.value);
            state.color = colorInput.value.toUpperCase();
            state.angle_degrees = Number(angle.input.value);
            state.beam_size = Number(beam.input.value);

            intensity.output.textContent = `${state.intensity}%`;
            angle.output.textContent = `${Math.round(state.angle_degrees)}°`;
            beam.output.textContent = `${Math.round(state.beam_size)}%`;

            lightingMarkDirty("Fixture cue settings changed");
            renderProRig();
            renderLightingOutput();
        };

        enabledInput.addEventListener("change", updateState);
        colorInput.addEventListener("input", updateState);
        intensity.input.addEventListener("input", updateState);
        angle.input.addEventListener("input", updateState);
        beam.input.addEventListener("input", updateState);

        remove.addEventListener("click", async () => {
            if (!window.confirm(`Remove ${fixture.label} from the lighting rig?`)) return;

            const response = await fetch(
                fixtureDeleteUrlTemplate.replace("999999", String(fixture.id)),
                {
                    method: "POST",
                    headers: { "X-CSRFToken": lightingCsrf() },
                }
            );
            const result = await response.json();

            if (!response.ok || !result.ok) {
                window.alert(result.error || "Could not remove fixture.");
                return;
            }

            lightingFixtures = lightingFixtures.filter(
                (item) => item.id !== fixture.id
            );
            lightingFixtures
                .sort((a,b) => a.fixture_number - b.fixture_number)
                .forEach((item,index) => item.fixture_number = index + 1);

            lightingCues.forEach((item) => {
                item.fixture_states = (item.fixture_states || []).filter(
                    (state) => Number(state.fixture_id) !== Number(fixture.id)
                );
            });

            selectedFixtureId = null;
            renderLightingAll();
            lightingMarkDirty("Fixture removed");
        });

        drawer.append(
            rigTitle,
            labelField,
            typeCard,
            notesField,
            cueTitle,
            enabledField,
            colorField,
            intensity.field,
            angle.field,
            beam.field,
            remove
        );

        return drawer;
    }

    function renderProFixtureList() {
        if (!proFixtureList) return;
        proFixtureList.innerHTML = "";
        const cue = activeLightingCue();

        lightingFixtures
            .slice()
            .sort((a,b) => a.fixture_number - b.fixture_number)
            .forEach((fixture) => {
                const meta = fixtureMeta(fixture);
                const state = fixtureState(cue, fixture.id, false);

                const card = document.createElement("div");
                card.className = (
                    "pro-fixture-card"
                    + (fixture.id === selectedFixtureId ? " open" : "")
                );

                const row = document.createElement("button");
                row.type = "button";
                row.className = "pro-fixture-row";

                const icon = document.createElement("span");
                icon.className = "pro-fixture-icon";
                icon.textContent = meta.icon;

                const copy = document.createElement("span");
                copy.className = "pro-fixture-copy";
                const name = document.createElement("strong");
                name.textContent = fixture.label;
                const detail = document.createElement("span");
                detail.textContent = `${meta.label} · ${lightingStageRegion(fixture)}`;
                copy.append(name, detail);

                const badge = document.createElement("span");
                badge.className = (
                    "pro-fixture-state-badge"
                    + (state?.is_on && Number(state.intensity)>0 ? " on" : "")
                );
                badge.textContent = (
                    state?.is_on && Number(state.intensity)>0
                        ? `${state.intensity}%`
                        : "Off"
                );

                row.append(icon, copy, badge);
                row.addEventListener("click", () => {
                    selectedLightingFocusId = null;
                    selectedFollowSpotId = null;
                    selectedFixtureId = (
                        selectedFixtureId === fixture.id
                            ? null
                            : fixture.id
                    );
                    renderLightingAll();
                });

                card.appendChild(row);
                if (fixture.id === selectedFixtureId) {
                    card.appendChild(buildFixtureDrawer(fixture));
                }
                proFixtureList.appendChild(card);
            });
    }

    function setLightingDesignMode(mode) {
        lightingDesignMode = mode === "pro" ? "pro" : "simple";
        const isPro = lightingDesignMode === "pro";

        simpleModeButton.classList.toggle("active", !isPro);
        proModeButton.classList.toggle("active", isPro);
        simpleLightingControls.hidden = isPro;
        proLightingControls.hidden = !isPro;
        app.classList.toggle("pro-lighting-mode", isPro);

        selectedLightingFocusId = null;
        selectedFollowSpotId = null;
        selectedFixtureId = null;
        renderLightingAll();
    }

    function renderLightingCueTabs() {
        cueTabs.innerHTML = "";

        sortedLightingCues().forEach((cue) => {
            const button = document.createElement("button");

            button.type = "button";
            button.className = (
                "lighting-cue-tab"
                + (
                    cue.id === activeLightingCueId
                        ? " active"
                        : ""
                )
                + (
                    cue.is_blackout
                        ? " blackout"
                        : ""
                )
            );

            const title = document.createElement("strong");
            title.textContent = `Cue ${cue.cue_number}`;

            const time = document.createElement("span");
            time.textContent = cue.is_blackout
                ? `${lightingFmt(cue.time_seconds)} · Blackout`
                : lightingFmt(cue.time_seconds);

            button.append(
                title,
                time
            );

            button.addEventListener("click", () => {
                activeLightingCueId = cue.id;
                selectedLightingFocusId = null;
                selectedFollowSpotId = null;

                renderLightingAll();
                activateLightingPanel(
                    "lighting-look"
                );
            });

            if (lightingCues.length > 1) {
                const remove = document.createElement("button");

                remove.type = "button";
                remove.className = "lighting-cue-delete";
                remove.textContent = "×";
                remove.title = (
                    `Delete Cue ${cue.cue_number}`
                );

                remove.addEventListener(
                    "click",
                    async (event) => {
                        event.stopPropagation();

                        if (
                            !window.confirm(
                                `Delete Cue ${cue.cue_number}?`
                            )
                        ) {
                            return;
                        }

                        const response = await fetch(
                            deleteLightingUrlTemplate.replace(
                                "999999",
                                String(cue.id)
                            ),
                            {
                                method: "POST",
                                headers: {
                                    "X-CSRFToken": lightingCsrf(),
                                },
                            }
                        );

                        const result = await response.json();

                        if (
                            !response.ok
                            || !result.ok
                        ) {
                            window.alert(
                                result.error
                                || "Could not delete lighting cue."
                            );
                            return;
                        }

                        lightingCues = lightingCues
                            .filter(
                                (item) => item.id !== cue.id
                            )
                            .sort(
                                (a, b) => (
                                    a.time_seconds - b.time_seconds
                                    || a.cue_number - b.cue_number
                                )
                            );

                        lightingCues.forEach(
                            (item, index) => {
                                item.cue_number = index + 1;
                            }
                        );

                        activeLightingCueId = (
                            lightingCues[0]?.id
                            || null
                        );

                        selectedLightingFocusId = null;

                        renderLightingAll();
                        lightingMarkDirty(
                            "Lighting cue deleted"
                        );
                    }
                );

                button.appendChild(remove);
            }

            cueTabs.appendChild(button);
        });
    }

    function buildFocusCardDrawer(area) {
        const drawer = document.createElement("div");
        drawer.className = "lighting-card-drawer";

        const heading = document.createElement("div");
        heading.className = "transition-selected-marker";

        const headingLabel = document.createElement("span");
        headingLabel.textContent = "Selected Focus";

        const headingName = document.createElement("strong");
        headingName.textContent = `Focus ${area.label}`;

        heading.append(headingLabel, headingName);

        const colorLabel = document.createElement("label");
        colorLabel.className = "board-info-field";

        const colorTitle = document.createElement("span");
        colorTitle.textContent = "Color";

        const colorInput = document.createElement("input");
        colorInput.type = "color";
        colorInput.value = area.color;

        colorLabel.append(colorTitle, colorInput);

        const makeRange = (label, value, min, max) => {
            const field = document.createElement("label");
            field.className = "lighting-range-field";

            const top = document.createElement("span");
            const title = document.createElement("strong");
            title.textContent = label;

            const output = document.createElement("b");
            output.textContent = `${Math.round(value)}%`;

            top.append(title, output);

            const input = document.createElement("input");
            input.type = "range";
            input.min = String(min);
            input.max = String(max);
            input.step = "1";
            input.value = String(value);

            field.append(top, input);

            return { field, input, output };
        };

        const intensity = makeRange(
            "Intensity",
            area.intensity,
            0,
            100
        );

        const softness = makeRange(
            "Softness",
            area.softness,
            0,
            100
        );

        const shapeLabel = document.createElement("label");
        shapeLabel.className = "board-info-field";

        const shapeTitle = document.createElement("span");
        shapeTitle.textContent = "Shape";

        const shapeSelect = document.createElement("select");
        shapeSelect.className = "encore-input";

        [
            ["circle", "Circle"],
            ["ellipse", "Ellipse"],
        ].forEach(([value, label]) => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = label;
            shapeSelect.appendChild(option);
        });

        shapeSelect.value = area.shape;
        shapeLabel.append(shapeTitle, shapeSelect);

        const width = makeRange(
            "Width",
            area.width,
            4,
            100
        );

        const height = makeRange(
            "Height",
            area.height,
            4,
            100
        );

        height.input.disabled = area.shape === "circle";

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "transition-remove-path";
        remove.textContent = "Remove Focus Area";

        const update = () => {
            area.color = colorInput.value.toUpperCase();
            area.intensity = Number(intensity.input.value);
            area.softness = Number(softness.input.value);
            area.shape = (
                shapeSelect.value === "ellipse"
                    ? "ellipse"
                    : "circle"
            );
            area.width = Number(width.input.value);
            area.height = (
                area.shape === "circle"
                    ? area.width
                    : Number(height.input.value)
            );

            intensity.output.textContent = `${Math.round(area.intensity)}%`;
            softness.output.textContent = `${Math.round(area.softness)}%`;
            width.output.textContent = `${Math.round(area.width)}%`;
            height.output.textContent = `${Math.round(area.height)}%`;
            height.input.disabled = area.shape === "circle";

            lightingMarkDirty("Lighting focus changed");
            renderLightingLook();
            renderLightingOutput();
        };

        colorInput.addEventListener("input", update);
        intensity.input.addEventListener("input", update);
        softness.input.addEventListener("input", update);
        width.input.addEventListener("input", update);
        height.input.addEventListener("input", update);

        shapeSelect.addEventListener("change", () => {
            update();
            renderLightingAll();
        });

        remove.addEventListener("click", () => {
            const cue = activeLightingCue();
            if (!cue) return;

            cue.focus_areas = cue.focus_areas.filter(
                (item) => item.id !== area.id
            );

            selectedLightingFocusId = null;

            renderLightingAll();
            lightingMarkDirty("Lighting focus removed");
        });

        drawer.append(
            heading,
            colorLabel,
            intensity.field,
            softness.field,
            shapeLabel,
            width.field,
            height.field,
            remove
        );

        return drawer;
    }

    function renderFocusList() {
        const cue = activeLightingCue();

        focusList.innerHTML = "";

        if (!cue) return;

        cue.focus_areas.forEach((area) => {
            const wrapper = document.createElement("div");
            wrapper.className = (
                "lighting-accordion-card"
                + (
                    area.id === selectedLightingFocusId
                        ? " open"
                        : ""
                )
            );

            const row = document.createElement("button");
            row.type = "button";
            row.className = (
                "lighting-focus-row"
                + (
                    area.id === selectedLightingFocusId
                        ? " active"
                        : ""
                )
            );

            const swatch = document.createElement("span");
            swatch.className = "lighting-focus-swatch";
            swatch.style.setProperty(
                "--focus-color",
                area.color
            );
            swatch.textContent = area.label;

            const copy = document.createElement("span");
            copy.className = "lighting-focus-row-copy";

            const title = document.createElement("strong");
            title.textContent = `Focus ${area.label}`;

            const detail = document.createElement("span");
            detail.textContent = (
                `${lightingStageRegion(area)} · ${area.intensity}%`
            );

            copy.append(title, detail);

            const right = document.createElement("span");
            right.className = "lighting-card-row-right";

            const color = document.createElement("small");
            color.textContent = area.color;

            const chevron = document.createElement("span");
            chevron.className = "lighting-drawer-chevron";
            chevron.textContent = (
                area.id === selectedLightingFocusId
                    ? "⌃"
                    : "⌄"
            );

            right.append(color, chevron);
            row.append(swatch, copy, right);

            row.addEventListener("click", () => {
                selectedFollowSpotId = null;

                selectedLightingFocusId = (
                    selectedLightingFocusId === area.id
                        ? null
                        : area.id
                );

                renderLightingAll();
            });

            wrapper.appendChild(row);

            if (
                area.id === selectedLightingFocusId
            ) {
                wrapper.appendChild(
                    buildFocusCardDrawer(area)
                );
            }

            focusList.appendChild(wrapper);
        });
    }

    function renderFocusEditor() {
        focusEditor.hidden = true;
    }

    function renderLightingCueEditor() {
        const cue = activeLightingCue();

        if (!cue) return;

        cueName.value = cue.name;
        cueMinute.value = String(
            Math.floor(
                cue.time_seconds / 60
            )
        );
        cueSecond.value = String(
            cue.time_seconds % 60
        ).padStart(2, "0");

        cueFade.value = String(
            cue.fade_seconds
        );

        cueBlackout.checked = cue.is_blackout;
        cueNotes.value = cue.notes;

        cueSummaryName.textContent = (
            `Cue ${cue.cue_number} · ${cue.name}`
        );

        cueSummaryTime.textContent = (
            `${lightingFmt(cue.time_seconds)} · `
            + `Fade ${Number(cue.fade_seconds).toFixed(1)}s`
            + (
                cue.is_blackout
                    ? " · Blackout"
                    : ""
            )
        );
    }

    function createLightingFocusElement(
        area,
        selected,
        playback=false
    ) {
        const element = document.createElement("div");

        element.className = (
            `lighting-focus shape-${area.shape}`
            + (
                selected
                    ? " selected"
                    : ""
            )
            + (
                playback
                    ? " playback-light"
                    : ""
            )
        );

        element.dataset.label = area.label;

        const rgb = hexToRgb(area.color);

        element.style.left = `${area.x}%`;
        element.style.top = `${area.y}%`;
        element.style.width = `${area.width}%`;
        element.style.height = `${area.height}%`;

        element.style.setProperty(
            "--focus-rgb",
            `${rgb.r}, ${rgb.g}, ${rgb.b}`
        );

        element.style.setProperty(
            "--focus-alpha",
            String(
                Math.max(
                    0,
                    Math.min(
                        1,
                        area.intensity / 100
                    )
                )
            )
        );

        element.style.setProperty(
            "--focus-softness",
            String(area.softness)
        );

        if (!playback) {
            let dragging = false;

            element.addEventListener(
                "pointerdown",
                (event) => {
                    if (
                        event.button !== 0
                        || event.target.classList.contains(
                            "lighting-focus-resize"
                        )
                    ) {
                        return;
                    }

                    dragging = true;
                    selectedLightingFocusId = area.id;
                    element.setPointerCapture(
                        event.pointerId
                    );
                    element.style.cursor = "grabbing";
                    event.preventDefault();
                }
            );

            element.addEventListener(
                "pointermove",
                (event) => {
                    if (!dragging) return;

                    const rect = stage.getBoundingClientRect();

                    area.x = Math.max(
                        0,
                        Math.min(
                            100,
                            (
                                (event.clientX - rect.left)
                                / rect.width
                            ) * 100
                        )
                    );

                    area.y = Math.max(
                        0,
                        Math.min(
                            100,
                            (
                                (event.clientY - rect.top)
                                / rect.height
                            ) * 100
                        )
                    );

                    element.style.left = `${area.x}%`;
                    element.style.top = `${area.y}%`;

                    lightingMarkDirty(
                        "Lighting focus moved"
                    );
                }
            );

            const stopDrag = (event) => {
                if (!dragging) return;

                dragging = false;
                element.style.cursor = "grab";

                try {
                    element.releasePointerCapture(
                        event.pointerId
                    );
                } catch {}

                renderLightingAll();
            };

            element.addEventListener(
                "pointerup",
                stopDrag
            );

            element.addEventListener(
                "pointercancel",
                stopDrag
            );

            element.addEventListener("click", () => {
                selectedLightingFocusId = area.id;
                renderLightingAll();
            });

            const resize = document.createElement("span");
            resize.className = "lighting-focus-resize";

            let resizing = false;

            resize.addEventListener(
                "pointerdown",
                (event) => {
                    if (event.button !== 0) return;

                    resizing = true;
                    selectedLightingFocusId = area.id;
                    resize.setPointerCapture(
                        event.pointerId
                    );
                    event.stopPropagation();
                    event.preventDefault();
                }
            );

            resize.addEventListener(
                "pointermove",
                (event) => {
                    if (!resizing) return;

                    const rect = stage.getBoundingClientRect();

                    const pointerX = (
                        (event.clientX - rect.left)
                        / rect.width
                    ) * 100;

                    const pointerY = (
                        (event.clientY - rect.top)
                        / rect.height
                    ) * 100;

                    area.width = Math.max(
                        4,
                        Math.min(
                            100,
                            Math.abs(
                                pointerX - area.x
                            ) * 2
                        )
                    );

                    area.height = (
                        area.shape === "circle"
                            ? area.width
                            : Math.max(
                                4,
                                Math.min(
                                    100,
                                    Math.abs(
                                        pointerY - area.y
                                    ) * 2
                                )
                            )
                    );

                    element.style.width = `${area.width}%`;
                    element.style.height = `${area.height}%`;

                    lightingMarkDirty(
                        "Lighting focus resized"
                    );
                }
            );

            const stopResize = (event) => {
                if (!resizing) return;

                resizing = false;

                try {
                    resize.releasePointerCapture(
                        event.pointerId
                    );
                } catch {}

                renderLightingAll();
            };

            resize.addEventListener(
                "pointerup",
                stopResize
            );

            resize.addEventListener(
                "pointercancel",
                stopResize
            );

            element.appendChild(resize);
        }

        return element;
    }

    function renderLightingLook(
        cue=activeLightingCue(),
        playback=false,
        opacity=1,
        append=false
    ) {
        if (lightingDesignMode === "pro") {
            renderProRig(cue, playback, opacity, append);
            return;
        }

        if (!append) {
            lightingLayer.innerHTML = "";
        }

        if (
            !cue
            || cue.is_blackout
        ) {
            return;
        }

        cue.focus_areas.forEach((area) => {
            const element = createLightingFocusElement(
                area,
                !playback
                && area.id === selectedLightingFocusId,
                playback
            );

            element.style.opacity = String(opacity);

            lightingLayer.appendChild(
                element
            );
        });

        (cue.follow_spots || []).forEach((spot) => {
            const element = createFollowSpotElement(
                spot,
                playback
            );

            element.style.opacity = String(opacity);

            lightingLayer.appendChild(
                element
            );
        });
    }

    function updateFocusFromControls() {
        const area = selectedLightingFocus();

        if (!area) return;

        area.color = focusColor.value.toUpperCase();
        area.intensity = Number(
            focusIntensity.value
        );
        area.softness = Number(
            focusSoftness.value
        );
        area.shape = (
            focusShape.value === "ellipse"
                ? "ellipse"
                : "circle"
        );
        area.width = Number(
            focusWidth.value
        );

        area.height = (
            area.shape === "circle"
                ? area.width
                : Number(
                    focusHeight.value
                )
        );

        lightingMarkDirty(
            "Lighting focus changed"
        );

        renderLightingAll();
    }

    function updateCueFromControls() {
        const cue = activeLightingCue();

        if (!cue) return;

        cue.name = (
            cueName.value.trim()
            || `Cue ${cue.cue_number}`
        );

        cue.time_seconds = (
            Math.max(
                0,
                Number(cueMinute.value) || 0
            ) * 60
        ) + Math.max(
            0,
            Math.min(
                59,
                Number(cueSecond.value) || 0
            )
        );

        cue.fade_seconds = Math.max(
            0,
            Math.min(
                120,
                Number(cueFade.value) || 0
            )
        );

        cue.is_blackout = cueBlackout.checked;
        cue.notes = cueNotes.value.trim();

        if (cue.is_blackout) {
            cue.focus_areas = [];
            cue.follow_spots = [];
            cue.fixture_states = [];
            selectedLightingFocusId = null;
            selectedFollowSpotId = null;
            selectedFixtureId = null;
        }

        lightingMarkDirty(
            "Lighting cue changed"
        );

        renderLightingAll();
    }

    function renderLightingOutput() {
        outputSheet.innerHTML = "";

        if (lightingFixtures.length) {
            const rig = document.createElement("div");
            rig.className = "pro-output-rig";

            const title = document.createElement("strong");
            title.textContent = "Pro Fixture Rig";
            rig.appendChild(title);

            lightingFixtures
                .slice()
                .sort((a,b) => a.fixture_number - b.fixture_number)
                .forEach((fixture) => {
                    const meta = fixtureMeta(fixture);
                    const row = document.createElement("div");
                    row.className = "pro-output-rig-row";
                    row.innerHTML = (
                        `<b>Fixture ${fixture.fixture_number}</b> · `
                        + `${fixture.label} · ${meta.label} · `
                        + `${lightingStageRegion(fixture)}`
                    );
                    rig.appendChild(row);
                });

            outputSheet.appendChild(rig);
        }

        sortedLightingCues().forEach((cue) => {
            const card = document.createElement("div");
            card.className = "lighting-output-cue";

            const title = document.createElement("strong");
            title.textContent = `LX ${cue.cue_number} — ${cue.name}`;

            const meta = document.createElement("div");
            meta.className = "lighting-output-meta";
            meta.textContent = (
                `${lightingFmt(cue.time_seconds)} · `
                + `Fade ${Number(cue.fade_seconds).toFixed(1)} sec`
            );

            card.append(title, meta);

            if (cue.is_blackout) {
                const row = document.createElement("div");
                row.className = "lighting-output-focus";
                row.innerHTML = "<b>LOOK:</b> BLACKOUT — all designed light out.";
                card.appendChild(row);
            } else {
                cue.focus_areas.forEach((area) => {
                    const row = document.createElement("div");
                    row.className = "lighting-output-focus";
                    row.innerHTML = (
                        `<b>Focus ${area.label}</b><br>`
                        + `${lightingStageRegion(area)} · `
                        + `${area.shape === "ellipse" ? "Elliptical" : "Circular"} focus · `
                        + `${area.intensity}% intensity · `
                        + `${area.softness}% softness · `
                        + `${area.color}`
                    );
                    card.appendChild(row);
                });

                (cue.follow_spots || []).forEach((spot) => {
                    const row = document.createElement("div");
                    row.className = "lighting-output-focus";
                    row.innerHTML = (
                        `<b>${spot.label}</b><br>`
                        + (
                            spot.target_type === "marker"
                                ? `Follow ${markerName(spot.marker)}`
                                : `Fixed at ${lightingStageRegion(spot)}`
                        )
                        + ` · ${spot.intensity}% intensity`
                        + ` · Beam ${Math.round(spot.size)}%`
                        + ` · ${spot.softness}% softness`
                        + ` · ${spot.color}`
                    );
                    card.appendChild(row);
                });

                (cue.fixture_states || [])
                    .filter(
                        (state) => state.is_on && Number(state.intensity) > 0
                    )
                    .forEach((state) => {
                        const fixture = lightingFixtures.find(
                            (item) => Number(item.id) === Number(state.fixture_id)
                        );
                        if (!fixture) return;

                        const fixtureMetaRow = fixtureMeta(fixture);
                        const row = document.createElement("div");
                        row.className = "lighting-output-focus";
                        row.innerHTML = (
                            `<b>Fixture ${fixture.fixture_number} · ${fixture.label}</b><br>`
                            + `${fixtureMetaRow.label} · `
                            + `${state.intensity}% intensity · `
                            + `${state.color} · `
                            + `Angle ${Math.round(state.angle_degrees)}° · `
                            + `Beam ${Math.round(state.beam_size)}%`
                        );
                        card.appendChild(row);
                    });
            }

            if (cue.notes) {
                const notes = document.createElement("div");
                notes.className = "lighting-output-focus";
                notes.innerHTML = `<b>Notes:</b> ${cue.notes}`;
                card.appendChild(notes);
            }

            outputSheet.appendChild(card);
        });
    }

    function lightingOutputText() {
        const sections = [];

        if (lightingFixtures.length) {
            const rigLines = ["PRO FIXTURE RIG"];

            lightingFixtures
                .slice()
                .sort((a,b) => a.fixture_number - b.fixture_number)
                .forEach((fixture) => {
                    const meta = fixtureMeta(fixture);
                    rigLines.push(
                        `Fixture ${fixture.fixture_number}: `
                        + `${fixture.label}; ${meta.label}; `
                        + `${lightingStageRegion(fixture)}.`
                    );
                });

            sections.push(rigLines.join("\n"));
        }

        sortedLightingCues().forEach((cue) => {
            const lines = [
                `LX ${cue.cue_number} — ${cue.name}`,
                `Time: ${lightingFmt(cue.time_seconds)}`,
                `Fade: ${Number(cue.fade_seconds).toFixed(1)} sec`,
            ];

            if (cue.is_blackout) {
                lines.push("LOOK: BLACKOUT — all designed light out.");
            } else {
                cue.focus_areas.forEach((area) => {
                    lines.push(
                        `Focus ${area.label}: `
                        + `${lightingStageRegion(area)}; `
                        + `${area.shape === "ellipse" ? "elliptical" : "circular"} focus; `
                        + `${area.intensity}% intensity; `
                        + `${area.softness}% softness; `
                        + `color ${area.color}.`
                    );
                });

                (cue.follow_spots || []).forEach((spot) => {
                    lines.push(
                        `${spot.label}: `
                        + (
                            spot.target_type === "marker"
                                ? `follow ${markerName(spot.marker)}`
                                : `fixed at ${lightingStageRegion(spot)}`
                        )
                        + `; ${spot.intensity}% intensity; `
                        + `beam size ${Math.round(spot.size)}%; `
                        + `${spot.softness}% softness; `
                        + `color ${spot.color}.`
                    );
                });

                (cue.fixture_states || [])
                    .filter(
                        (state) => state.is_on && Number(state.intensity) > 0
                    )
                    .forEach((state) => {
                        const fixture = lightingFixtures.find(
                            (item) => Number(item.id) === Number(state.fixture_id)
                        );
                        if (!fixture) return;

                        const meta = fixtureMeta(fixture);
                        lines.push(
                            `Fixture ${fixture.fixture_number} (${fixture.label}): `
                            + `${meta.label}; `
                            + `${state.intensity}% intensity; `
                            + `color ${state.color}; `
                            + `angle ${Math.round(state.angle_degrees)}°; `
                            + `beam ${Math.round(state.beam_size)}%.`
                        );
                    });
            }

            if (cue.notes) {
                lines.push(`Notes: ${cue.notes}`);
            }

            sections.push(lines.join("\n"));
        });

        return sections.join("\n\n");
    }

    function cueStateAtTime(time) {
        const ordered = sortedLightingCues();

        if (!ordered.length) {
            return {
                previous: null,
                current: null,
                progress: 1,
            };
        }

        let current = null;

        for (const cue of ordered) {
            if (cue.time_seconds <= time) {
                current = cue;
            } else {
                break;
            }
        }

        if (!current) {
            return {
                previous: null,
                current: null,
                progress: 1,
            };
        }

        const index = ordered.indexOf(current);
        const previous = (
            index > 0
                ? ordered[index - 1]
                : null
        );

        const fade = Math.max(
            0,
            Number(current.fade_seconds) || 0
        );

        const elapsed = Math.max(
            0,
            time - current.time_seconds
        );

        return {
            previous,
            current,
            progress: (
                fade > 0
                    ? Math.max(
                        0,
                        Math.min(
                            1,
                            elapsed / fade
                        )
                    )
                    : 1
            ),
        };
    }

    function renderPlaybackLighting(time) {
        lightingLayer.innerHTML = "";

        const state = cueStateAtTime(time);

        if (!state.current) {
            app.classList.remove(
                "has-lighting-cues"
            );
            return;
        }

        app.classList.add(
            "has-lighting-cues"
        );

        if (
            state.previous
            && state.progress < 1
            && !state.previous.is_blackout
        ) {
            renderLightingLook(
                state.previous,
                true,
                1 - state.progress,
                true
            );
        }

        if (!state.current.is_blackout) {
            renderLightingLook(
                state.current,
                true,
                state.progress,
                true
            );
        }
    }

    function renderLightingAll() {
        renderLightingCueTabs();
        renderFocusList();
        renderFocusEditor();
        renderFollowList();
        renderFollowEditor();
        renderProFixtureList();
        renderLightingCueEditor();
        renderLightingOutput();

        if (
            lightingMode
            && !lightingPlaybackEnabled
        ) {
            renderLightingLook();
        }
    }

    function enterLightingMode() {
        if (
            app.classList.contains(
                "transition-mode"
            )
        ) {
            exitTransitionMode();
            renderTabs();
            renderStage();
        }

        lightingMode = true;

        app.classList.add(
            "lighting-mode"
        );

        cueTabsShell.hidden = false;

        lookTab.hidden = false;
        cueTab.hidden = false;
        outputTab.hidden = false;

        activateLightingPanel(
            "lighting-look"
        );

        renderLightingAll();
    }

    function exitLightingMode() {
        lightingMode = false;

        app.classList.remove(
            "lighting-mode"
        );

        cueTabsShell.hidden = true;

        lookTab.hidden = true;
        cueTab.hidden = true;
        outputTab.hidden = true;

        lightingLayer.innerHTML = "";

        activateLightingPanel(
            "information"
        );
    }

    async function createLightingCue({
        blackout=false,
        useModal=true,
    }={}) {
        const current = activeLightingCue();

        const time = (
            useModal
                ? (
                    Math.max(
                        0,
                        Number(lightingModalMinute.value) || 0
                    ) * 60
                    + Math.max(
                        0,
                        Math.min(
                            59,
                            Number(lightingModalSecond.value) || 0
                        )
                    )
                )
                : (
                    current
                        ? current.time_seconds + 1
                        : Math.max(
                            0,
                            Math.round(lightingPlaybackTime)
                        )
                )
        );

        const fade = (
            useModal
                ? Math.max(
                    0,
                    Math.min(
                        120,
                        Number(lightingModalFade.value) || 0
                    )
                )
                : 0
        );

        const response = await fetch(
            addLightingUrl,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": lightingCsrf(),
                },
                body: JSON.stringify(
                    {
                        name: (
                            blackout
                                ? "Blackout"
                                : (
                                    useModal
                                        ? lightingModalName.value.trim()
                                        : ""
                                )
                        ),
                        time_seconds: time,
                        fade_seconds: fade,
                        is_blackout: blackout,
                    }
                ),
            }
        );

        const result = await response.json();

        if (
            !response.ok
            || !result.ok
        ) {
            throw new Error(
                result.error
                || "Could not add lighting cue."
            );
        }

        const copyLook = (
            !blackout
            && current
            && (
                !useModal
                || lightingModalCopy.checked
            )
        );

        const cue = {
            ...result.cue,
            id: Number(result.cue.id),
            cue_number: Number(
                result.cue.cue_number
            ),
            time_seconds: Number(
                result.cue.time_seconds
            ),
            fade_seconds: Number(
                result.cue.fade_seconds
            ),
            is_blackout: Boolean(
                result.cue.is_blackout
            ),
            focus_areas: (
                copyLook
                    ? current.focus_areas.map(
                        (area) => ({
                            ...area,
                            id: makeId(),
                        })
                    )
                    : []
            ),
            follow_spots: (
                copyLook
                    ? (current.follow_spots || []).map(
                        (spot) => ({
                            ...spot,
                            id: makeId(),
                        })
                    )
                    : []
            ),
            fixture_states: [],
        };

        lightingCues.push(cue);

        activeLightingCueId = cue.id;
        selectedLightingFocusId = null;

        if (useModal) {
            lightingModal.hidden = true;
        }

        renderLightingAll();

        lightingMarkDirty(
            blackout
                ? "Blackout cue added"
                : "Lighting cue added"
        );
    }

    lightingToggle.addEventListener(
        "click",
        () => {
            if (lightingMode) {
                exitLightingMode();
            } else {
                enterLightingMode();
            }
        }
    );

    simpleModeButton.addEventListener("click", () => {
        setLightingDesignMode("simple");
    });

    proModeButton.addEventListener("click", () => {
        setLightingDesignMode("pro");
    });

    document.querySelectorAll("[data-pro-fixture-type]").forEach((button) => {
        const fixtureType = button.dataset.proFixtureType;

        button.addEventListener("click", async () => {
            try {
                await createProFixture(fixtureType, { x: 50, y: 12 });
            } catch (error) {
                window.alert(error.message);
            }
        });

        button.addEventListener("dragstart", (event) => {
            event.dataTransfer.setData(
                "text/encore-fixture-type",
                fixtureType
            );
            event.dataTransfer.effectAllowed = "copy";
        });
    });

    stage.addEventListener("dragover", (event) => {
        if (
            lightingMode
            && lightingDesignMode === "pro"
            && Array.from(event.dataTransfer.types || []).includes(
                "text/encore-fixture-type"
            )
        ) {
            event.preventDefault();
            stage.classList.add("pro-fixture-drop-target");
        }
    });

    stage.addEventListener("dragleave", () => {
        stage.classList.remove("pro-fixture-drop-target");
    });

    stage.addEventListener("drop", async (event) => {
        const fixtureType = event.dataTransfer.getData(
            "text/encore-fixture-type"
        );

        stage.classList.remove("pro-fixture-drop-target");

        if (
            !lightingMode
            || lightingDesignMode !== "pro"
            || !fixtureTypeMeta[fixtureType]
        ) {
            return;
        }

        event.preventDefault();

        try {
            await createProFixture(
                fixtureType,
                pointerPct(event.clientX, event.clientY)
            );
        } catch (error) {
            window.alert(error.message);
        }
    });

    addFocusButton.addEventListener(
        "click",
        () => {
            const cue = activeLightingCue();

            if (
                !cue
                || cue.is_blackout
            ) {
                return;
            }

            const label = nextFocusLabel(cue);

            const area = {
                id: makeId(),
                label,
                x: 50,
                y: 50,
                width: 24,
                height: 24,
                color: "#FFFFFF",
                intensity: 70,
                softness: 70,
                shape: "circle",
            };

            cue.focus_areas.push(area);
            selectedLightingFocusId = area.id;

            renderLightingAll();

            lightingMarkDirty(
                `Focus ${label} added`
            );
        }
    );

    addFollowButton.addEventListener(
        "click",
        () => {
            const cue = activeLightingCue();

            if (!cue || cue.is_blackout) return;

            cue.follow_spots = cue.follow_spots || [];

            const spot = {
                id: makeId(),
                label: `Follow Spot ${cue.follow_spots.length + 1}`,
                target_type: "marker",
                marker: 1,
                x: 50,
                y: 50,
                size: 18,
                color: "#FFFFFF",
                intensity: 80,
                softness: 55,
            };

            cue.follow_spots.push(spot);
            selectedFollowSpotId = spot.id;
            selectedLightingFocusId = null;

            renderLightingAll();
            lightingMarkDirty(`${spot.label} added`);
        }
    );

    [
        followTargetType,
        followMarker,
        followColor,
        followIntensity,
        followSize,
        followSoftness,
    ].forEach((control) => {
        control.addEventListener(
            control.type === "range" ? "input" : "change",
            updateFollowFromControls
        );
    });

    removeFollowButton.addEventListener(
        "click",
        () => {
            const cue = activeLightingCue();

            if (!cue || !selectedFollowSpotId) return;

            cue.follow_spots = (cue.follow_spots || []).filter(
                (spot) => spot.id !== selectedFollowSpotId
            );

            selectedFollowSpotId = null;

            renderLightingAll();
            lightingMarkDirty("Follow spot removed");
        }
    );

    removeFocusButton.addEventListener(
        "click",
        () => {
            const cue = activeLightingCue();

            if (
                !cue
                || !selectedLightingFocusId
            ) {
                return;
            }

            cue.focus_areas = cue.focus_areas.filter(
                (area) => (
                    area.id !== selectedLightingFocusId
                )
            );

            selectedLightingFocusId = null;

            renderLightingAll();

            lightingMarkDirty(
                "Lighting focus removed"
            );
        }
    );

    [
        focusColor,
        focusIntensity,
        focusSoftness,
        focusShape,
        focusWidth,
        focusHeight,
    ].forEach((control) => {
        control.addEventListener(
            control.type === "range"
                ? "input"
                : "change",
            updateFocusFromControls
        );
    });

    [
        cueName,
        cueMinute,
        cueSecond,
        cueFade,
        cueBlackout,
        cueNotes,
    ].forEach((control) => {
        control.addEventListener(
            (
                control.type === "text"
                || control.tagName === "TEXTAREA"
            )
                ? "input"
                : "change",
            updateCueFromControls
        );
    });

    addCueButton.addEventListener(
        "click",
        () => {
            lightingModalError.hidden = true;
            lightingModalName.value = "";

            const current = activeLightingCue();

            const suggested = current
                ? current.time_seconds + 8
                : 0;

            lightingModalMinute.value = String(
                Math.floor(
                    suggested / 60
                )
            );

            lightingModalSecond.value = String(
                suggested % 60
            ).padStart(2, "0");

            lightingModalFade.value = "1";
            lightingModalCopy.checked = true;
            lightingModal.hidden = false;
        }
    );

    lightingModalClose.addEventListener(
        "click",
        () => {
            lightingModal.hidden = true;
        }
    );

    lightingModalCancel.addEventListener(
        "click",
        () => {
            lightingModal.hidden = true;
        }
    );

    lightingModalSave.addEventListener(
        "click",
        async () => {
            lightingModalError.hidden = true;
            lightingModalSave.disabled = true;
            lightingModalSave.textContent = "Adding…";

            try {
                await createLightingCue(
                    {
                        blackout: false,
                        useModal: true,
                    }
                );
            } catch (error) {
                lightingModalError.textContent = error.message;
                lightingModalError.hidden = false;
            } finally {
                lightingModalSave.disabled = false;
                lightingModalSave.textContent = "Add Cue";
            }
        }
    );

    blackoutShortcut.addEventListener(
        "click",
        async () => {
            try {
                await createLightingCue(
                    {
                        blackout: true,
                        useModal: false,
                    }
                );
            } catch (error) {
                window.alert(
                    error.message
                );
            }
        }
    );

    copyOutputButton.addEventListener(
        "click",
        async () => {
            try {
                await navigator.clipboard.writeText(
                    lightingOutputText()
                );

                copyOutputButton.textContent = "Copied";

                setTimeout(
                    () => {
                        copyOutputButton.textContent = "Copy Cue Sheet";
                    },
                    1200
                );
            } catch {
                window.alert(
                    "Could not copy cue sheet."
                );
            }
        }
    );

    tabs.addEventListener(
        "click",
        (event) => {
            if (!lightingMode) return;

            if (
                event.target.closest(
                    ".transition-tab-button"
                )
            ) {
                exitLightingMode();
                return;
            }

            if (
                event.target.closest(
                    ".formation-tab"
                )
            ) {
                setTimeout(
                    () => {
                        if (lightingMode) {
                            activateLightingPanel(
                                "lighting-look"
                            );
                            renderLightingAll();
                        }
                    },
                    0
                );
            }
        },
        true
    );

    window.EncoreLighting = {
        serialize() {
            return lightingCues.map((cue) => ({
                id: cue.id,
                cue_number: cue.cue_number,
                name: cue.name,
                time_seconds: cue.time_seconds,
                fade_seconds: cue.fade_seconds,
                is_blackout: cue.is_blackout,
                notes: cue.notes,
                focus_areas: cue.focus_areas,
                follow_spots: cue.follow_spots || [],
                fixture_states: cue.fixture_states || [],
            }));
        },

        serializeFixtures() {
            return lightingFixtures.map((fixture) => ({
                id: fixture.id,
                fixture_number: fixture.fixture_number,
                label: fixture.label,
                fixture_type: fixture.fixture_type,
                x: fixture.x,
                y: fixture.y,
                notes: fixture.notes,
            }));
        },

        onPlaybackTime(time, enabled) {
            lightingPlaybackTime = Number(time) || 0;
            lightingPlaybackEnabled = Boolean(enabled);

            if (lightingPlaybackEnabled) {
                renderPlaybackLighting(
                    lightingPlaybackTime
                );
                return;
            }

            if (lightingMode) {
                app.classList.add(
                    "has-lighting-cues"
                );
                renderLightingLook();
            } else {
                lightingLayer.innerHTML = "";
                app.classList.remove(
                    "has-lighting-cues"
                );
            }
        },
    };

    renderLightingAll();
})();


/* =========================================================
   Stage Drawing V1
   ========================================================= */
(() => {
    const drawLayer = document.getElementById("stage-drawing-layer");
    const textLayer = document.getElementById("stage-text-layer");
    const drawInstruction = document.getElementById("draw-instruction");
    const drawProperties = document.getElementById("draw-properties");
    const drawPropertiesEmpty = document.getElementById("draw-properties-empty");
    const drawSelectedName = document.getElementById("draw-selected-name");
    const shapeProperties = document.getElementById("shape-draw-properties");
    const lineProperties = document.getElementById("line-draw-properties");
    const textProperties = document.getElementById("text-draw-properties");
    const deleteDrawingButton = document.getElementById("delete-stage-drawing");

    if (
        !drawLayer
        || !textLayer
    ) {
        return;
    }

    const STAGE_W = 980;
    const STAGE_H = 650;

    const drawTools = Array.from(
        document.querySelectorAll(
            "[data-draw-tool]"
        )
    );

    const fillEnabled = document.getElementById("draw-fill-enabled");
    const fillColor = document.getElementById("draw-fill-color");
    const strokeEnabled = document.getElementById("draw-stroke-enabled");
    const strokeColor = document.getElementById("draw-stroke-color");
    const strokeWidth = document.getElementById("draw-stroke-width");
    const strokeWidthValue = document.getElementById("draw-stroke-width-value");

    const lineStrokeEnabled = document.getElementById("draw-line-stroke-enabled");
    const lineColor = document.getElementById("draw-line-color");
    const lineWidth = document.getElementById("draw-line-width");
    const lineWidthValue = document.getElementById("draw-line-width-value");
    const lineStraighten = document.getElementById("draw-line-straighten");

    const textContent = document.getElementById("draw-text-content");
    const textFont = document.getElementById("draw-text-font");
    const textSize = document.getElementById("draw-text-size");
    const textSizeValue = document.getElementById("draw-text-size-value");
    const textBold = document.getElementById("draw-text-bold");
    const textItalic = document.getElementById("draw-text-italic");
    const textUnderline = document.getElementById("draw-text-underline");
    const textColor = document.getElementById("draw-text-color");
    const textAlignButtons = Array.from(
        document.querySelectorAll(
            "[data-text-align]"
        )
    );

    const colorPalette = [
        "#FFFFFF",
        "#CBD5E1",
        "#94A3B8",
        "#64748B",
        "#00024E",
        "#1663FF",
        "#0197FC",
        "#10B981",
        "#F59E0B",
        "#EF4444",
        "#EC4899",
        "#8B5CF6",
        "#111827",
        "#000000",
    ];

    let drawings = (
        data.stage_drawings
        || []
    ).map(normalizeDrawing);

    let activeTool = "select";
    let selectedDrawingId = null;
    let drawingGesture = null;
    let draggingDrawing = null;
    let drawPanelActive = false;
    let previewElement = null;

    function makeDrawingId() {
        if (
            window.crypto
            && window.crypto.randomUUID
        ) {
            return window.crypto.randomUUID();
        }

        return (
            "drawing-"
            + Date.now()
            + "-"
            + Math.random().toString(16).slice(2)
        );
    }

    function clamp(value, min, max) {
        return Math.max(
            min,
            Math.min(
                max,
                Number(value)
            )
        );
    }

    function pctToX(value) {
        return (
            clamp(
                value,
                0,
                100
            )
            / 100
        ) * STAGE_W;
    }

    function pctToY(value) {
        return (
            clamp(
                value,
                0,
                100
            )
            / 100
        ) * STAGE_H;
    }

    function normalizeDrawing(item) {
        const type = String(
            item.type
            || "rectangle"
        );

        const base = {
            id: String(
                item.id
                || makeDrawingId()
            ),
            type,
        };

        if (type === "line") {
            return {
                ...base,
                x1: Number(item.x1 ?? 30),
                y1: Number(item.y1 ?? 50),
                x2: Number(item.x2 ?? 70),
                y2: Number(item.y2 ?? 50),
                cx: Number(item.cx ?? 50),
                cy: Number(item.cy ?? 50),
                stroke_enabled: item.stroke_enabled !== false,
                stroke_color: item.stroke_color || "#00024E",
                stroke_width: Number(item.stroke_width ?? 2),
            };
        }

        if (type === "text") {
            return {
                ...base,
                x: Number(item.x ?? 50),
                y: Number(item.y ?? 50),
                width: Number(item.width ?? 24),
                height: Number(item.height ?? 8),
                text: String(item.text ?? "Text"),
                font_family: item.font_family || "Arial, sans-serif",
                font_size: Number(item.font_size ?? 24),
                bold: Boolean(item.bold),
                italic: Boolean(item.italic),
                underline: Boolean(item.underline),
                align: ["left","center","right"].includes(item.align)
                    ? item.align
                    : "left",
                color: item.color || "#00024E",
            };
        }

        return {
            ...base,
            x: Number(item.x ?? 35),
            y: Number(item.y ?? 35),
            width: Number(item.width ?? 20),
            height: Number(item.height ?? 20),
            fill_enabled: item.fill_enabled !== false,
            fill_color: item.fill_color || "#DCE6FF",
            stroke_enabled: item.stroke_enabled !== false,
            stroke_color: item.stroke_color || "#00024E",
            stroke_width: Number(item.stroke_width ?? 2),
        };
    }

    function selectedDrawing() {
        return drawings.find(
            (item) => (
                item.id
                === selectedDrawingId
            )
        ) || null;
    }

    function drawToolName(type) {
        const names = {
            square: "Square",
            rectangle: "Rectangle",
            circle: "Circle",
            half_circle: "Half Circle",
            oval: "Oval",
            triangle: "Triangle",
            line: "Line",
            text: "Text",
        };

        return names[type]
            || "Drawing";
    }

    function markDrawingDirty(message) {
        data.stage_drawings = drawings;
        markDirty(
            message
            || "Stage drawing changed"
        );
    }

    function svgElement(name, attrs={}) {
        const element = document.createElementNS(
            "http://www.w3.org/2000/svg",
            name
        );

        Object.entries(attrs).forEach(
            ([key,value]) => {
                if (
                    value !== null
                    && value !== undefined
                ) {
                    element.setAttribute(
                        key,
                        String(value)
                    );
                }
            }
        );

        return element;
    }

    function shapeBounds(item) {
        let widthPx = pctToX(
            item.width
        );

        let heightPx = pctToY(
            item.height
        );

        if (
            item.type === "square"
            || item.type === "circle"
        ) {
            const size = Math.max(
                12,
                Math.min(
                    widthPx,
                    heightPx
                )
            );

            widthPx = size;
            heightPx = size;
        }

        return {
            x: pctToX(item.x),
            y: pctToY(item.y),
            w: widthPx,
            h: heightPx,
        };
    }

    function linePath(item) {
        const x1 = pctToX(
            item.x1
        );
        const y1 = pctToY(
            item.y1
        );
        const x2 = pctToX(
            item.x2
        );
        const y2 = pctToY(
            item.y2
        );
        const cx = pctToX(
            item.cx
        );
        const cy = pctToY(
            item.cy
        );

        return (
            `M ${x1} ${y1} `
            + `Q ${cx} ${cy} `
            + `${x2} ${y2}`
        );
    }

    function renderShape(item) {
        const bounds = shapeBounds(
            item
        );

        const group = svgElement(
            "g",
            {
                "data-drawing-id": item.id,
                "class": (
                    "stage-drawing-item"
                    + (
                        item.id === selectedDrawingId
                            ? " selected"
                            : ""
                    )
                ),
            }
        );

        const style = {
            fill: item.fill_enabled
                ? item.fill_color
                : "none",
            stroke: item.stroke_enabled
                ? item.stroke_color
                : "none",
            "stroke-width": item.stroke_width,
            "vector-effect": "non-scaling-stroke",
        };

        let shape;

        if (
            item.type === "square"
            || item.type === "rectangle"
        ) {
            shape = svgElement(
                "rect",
                {
                    x: bounds.x,
                    y: bounds.y,
                    width: bounds.w,
                    height: bounds.h,
                    rx: 2,
                    ...style,
                }
            );
        } else if (
            item.type === "circle"
            || item.type === "oval"
        ) {
            shape = svgElement(
                "ellipse",
                {
                    cx: bounds.x + bounds.w / 2,
                    cy: bounds.y + bounds.h / 2,
                    rx: bounds.w / 2,
                    ry: bounds.h / 2,
                    ...style,
                }
            );
        } else if (
            item.type === "half_circle"
        ) {
            const x1 = bounds.x;
            const x2 = bounds.x + bounds.w;
            const y = bounds.y + bounds.h;
            const rx = bounds.w / 2;
            const ry = bounds.h;

            shape = svgElement(
                "path",
                {
                    d: (
                        `M ${x1} ${y} `
                        + `A ${rx} ${ry} 0 0 1 ${x2} ${y} `
                        + `L ${x1} ${y} Z`
                    ),
                    ...style,
                }
            );
        } else {
            shape = svgElement(
                "polygon",
                {
                    points: (
                        `${bounds.x + bounds.w / 2},${bounds.y} `
                        + `${bounds.x + bounds.w},${bounds.y + bounds.h} `
                        + `${bounds.x},${bounds.y + bounds.h}`
                    ),
                    ...style,
                }
            );
        }

        shape.classList.add(
            "stage-drawing-shape"
        );
        shape.dataset.drawingId = item.id;

        group.appendChild(
            shape
        );

        const hit = svgElement(
            "rect",
            {
                x: bounds.x,
                y: bounds.y,
                width: bounds.w,
                height: bounds.h,
                fill: "rgba(0,0,0,0.001)",
                stroke: "transparent",
                "class": "stage-drawing-hit stage-drawing-shape-hit",
                "data-drawing-id": item.id,
            }
        );

        group.appendChild(
            hit
        );

        if (
            item.id
            === selectedDrawingId
        ) {
            const selection = svgElement(
                "rect",
                {
                    x: bounds.x,
                    y: bounds.y,
                    width: bounds.w,
                    height: bounds.h,
                    fill: "none",
                    stroke: "#1663FF",
                    "stroke-width": 1.5,
                    "stroke-dasharray": "6 4",
                    "vector-effect": "non-scaling-stroke",
                    "class": "stage-drawing-selection",
                }
            );

            const handle = svgElement(
                "circle",
                {
                    cx: bounds.x + bounds.w,
                    cy: bounds.y + bounds.h,
                    r: 6,
                    fill: "#FFFFFF",
                    stroke: "#1663FF",
                    "stroke-width": 2,
                    "vector-effect": "non-scaling-stroke",
                    "class": "stage-drawing-handle stage-drawing-resize-handle",
                    "data-handle": "resize",
                }
            );

            group.append(
                selection,
                handle
            );
        }

        bindDrawingPointer(
            group,
            item
        );

        drawLayer.appendChild(
            group
        );
    }

    function renderLine(item) {
        const group = svgElement(
            "g",
            {
                "data-drawing-id": item.id,
                "class": (
                    "stage-drawing-item stage-drawing-line"
                    + (
                        item.id === selectedDrawingId
                            ? " selected"
                            : ""
                    )
                ),
            }
        );

        const visible = svgElement(
            "path",
            {
                d: linePath(item),
                fill: "none",
                stroke: item.stroke_enabled
                    ? item.stroke_color
                    : "transparent",
                "stroke-width": item.stroke_width,
                "vector-effect": "non-scaling-stroke",
                "class": "stage-drawing-line-visible",
            }
        );

        const hit = svgElement(
            "path",
            {
                d: linePath(item),
                fill: "none",
                stroke: "rgba(0,0,0,0.001)",
                "stroke-width": 16,
                "vector-effect": "non-scaling-stroke",
                "class": "stage-drawing-hit",
                "data-drawing-id": item.id,
            }
        );

        group.append(
            visible,
            hit
        );

        if (
            item.id
            === selectedDrawingId
        ) {
            [
                ["start", item.x1, item.y1],
                ["curve", item.cx, item.cy],
                ["end", item.x2, item.y2],
            ].forEach(
                ([name,x,y]) => {
                    const handle = svgElement(
                        "circle",
                        {
                            cx: pctToX(x),
                            cy: pctToY(y),
                            r: name === "curve"
                                ? 6
                                : 7,
                            fill: name === "curve"
                                ? "#DCE6FF"
                                : "#FFFFFF",
                            stroke: "#1663FF",
                            "stroke-width": 2,
                            "vector-effect": "non-scaling-stroke",
                            "class": (
                                "stage-drawing-handle "
                                + (
                                    name === "curve"
                                        ? "stage-drawing-curve-handle"
                                        : "stage-drawing-line-handle"
                                )
                            ),
                            "data-handle": name,
                        }
                    );

                    group.appendChild(
                        handle
                    );
                }
            );
        }

        bindDrawingPointer(
            group,
            item
        );

        drawLayer.appendChild(
            group
        );
    }

    function renderText(item) {
        const wrapper = document.createElement(
            "div"
        );

        wrapper.className = (
            "stage-text-drawing"
            + (
                item.id === selectedDrawingId
                    ? " selected"
                    : ""
            )
        );

        wrapper.dataset.drawingId = item.id;
        wrapper.style.left = `${item.x}%`;
        wrapper.style.top = `${item.y}%`;
        wrapper.style.width = `${item.width}%`;
        wrapper.style.minHeight = `${item.height}%`;
        wrapper.style.fontFamily = item.font_family;
        wrapper.style.fontSize = `${item.font_size}px`;
        wrapper.style.fontWeight = item.bold
            ? "700"
            : "400";
        wrapper.style.fontStyle = item.italic
            ? "italic"
            : "normal";
        wrapper.style.textDecoration = item.underline
            ? "underline"
            : "none";
        wrapper.style.textAlign = item.align;
        wrapper.style.color = item.color;
        wrapper.textContent = item.text;

        wrapper.addEventListener(
            "pointerdown",
            (event) => {
                if (
                    !drawPanelActive
                    || activeTool !== "select"
                ) {
                    return;
                }

                selectedDrawingId = item.id;

                draggingDrawing = {
                    kind: "move-text",
                    id: item.id,
                    start: pointerPct(
                        event.clientX,
                        event.clientY
                    ),
                    origin: {
                        x: item.x,
                        y: item.y,
                    },
                };

                wrapper.setPointerCapture(
                    event.pointerId
                );

                event.preventDefault();
                event.stopPropagation();

                renderDrawings();
                renderDrawingProperties();
            }
        );

        wrapper.addEventListener(
            "pointermove",
            (event) => {
                if (
                    !draggingDrawing
                    || draggingDrawing.id !== item.id
                    || draggingDrawing.kind !== "move-text"
                ) {
                    return;
                }

                const current = pointerPct(
                    event.clientX,
                    event.clientY
                );

                item.x = clamp(
                    draggingDrawing.origin.x
                    + current.x
                    - draggingDrawing.start.x,
                    0,
                    100 - item.width
                );

                item.y = clamp(
                    draggingDrawing.origin.y
                    + current.y
                    - draggingDrawing.start.y,
                    0,
                    100 - item.height
                );

                wrapper.style.left = `${item.x}%`;
                wrapper.style.top = `${item.y}%`;

                markDrawingDirty(
                    "Text moved"
                );
            }
        );

        const end = (event) => {
            if (
                !draggingDrawing
                || draggingDrawing.id !== item.id
            ) {
                return;
            }

            draggingDrawing = null;

            try {
                wrapper.releasePointerCapture(
                    event.pointerId
                );
            } catch {}

            renderDrawings();
        };

        wrapper.addEventListener(
            "pointerup",
            end
        );

        wrapper.addEventListener(
            "pointercancel",
            end
        );

        textLayer.appendChild(
            wrapper
        );
    }

    function renderDrawings() {
        drawLayer.innerHTML = "";
        textLayer.innerHTML = "";

        drawings.forEach(
            (item) => {
                if (
                    item.type === "line"
                ) {
                    renderLine(
                        item
                    );
                } else if (
                    item.type === "text"
                ) {
                    renderText(
                        item
                    );
                } else {
                    renderShape(
                        item
                    );
                }
            }
        );

        stage.classList.toggle(
            "draw-tool-active",
            activeTool !== "select"
        );

        stage.classList.toggle(
            "draw-select-active",
            activeTool === "select"
        );
    }

    function pointerFromSvgEvent(event) {
        return pointerPct(
            event.clientX,
            event.clientY
        );
    }

    function beginDrawingSelection(
        event,
        item
    ) {
        if (
            !drawPanelActive
            || activeTool !== "select"
            || !item
        ) {
            return false;
        }

        selectedDrawingId = item.id;

        const handle = (
            event.target instanceof Element
                ? event.target.closest("[data-handle]")
                : null
        );

        const start = pointerFromSvgEvent(
            event
        );

        if (
            item.type === "line"
            && handle
        ) {
            draggingDrawing = {
                kind: "line-handle",
                id: item.id,
                handle: handle.dataset.handle,
            };
        } else if (
            handle
            && handle.dataset.handle === "resize"
        ) {
            draggingDrawing = {
                kind: "resize",
                id: item.id,
                start,
                origin: {
                    width: item.width,
                    height: item.height,
                },
            };
        } else {
            draggingDrawing = {
                kind: "move",
                id: item.id,
                start,
                origin: item.type === "line"
                    ? {
                        x1: item.x1,
                        y1: item.y1,
                        x2: item.x2,
                        y2: item.y2,
                        cx: item.cx,
                        cy: item.cy,
                    }
                    : {
                        x: item.x,
                        y: item.y,
                    },
            };
        }

        try {
            drawLayer.setPointerCapture(
                event.pointerId
            );
        } catch {}

        event.preventDefault();
        event.stopPropagation();

        renderDrawings();
        renderDrawingProperties();

        return true;
    }

    function bindDrawingPointer(
        group,
        item
    ) {
        /*
        Selection is delegated from drawLayer below. Keeping the
        drawing id on each group gives SVG shapes one consistent
        interaction path regardless of which child was clicked.
        */
        group.dataset.drawingId = item.id;
    }

    drawLayer.addEventListener(
        "pointerdown",
        (event) => {
            if (
                !drawPanelActive
                || activeTool !== "select"
            ) {
                return;
            }

            const target = (
                event.target instanceof Element
                    ? event.target.closest("[data-drawing-id]")
                    : null
            );

            if (!target) {
                selectedDrawingId = null;
                draggingDrawing = null;
                renderDrawings();
                renderDrawingProperties();
                return;
            }

            const item = drawings.find(
                (row) => (
                    row.id === target.dataset.drawingId
                )
            );

            beginDrawingSelection(
                event,
                item
            );
        },
        true
    );

    drawLayer.addEventListener(
        "pointermove",
        (event) => {
            if (
                !draggingDrawing
            ) {
                return;
            }

            const item = drawings.find(
                (row) => (
                    row.id === draggingDrawing.id
                )
            );

            if (!item) {
                return;
            }

            const current = pointerFromSvgEvent(
                event
            );

            if (
                draggingDrawing.kind === "line-handle"
            ) {
                if (
                    draggingDrawing.handle === "start"
                ) {
                    item.x1 = current.x;
                    item.y1 = current.y;
                } else if (
                    draggingDrawing.handle === "end"
                ) {
                    item.x2 = current.x;
                    item.y2 = current.y;
                } else {
                    item.cx = current.x;
                    item.cy = current.y;
                }
            } else if (
                draggingDrawing.kind === "resize"
            ) {
                const deltaX = (
                    current.x
                    - draggingDrawing.start.x
                );

                const deltaY = (
                    current.y
                    - draggingDrawing.start.y
                );

                item.width = clamp(
                    draggingDrawing.origin.width
                    + deltaX,
                    2,
                    100 - item.x
                );

                item.height = clamp(
                    draggingDrawing.origin.height
                    + deltaY,
                    2,
                    100 - item.y
                );

                if (
                    item.type === "square"
                    || item.type === "circle"
                ) {
                    const widthPx = pctToX(
                        item.width
                    );

                    item.height = clamp(
                        (
                            widthPx
                            / STAGE_H
                        ) * 100,
                        2,
                        100 - item.y
                    );
                }
            } else if (
                draggingDrawing.kind === "move"
            ) {
                const dx = (
                    current.x
                    - draggingDrawing.start.x
                );

                const dy = (
                    current.y
                    - draggingDrawing.start.y
                );

                if (
                    item.type === "line"
                ) {
                    const points = [
                        ["x1","y1"],
                        ["x2","y2"],
                        ["cx","cy"],
                    ];

                    const next = {};

                    points.forEach(
                        ([xKey,yKey]) => {
                            next[xKey] = draggingDrawing.origin[xKey] + dx;
                            next[yKey] = draggingDrawing.origin[yKey] + dy;
                        }
                    );

                    const minX = Math.min(
                        next.x1,
                        next.x2,
                        next.cx
                    );

                    const maxX = Math.max(
                        next.x1,
                        next.x2,
                        next.cx
                    );

                    const minY = Math.min(
                        next.y1,
                        next.y2,
                        next.cy
                    );

                    const maxY = Math.max(
                        next.y1,
                        next.y2,
                        next.cy
                    );

                    const adjustX = (
                        minX < 0
                            ? -minX
                            : maxX > 100
                                ? 100 - maxX
                                : 0
                    );

                    const adjustY = (
                        minY < 0
                            ? -minY
                            : maxY > 100
                                ? 100 - maxY
                                : 0
                    );

                    points.forEach(
                        ([xKey,yKey]) => {
                            item[xKey] = next[xKey] + adjustX;
                            item[yKey] = next[yKey] + adjustY;
                        }
                    );
                } else {
                    item.x = clamp(
                        draggingDrawing.origin.x + dx,
                        0,
                        100 - item.width
                    );

                    item.y = clamp(
                        draggingDrawing.origin.y + dy,
                        0,
                        100 - item.height
                    );
                }
            }

            markDrawingDirty(
                "Stage drawing changed"
            );

            renderDrawings();
        }
    );

    const endSvgDrag = (event) => {
        if (
            !draggingDrawing
        ) {
            return;
        }

        draggingDrawing = null;

        try {
            drawLayer.releasePointerCapture(
                event.pointerId
            );
        } catch {}

        renderDrawings();
        renderDrawingProperties();
    };

    drawLayer.addEventListener(
        "pointerup",
        endSvgDrag
    );

    drawLayer.addEventListener(
        "pointercancel",
        endSvgDrag
    );

    function clearDrawingPreview() {
        if (
            previewElement
            && previewElement.parentNode
        ) {
            previewElement.parentNode.removeChild(
                previewElement
            );
        }

        previewElement = null;
    }

    function renderDrawingPreview(
        tool,
        start,
        end
    ) {
        clearDrawingPreview();

        const preview = createFromDrag(
            tool,
            start,
            end
        );

        if (!preview) return;

        if (preview.type === "text") {
            const bounds = {
                x: pctToX(preview.x),
                y: pctToY(preview.y),
                w: pctToX(preview.width),
                h: pctToY(preview.height),
            };

            previewElement = svgElement(
                "rect",
                {
                    x: bounds.x,
                    y: bounds.y,
                    width: bounds.w,
                    height: bounds.h,
                    fill: "rgba(22,99,255,.06)",
                    stroke: "#1663FF",
                    "stroke-width": 1.5,
                    "stroke-dasharray": "7 5",
                    "vector-effect": "non-scaling-stroke",
                    "class": "stage-drawing-preview",
                }
            );
        } else if (preview.type === "line") {
            previewElement = svgElement(
                "path",
                {
                    d: linePath(preview),
                    fill: "none",
                    stroke: "#1663FF",
                    "stroke-width": 1.5,
                    "stroke-dasharray": "7 5",
                    "vector-effect": "non-scaling-stroke",
                    "class": "stage-drawing-preview",
                }
            );
        } else {
            const bounds = shapeBounds(
                preview
            );

            if (
                preview.type === "square"
                || preview.type === "rectangle"
            ) {
                previewElement = svgElement(
                    "rect",
                    {
                        x: bounds.x,
                        y: bounds.y,
                        width: bounds.w,
                        height: bounds.h,
                        rx: 2,
                        fill: "rgba(22,99,255,.06)",
                        stroke: "#1663FF",
                        "stroke-width": 1.5,
                        "stroke-dasharray": "7 5",
                        "vector-effect": "non-scaling-stroke",
                        "class": "stage-drawing-preview",
                    }
                );
            } else if (
                preview.type === "circle"
                || preview.type === "oval"
            ) {
                previewElement = svgElement(
                    "ellipse",
                    {
                        cx: bounds.x + bounds.w / 2,
                        cy: bounds.y + bounds.h / 2,
                        rx: bounds.w / 2,
                        ry: bounds.h / 2,
                        fill: "rgba(22,99,255,.06)",
                        stroke: "#1663FF",
                        "stroke-width": 1.5,
                        "stroke-dasharray": "7 5",
                        "vector-effect": "non-scaling-stroke",
                        "class": "stage-drawing-preview",
                    }
                );
            } else if (
                preview.type === "half_circle"
            ) {
                const x1 = bounds.x;
                const x2 = bounds.x + bounds.w;
                const y = bounds.y + bounds.h;
                const rx = bounds.w / 2;
                const ry = bounds.h;

                previewElement = svgElement(
                    "path",
                    {
                        d: (
                            `M ${x1} ${y} `
                            + `A ${rx} ${ry} 0 0 1 ${x2} ${y} `
                            + `L ${x1} ${y} Z`
                        ),
                        fill: "rgba(22,99,255,.06)",
                        stroke: "#1663FF",
                        "stroke-width": 1.5,
                        "stroke-dasharray": "7 5",
                        "vector-effect": "non-scaling-stroke",
                        "class": "stage-drawing-preview",
                    }
                );
            } else {
                previewElement = svgElement(
                    "polygon",
                    {
                        points: (
                            `${bounds.x + bounds.w / 2},${bounds.y} `
                            + `${bounds.x + bounds.w},${bounds.y + bounds.h} `
                            + `${bounds.x},${bounds.y + bounds.h}`
                        ),
                        fill: "rgba(22,99,255,.06)",
                        stroke: "#1663FF",
                        "stroke-width": 1.5,
                        "stroke-dasharray": "7 5",
                        "vector-effect": "non-scaling-stroke",
                        "class": "stage-drawing-preview",
                    }
                );
            }
        }

        if (previewElement) {
            drawLayer.appendChild(
                previewElement
            );
        }
    }

    function createFromDrag(
        tool,
        start,
        end
    ) {
        const x = Math.min(
            start.x,
            end.x
        );

        const y = Math.min(
            start.y,
            end.y
        );

        const width = Math.max(
            2,
            Math.abs(
                end.x
                - start.x
            )
        );

        const height = Math.max(
            2,
            Math.abs(
                end.y
                - start.y
            )
        );

        if (
            tool === "line"
        ) {
            return {
                id: makeDrawingId(),
                type: "line",
                x1: start.x,
                y1: start.y,
                x2: end.x,
                y2: end.y,
                cx: (
                    start.x
                    + end.x
                ) / 2,
                cy: (
                    start.y
                    + end.y
                ) / 2,
                stroke_enabled: true,
                stroke_color: "#00024E",
                stroke_width: 2,
            };
        }

        if (
            tool === "text"
        ) {
            return {
                id: makeDrawingId(),
                type: "text",
                x,
                y,
                width: Math.max(
                    12,
                    width
                ),
                height: Math.max(
                    6,
                    height
                ),
                text: "Text",
                font_family: "Arial, sans-serif",
                font_size: 24,
                bold: false,
                italic: false,
                underline: false,
                align: "left",
                color: "#00024E",
            };
        }

        let nextWidth = width;
        let nextHeight = height;

        if (
            tool === "square"
            || tool === "circle"
        ) {
            const pixelWidth = pctToX(
                width
            );
            const pixelHeight = pctToY(
                height
            );

            const size = Math.max(
                18,
                Math.min(
                    pixelWidth,
                    pixelHeight
                )
            );

            nextWidth = (
                size
                / STAGE_W
            ) * 100;

            nextHeight = (
                size
                / STAGE_H
            ) * 100;
        }

        return {
            id: makeDrawingId(),
            type: tool,
            x,
            y,
            width: nextWidth,
            height: nextHeight,
            fill_enabled: true,
            fill_color: "#DCE6FF",
            stroke_enabled: true,
            stroke_color: "#00024E",
            stroke_width: 2,
        };
    }

    stage.addEventListener(
        "pointerdown",
        (event) => {
            if (
                !drawPanelActive
                || activeTool === "select"
                || event.button !== 0
                || event.target.closest(
                    ".stage-drawing-item, .stage-text-drawing"
                )
            ) {
                return;
            }

            const start = pointerPct(
                event.clientX,
                event.clientY
            );

            drawingGesture = {
                tool: activeTool,
                start,
                current: start,
            };

            stage.setPointerCapture(
                event.pointerId
            );

            event.preventDefault();
            event.stopPropagation();
        },
        true
    );

    stage.addEventListener(
        "pointermove",
        (event) => {
            if (
                !drawingGesture
            ) {
                return;
            }

            drawingGesture.current = pointerPct(
                event.clientX,
                event.clientY
            );

            renderDrawingPreview(
                drawingGesture.tool,
                drawingGesture.start,
                drawingGesture.current
            );
        },
        true
    );

    const finishCreation = (event) => {
        if (
            !drawingGesture
        ) {
            return;
        }

        const item = createFromDrag(
            drawingGesture.tool,
            drawingGesture.start,
            drawingGesture.current
        );

        drawings.push(
            item
        );

        selectedDrawingId = item.id;
        drawingGesture = null;
        clearDrawingPreview();

        try {
            stage.releasePointerCapture(
                event.pointerId
            );
        } catch {}

        setTool(
            "select"
        );

        renderDrawings();
        renderDrawingProperties();

        markDrawingDirty(
            `${drawToolName(item.type)} added`
        );
    };

    stage.addEventListener(
        "pointerup",
        finishCreation,
        true
    );

    stage.addEventListener(
        "pointercancel",
        () => {
            drawingGesture = null;
            clearDrawingPreview();
        },
        true
    );

    stage.addEventListener(
        "click",
        (event) => {
            if (
                activeTool !== "select"
            ) {
                return;
            }

            if (
                event.target === stage
                || event.target.classList.contains(
                    "stage-grid-overlay"
                )
                || event.target.classList.contains(
                    "stage-main-outline"
                )
            ) {
                selectedDrawingId = null;
                renderDrawings();
                renderDrawingProperties();
            }
        }
    );

    function setTool(tool) {
        activeTool = tool;

        drawTools.forEach(
            (button) => {
                button.classList.toggle(
                    "active",
                    button.dataset.drawTool === activeTool
                );
            }
        );

        if (
            drawInstruction
        ) {
            drawInstruction.textContent = (
                activeTool === "select"
                    ? "Select a drawing to move or edit it."
                    : "Drag on the stage to add "
                        + drawToolName(activeTool).toLowerCase()
                        + "."
            );
        }

        renderDrawings();
    }

    drawTools.forEach(
        (button) => {
            button.addEventListener(
                "click",
                () => {
                    setTool(
                        button.dataset.drawTool
                    );
                }
            );
        }
    );

    function updateStyleButtons(
        item
    ) {
        textBold?.classList.toggle(
            "active",
            Boolean(item.bold)
        );

        textItalic?.classList.toggle(
            "active",
            Boolean(item.italic)
        );

        textUnderline?.classList.toggle(
            "active",
            Boolean(item.underline)
        );

        textAlignButtons.forEach(
            (button) => {
                button.classList.toggle(
                    "active",
                    button.dataset.textAlign === item.align
                );
            }
        );
    }

    function renderDrawingProperties() {
        const item = selectedDrawing();

        if (
            !item
        ) {
            drawProperties.hidden = true;
            drawPropertiesEmpty.hidden = false;
            return;
        }

        drawProperties.hidden = false;
        drawPropertiesEmpty.hidden = true;

        drawSelectedName.textContent = drawToolName(
            item.type
        );

        shapeProperties.hidden = (
            item.type === "line"
            || item.type === "text"
        );

        lineProperties.hidden = (
            item.type !== "line"
        );

        textProperties.hidden = (
            item.type !== "text"
        );

        if (
            item.type === "line"
        ) {
            lineStrokeEnabled.checked = item.stroke_enabled !== false;
            lineColor.value = item.stroke_color;
            lineWidth.value = String(item.stroke_width);
            lineWidthValue.textContent = String(item.stroke_width);
        } else if (
            item.type === "text"
        ) {
            textContent.value = item.text;
            textFont.value = item.font_family;
            textSize.value = String(item.font_size);
            textSizeValue.textContent = String(item.font_size);
            textColor.value = item.color;
            updateStyleButtons(
                item
            );
        } else {
            fillEnabled.checked = item.fill_enabled !== false;
            fillColor.value = item.fill_color;
            strokeEnabled.checked = item.stroke_enabled !== false;
            strokeColor.value = item.stroke_color;
            strokeWidth.value = String(item.stroke_width);
            strokeWidthValue.textContent = String(item.stroke_width);
        }
    }

    function updateSelectedShape() {
        const item = selectedDrawing();

        if (
            !item
            || item.type === "line"
            || item.type === "text"
        ) {
            return;
        }

        item.fill_enabled = fillEnabled.checked;
        item.fill_color = fillColor.value.toUpperCase();
        item.stroke_enabled = strokeEnabled.checked;
        item.stroke_color = strokeColor.value.toUpperCase();
        item.stroke_width = Number(
            strokeWidth.value
        );

        strokeWidthValue.textContent = String(
            item.stroke_width
        );

        markDrawingDirty(
            "Shape style changed"
        );

        renderDrawings();
    }

    [
        fillEnabled,
        fillColor,
        strokeEnabled,
        strokeColor,
        strokeWidth,
    ].forEach(
        (control) => {
            control?.addEventListener(
                control?.type === "range"
                    ? "input"
                    : "change",
                updateSelectedShape
            );
        }
    );

    function updateSelectedLine() {
        const item = selectedDrawing();

        if (
            !item
            || item.type !== "line"
        ) {
            return;
        }

        item.stroke_enabled = lineStrokeEnabled.checked;
        item.stroke_color = lineColor.value.toUpperCase();
        item.stroke_width = Number(
            lineWidth.value
        );

        lineWidthValue.textContent = String(
            item.stroke_width
        );

        markDrawingDirty(
            "Line style changed"
        );

        renderDrawings();
    }

    [
        lineStrokeEnabled,
        lineColor,
        lineWidth,
    ].forEach(
        (control) => {
            control?.addEventListener(
                control?.type === "range"
                    ? "input"
                    : "change",
                updateSelectedLine
            );
        }
    );

    lineStraighten?.addEventListener(
        "click",
        () => {
            const item = selectedDrawing();

            if (
                !item
                || item.type !== "line"
            ) {
                return;
            }

            item.cx = (
                item.x1
                + item.x2
            ) / 2;

            item.cy = (
                item.y1
                + item.y2
            ) / 2;

            markDrawingDirty(
                "Line straightened"
            );

            renderDrawings();
        }
    );

    function updateSelectedText() {
        const item = selectedDrawing();

        if (
            !item
            || item.type !== "text"
        ) {
            return;
        }

        item.text = textContent.value;
        item.font_family = textFont.value;
        item.font_size = Number(
            textSize.value
        );
        item.color = textColor.value.toUpperCase();

        textSizeValue.textContent = String(
            item.font_size
        );

        markDrawingDirty(
            "Text changed"
        );

        renderDrawings();
    }

    [
        textContent,
        textFont,
        textSize,
        textColor,
    ].forEach(
        (control) => {
            control?.addEventListener(
                control?.type === "range"
                    || control?.tagName === "TEXTAREA"
                    ? "input"
                    : "change",
                updateSelectedText
            );
        }
    );

    [
        [textBold, "bold"],
        [textItalic, "italic"],
        [textUnderline, "underline"],
    ].forEach(
        ([button,key]) => {
            button?.addEventListener(
                "click",
                () => {
                    const item = selectedDrawing();

                    if (
                        !item
                        || item.type !== "text"
                    ) {
                        return;
                    }

                    item[key] = !item[key];

                    updateStyleButtons(
                        item
                    );

                    markDrawingDirty(
                        "Text style changed"
                    );

                    renderDrawings();
                }
            );
        }
    );

    textAlignButtons.forEach(
        (button) => {
            button.addEventListener(
                "click",
                () => {
                    const item = selectedDrawing();

                    if (
                        !item
                        || item.type !== "text"
                    ) {
                        return;
                    }

                    item.align = button.dataset.textAlign;

                    updateStyleButtons(
                        item
                    );

                    markDrawingDirty(
                        "Text alignment changed"
                    );

                    renderDrawings();
                }
            );
        }
    );

    deleteDrawingButton?.addEventListener(
        "click",
        () => {
            if (
                !selectedDrawingId
            ) {
                return;
            }

            drawings = drawings.filter(
                (item) => (
                    item.id !== selectedDrawingId
                )
            );

            selectedDrawingId = null;

            markDrawingDirty(
                "Stage drawing deleted"
            );

            renderDrawings();
            renderDrawingProperties();
        }
    );

    function buildColorSwatches() {
        document.querySelectorAll(
            ".draw-color-swatches"
        ).forEach(
            (holder) => {
                holder.innerHTML = "";

                colorPalette.forEach(
                    (color) => {
                        const button = document.createElement(
                            "button"
                        );

                        button.type = "button";
                        button.style.setProperty(
                            "--draw-swatch",
                            color
                        );
                        button.title = color;

                        button.addEventListener(
                            "click",
                            () => {
                                const target = holder.dataset.drawColorTarget;

                                if (
                                    target === "fill"
                                ) {
                                    fillColor.value = color;
                                    updateSelectedShape();
                                } else if (
                                    target === "stroke"
                                ) {
                                    strokeColor.value = color;
                                    updateSelectedShape();
                                } else if (
                                    target === "line"
                                ) {
                                    lineColor.value = color;
                                    updateSelectedLine();
                                } else if (
                                    target === "text"
                                ) {
                                    textColor.value = color;
                                    updateSelectedText();
                                }
                            }
                        );

                        holder.appendChild(
                            button
                        );
                    }
                );
            }
        );
    }

    document.addEventListener(
        "keydown",
        (event) => {
            if (
                (event.key === "Delete"
                    || event.key === "Backspace")
                && selectedDrawingId
                && !event.target.matches(
                    "input, textarea, select"
                )
            ) {
                event.preventDefault();

                deleteDrawingButton?.click();
            }
        }
    );

    window.EncoreStageDrawing = {
        serialize() {
            return drawings.map(
                (item) => ({
                    ...item,
                })
            );
        },

        render() {
            renderDrawings();
        },

        setPanelActive(active) {
            drawPanelActive = Boolean(active);

            app.classList.toggle(
                "draw-panel-active",
                drawPanelActive
            );

            if (!drawPanelActive) {
                drawingGesture = null;
                draggingDrawing = null;
                clearDrawingPreview();
            }

            renderDrawings();
            renderDrawingProperties();
        },

        getState() {
            return {
                drawPanelActive,
                activeTool,
                selectedDrawingId,
                drawingCount: drawings.length,
            };
        },
    };

    buildColorSwatches();

    const initialDrawPanel = document.querySelector(
        '[data-panel-content="draw"]'
    );

    drawPanelActive = Boolean(
        initialDrawPanel
        && !initialDrawPanel.hidden
    );

    app.classList.toggle(
        "draw-panel-active",
        drawPanelActive
    );

    renderDrawings();
    renderDrawingProperties();
})();


// Studio stage / lighting presets. The server replaces only selected layers.
(function setupVenueTemplates(){
 const select=document.getElementById("venue-template-select"),apply=document.getElementById("venue-template-apply"),save=document.getElementById("venue-template-save"),undo=document.getElementById("venue-template-undo"),notice=document.getElementById("venue-template-status");
 if(!select||!apply)return;
 const feedback=(message)=>{notice.textContent=message};
 async function post(url,body){const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":csrf()},body:JSON.stringify(body)});const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||"Unable to update venue template");return result}
 async function ensureSaved(){await saveBoard(true);if(dirty)throw Error("Save the drawing board before using a template.")}
 apply.addEventListener("click",async()=>{const stage=document.getElementById("venue-import-stage").checked,lighting=document.getElementById("venue-import-lighting").checked;if(!select.value||!(stage||lighting)){feedback("Select a venue and at least one import category.");return}if(!confirm("Replace the selected stage/lighting layers? Dancers, formations, and transitions will remain unchanged."))return;apply.disabled=true;try{await ensureSaved();await post(app.dataset.templateApplyUrl,{template_id:Number(select.value),stage,lighting});window.location.reload()}catch(err){feedback(err.message)}finally{apply.disabled=false}});
 if(save)save.addEventListener("click",async()=>{const input=document.getElementById("venue-template-name"),name=input.value.trim();if(!name){feedback("Enter a venue name.");return}save.disabled=true;try{await ensureSaved();const result=await post(app.dataset.templateSaveUrl,{name});const option=document.createElement("option");option.value=result.id;option.textContent=result.name;select.appendChild(option);select.value=String(result.id);input.value="";feedback("Venue template saved.")}catch(err){feedback(err.message)}finally{save.disabled=false}});
 if(undo)undo.addEventListener("click",async()=>{if(!confirm("Restore the stage/lighting setup from before your last template import?"))return;undo.disabled=true;try{await ensureSaved();await post(app.dataset.templateUndoUrl,{});window.location.reload()}catch(err){feedback(err.message)}finally{undo.disabled=false}});
})();
})();
