import fs from "fs";

const segs = [
  { mode: "EDSA-Bus", from_id: "monumento_circle", to_id: "edsa_bus_north_ave" },
  { mode: "EDSA-Bus", from_id: "edsa_bus_north_ave", to_id: "edsa_bus_quezon_ave" } // continuing...
];

const anchors = new Map([
  ["monumento_circle", { id: "monumento_circle", name: "Monumento Circle", lat: 1, lng: 1 }],
  ["edsa_bus_north_ave", { id: "v_edsa_north", name: "North Avenue", lat: 3, lng: 3 }],
  ["edsa_bus_quezon_ave", { id: "v_edsa_quezon", name: "Quezon Avenue", lat: 4, lng: 4 }]
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
          role = "transfer";
          displayMode = departingMode;
      }
  }
  
  if (role !== "stop") features.push({ name: a.name, role, displayMode });
});

console.log("Features:", features);
