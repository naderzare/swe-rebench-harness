from __future__ import annotations

import importlib.util
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from .suites import SuiteError


Candidate = dict[str, Any]
Selector = Callable[..., list[Candidate]]


def difficulty_from_meta(meta: Any) -> str | None:
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            return None
    if not isinstance(meta, dict):
        return None
    value = meta.get("llm_metadata", {}).get("difficulty")
    return str(value).lower() if value else None


def candidate_from_row(row: dict[str, Any]) -> Candidate:
    return {
        "instance_id": row["instance_id"],
        "repo": row["repo"],
        "language": str(row.get("language", "unknown")).lower(),
        "difficulty": difficulty_from_meta(row.get("meta")) or "unknown",
        "base_commit": row.get("base_commit"),
        "created_at": str(row.get("created_at", "")),
        "image_name": row.get("image_name"),
    }


def filter_candidates(
    candidates: list[Candidate],
    *,
    difficulty: str | None,
    languages: list[str] | None,
    excluded_tasks: set[str] | None = None,
    excluded_repos: set[str] | None = None,
) -> list[Candidate]:
    language_set = {value.lower() for value in languages or []}
    difficulty = difficulty.lower() if difficulty else None
    excluded_tasks = excluded_tasks or set()
    excluded_repos = excluded_repos or set()
    return sorted(
        (
            candidate
            for candidate in candidates
            if (difficulty is None or candidate["difficulty"] == difficulty)
            and (not language_set or candidate["language"] in language_set)
            and candidate["instance_id"] not in excluded_tasks
            and candidate["repo"] not in excluded_repos
        ),
        key=lambda candidate: candidate["instance_id"],
    )


def select_balanced(
    candidates: list[Candidate],
    *,
    count: int,
    seed: int,
    options: dict[str, Any],
) -> list[Candidate]:
    requested_languages = options.get("languages") or []
    languages = [value.lower() for value in requested_languages]
    if not languages:
        languages = sorted({candidate["language"] for candidate in candidates})
    if not languages:
        raise SuiteError("No candidate languages are available")

    maximum = options.get("max_per_language")
    if maximum is None:
        maximum = (count + len(languages) - 1) // len(languages)

    rng = random.Random(seed)
    pools: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        pools[candidate["language"]].append(candidate)
    for language in languages:
        rng.shuffle(pools[language])

    unique_repositories = bool(options.get("unique_repositories"))
    selected: list[Candidate] = []
    used_repositories: set[str] = set()
    language_counts: Counter[str] = Counter()

    while len(selected) < count:
        made_progress = False
        for language in languages:
            if len(selected) >= count:
                break
            if language_counts[language] >= maximum:
                continue
            pool = pools[language]
            while pool:
                candidate = pool.pop()
                if unique_repositories and candidate["repo"] in used_repositories:
                    continue
                selected.append(candidate)
                used_repositories.add(candidate["repo"])
                language_counts[language] += 1
                made_progress = True
                break
        if not made_progress:
            raise SuiteError(
                f"Balanced selection found only {len(selected)} of {count} tasks. "
                "Relax the language, repository, or per-language constraints."
            )
    return selected


def select_random(
    candidates: list[Candidate],
    *,
    count: int,
    seed: int,
    options: dict[str, Any],
) -> list[Candidate]:
    pool = list(candidates)
    random.Random(seed).shuffle(pool)
    unique_repositories = bool(options.get("unique_repositories"))
    maximum = options.get("max_per_language")
    used_repositories: set[str] = set()
    language_counts: Counter[str] = Counter()
    selected: list[Candidate] = []
    for candidate in pool:
        if unique_repositories and candidate["repo"] in used_repositories:
            continue
        if maximum is not None and language_counts[candidate["language"]] >= maximum:
            continue
        selected.append(candidate)
        used_repositories.add(candidate["repo"])
        language_counts[candidate["language"]] += 1
        if len(selected) == count:
            return selected
    raise SuiteError(
        f"Random selection found only {len(selected)} of {count} tasks. "
        "Relax the selection constraints."
    )


BUILTIN_SELECTORS: dict[str, Selector] = {
    "balanced": select_balanced,
    "random": select_random,
}


def load_selector(path: Path) -> Selector:
    if not path.is_file():
        raise SuiteError(f"Selector file does not exist: {path}")
    spec = importlib.util.spec_from_file_location(f"rebench_user_selector_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise SuiteError(f"Could not load selector: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise SuiteError(f"Selector failed while loading: {exc}") from exc
    selector = getattr(module, "select_tasks", None)
    if not callable(selector):
        raise SuiteError(f"Selector must define a callable select_tasks function: {path}")
    return selector


def validate_selection(
    selected: Any,
    candidates: list[Candidate],
    *,
    count: int,
    unique_repositories: bool,
    max_per_language: int | None,
) -> list[Candidate]:
    if not isinstance(selected, list):
        raise SuiteError("Selector must return a list of candidate dictionaries")
    if len(selected) != count:
        raise SuiteError(f"Selector returned {len(selected)} tasks; expected exactly {count}")

    available = {candidate["instance_id"]: candidate for candidate in candidates}
    ids: list[str] = []
    normalized: list[Candidate] = []
    for index, candidate in enumerate(selected):
        if not isinstance(candidate, dict) or not candidate.get("instance_id"):
            raise SuiteError(f"Selector result {index} is not a candidate dictionary")
        instance_id = candidate["instance_id"]
        if instance_id not in available:
            raise SuiteError(f"Selector returned an unknown or filtered task: {instance_id}")
        ids.append(instance_id)
        normalized.append(available[instance_id])
    duplicates = sorted(value for value, amount in Counter(ids).items() if amount > 1)
    if duplicates:
        raise SuiteError(f"Selector returned duplicate tasks: {', '.join(duplicates)}")

    repositories = [candidate["repo"] for candidate in normalized]
    if unique_repositories and len(repositories) != len(set(repositories)):
        raise SuiteError("Selector returned repeated repositories while uniqueness is required")
    if max_per_language is not None:
        excessive = {
            language: amount
            for language, amount in Counter(candidate["language"] for candidate in normalized).items()
            if amount > max_per_language
        }
        if excessive:
            detail = ", ".join(f"{language}={amount}" for language, amount in sorted(excessive.items()))
            raise SuiteError(f"Selector exceeded --max-per-language: {detail}")
    return normalized
