// Offline execution of the real original and patched bundle's volume methods.
// No Home Assistant connection or device command is made.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {original, patched} = JSON.parse(fs.readFileSync(0, 'utf8'));
function extract(source, start, end) {
  const a=source.indexOf(start), b=source.indexOf(end,a+start.length);
  assert.ok(a>=0 && b>a, `Missing bundle method ${start}`);
  return source.slice(a,b);
}
function harness(source, legacy=false) {
  let now=0, serial=0;
  const timers=new Map(), calls=[], notices=[];
  const schedule=(fn,delay,interval=false)=>{const id=++serial;timers.set(id,{fn,at:now+delay,delay,interval});return id};
  const controls={};
  for (const id of ['plusButton','minusButton']) controls[id]={listeners:{},addEventListener(type,fn){this.listeners[type]=fn},emit(type){return this.listeners[type]?.({preventDefault(){}})}};
  const methods=legacy?extract(source,'firstUpdated(t){super.firstUpdated(t);','updated(t){'):extract(source,'async _volumeClick(action){','updated(t){');
  const service=extract(source,'callServiceFromConfig(t,e,o){','_getIcon(t,e){');
  class Base {firstUpdated(){}}
  const C=vm.runInNewContext(`(class extends Base {${methods}${service}})`, {
    Base, setTimeout:(f,d)=>schedule(f,d),setInterval:(f,d)=>schedule(f,d,true),
    clearTimeout:id=>timers.delete(id),clearInterval:id=>timers.delete(id),
    CustomEvent:class {constructor(type,options){this.type=type;Object.assign(this,options)}}
  });
  const card=new C();
  Object.assign(card,{isConnected:true,config:{entity:'media_player.tv'},output_entity:'media_player.tv',volume_value:10,
    shadowRoot:{querySelector:selector=>controls[selector.slice(1)]},
    hass:{states:{'media_player.tv':{state:'on'}},callService:(domain,action,data)=>{calls.push({domain,action,data});return Promise.resolve()}},
    dispatchEvent:event=>notices.push(event)});
  if(legacy) card.firstUpdated(new Map());
  else for (const id of Object.keys(controls)) {
    const match=source.match(new RegExp('id="'+id+'" @click=\\$\\{([^}]+)\\}'));
    assert.ok(match,`Missing declarative click for ${id}`);
    controls[id].addEventListener('click',vm.runInNewContext(`(function(){return ${match[1]}}).call(card)`,{card}));
  }
  const advance=duration=>{const until=now+duration;let bound=10000;while(bound--){const candidates=[...timers].filter(([,x])=>x.at<=until).sort((a,b)=>a[1].at-b[1].at);if(!candidates.length)break;const [id,t]=candidates[0];now=t.at;timers.delete(id);if(t.interval){t.at+=t.delay;timers.set(id,t)}t.fn()}assert.ok(bound>0);now=until};
  return {card,controls,calls,notices,timers,advance};
}
(async()=>{
  const old=harness(original,true);
  old.controls.plusButton.emit('mousedown');old.advance(1000);
  // Releasing outside the button does not reach its mouseup handler.
  const initial=old.calls.length;old.advance(1000);assert.ok(old.calls.length>initial);
  old.controls.minusButton.emit('mousedown');old.advance(500);
  old.controls.minusButton.emit('mouseup');const count=old.calls.length;
  old.advance(1000);assert.ok(old.calls.length>count,'Old UP interval remains after DOWN steals timer handle');

  const h=harness(patched);
  for(const event of ['mousedown','touchstart','pointerdown'])h.controls.plusButton.emit(event);
  h.advance(10000);assert.equal(h.calls.length,0,'Hold does not repeat');
  for(const event of ['mouseup','touchend','pointerup','pointercancel','touchcancel','mouseleave'])h.controls.plusButton.emit(event);
  h.advance(10000);assert.equal(h.calls.length,0,'Release/cancel outside cannot start a command');
  await h.controls.plusButton.emit('click');assert.equal(h.calls.length,1);
  assert.equal(h.calls[0].action,'volume_up');
  h.advance(60000);assert.equal(h.calls.length,1,'No delayed repeat after click');
  await h.controls.minusButton.emit('click');assert.equal(h.calls.length,2);
  assert.equal(h.calls[1].action,'volume_down');
  h.advance(60000);assert.equal(h.calls.length,2);
  for(const state of ['off','unknown','unavailable',undefined]){
    h.card.hass.states['media_player.tv'].state=state;
    await h.controls.plusButton.emit('click');await h.controls.minusButton.emit('click');
  }
  delete h.card.hass.states['media_player.tv'];await h.controls.plusButton.emit('click');
  assert.equal(h.calls.length,2,'Unavailable player produces no command');
  h.card.hass.states['media_player.tv']={state:'on'};h.card.isConnected=false;
  await h.controls.plusButton.emit('click');assert.equal(h.calls.length,2,'Detached card produces no command');
  h.card.isConnected=true;
  const other=harness(patched);await other.controls.plusButton.emit('click');
  assert.equal(other.calls.length,1);assert.equal(h.calls.length,2,'Two cards do not share repeat state');
  h.card.output_entity='media_player.amplifier';h.card.hass.states['media_player.amplifier']={state:'on'};
  await h.controls.plusButton.emit('click');assert.equal(h.calls.at(-1).data.entity_id,'media_player.amplifier');
  h.card.config.keys={VOLUME_DOWN:{service:'script.safe_volume',data:{direction:'down'}}};
  await h.controls.minusButton.emit('click');assert.equal(h.calls.at(-1).domain,'script');assert.equal(h.calls.at(-1).action,'safe_volume');
  h.card.hass.states['media_player.amplifier'].state='off';
  const beforeOverride=h.calls.length;
  await h.controls.minusButton.emit('click');
  assert.equal(h.calls.length,beforeOverride+1,'Explicit custom route does not depend on default player power');
  assert.equal(h.calls.at(-1).action,'safe_volume');
  await h.controls.plusButton.emit('click');
  assert.equal(h.calls.length,beforeOverride+1,'Default route still blocks powered-off player');
  h.card.hass.states['media_player.amplifier'].state='on';
  h.card.hass.callService=()=>Promise.reject(new Error('offline'));
  await h.controls.plusButton.emit('click');assert.equal(h.notices.length,1);assert.equal(h.notices[0].type,'hass-notification');
  h.card.hass.callService=()=>{throw new Error('sync failure')};
  await h.controls.plusButton.emit('click');assert.equal(h.notices.length,2);
  h.advance(60000);assert.equal(h.notices.length,2,'Rejected call is not retried');
  console.log(JSON.stringify({oldRunawayReproduced:true,singleStepCases:15,noNetwork:true}));
})().catch(error=>{console.error(error);process.exitCode=1});
