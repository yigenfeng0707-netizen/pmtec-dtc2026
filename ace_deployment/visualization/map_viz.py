"""
Map Visualization - Generates interactive Leaflet HTML maps.
DTB Model: Application Store (visualization plugin) + Plug-and-Play output module.
"""

import json
import os
from models.base import BaseNetwork
from models.aircraft import AircraftFleet
from config import OUTPUT_DIR


class MapVisualizer:
    """Generates interactive HTML maps using Leaflet.js."""

    def __init__(self, network: BaseNetwork, fleet: AircraftFleet):
        self.network = network
        self.fleet = fleet

    def generate_deployment_map(
        self, plan=None, threats=None, damage_report=None, output_path: str = None
    ) -> str:
        """Generate a comprehensive deployment visualization HTML."""
        if not output_path:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(OUTPUT_DIR, "ace_deployment_map.html")

        # Prepare base data
        bases_js = []
        for bid, base in self.network.bases.items():
            ac_count = len(base.current_aircraft)
            ac_types = {}
            for ac in base.current_aircraft:
                ac_types[ac.ac_type] = ac_types.get(ac.ac_type, 0) + 1
            bases_js.append(
                {
                    "id": base.id,
                    "name": base.name,
                    "name_cn": base.name_cn,
                    "lat": base.lat,
                    "lon": base.lon,
                    "region": base.region,
                    "ace_hub": base.ace_hub,
                    "branch": base.branch,
                    "ac_count": ac_count,
                    "ac_types": ac_types,
                    "vulnerability": round(base.vulnerability_index, 2),
                    "defense_level": base.defense_level,
                    "utilization": round(base.utilization * 100, 0),
                    "parking_capacity": base.parking_capacity,
                    "role": base.role[:80] if base.role else "",
                }
            )

        # Prepare transfer lines
        transfers_js = []
        if plan and hasattr(plan, "transfers"):
            for t in plan.transfers:
                from_base = self.network.get(t["from_base"])
                to_base = self.network.get(t["to_base"])
                if from_base and to_base:
                    transfers_js.append(
                        {
                            "from_lat": from_base.lat,
                            "from_lon": from_base.lon,
                            "to_lat": to_base.lat,
                            "to_lon": to_base.lon,
                            "ac_type": t["ac_type"],
                            "distance_km": t["distance_km"],
                        }
                    )

        # Prepare threat markers
        threats_js = []
        if threats:
            for threat in threats.threats:
                target = self.network.get(threat.target_base_id)
                if target:
                    threats_js.append(
                        {
                            "lat": target.lat,
                            "lon": target.lon,
                            "type": threat.threat_type,
                            "quantity": threat.quantity,
                            "warhead_kg": threat.warhead_kg,
                            "target": target.name,
                        }
                    )

        # Prepare damage markers
        damage_js = []
        if damage_report:
            for base_hit in damage_report.bases_hit:
                base = self.network.get(base_hit.base_id)
                if base:
                    damage_js.append(
                        {
                            "lat": base.lat,
                            "lon": base.lon,
                            "name": base.name,
                            "aircraft_destroyed": base_hit.aircraft_destroyed,
                            "runway_destroyed": base_hit.runway_destroyed,
                            "repair_hours": round(base_hit.runway_repair_hours, 1),
                        }
                    )

        html = self._build_html(bases_js, transfers_js, threats_js, damage_js)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path

    def _build_html(self, bases, transfers, threats, damages):
        bases_json = json.dumps(bases, ensure_ascii=False)
        transfers_json = json.dumps(transfers, ensure_ascii=False)
        threats_json = json.dumps(threats, ensure_ascii=False)
        damages_json = json.dumps(damages, ensure_ascii=False)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ACE Deployment Visualization - DTC 2026 Level 2</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0e17; color: #e0e0e0; }}
#map {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 1; }}
#info-panel {{ position: absolute; top: 10px; right: 10px; z-index: 1000;
  background: rgba(15,23,35,0.95); padding: 16px; border-radius: 8px;
  border: 1px solid #2a3f5f; max-width: 320px; font-size: 12px; }}
