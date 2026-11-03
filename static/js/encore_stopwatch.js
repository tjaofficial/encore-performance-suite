document.querySelectorAll('[data-stopwatch]').forEach(function(root){
 let base=0,started=0,running=false,laps=0;const display=root.querySelector('[data-sw-time]'),status=root.querySelector('[data-sw-status]'),start=root.querySelector('[data-sw-start]'),lap=root.querySelector('[data-sw-lap]'),reset=root.querySelector('[data-sw-reset]'),list=root.querySelector('[data-sw-laps]');
 const elapsed=()=>base+(running?performance.now()-started:0);
 const format=ms=>{const m=Math.floor(ms/60000);const s=Math.floor(ms/1000)%60;const cs=Math.floor(ms/10)%100;return String(m).padStart(2,'0')+':'+String(s).padStart(2,'0')+'<span>.'+String(cs).padStart(2,'0')+'</span>';};
 function tick(){display.innerHTML=format(elapsed());if(running)requestAnimationFrame(tick);}
 start.addEventListener('click',()=>{if(running){base=elapsed();running=false;start.textContent='▶ Resume';status.textContent='Paused';}else{started=performance.now();running=true;start.textContent='Ⅱ Pause';status.textContent='Running';requestAnimationFrame(tick);}lap.disabled=!running;});
 lap.addEventListener('click',()=>{const item=document.createElement('div');const number=document.createElement('strong');number.textContent='Lap '+(++laps);const time=document.createElement('span');time.textContent=display.textContent;item.append(number,time);list.prepend(item);});
 reset.addEventListener('click',()=>{base=0;started=0;running=false;laps=0;start.textContent='▶ Start';status.textContent='Ready';lap.disabled=true;list.replaceChildren();tick();});tick();
});