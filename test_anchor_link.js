import fs from "fs";

const segs = [
  { mode: "EDSA-Bus", from_id: "monumento_circle", to_id: "v_edsa_monumento" }, // anchor link
  { mode: "EDSA-Bus", from_id: "v_edsa_monumento", to_id: "v_edsa_north_ave" }, // ride
  { mode: "Walk", from_id: "v_edsa_north_ave", to_id: "mrt3_north_ave" }, // transfer
  { mode: "MRT-3", from_id: "mrt3_north_ave", to_id: "mrt3_shaw" } // ride
];

const anchors = new Map([
  ["monumento_circle", { id: "monumento_circle", name: "Monumento Circle", lat: 1, lng: 1 }],
  ["v_edsa_monumento", { id: "v_edsa_monumento", name: "Monumento", lat: 2, lng: 2 }],
  ["v_edsa_north_ave", { id: "v_edsa_north_ave", name: "North Avenue", lat: 3, lng: 3 }],
  ["mrt3_north_ave", { id: "mrt3_north_ave", name: "North Avenue", lat: 4, lng: 4 }],
  ["mrt3_shaw", { id: "mrt3_shaw", name: "Shaw", lat: 5, lng: 5 }]
]);

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
      const arrivingMode = segs[i - 1].mode;
      const departingMode = segs[i].mode;
      if (arrivingMode !== departingMode) {
          if (arrivingMode === 'Walk') {
              role = "board";
              displayMode = departingMode;
          } else if (departingMode === 'Walk') {
              role = "alight";
              displayMode = arrivingMode;
          } else {
              role = "transfer";
              displayMode = departingMode;
          }
      } else if (arrivingMode === 'Jeepney' && departingMode === 'Jeepney' && !String(id).startsWith('v_')) {
          role = "transfer";
          displayMode = departingMode;
      }
  }
  
  if (role !== "stop") {
      features.push({ name: a.name, role, displayMode });
  } else {
      console.log("HIDDEN (stop):", a.name);
  }
});

console.log("Features to draw:", features);
