#!/usr/bin/env python3
"""Apply reviewed map-loader and tire-availability fixes to Vehicle Info Card 1.12.3.

Preserve the bundled map and report unavailable pressure without inventing values.
"""

import argparse
import hashlib
from pathlib import Path

UPSTREAM_SHA256 = "ea1a5f23dfd4f28a2b2eb48d99adc2f40b65d3d2e36a8364442d6ddfdca9dcfe"
LEGACY_MARKER = "// ha-homelab: Vehicle Info Card 1.12.3 bundled map guard v1\n"
V2_MARKER = "// ha-homelab: Vehicle Info Card 1.12.3 map and tire guards v2\n"
MARKER = "// ha-homelab: Vehicle Info Card 1.12.3 map and tire guards v3\n"
BEFORE = "FX().catch(console.error)"
AFTER = '(customElements.get("extra-map-card")||FX().catch(console.error))'
BUNDLED_MAP = 'customElements.get("extra-map-card")||customElements.define("extra-map-card",Wme);'

# Exact fragments from the SHA-pinned upstream bundle; no downloaded assets in Git.
TYRE_BEFORE = 'this.getMinMaxTyrePressure=()=>{var e;if(!this.DataKeys.tyrePressures)return"";const t=this.DataKeys.tyrePressures.map(e=>{var t,i;return{pressure:this.getEntityState(null===(t=this.vehicleEntities[e.key])||void 0===t?void 0:t.entity_id)||"",unit:this.getEntityAttribute(null===(i=this.vehicleEntities[e.key])||void 0===i?void 0:i.entity_id,"unit_of_measurement")}}),i=Math.min(...t.map(({pressure:e})=>parseFloat(e))),r=Math.max(...t.map(({pressure:e})=>parseFloat(e))),a=(null===(e=t[0])||void 0===e?void 0:e.unit)||"";return`${i%1==0?i.toFixed(0):i.toFixed(1)} - ${r%1==0?r.toFixed(0):r.toFixed(1)} ${a}`}'
TYRE_AFTER = """this.getMinMaxTyrePressure=()=>{
  if(!this.DataKeys.tyrePressures)return "";
  const unavailable=this._hass.localize("state.default.unavailable")||"Unavailable";
  const readings=this.DataKeys.tyrePressures.map(key=>{
    const entity=this.vehicleEntities[key.key]?.entity_id;
    const raw=this.getEntityState(entity);
    const pressure=typeof raw==="string"&&raw.trim()!==""?Number(raw):NaN;
    return {pressure,unit:this.getEntityAttribute(entity,"unit_of_measurement")};
  });
  if(readings.length!==4||readings.some(({pressure,unit})=>
    !Number.isFinite(pressure)||pressure<0||!unit||unit!==readings[0].unit))return unavailable;
  const values=readings.map(({pressure})=>pressure);
  const format=value=>value.toFixed(Number.isInteger(value)?0:1);
  return `${format(Math.min(...values))} - ${format(Math.max(...values))} ${readings[0].unit}`;
}"""
DISCOVERY_BEFORE = '.filter(t=>e.states[t.entity_id]&&!["unavailable","unknown"].includes(e.states[t.entity_id].state))'
DISCOVERY_AFTER = '.filter(t=>["_tirepressurefrontleft","_tirepressurefrontright","_tirepressurerearleft","_tirepressurerearright"].some(s=>(t.unique_id||"").endsWith(s)||t.entity_id.endsWith(s))||e.states[t.entity_id]&&!["unavailable","unknown"].includes(e.states[t.entity_id].state))'
# Render only the requested panel: hidden vehicle panels may lack telemetry.
RENDER_BEFORE = '_renderCustomCard(){var e;if(!this._currentCardType)return oe``;const t={tripCards:this._renderDefaultTripCard(),vehicleCards:this._renderDefaultVehicleCard(),ecoCards:this._renderDefaultEcoCard(),tyreCards:this._renderDefaultTyreCard(),servicesCard:this._renderServiceControl(),emptyCustom:this._showWarning("No custom card provided")},i=this._currentCardType,o=e=>{var t,i;return null!==(i=null===(t=this.buttonCards[e])||void 0===t?void 0:t.card_type)&&void 0!==i?i:"default"};let s;if("servicesCard"===i)s=t[i];else{const r=this.buttonCards[i],a=null!==(e=r.card_type)&&void 0!==e?e:"default",n=iX(r.custom_card)?t.emptyCustom:r.custom_card.map(e=>e);s="custom"===a?n:t[i]}'
RENDER_AFTER = '_renderCustomCard(){var e;if(!this._currentCardType)return oe``;const t={tripCards:()=>this._renderDefaultTripCard(),vehicleCards:()=>this._renderDefaultVehicleCard(),ecoCards:()=>this._renderDefaultEcoCard(),tyreCards:()=>this._renderDefaultTyreCard(),servicesCard:()=>this._renderServiceControl(),emptyCustom:this._showWarning("No custom card provided")},i=this._currentCardType,o=e=>{var t,i;return null!==(i=null===(t=this.buttonCards[e])||void 0===t?void 0:t.card_type)&&void 0!==i?i:"default"};let s;if("servicesCard"===i)s=t[i]();else{const r=this.buttonCards[i],a=null!==(e=r.card_type)&&void 0!==e?e:"default",n=iX(r.custom_card)?t.emptyCustom:r.custom_card.map(e=>e);s="custom"===a?n:t[i]()}'
# Unknown warning status must not be presented as normal tire pressure.
WARNING_BEFORE = 'v=f?g:y;return oe'
WARNING_AFTER = 'v=["on","off"].includes(this.getEntityState(this.vehicleEntities.tirePressureWarning?.entity_id))?(f?g:y):(this._hass.localize("state.default.unavailable")||"Unavailable");return oe'
V2_REPLACEMENTS = ((BEFORE, AFTER), (TYRE_BEFORE, TYRE_AFTER), (DISCOVERY_BEFORE, DISCOVERY_AFTER))
V3_DISCOVERY_AFTER = DISCOVERY_AFTER.replace('"_tirepressurerearright"]', '"_tirepressurerearright","_tirewarninglamp"]')
REPLACEMENTS = (
    (BEFORE, AFTER), (TYRE_BEFORE, TYRE_AFTER),
    (DISCOVERY_BEFORE, V3_DISCOVERY_AFTER),
    (RENDER_BEFORE, RENDER_AFTER), (WARNING_BEFORE, WARNING_AFTER),
)


