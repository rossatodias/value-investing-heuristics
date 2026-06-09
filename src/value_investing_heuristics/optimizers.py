"""Heuristic optimizers for screening thresholds."""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from .config import THETA_BOUNDS

Theta = dict[str, float]
FitnessFn = Callable[[Theta], float]


@dataclass(frozen=True)
class OptimizerResult:
    theta: Theta
    fitness: float
    trials: int
    history: list[dict[str, float | int | str]]


class TrialLogger:
    def __init__(self, path: str | Path | None, *, strategy: str, metric: str = "train_sharpe") -> None:
        self.path = Path(path) if path is not None else None
        self.strategy = strategy
        self.metric = metric
        self.count = 0
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                with self.path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "timestamp_utc",
                            "strategy",
                            "trial",
                            "seed",
                            "metric",
                            "fitness",
                            *THETA_BOUNDS.keys(),
                        ],
                    )
                    writer.writeheader()

    def log(self, theta: Theta, fitness: float, seed: int | None = None) -> None:
        self.count += 1
        if self.path is None:
            return
        row = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "strategy": self.strategy,
            "trial": self.count,
            "seed": seed,
            "metric": self.metric,
            "fitness": fitness,
        }
        row.update(theta)
        with self.path.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=list(row.keys())).writerow(row)


def random_theta(rng: random.Random) -> Theta:
    return {name: rng.uniform(lo, hi) for name, (lo, hi) in THETA_BOUNDS.items()}


def clip_theta(theta: Theta) -> Theta:
    return {name: min(max(value, THETA_BOUNDS[name][0]), THETA_BOUNDS[name][1]) for name, value in theta.items()}


def mutate(theta: Theta, rng: random.Random, rate: float = 0.1, scale: float = 0.1) -> Theta:
    out = dict(theta)
    for name, (lo, hi) in THETA_BOUNDS.items():
        if rng.random() < rate:
            out[name] += rng.gauss(0.0, scale * (hi - lo))
    return clip_theta(out)


def crossover(a: Theta, b: Theta, rng: random.Random) -> Theta:
    alpha = rng.random()
    return clip_theta({name: alpha * a[name] + (1.0 - alpha) * b[name] for name in THETA_BOUNDS})


def _safe_fitness(fn: FitnessFn, theta: Theta) -> float:
    value = fn(theta)
    if value is None or np.isnan(value):
        return -1e9
    return float(value)


def genetic_algorithm(
    fitness_fn: FitnessFn,
    *,
    seed: int = 42,
    population_size: int = 50,
    generations: int = 100,
    crossover_prob: float = 0.8,
    mutation_prob: float = 0.1,
    patience: int = 20,
    logger: TrialLogger | None = None,
) -> OptimizerResult:
    rng = random.Random(seed)
    population = [random_theta(rng) for _ in range(population_size)]
    scores = [_safe_fitness(fitness_fn, theta) for theta in population]
    if logger:
        for theta, score in zip(population, scores, strict=False):
            logger.log(theta, score, seed)

    best_idx = int(np.argmax(scores))
    best_theta = population[best_idx]
    best_score = scores[best_idx]
    stale = 0
    history: list[dict[str, float | int | str]] = []

    for generation in range(generations):
        next_population = [best_theta]
        while len(next_population) < population_size:
            p1 = _tournament(population, scores, rng)
            p2 = _tournament(population, scores, rng)
            child = crossover(p1, p2, rng) if rng.random() < crossover_prob else dict(p1)
            child = mutate(child, rng, rate=mutation_prob)
            next_population.append(child)

        population = next_population
        scores = [_safe_fitness(fitness_fn, theta) for theta in population]
        if logger:
            for theta, score in zip(population, scores, strict=False):
                logger.log(theta, score, seed)

        current_idx = int(np.argmax(scores))
        current_score = scores[current_idx]
        if current_score > best_score:
            best_theta = population[current_idx]
            best_score = current_score
            stale = 0
        else:
            stale += 1

        history.append({"generation": generation, "best_fitness": best_score, "current_best": current_score})
        if stale >= patience:
            break

    return OptimizerResult(best_theta, best_score, logger.count if logger else len(history) * population_size, history)


def _tournament(population: list[Theta], scores: list[float], rng: random.Random) -> Theta:
    a, b = rng.sample(range(len(population)), 2)
    return population[a] if scores[a] >= scores[b] else population[b]


def simulated_annealing(
    fitness_fn: FitnessFn,
    *,
    seed: int = 42,
    initial_temperature: float = 1.0,
    final_temperature: float = 0.001,
    cooling: float = 0.95,
    logger: TrialLogger | None = None,
) -> OptimizerResult:
    rng = random.Random(seed)
    current = random_theta(rng)
    current_score = _safe_fitness(fitness_fn, current)
    best = dict(current)
    best_score = current_score
    if logger:
        logger.log(current, current_score, seed)

    temp = initial_temperature
    iteration = 0
    history: list[dict[str, float | int | str]] = []

    while temp > final_temperature:
        candidate = mutate(current, rng, rate=1.0, scale=0.08)
        score = _safe_fitness(fitness_fn, candidate)
        if logger:
            logger.log(candidate, score, seed)
        delta = score - current_score
        accept = delta >= 0 or rng.random() < math.exp(delta / max(temp, 1e-12))
        if accept:
            current = candidate
            current_score = score
        if score > best_score:
            best = candidate
            best_score = score
        history.append({"iteration": iteration, "temperature": temp, "best_fitness": best_score})
        temp *= cooling
        iteration += 1

    return OptimizerResult(best, best_score, logger.count if logger else iteration, history)
