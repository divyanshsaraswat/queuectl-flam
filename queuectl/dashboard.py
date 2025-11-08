"""Web dashboard for QueueCTL monitoring"""

from flask import Flask, render_template_string, jsonify
from .storage import JobStorage
from .config import Config
import os
import platform

app = Flask(__name__)

# Dashboard HTML template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QueueCTL Dashboard</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #ffffff;
            padding: 10px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            padding: 15px;
            margin-bottom: 15px;
            border: 1px solid #000000;
        }
        .header h1 {
            margin: 0 0 5px 0;
            font-size: 20px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
            margin-bottom: 15px;
        }
        .stat-card {
            padding: 10px;
            border: 1px solid #000000;
            text-align: center;
        }
        .stat-card h3 {
            font-size: 12px;
            margin: 0 0 5px 0;
        }
        .stat-card .value {
            font-size: 24px;
            font-weight: bold;
        }
        .jobs-section {
            padding: 15px;
            margin-bottom: 15px;
            border: 1px solid #000000;
        }
        .jobs-section h2 {
            margin: 0 0 10px 0;
            font-size: 16px;
        }
        .table-wrapper {
            overflow-x: auto;
            width: 100%;
        }
        .jobs-table {
            width: 100%;
            min-width: 600px;
            border-collapse: collapse;
            border: 1px solid #000000;
        }
        .jobs-table th,
        .jobs-table td {
            padding: 8px;
            text-align: left;
            border: 1px solid #000000;
        }
        .jobs-table th {
            background: #cccccc;
        }
        .badge {
            padding: 2px 5px;
            border: 1px solid #000000;
            font-size: 11px;
        }
        .metrics-section {
            padding: 15px;
            border: 1px solid #000000;
        }
        .metrics-section h2 {
            margin: 0 0 10px 0;
            font-size: 16px;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
        }
        .metric-item {
            padding: 10px;
            border: 1px solid #000000;
        }
        .metric-item label {
            display: block;
            font-size: 12px;
            margin-bottom: 5px;
        }
        .metric-item .value {
            font-size: 18px;
            font-weight: bold;
        }
        .refresh-btn {
            background: #ffffff;
            color: #000000;
            border: 1px solid #000000;
            padding: 5px 10px;
            cursor: pointer;
            font-size: 12px;
            margin-top: 10px;
        }
        .auto-refresh {
            margin-top: 5px;
            font-size: 11px;
        }
        @media (max-width: 768px) {
            body {
                padding: 5px;
            }
            .container {
                max-width: 100%;
            }
            .header {
                padding: 10px;
            }
            .header h1 {
                font-size: 18px;
            }
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
                gap: 8px;
            }
            .stat-card {
                padding: 8px;
            }
            .stat-card h3 {
                font-size: 11px;
            }
            .stat-card .value {
                font-size: 20px;
            }
            .metrics-grid {
                grid-template-columns: repeat(2, 1fr);
                gap: 8px;
            }
            .metric-item {
                padding: 8px;
            }
            .metric-item label {
                font-size: 11px;
            }
            .metric-item .value {
                font-size: 16px;
            }
            .jobs-section {
                padding: 10px;
            }
            .jobs-section h2 {
                font-size: 14px;
            }
            .jobs-table th,
            .jobs-table td {
                padding: 6px;
                font-size: 12px;
            }
            .badge {
                font-size: 10px;
                padding: 1px 4px;
            }
            .metrics-section {
                padding: 10px;
            }
            .metrics-section h2 {
                font-size: 14px;
            }
        }
        @media (max-width: 480px) {
            .stats-grid {
                grid-template-columns: 1fr;
            }
            .metrics-grid {
                grid-template-columns: 1fr;
            }
            .jobs-table {
                min-width: 500px;
            }
            .jobs-table th,
            .jobs-table td {
                padding: 4px;
                font-size: 11px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>QueueCTL Dashboard</h1>
            <p>Job queue monitoring</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Jobs</h3>
                <div class="value" id="total">0</div>
            </div>
            <div class="stat-card pending">
                <h3>Pending</h3>
                <div class="value" id="pending">0</div>
            </div>
            <div class="stat-card processing">
                <h3>Processing</h3>
                <div class="value" id="processing">0</div>
            </div>
            <div class="stat-card completed">
                <h3>Completed</h3>
                <div class="value" id="completed">0</div>
            </div>
            <div class="stat-card failed">
                <h3>Failed</h3>
                <div class="value" id="failed">0</div>
            </div>
            <div class="stat-card dead">
                <h3>Dead (DLQ)</h3>
                <div class="value" id="dead">0</div>
            </div>
        </div>
        
        <div class="metrics-section">
            <h2>Execution Metrics</h2>
            <div class="metrics-grid">
                <div class="metric-item">
                    <label>Success Rate</label>
                    <div class="value" id="success-rate">0%</div>
                </div>
                <div class="metric-item">
                    <label>Avg Execution Time</label>
                    <div class="value" id="avg-time">0.00s</div>
                </div>
                <div class="metric-item">
                    <label>Min Execution Time</label>
                    <div class="value" id="min-time">0.00s</div>
                </div>
                <div class="metric-item">
                    <label>Max Execution Time</label>
                    <div class="value" id="max-time">0.00s</div>
                </div>
            </div>
        </div>
        
        <div class="jobs-section">
            <h2>Recent Jobs</h2>
            <div class="table-wrapper">
            <table class="jobs-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Command</th>
                        <th>State</th>
                        <th>Priority</th>
                        <th>Attempts</th>
                        <th>Execution Time</th>
                        <th>Created At</th>
                    </tr>
                </thead>
                <tbody id="jobs-tbody">
                    <tr><td colspan="7" style="text-align: center;">Loading...</td></tr>
                </tbody>
            </table>
            </div>
            <button class="refresh-btn" onclick="loadData()">Refresh</button>
            <div class="auto-refresh">Auto-refreshing every 5 seconds</div>
        </div>
    </div>
    
    <script>
        function loadData() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('total').textContent = data.total || 0;
                    document.getElementById('pending').textContent = data.pending || 0;
                    document.getElementById('processing').textContent = data.processing || 0;
                    document.getElementById('completed').textContent = data.completed || 0;
                    document.getElementById('failed').textContent = data.failed || 0;
                    document.getElementById('dead').textContent = data.dead || 0;
                    
                    if (data.execution_metrics) {
                        const m = data.execution_metrics;
                        document.getElementById('success-rate').textContent = 
                            (data.success_rate || 0).toFixed(1) + '%';
                        document.getElementById('avg-time').textContent = 
                            (m.avg_execution_time || 0).toFixed(2) + 's';
                        document.getElementById('min-time').textContent = 
                            (m.min_execution_time || 0).toFixed(2) + 's';
                        document.getElementById('max-time').textContent = 
                            (m.max_execution_time || 0).toFixed(2) + 's';
                    }
                });
            
            fetch('/api/jobs?limit=20')
                .then(r => r.json())
                .then(jobs => {
                    const tbody = document.getElementById('jobs-tbody');
                    if (jobs.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center;">No jobs found</td></tr>';
                        return;
                    }
                    tbody.innerHTML = jobs.map(job => `
                        <tr>
                            <td><code>${job.id}</code></td>
                            <td><code style="max-width: 300px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${job.command || ''}</code></td>
                            <td><span class="badge ${job.state}">${job.state}</span></td>
                            <td>${job.priority || 0}</td>
                            <td>${job.attempts || 0}/${job.max_retries || 0}</td>
                            <td>${job.execution_time ? job.execution_time.toFixed(2) + 's' : '-'}</td>
                            <td>${new Date(job.created_at).toLocaleString()}</td>
                        </tr>
                    `).join('');
                });
        }
        
        // Load data on page load
        loadData();
        
        // Auto-refresh every 5 seconds
        setInterval(loadData, 5000);
    </script>
