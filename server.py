# server.py
from flask import Flask, render_template_string
from state import game_state, last_event_result, last_modules_result, stats, prev_stats, log_store

app = Flask(__name__)

@app.route("/")
def index():
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Detection Dashboard</title>
        <meta http-equiv="refresh" content="1">
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
                <h4>Game State: <span class="badge badge-primary">{{ game_state }}</span></h4>
                <h5>Latest Event Analysis:</h5>
                <pre>{{ last_event_result }}</pre>
                <h5>Latest Modules Analysis:</h5>
                <pre>{{ last_modules_result }}</pre>
            </div>
            <h3>Session Statistics</h3>
            <table class="table table-bordered stats-table">
                <thead class="thead-dark">
                    <tr>
                        <th>Metric</th>
                        <th>Count</th>
                    </tr>
                </thead>
                <tbody>
                    {% for metric, value, changed in rows %}
                    <tr {% if changed %} class="table-success" {% endif %}>
                        <td>{{ metric }}</td>
                        <td>{{ value }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <div class="card mb-4">
                <div class="card-header">
                    <strong>Recent Logs</strong>
                </div>
                <div class="card-body log-container">
                    <pre>{{ logs }}</pre>
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
            <p class="mt-3 text-muted">Page refreshes every 1 second.</p>
        </div>
    </body>
    </html>
    """
    rows = []
    for metric, value in stats.items():
        changed = (prev_stats.get(metric) != value)
        rows.append((metric.capitalize().replace("_", " "), value, changed))
    # Update prev_stats with the current stats
    prev_stats.clear()
    prev_stats.update(stats)

    recent_logs = "\n".join(log_store[-50:])
    return render_template_string(
        html_template,
        logs=recent_logs,
        game_state=game_state,
        last_event_result=last_event_result,
        last_modules_result=last_modules_result,
        rows=rows
    )

def start_server():
    """Start the Flask web server."""
    app.run(host="0.0.0.0", port=5000, debug=False)