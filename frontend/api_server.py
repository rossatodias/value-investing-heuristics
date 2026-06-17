"""
VIH Frontend — API Bridge Server

Proxy between the web frontend and the CLI backend.
Does NOT modify any backend logic. Only invokes `vih` commands
via subprocess and serves output files.

Usage:
    cd frontend
    python api_server.py

    Open http://localhost:5050
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

# --- Paths ---
FRONTEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FRONTEND_DIR.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
MANUAL_PATH = PROJECT_ROOT / "manual.md"

# --- App ---
app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR / "static"),
    template_folder=str(FRONTEND_DIR / "templates"),
)
CORS(app)


# ====================================================================
# Static / SPA
# ====================================================================

@app.route("/")
def index():
    return send_file(str(FRONTEND_DIR / "templates" / "index.html"))


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(str(FRONTEND_DIR / "static"), filename)


# ====================================================================
# API: File Status
# ====================================================================

@app.route("/api/status")
def file_status():
    """Check which data files exist."""
    status = {
        "fundamentals": (DATA_PROCESSED / "fundamentals.csv").exists(),
        "mapping": (DATA_RAW / "cnpj_ticker_map.csv").exists(),
        "prices": (DATA_RAW / "prices.csv").exists(),
        "cdi": (DATA_PROCESSED / "cdi.csv").exists(),
        "ibrx100": (DATA_PROCESSED / "ibrx100_history.csv").exists(),
        "summary": (OUTPUTS_DIR / "backtest_summary.csv").exists(),
        "selections": (OUTPUTS_DIR / "backtest_selections.csv").exists(),
        "report": (OUTPUTS_DIR / "backtest_report.md").exists(),
        "trials": (OUTPUTS_DIR / "backtest_trials.csv").exists(),
    }
    return jsonify(status)


# ====================================================================
# API: Serve Output Files
# ====================================================================

@app.route("/api/outputs/<path:filepath>")
def serve_output(filepath):
    """Serve files from the outputs/ directory."""
    full_path = OUTPUTS_DIR / filepath
    if not full_path.exists():
        return Response("File not found", status=404)
    # Security: ensure path is within outputs
    try:
        full_path.resolve().relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        return Response("Forbidden", status=403)
    return send_file(str(full_path))


# ====================================================================
# API: Manual
# ====================================================================

@app.route("/api/manual")
def serve_manual():
    """Serve the manual.md content."""
    if not MANUAL_PATH.exists():
        return Response("Manual not found", status=404)
    return Response(MANUAL_PATH.read_text(encoding="utf-8"), mimetype="text/plain")


# ====================================================================
# API: Data Profile
# ====================================================================

@app.route("/api/data-profile")
def data_profile():
    """Serve the data_profile.json if available."""
    profile_path = OUTPUTS_DIR / "data_profile.json"
    if not profile_path.exists():
        return jsonify({})
    return Response(profile_path.read_text(encoding="utf-8"), mimetype="application/json")


# ====================================================================
# API: Run Pipeline Step (SSE streaming)
# ====================================================================

@app.route("/api/run-step", methods=["POST"])
def run_step():
    """
    Execute a pipeline step via subprocess and stream output as SSE.

    Request JSON:
        { "command": "prepare" | "fetch-mapping" | "fetch-prices" | "fetch-aux" | "backtest",
          "cost_bps": 10  (optional, for backtest) }
    """
    data = request.get_json(force=True, silent=True) or {}
    command = data.get("command", "")
    cost_bps = data.get("cost_bps", 10)

    # fetch-aux runs two commands sequentially
    if command == "fetch-aux":
        return _run_aux_commands()

    # Build the CLI command
    cmd = _build_command(command, cost_bps)
    if cmd is None:
        def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'text': f'Comando desconhecido: {command}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'success': False, 'error': 'Comando desconhecido'})}\n\n"
        return Response(error_stream(), mimetype="text/event-stream")

    def generate():
        try:
            yield f"data: {json.dumps({'type': 'output', 'text': '$ ' + ' '.join(cmd)})}\n\n"

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )

            for line in iter(proc.stdout.readline, ""):
                stripped = line.rstrip("\n")
                if stripped:
                    yield f"data: {json.dumps({'type': 'output', 'text': stripped})}\n\n"

            proc.wait()

            if proc.returncode == 0:
                yield f"data: {json.dumps({'type': 'done', 'success': True})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'done', 'success': False, 'error': f'Exit code {proc.returncode}'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'success': False, 'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


def _run_aux_commands():
    """Handle fetch-aux: runs fetch-cdi + fetch-ibrx100 sequentially."""
    python = sys.executable
    base = [python, "-m", "value_investing_heuristics.cli"]
    commands = [
        (base + ["fetch-cdi", "--start", "2020-01-01"], "fetch-cdi"),
        (base + ["fetch-ibrx100", "--start-year", "2021"], "fetch-ibrx100"),
    ]

    def generate():
        all_success = True
        for cmd, label in commands:
            yield f"data: {json.dumps({'type': 'output', 'text': f'--- Executando: vih {label} ---'})}\n\n"
            yield f"data: {json.dumps({'type': 'output', 'text': '$ ' + ' '.join(cmd)})}\n\n"

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    cwd=str(PROJECT_ROOT),
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
                for line in iter(proc.stdout.readline, ""):
                    stripped = line.rstrip("\n")
                    if stripped:
                        yield f"data: {json.dumps({'type': 'output', 'text': stripped})}\n\n"
                proc.wait()
                if proc.returncode != 0:
                    all_success = False
                    yield f"data: {json.dumps({'type': 'error', 'text': f'{label} falhou (exit {proc.returncode})'})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'output', 'text': f'{label} concluido com sucesso.'})}\n\n"
            except Exception as e:
                all_success = False
                yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'success': all_success})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


def _build_command(command: str, cost_bps: float) -> list[str] | None:
    """Build the subprocess command list for a given pipeline step."""
    python = sys.executable
    base = [python, "-m", "value_investing_heuristics.cli"]

    if command == "prepare":
        return base + ["prepare", "--input", str(PROJECT_ROOT / "itr_completo.csv")]
    elif command == "fetch-mapping":
        return base + ["fetch-mapping"]
    elif command == "fetch-prices":
        return base + ["fetch-prices", "--start", "2021-01-01"]
    elif command == "backtest":
        return base + ["backtest", "--cost-bps", str(cost_bps)]
    return None


# ====================================================================
# Main
# ====================================================================

if __name__ == "__main__":
    port = int(os.environ.get("VIH_PORT", 5050))
    print(f"\n  VIH Frontend Server")
    print(f"  http://localhost:{port}\n")
    print(f"  Project root: {PROJECT_ROOT}")
    print(f"  Outputs dir:  {OUTPUTS_DIR}\n")
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