</body>
</html>
"""


@app.route('/')
def dashboard():
    """Render the dashboard"""
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/stats')
def api_stats():
    """Get queue statistics"""
    storage = JobStorage()
    stats = storage.get_stats()
    return jsonify(stats)


@app.route('/api/jobs')
def api_jobs():
    """Get jobs list"""
    from flask import request
    storage = JobStorage()
    
    state = request.args.get('state')
    limit = int(request.args.get('limit', 50))
    
    if state:
        jobs = storage.get_jobs_by_state(state)
    else:
        # Get all jobs, sorted by updated_at
        with storage.lock:
            import sqlite3
            conn = sqlite3.connect(storage.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM jobs 
                ORDER BY updated_at DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            jobs = [dict(row) for row in rows]
    
    return jsonify(jobs)


@app.route('/api/job/<job_id>')
def api_job(job_id):
    """Get a specific job"""
    storage = JobStorage()
    job = storage.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


def get_active_workers():
    """Get count of active workers"""
    pid_file = "queuectl.workers.pid"
    if not os.path.exists(pid_file):
        return 0
    
    with open(pid_file, 'r') as f:
        pids = [int(pid) for pid in f.read().strip().split('\n') if pid]
    
    alive_workers = 0
    for pid in pids:
        try:
            os.kill(pid, 0)
            alive_workers += 1
        except OSError:
            pass
    
    return alive_workers


@app.route('/api/workers')
def api_workers():
    """Get worker information"""
    return jsonify({
        'active': get_active_workers()
    })


def run_dashboard(host='127.0.0.1', port=5000, debug=False):
    """Run the dashboard server"""
    print(f"🚀 Starting QueueCTL Dashboard on http://{host}:{port}")
    print(f"📊 Open your browser to view the dashboard")
    app.run(host=host, port=port, debug=debug)

