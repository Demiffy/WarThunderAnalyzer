from flask import Flask, render_template_string, jsonify
import time
import state

app = Flask(__name__, static_url_path='/static', static_folder='static')

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Detection Dashboard</title>
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
    <style>
        body { margin: 20px; }
        pre { background: #f8f9fa; padding: 15px; border-radius: 5px; }
        .log-container { max-height: 400px; overflow-y: scroll; }
        .status-box { padding: 15px; border-radius: 5px; background: #e9ecef; margin-bottom: 20px; }
        .stats-table td, .stats-table th { padding: 0.75rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="my-4">Detection Dashboard</h1>
        <div class="status-box">
            <h4>Game State: <span id="game_state" class="badge badge-primary"></span></h4>
            <h5>Latest Event Analysis:</h5>
            <pre id="last_event_result"></pre>
            <h5>Latest Modules Analysis:</h5>
            <pre id="last_modules_result"></pre>
        </div>
        <h3>Session Statistics</h3>
        <table class="table table-bordered stats-table" id="stats_table">
            <thead class="thead-dark">
                <tr>
                    <th>Metric</th>
                    <th>Count</th>
                </tr>
            </thead>
            <tbody id="stats_body">
            </tbody>
        </table>
        <div class="card mb-4">
            <div class="card-header">
                <strong>Recent Logs</strong>
            </div>
            <div class="card-body log-container">
                <pre id="logs"></pre>
            </div>
        </div>
        <div class="card">
            <div class="card-header">
                <strong>Additional Info</strong>
            </div>
            <div class="card-body">
                <p>Snapshots TODO</p>
            </div>
        </div>
        <p class="mt-3 text-muted">This page updates automatically.</p>
    </div>
    <script>
        function updateStatus(){
            fetch('/status')
            .then(response => response.json())
            .then(data => {
                document.getElementById('game_state').textContent = data.game_state;
                document.getElementById('last_event_result').textContent = data.last_event_result;
                document.getElementById('last_modules_result').textContent = data.last_modules_result;
                
                // Update statistics table.
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
            })
            .catch(err => console.error("Error fetching status:", err));
        }
        // Update every second.
        setInterval(updateStatus, 1000);
        // Initial update.
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
    EVENT_TIMEOUT = 5
    MODULE_TIMEOUT = 5

    event_result = state.last_event_result
    module_result = state.last_modules_result

    if current_time - state.last_event_timestamp > EVENT_TIMEOUT:
        event_result = ""
    if current_time - state.last_modules_timestamp > MODULE_TIMEOUT:
        module_result = ""

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
        "last_modules_result": module_result,
        "stats_rows": stats_rows,
        "logs": recent_logs
    }
    return jsonify(data)

def start_server():
    """Start the Flask web server."""
    app.run(host="0.0.0.0", port=5000, debug=False)