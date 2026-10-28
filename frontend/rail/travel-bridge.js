// The railway module stays isolated; only an explicitly confirmed itinerary
// crosses into the travel app. There is no direct access to the parent's state.
import {savePlanRecord, priceRoute} from './saved-plans.js';
import {finalizeDecision} from './decision-model.js';
const query = new URLSearchParams(location.search);
export const embedded = parent !== window && query.get('embedded') === '1';
const nonce = query.get('session');
let readSelection = () => null;
const send = (type, journey = null) => {
  if (embedded) parent.postMessage({type, session: nonce, journey}, location.origin);
};
if (embedded) document.body.classList.add('travel-embedded');
export function bridgeURL(params) {
  if (embedded) { params.set('embedded', '1'); params.set('session', nonce); }
}
export function configureTravelBridge(reader) {
  readSelection = reader;
  window.addEventListener('message', event => {
    if (!embedded || event.origin !== location.origin || event.source !== parent || event.data?.session !== nonce) return;
    if (event.data.type === 'travel:commit') send('rail:commit', readSelection());
  });
  send('rail:ready');
}
export function clearTravelSelection() { send('rail:selection'); }
export function publishTravelSelection() { send('rail:selection', readSelection()); }
export function toTravelJourney(network, route, options, quotes, riskRules) {
  if (!route?.legs?.length || !options) return null;
  try {
    // Revalidate the entire route, not a partial service preview; stale fares
    // are deliberately discarded before handing the selection to the host.
    const priced = priceRoute(network, route, options, quotes);
    const from = network.stops[route.legs[0].from][1];
    const to = network.stops[route.legs.at(-1).to][1];
    const date = options.date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3');
    const time = String(Math.floor(options.earliest / 60)).padStart(2, '0') + ':' + String(options.earliest % 60).padStart(2, '0');
    const p = savePlanRecord(network, {name: from + ' → ' + to, options, route: priced, fields: {from, to, date, time}});
    const final = finalizeDecision(network, {plans: [p], finals: []}, p, priced, riskRules).finals[0];
    return {id: final.id, savedAt: final.savedAt, snapshot: p.snapshot,
      date, from, to, legs: final.itinerary.legs, duration: final.reference.metrics.duration,
      transfers: final.reference.metrics.transfers, cost: final.reference.metrics.cost,
      risk: final.reference.metrics.risk.label, fares: final.reference.fares};
  } catch { return null; }
}