def patch(source: str) -> str:
    """Reject unknown bundles and damaged previously patched assets."""
    candidate = source
    if candidate.startswith(MARKER):
        candidate = candidate.removeprefix(MARKER)
        reverse = REPLACEMENTS
    elif candidate.startswith(V2_MARKER):
        candidate = candidate.removeprefix(V2_MARKER)
        reverse = V2_REPLACEMENTS
    elif candidate.startswith(LEGACY_MARKER):
        candidate = candidate.removeprefix(LEGACY_MARKER)
        reverse = ((BEFORE, AFTER),)
    else:
        reverse = ()
    for before, after in reverse:
        if candidate.count(after) != 1:
            raise ValueError("Unexpected patched Vehicle Info Card source")
        candidate = candidate.replace(after, before, 1)
    if hashlib.sha256(candidate.encode()).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("Unexpected Vehicle Info Card version; review upstream before applying")
    if candidate.count(BUNDLED_MAP) != 1 or candidate.index(BUNDLED_MAP) >= candidate.index(BEFORE):
        raise ValueError("Bundled map must register before the loader")
    for before, after in REPLACEMENTS:
        if candidate.count(before) != 1:
            raise ValueError("Unexpected Vehicle Info Card patch target")
        candidate = candidate.replace(before, after, 1)
    return MARKER + candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Use a separate output file; retain the original for rollback")
    result = patch(args.source.read_text())
    args.output.write_text(result)
    print("Output SHA256:", hashlib.sha256(result.encode()).hexdigest())


if __name__ == "__main__":
    main()
