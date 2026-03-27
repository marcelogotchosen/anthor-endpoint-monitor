#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


INTERVAL_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 120
HISTORY_LENGTH = 30
MAX_LOG_LINES = 10
ENDPOINTS_DIR = Path(__file__).resolve().parent / "endpoints"
GRAPH_LEVELS = " .:-=+*#%@"
ANSI_RED = "\033[31m"
ANSI_RESET = "\033[0m"
MIN_TERMINAL_COLUMNS = 120
MIN_TERMINAL_ROWS = 28


@dataclass
class EndpointState:
    name: str
    path: Path
    latencies: deque[float] = field(default_factory=lambda: deque(maxlen=HISTORY_LENGTH))
    outcomes: deque[bool] = field(default_factory=lambda: deque(maxlen=HISTORY_LENGTH))
    runs: int = 0
    successes: int = 0
    failures: int = 0
    last_duration: float | None = None
    last_error: str = ""
    last_run_at: str = "-"

    def record(self, success: bool, duration: float, message: str, stamp: str) -> None:
        self.runs += 1
        self.last_duration = duration
        self.last_run_at = stamp
        self.latencies.append(duration)
        self.outcomes.append(success)
        if success:
            self.successes += 1
            self.last_error = ""
        else:
            self.failures += 1
            self.last_error = message

    @property
    def status(self) -> str:
        if self.runs == 0:
            return "PENDENTE"
        if self.outcomes and self.outcomes[-1]:
            return "OK"
        return "FALHA"

    @property
    def avg_duration(self) -> float | None:
        if not self.latencies:
            return None
        return sum(self.latencies) / len(self.latencies)

    @property
    def min_duration(self) -> float | None:
        if not self.latencies:
            return None
        return min(self.latencies)

    @property
    def max_duration(self) -> float | None:
        if not self.latencies:
            return None
        return max(self.latencies)


def now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clear_screen() -> None:
    print("\033[2J\033[H", end="")


def ensure_min_terminal_size() -> tuple[int, int]:
    try:
        size = os.get_terminal_size()
    except OSError:
        return 0, 0

    columns = size.columns
    rows = size.lines

    if columns < MIN_TERMINAL_COLUMNS or rows < MIN_TERMINAL_ROWS:
        print(f"\033[8;{MIN_TERMINAL_ROWS};{MIN_TERMINAL_COLUMNS}t", end="")
        sys.stdout.flush()
        time.sleep(0.05)
        try:
            resized = os.get_terminal_size()
            columns = resized.columns
            rows = resized.lines
        except OSError:
            pass

    return columns, rows