#info-panel h3 {{ color: #4fc3f7; margin-bottom: 8px; font-size: 14px; }}
#info-panel .stat {{ display: flex; justify-content: space-between; margin: 4px 0; }}
#info-panel .stat-label {{ color: #888; }}
#info-panel .stat-value {{ color: #4fc3f7; font-weight: bold; }}
.legend {{ position: absolute; bottom: 20px; left: 10px; z-index: 1000;
  background: rgba(15,23,35,0.95); padding: 12px; border-radius: 8px;
  border: 1px solid #2a3f5f; font-size: 11px; }}
.legend-item {{ display: flex; align-items: center; margin: 4px 0; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; border: 2px solid #fff; }}
</style>
</head>
<body>
<div id="map"></div>
<div id="info-panel">
  <h3>ACE Deployment Engine</h3>
  <div class="stat"><span class="stat-label">Total Bases</span><span class="stat-value" id="stat-bases">0</span></div>
  <div class="stat"><span class="stat-label">Total Aircraft</span><span class="stat-value" id="stat-aircraft">0</span></div>
  <div class="stat"><span class="stat-label">ACE Hubs</span><span class="stat-value" id="stat-hubs">0</span></div>
  <div class="stat"><span class="stat-label">Network Vulnerability</span><span class="stat-value" id="stat-vuln">0</span></div>
  <div class="stat"><span class="stat-label">Transfers</span><span class="stat-value" id="stat-transfers">0</span></div>
  <div class="stat"><span class="stat-label">Threats</span><span class="stat-value" id="stat-threats">0</span></div>
</div>
<div class="legend">
  <div class="legend-item"><div class="legend-dot" style="background:#d32f2f"></div>ACE Hub (high value)</div>
  <div class="legend-item"><div class="legend-dot" style="background:#1565c0"></div>Spoke Base</div>
  <div class="legend-item"><div class="legend-dot" style="background:#e65100"></div>Threat Target</div>
  <div class="legend-item"><div class="legend-dot" style="background:#c62828;border-color:#f44336"></div>Damaged Base</div>
  <div style="width:24px;height:3px;background:#4fc3f7;margin:4px 0;"></div>Transfer Route</div>
</div>
<script>
const bases = {bases_json};
const transfers = {transfers_json};
const threats = {threats_json};
const damages = {damages_json};

const map = L.map('map', {{ zoomControl: true }}).setView([20, 140], 3);
L.tileLayer('tiles/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; OpenStreetMap 离线瓦片',
  maxZoom: 18, maxNativeZoom: 7
}}).addTo(map);

let totalAircraft = 0, hubCount = 0, totalVuln = 0;
const damageMap = {{}};
damages.forEach(d => damageMap[d.lat + ',' + d.lon] = d);

bases.forEach(b => {{
  totalAircraft += b.ac_count;
  if (b.ace_hub) hubCount++;
  totalVuln += b.vulnerability;

  const isDamaged = damageMap[b.lat + ',' + b.lon];
  let color;
  if (isDamaged) color = '#c62828';
  else if (b.ace_hub) color = '#d32f2f';
  else color = '#1565c0';

  const radius = Math.max(6, Math.min(16, 4 + b.ac_count * 0.6));

  const marker = L.circleMarker([b.lat, b.lon], {{
    radius: radius, color: '#fff', weight: 2, fillColor: color, fillOpacity: 0.8
  }}).addTo(map);

  let popContent = '<div style="min-width:200px;">';
  popContent += '<b>' + b.name + '</b> (' + b.name_cn + ')<br>';
  popContent += '<hr style="border-color:#333;margin:4px 0;">';
  popContent += 'Region: ' + b.region + '<br>';
  popContent += 'Branch: ' + b.branch + '<br>';
  popContent += 'ACE Hub: ' + (b.ace_hub ? 'Yes' : 'No') + '<br>';
  popContent += 'Defense Level: ' + b.defense_level + '/3<br>';
  popContent += 'Aircraft: <b>' + b.ac_count + '</b>/' + b.parking_capacity + '<br>';
  popContent += 'Utilization: ' + b.utilization + '%<br>';
  popContent += 'Vulnerability: ' + b.vulnerability + '<br>';
  if (Object.keys(b.ac_types).length > 0) {{
    popContent += '<hr style="border-color:#333;margin:4px 0;">';
    popContent += '<b>Aircraft Types:</b><br>';
    for (const [type, count] of Object.entries(b.ac_types)) {{
      popContent += '&nbsp;&nbsp;' + type + ': ' + count + '<br>';
    }}
  }}
  if (isDamaged) {{
    popContent += '<hr style="border-color:#333;margin:4px 0;">';
    popContent += '<span style="color:#f44336;">DAMAGE: ' + isDamaged.aircraft_destroyed + ' aircraft lost</span><br>';
    popContent += '<span style="color:#f44336;">Runway: ' + (isDamaged.runway_destroyed ? 'DESTROYED' : 'OK') + '</span><br>';
    popContent += '<span style="color:#f44336;">Repair: ' + isDamaged.repair_hours + 'h</span><br>';
  }}
  popContent += '</div>';
  marker.bindPopup(popContent);
}});

// Draw transfer routes
transfers.forEach(t => {{
  L.polyline([
    [t.from_lat, t.from_lon],
    [t.to_lat, t.to_lon]
  ], {{
    color: '#4fc3f7', weight: 2, opacity: 0.6, dashArray: '5,5'
  }}).addTo(map);
}});

// Draw threat indicators
threats.forEach(t => {{
  L.circleMarker([t.lat, t.lon], {{
    radius: 20, color: '#e65100', weight: 3, fillColor: '#ff5722', fillOpacity: 0.15
  }}).addTo(map).bindPopup(
    '<b>THREAT: ' + t.type + '</b><br>' +
    'Target: ' + t.target + '<br>' +
    'Quantity: ' + t.quantity + '<br>' +
    'Warhead: ' + t.warhead_kg + ' kg'
  );
}});

document.getElementById('stat-bases').textContent = bases.length;
document.getElementById('stat-aircraft').textContent = totalAircraft;
document.getElementById('stat-hubs').textContent = hubCount;
document.getElementById('stat-vuln').textContent = totalVuln.toFixed(1);
document.getElementById('stat-transfers').textContent = transfers.length;
document.getElementById('stat-threats').textContent = threats.length;
</script>
</body>
</html>"""
