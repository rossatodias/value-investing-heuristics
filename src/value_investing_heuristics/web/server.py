"""Web bridge: serves the SPA and streams CLI pipeline runs to the browser."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

from value_investing_heuristics import config

WEB_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = config.ROOT
OUTPUTS_DIR = config.OUTPUTS
DATA_RAW = config.DATA_RAW
DATA_PROCESSED = config.DATA_PROCESSED
MANUAL_PATH = config.ROOT / "manual.md"

app = Flask(
    __name__,
    static_folder=str(WEB_DIR / "static"),
    template_folder=str(WEB_DIR / "templates"),
)
CORS(app)

CLI_BASE = [sys.executable, "-m", "value_investing_heuristics.cli"]


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _stream_subprocess(cmd: list[str]):
    """Run *cmd* and yield its stdout as SSE 'output' events.

    Returns the process exit code (via ``yield from``). Launch failures
    (e.g. interpreter or module missing) raise OSError to the caller.
    """
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
            yield _sse({"type": "output", "text": stripped})
    proc.wait()
    return proc.returncode


@app.route("/")
def index():
    return send_file(str(WEB_DIR / "templates" / "index.html"))


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(str(WEB_DIR / "static"), filename)


@app.route("/api/status")
def file_status():
    """Report which pipeline data files already exist."""
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


@app.route("/api/outputs/<path:filepath>")
def serve_output(filepath):
    """Serve a file from outputs/, refusing paths that escape the directory."""
    full_path = OUTPUTS_DIR / filepath
    if not full_path.exists():
        return Response("File not found", status=404)
    try:
        full_path.resolve().relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        return Response("Forbidden", status=403)
    return send_file(str(full_path))


@app.route("/api/manual")
def serve_manual():
    if not MANUAL_PATH.exists():
        return Response("Manual not found", status=404)
    return Response(MANUAL_PATH.read_text(encoding="utf-8"), mimetype="text/plain")


@app.route("/api/data-profile")
def data_profile():
    profile_path = OUTPUTS_DIR / "data_profile.json"
    if not profile_path.exists():
        return jsonify({})
    return Response(profile_path.read_text(encoding="utf-8"), mimetype="application/json")


@app.route("/api/run-step", methods=["POST"])
def run_step():
    """Run one pipeline step in a subprocess and stream its output as SSE.

    Request JSON: {"command": "prepare"|"fetch-mapping"|"fetch-prices"|"fetch-aux"|"backtest",
                   "cost_bps": 10}  (cost_bps only used by backtest).
    """
    data = request.get_json(force=True, silent=True) or {}
    command = data.get("command", "")
    cost_bps = data.get("cost_bps", 10)

    if command == "fetch-aux":
        return _run_aux_commands()

    cmd = _build_command(command, cost_bps)
    if cmd is None:
        def error_stream():
            yield _sse({"type": "error", "text": f"Comando desconhecido: {command}"})
            yield _sse({"type": "done", "success": False, "error": "Comando desconhecido"})
        return Response(error_stream(), mimetype="text/event-stream")

    def generate():
        yield _sse({"type": "output", "text": "$ " + " ".join(cmd)})
        try:
            rc = yield from _stream_subprocess(cmd)
        except OSError as e:
            yield _sse({"type": "error", "text": str(e)})
            yield _sse({"type": "done", "success": False, "error": str(e)})
            return
        if rc == 0:
            yield _sse({"type": "done", "success": True})
        else:
            yield _sse({"type": "done", "success": False, "error": f"Exit code {rc}"})

    return Response(generate(), mimetype="text/event-stream")


def _run_aux_commands():
    """Stream fetch-cdi then fetch-ibrx100 as a single SSE response."""
    commands = [
        (CLI_BASE + ["fetch-cdi", "--start", "2020-01-01"], "fetch-cdi"),
        (CLI_BASE + ["fetch-ibrx100", "--start-year", "2021"], "fetch-ibrx100"),
    ]

    def generate():
        all_success = True
        for cmd, label in commands:
            yield _sse({"type": "output", "text": f"--- Executando: vih {label} ---"})
            yield _sse({"type": "output", "text": "$ " + " ".join(cmd)})
            try:
                rc = yield from _stream_subprocess(cmd)
            except OSError as e:
                all_success = False
                yield _sse({"type": "error", "text": str(e)})
                continue
            if rc != 0:
                all_success = False
                yield _sse({"type": "error", "text": f"{label} falhou (exit {rc})"})
            else:
                yield _sse({"type": "output", "text": f"{label} concluido com sucesso."})
        yield _sse({"type": "done", "success": all_success})

    return Response(generate(), mimetype="text/event-stream")


def _build_command(command: str, cost_bps: float) -> list[str] | None:
    """Map a pipeline step name to its CLI argument list."""
    args = {
        "prepare": ["prepare", "--input", str(DATA_RAW / "itr_completo.csv")],
        "fetch-mapping": ["fetch-mapping"],
        "fetch-prices": ["fetch-prices", "--start", "2021-01-01"],
        "backtest": ["backtest", "--cost-bps", str(cost_bps)],
    }.get(command)
    return CLI_BASE + args if args else None


def main() -> int:
    port = int(os.environ.get("VIH_PORT", 5050))
    print(f"\n  Value Investing Heuristics — http://localhost:{port}")
    print(f"  Project root: {PROJECT_ROOT}\n")
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