def play_alert() -> None:
    if shutil.which("afplay"):
        subprocess.run(
            ["afplay", "/System/Library/Sounds/Sosumi.aiff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    print("\a", end="", flush=True)


def truncate(text: str, limit: int = 140) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def format_seconds(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.3f}s"


def load_endpoint_paths() -> list[Path]:
    ENDPOINTS_DIR.mkdir(exist_ok=True)
    return sorted(
        path
        for path in ENDPOINTS_DIR.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )


def build_states(paths: list[Path]) -> list[EndpointState]:
    return [EndpointState(name=path.stem, path=path) for path in paths]


def detect_body_error(body: str) -> str | None:
    text = body.strip()
    if not text:
        return "Resposta vazia."

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None

    if isinstance(payload, dict):
        if payload.get("errors"):
            return truncate(json.dumps(payload["errors"], ensure_ascii=True), 200)
        if payload.get("error"):
            return truncate(json.dumps(payload["error"], ensure_ascii=True), 200)

    return None


def run_endpoint(path: Path) -> tuple[bool, float, str]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            ["zsh", str(path)],
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
            check=False,
            cwd=str(path.parent),
        )
    except subprocess.TimeoutExpired:
        duration = time.perf_counter() - started
        return False, duration, "Timeout ao aguardar resposta do curl."
    except Exception as exc:
        duration = time.perf_counter() - started
        return False, duration, f"Erro ao executar endpoint: {exc}"

    duration = time.perf_counter() - started

    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "Comando terminou com erro."
        return False, duration, truncate(details, 200)

    body_error = detect_body_error(result.stdout)
    if body_error:
        return False, duration, body_error

    return True, duration, truncate(result.stdout or "Resposta OK.", 100)


def build_graph(state: EndpointState, width: int = HISTORY_LENGTH) -> str:
    if not state.outcomes:
        return "." * width

    values = list(state.latencies)[-width:]
    outcomes = list(state.outcomes)[-width:]
    successful = [value for value, ok in zip(values, outcomes) if ok]
    max_value = max(successful, default=1.0)

    chars = []
    for value, ok in zip(values, outcomes):
        if not ok:
            chars.append("X")
            continue
        if max_value <= 0:
            chars.append(GRAPH_LEVELS[0])
            continue
        ratio = value / max_value
        index = min(len(GRAPH_LEVELS) - 1, int(round(ratio * (len(GRAPH_LEVELS) - 1))))
        chars.append(GRAPH_LEVELS[index])

    graph = "".join(chars)
    if len(graph) < width:
        graph = "." * (width - len(graph)) + graph
    return graph


def render_dashboard(
    states: list[EndpointState],
    logs: deque[str],
    cycle: int,
    cycle_started_at: float | None,
    next_run_at: float | None,
) -> None:
    clear_screen()
    columns, rows = ensure_min_terminal_size()
    print("=" * 100)
    print("Anthor Endpoint Monitor")
    print(f"Iniciado em: {now_string()} | ciclo: {cycle} | intervalo alvo: {INTERVAL_SECONDS}s")
    print(f"Endpoints monitorados: {len(states)} | pasta: {ENDPOINTS_DIR}")
    if columns and rows:
        print(
            f"Terminal atual: {columns}x{rows} | minimo recomendado: "
            f"{MIN_TERMINAL_COLUMNS}x{MIN_TERMINAL_ROWS}"
        )
    if cycle_started_at is not None:
        print(f"Ultimo ciclo iniciado em: {datetime.fromtimestamp(cycle_started_at).strftime('%Y-%m-%d %H:%M:%S')}")
    if next_run_at is not None:
        remaining = max(0.0, next_run_at - time.time())
        print(f"Proxima rodada em: {remaining:.1f}s")
    print("=" * 100)
    print()

    if not states:
        print("Nenhum endpoint encontrado. Adicione arquivos com curl dentro da pasta 'endpoints/'.")
    else:
        for state in states:
            lines = []
            lines.append(
                f"[{state.status:<7}] {state.name} | last {format_seconds(state.last_duration)} "
                f"| avg {format_seconds(state.avg_duration)} | min {format_seconds(state.min_duration)} "
                f"| max {format_seconds(state.max_duration)} | ok {state.successes} | falhas {state.failures}"
            )
            lines.append(f"  grafico: {build_graph(state)}")
            lines.append(f"  arquivo : {state.path.name} | ultima execucao: {state.last_run_at}")
            if state.last_error:
                lines.append(f"  ultimo erro: {truncate(state.last_error, 180)}")

            if state.status == "FALHA":
                for line in lines:
                    print(f"{ANSI_RED}{line}{ANSI_RESET}")
            else:
                for line in lines:
                    print(line)
            print()

    print("-" * 100)
    print("Eventos recentes")
    if not logs:
        print("Nenhum evento ainda.")
    else:
        for line in logs:
            print(line)
    print("-" * 100)
    print("Ctrl+C para encerrar.")
    print(flush=True)


def monitor() -> None:
    endpoint_paths = load_endpoint_paths()
    states = build_states(endpoint_paths)
    logs: deque[str] = deque(maxlen=MAX_LOG_LINES)
    cycle = 1
    cycle_started_at = None
    next_run_at = None

    render_dashboard(states, logs, cycle, cycle_started_at, next_run_at)

    while True:
        clear_screen()
        ensure_min_terminal_size()
        cycle_started_at = time.time()
        next_run_at = cycle_started_at + INTERVAL_SECONDS
        endpoint_paths = load_endpoint_paths()

        known_paths = {state.path for state in states}
        for path in endpoint_paths:
            if path not in known_paths:
                states.append(EndpointState(name=path.stem, path=path))
                logs.appendleft(f"[{now_string()}] Endpoint adicionado: {path.name}")

        current_paths = set(endpoint_paths)
        removed = [state for state in states if state.path not in current_paths]
        for state in removed:
            logs.appendleft(f"[{now_string()}] Endpoint removido: {state.path.name}")
        states = [state for state in states if state.path in current_paths]
        states.sort(key=lambda item: item.name)

        for state in states:
            stamp = now_string()
            success, duration, details = run_endpoint(state.path)
            state.record(success=success, duration=duration, message=details, stamp=stamp)
            if success:
                logs.appendleft(
                    f"[{stamp}] {state.name}: OK em {duration:.3f}s"
                )
            else:
                logs.appendleft(
                    f"[{stamp}] {state.name}: FALHOU em {duration:.3f}s | {truncate(details, 120)}"
                )
                play_alert()
            render_dashboard(states, logs, cycle, cycle_started_at, next_run_at)

        elapsed = time.time() - cycle_started_at
        sleep_for = max(0.0, INTERVAL_SECONDS - elapsed)
        next_run_at = time.time() + sleep_for
        render_dashboard(states, logs, cycle, cycle_started_at, next_run_at)
        time.sleep(sleep_for)
        cycle += 1


if __name__ == "__main__":
    try:
        monitor()
    except KeyboardInterrupt:
        print("\nMonitor encerrado pelo usuario.")
        sys.exit(0)
