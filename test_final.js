import fs from "fs";

function linkStationName(anchor, mode) {
  // Mock logic
  if (anchor.id === "monumento_circle" && mode === "EDSA-Bus") return "Monumento";
  if (anchor.id === "north_ave_circle" && mode === "EDSA-Bus") return "North Avenue";
  if (anchor.id === "north_ave_circle" && mode === "MRT-3") return "North Avenue";
  return null;
}

function isAnchorLink(a, b, mode) {
  const aAnchor = !String(a.id).startsWith("v_") && !String(a.id).startsWith("mrt"), bAnchor = !String(b.id).startsWith("v_") && !String(b.id).startsWith("mrt");
  if (aAnchor === bAnchor) return false;
  const [anchor, station] = aAnchor ? [a, b] : [b, a];
  return linkStationName(anchor, mode) === station.name;
}

const segs = [
  { mode: "EDSA-Bus", from_id: "monumento_circle", to_id: "v_edsa_monumento" }, // anchor link
  { mode: "EDSA-Bus", from_id: "v_edsa_monumento", to_id: "v_edsa_north_ave" }, // ride
  { mode: "EDSA-Bus", from_id: "v_edsa_north_ave", to_id: "north_ave_circle" }, // anchor link
  { mode: "MRT-3", from_id: "north_ave_circle", to_id: "mrt3_north_ave" }, // anchor link
  { mode: "MRT-3", from_id: "mrt3_north_ave", to_id: "mrt3_shaw" } // ride
];

const anchors = new Map([
  ["monumento_circle", { id: "monumento_circle", name: "Monumento Circle", lat: 1, lng: 1 }],
  ["v_edsa_monumento", { id: "v_edsa_monumento", name: "Monumento", lat: 2, lng: 2 }],
  ["v_edsa_north_ave", { id: "v_edsa_north_ave", name: "North Avenue", lat: 3, lng: 3 }],
  ["north_ave_circle", { id: "north_ave_circle", name: "North Ave Circle", lat: 3.5, lng: 3.5 }],
  ["mrt3_north_ave", { id: "mrt3_north_ave", name: "North Avenue", lat: 4, lng: 4 }],
  ["mrt3_shaw", { id: "mrt3_shaw", name: "Shaw", lat: 5, lng: 5 }]
]);

function isTransitRide(seg, anchors) {
    if (seg.mode === 'Walk') return false;
    const a = anchors.get(seg.from_id);
    const b = anchors.get(seg.to_id);
    if (!a || !b) return false;
    if (isAnchorLink(a, b, seg.mode)) return false;
    return true;
}

const nodeIds = [segs[0].from_id, ...segs.map(s => s.to_id)];
const features = [];

nodeIds.forEach((id, i) => {
  const a = anchors.get(id);
  if (!a) return;
  
  let role = "stop";
  let displayMode = null;

  if (i === 0) {
      role = "origin";
      if (segs.length > 0) displayMode = segs[0].mode;
  } else if (i === nodeIds.length - 1) {
      role = "destination";
      if (segs.length > 0) displayMode = segs[i - 1].mode;
  } else {
      const arrivingIsRide = isTransitRide(segs[i - 1], anchors);
      const departingIsRide = isTransitRide(segs[i], anchors);
      
      if (!arrivingIsRide && departingIsRide) {
          role = "board";
          displayMode = segs[i].mode;
      } else if (arrivingIsRide && !departingIsRide) {
          role = "alight";
          displayMode = segs[i - 1].mode;
      } else if (arrivingIsRide && departingIsRide && segs[i - 1].mode !== segs[i].mode) {
          role = "transfer";
          displayMode = segs[i].mode;
      } else if (!arrivingIsRide && !departingIsRide) {
          role = "transfer";
          displayMode = segs[i].mode;
      } else if (segs[i - 1].mode === 'Jeepney' && segs[i].mode === 'Jeepney' && !String(id).startsWith('v_')) {
          role = "transfer";
          displayMode = segs[i].mode;
      }
  }
  
  if (role !== "stop") features.push({ name: a.name, role, displayMode });
  else console.log("HIDDEN:", a.name);
});

console.log("Features:", features);
