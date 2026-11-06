#!/usr/bin/env python3
"""Build a reviewed LG WebOS Remote Control 2.1.0 single-step-volume asset.

The original HACS file remains unchanged. Review a new upstream bundle before
updating the SHA allowlist. Pointer holds deliberately do not repeat volume.
"""
import argparse
import hashlib
from pathlib import Path

UPSTREAM_SHA256 = "45fda8299d5553662b2bdd53616ec99daadc09431b5d19df1c199235c1e8825e"
MARKER = "// ha-homelab: LG remote 2.1.0 single-step-volume v1\n"
BEFORE = 'firstUpdated(t){super.firstUpdated(t);const e=this.shadowRoot.querySelector("#plusButton"),o=this.shadowRoot.querySelector("#minusButton"),i=this.output_entity===this.config.ampli_entity?250:100;let s,n=!1;const r=t=>{this.callServiceFromConfig(t.toUpperCase(),`media_player.${t}`,{entity_id:this.output_entity})};e.addEventListener("mousedown",(()=>{isNaN(this.volume_value)||(n=!1,this._show_vol_text=!0,s=setTimeout((()=>{n=!0,r("volume_up"),s=setInterval((()=>r("volume_up")),i)}),500))})),e.addEventListener("touchstart",(t=>{t.preventDefault(),isNaN(this.volume_value)||(n=!1,this._show_vol_text=!0,s=setTimeout((()=>{n=!0,r("volume_up"),s=setInterval((()=>r("volume_up")),i)}),500))})),e.addEventListener("mouseup",(()=>{clearTimeout(s),n||r("volume_up"),clearInterval(s),this.valueDisplayTimeout=setTimeout((()=>{this._show_vol_text=!1}),500)})),e.addEventListener("touchend",(()=>{clearTimeout(s),n||r("volume_up"),clearInterval(s),this.valueDisplayTimeout=setTimeout((()=>{this._show_vol_text=!1}),500)})),o.addEventListener("mousedown",(()=>{isNaN(this.volume_value)||(n=!1,this._show_vol_text=!0,s=setTimeout((()=>{n=!0,r("volume_down"),s=setInterval((()=>r("volume_down")),i)}),400))})),o.addEventListener("touchstart",(t=>{t.preventDefault(),isNaN(this.volume_value)||(n=!1,this._show_vol_text=!0,s=setTimeout((()=>{n=!0,r("volume_down"),s=setInterval((()=>r("volume_down")),i)}),400))})),o.addEventListener("mouseup",(()=>{clearTimeout(s),n||r("volume_down"),clearInterval(s),this.valueDisplayTimeout=setTimeout((()=>{this._show_vol_text=!1}),500)})),o.addEventListener("touchend",(()=>{clearTimeout(s),n||r("volume_down"),clearInterval(s),this.valueDisplayTimeout=setTimeout((()=>{this._show_vol_text=!1}),500)}))}'
AFTER = """async _volumeClick(action){
  if(!this.isConnected)return;
  const target=this.output_entity;
  const state=this.hass?.states?.[target]?.state;
  const override=this.config.keys?.[action.toUpperCase()];
  const custom=typeof override?.service==="string"&&override.service.trim();
  if(!custom&&(!state||["off","unavailable","unknown"].includes(state)))return;
  clearTimeout(this.valueDisplayTimeout);
  this._show_vol_text=true;
  try {
    await this.callServiceFromConfig(action.toUpperCase(),`media_player.${action}`,{entity_id:target});
  } catch (error) {
    this.dispatchEvent(new CustomEvent("hass-notification", {bubbles:true,composed:true,detail:{message:"Unable to change volume. Check the player connection."}}));
  }
  this.valueDisplayTimeout=setTimeout(()=>{this._show_vol_text=false},500);
}"""
SERVICE_BEFORE = ',this.hass.callService(s.split(".")[0],s.split(".")[1],n)'
SERVICE_AFTER = ';return this.hass.callService(s.split(".")[0],s.split(".")[1],n)'
REPLACEMENTS = (
 (SERVICE_BEFORE, SERVICE_AFTER),
 (BEFORE, AFTER),
 ('id="plusButton"', 'id="plusButton" @click=${()=>this._volumeClick("volume_up")}'),
 ('id="minusButton"', 'id="minusButton" @click=${()=>this._volumeClick("volume_down")}'),
)

def patch(source: str) -> str:
    candidate = source
    if candidate.startswith(MARKER):
        candidate = candidate.removeprefix(MARKER)
        for before, after in REPLACEMENTS:
            if candidate.count(after) != 1:
                raise ValueError("Unexpected previously patched LG remote")
            candidate = candidate.replace(after, before, 1)
    if hashlib.sha256(candidate.encode()).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("Unreviewed LG remote bundle; review upstream before patching")
    for before, after in REPLACEMENTS:
        if candidate.count(before) != 1:
            raise ValueError("Unexpected LG remote patch target")
        candidate = candidate.replace(before, after, 1)
    return MARKER + candidate

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Retain original; output must be separate")
    result = patch(args.source.read_text())
    args.output.write_text(result)
    print(hashlib.sha256(result.encode()).hexdigest())

if __name__ == "__main__":
    main()
