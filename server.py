from flask import Flask, render_template_string, jsonify
import time
import state
import logging

logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__, static_url_path='/static', static_folder='static')

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Detection Dashboard</title>
    <!-- Dark theme using Bootswatch Darkly -->
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootswatch/4.5.2/darkly/bootstrap.min.css">
    <style>
        body { 
            margin: 20px; 
            background-color: #2b2b2b; 
            color: #ddd; 
        }
        pre { 
            background: #3c3f41; 
            padding: 15px; 
            border-radius: 5px; 
            color: #ddd; 
        }
        .log-container { 
            max-height: 300px; 
            overflow-y: scroll; 
            background: #3c3f41; 
            padding: 15px; 
            border-radius: 5px; 
        }
        .status-box { 
            padding: 15px; 
            border-radius: 5px; 
            background: #3c3f41; 
            margin-bottom: 20px; 
        }
        .stats-table td, .stats-table th { 
            padding: 0.75rem; 
        }
        .module-img { 
            width: 100px; 
            height: 100px; 
            margin: 5px; 
            border: 2px solid #444; 
            border-radius: 5px; 
        }
        #modules_container { 
            display: flex; 
            flex-wrap: wrap; 
        }
        .snapshot-img { 
            max-width: 100%; 
            border: 2px solid #444; 
            border-radius: 5px; 
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="my-4">Detection Dashboard</h1>
        <!-- Top row: Left = Status, Right = Session Statistics -->
        <div class="row">
            <div class="col-md-6">
                <div class="status-box">
                    <h4>Game State: <span id="game_state" class="badge badge-primary"></span></h4>
                    <h5>Latest Event Analysis:</h5>
                    <pre id="last_event_result"></pre>
                    <h5>Modules Analysis:</h5>
                    <div id="modules_container"></div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="status-box">
                    <h4>Session Statistics</h4>
                    <table class="table table-bordered stats-table" id="stats_table">
                        <thead class="thead-dark">
                            <tr>
                                <th>Metric</th>
                                <th>Count</th>
                            </tr>
                        </thead>
                        <tbody id="stats_body"></tbody>
                    </table>
                </div>
            </div>
        </div>
        <!-- Snapshots section below -->
        <div class="status-box">
            <h4>Snapshots</h4>
            <div class="row">
                <div class="col-6">
                    <h6>Raw Event Snapshot:</h6>
                    <img id="raw_snapshot" class="snapshot-img" src="" alt="" style="display:none;" />
                </div>
                <div class="col-6">
                    <h6>Processed Event Snapshot:</h6>
                    <img id="processed_snapshot" class="snapshot-img" src="" alt="" style="display:none;" />
                </div>
            </div>
        </div>
        <div class="card mb-4">
            <div class="card-header"><strong>Recent Logs</strong></div>
            <div class="card-body log-container">
                <pre id="logs"></pre>
            </div>
        </div>
        <div class="card">
            <div class="card-header"><strong>Additional Info</strong></div>
            <div class="card-body">
                <p>Minimap Tracker TODO</p>
            </div>
        </div>
        <p class="mt-3 text-muted">This page updates automatically.</p>
    </div>
    <script>
        // Mapping of module names to image file paths.
        const modulesMapping = {
            "Track": { normal: "/static/img/track.png", lit: "/static/img/track_lit.png" },
            "Cannon barrel": { normal: "/static/img/cannon_barrel.png", lit: "/static/img/cannon_barrel_lit.png" },
            "Horizontal turret drive": { normal: "/static/img/horizontal_turret_drive.png", lit: "/static/img/horizontal_turret_drive_lit.png" },
            "Vertical turret drive": { normal: "/static/img/vertical_turret_drive.png", lit: "/static/img/vertical_turret_drive_lit.png" },
            "Driver": { normal: "/static/img/driver.png", lit: "/static/img/driver_lit.png" },
            "Gunner": { normal: "/static/img/gunner.png", lit: "/static/img/gunner_lit.png" },
            "Commander": { normal: "/static/img/commander.png", lit: "/static/img/commander_lit.png" },
            "Loader": { normal: "/static/img/loader.png", lit: "/static/img/loader_lit.png" },
            "Machine gunner": { normal: "/static/img/machine_gunner.png", lit: "/static/img/machine_gunner_lit.png" },
            "Cannon breech": { normal: "/static/img/cannon_breech.png", lit: "/static/img/cannon_breech_lit.png" },
            "Fuel tank": { normal: "/static/img/fuel_tank.png", lit: "/static/img/fuel_tank_lit.png" },
            "Engine": { normal: "/static/img/engine.png", lit: "/static/img/engine_lit.png" },
            "Transmission": { normal: "/static/img/transmission.png", lit: "/static/img/transmission_lit.png" },
            "Radiator": { normal: "/static/img/radiator.png", lit: "/static/img/radiator_lit.png" },
            "Ammo": { normal: "/static/img/ammo.png", lit: "/static/img/ammo_lit.png" },
            "Autoloader": { normal: "/static/img/autoloader.png", lit: "/static/img/autoloader_lit.png" }
        };

        function updateStatus(){
            fetch('/status')
            .then(response => response.json())
            .then(data => {
                document.getElementById('game_state').textContent = data.game_state;
                document.getElementById('last_event_result').textContent = data.last_event_result;
                
                // Update Modules Analysis images.
                let modulesContainer = document.getElementById('modules_container');
                modulesContainer.innerHTML = "";
                for (let moduleName in modulesMapping) {
                    let img = document.createElement('img');
                    img.className = "module-img";
                    if (data.modules_hit.includes(moduleName)) {
                        img.src = modulesMapping[moduleName].lit;
                    } else {
                        img.src = modulesMapping[moduleName].normal;
                    }
                    img.alt = moduleName;
                    modulesContainer.appendChild(img);
                }
                
                // Update Session Statistics table.
                let statsBody = document.getElementById('stats_body');
                statsBody.innerHTML = "";
                data.stats_rows.forEach(function(row){
                    let tr = document.createElement('tr');
                    if(row.changed){
                        tr.classList.add("table-success");
                    }
                    let tdMetric = document.createElement('td');
                    tdMetric.textContent = row.metric;
                    let tdValue = document.createElement('td');
                    tdValue.textContent = row.value;
                    tr.appendChild(tdMetric);
                    tr.appendChild(tdValue);
                    statsBody.appendChild(tr);
                });
                
                document.getElementById('logs').textContent = data.logs;
                
                // Update Snapshots: show image only if URL is provided.
                let rawSnapshot = document.getElementById('raw_snapshot');
                let processedSnapshot = document.getElementById('processed_snapshot');
                if(data.raw_event_snapshot){
                    rawSnapshot.src = data.raw_event_snapshot;
                    rawSnapshot.style.display = "block";
                } else {
                    rawSnapshot.style.display = "none";
                }
                if(data.processed_event_snapshot){
                    processedSnapshot.src = data.processed_event_snapshot;
                    processedSnapshot.style.display = "block";
                } else {
                    processedSnapshot.style.display = "none";
                }
            })
            .catch(err => console.error("Error fetching status:", err));
        }
        setInterval(updateStatus, 1000);
        updateStatus();
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/status")
def status_endpoint():
    current_time = time.time()
    TIMEOUT = 5

    event_result = state.last_event_result
    module_result = state.last_modules_result
    if current_time - state.last_event_timestamp > TIMEOUT:
        event_result = ""
    if current_time - state.last_modules_timestamp > TIMEOUT:
        module_result = ""

    modules_hit = []
    if module_result:
        modules_hit = [m.strip() for m in module_result.split(";") if m.strip()]

    raw_snapshot = state.last_raw_event_snapshot if current_time - state.last_event_timestamp <= TIMEOUT else ""
    processed_snapshot = state.last_processed_event_snapshot if current_time - state.last_event_timestamp <= TIMEOUT else ""

    stats_rows = []
    for metric, value in state.stats.items():
        changed = (state.prev_stats.get(metric) != value)
        stats_rows.append({
            "metric": metric.capitalize().replace("_", " "),
            "value": value,
            "changed": changed
        })
    state.prev_stats.clear()
    state.prev_stats.update(state.stats)

    recent_logs = "\n".join(state.log_store[-50:])

    data = {
        "game_state": state.game_state,
        "last_event_result": event_result,
        "modules_hit": modules_hit,
        "stats_rows": stats_rows,
        "logs": recent_logs,
        "raw_event_snapshot": raw_snapshot,
        "processed_event_snapshot": processed_snapshot
    }
    return jsonify(data)

def start_server():
    app.run(host="0.0.0.0", port=5000, debug=False)