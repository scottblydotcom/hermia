"""Tests for hermia.backend — backend stack metadata resolution."""

from hermia.backend import resolve_stack


def test_resolve_stack_full() -> None:
    entry = {
        "name": "gpu-box",
        "host": "http://10.0.0.5:11434",
        "stack": {"gpu_arch": "sm_89", "runtime_version": "CUDA 12.8"},
    }
    result = resolve_stack(entry, "0.24.0")
    assert result["gpu_arch"] == "sm_89"
    assert result["runtime_version"] == "CUDA 12.8"
    assert result["backend_stack"] == "0.24.0 | sm_89 | CUDA 12.8"


def test_resolve_stack_no_stack_block() -> None:
    entry = {"name": "gpu-box", "host": "http://10.0.0.5:11434"}
    result = resolve_stack(entry)
    assert result["gpu_arch"] is None
    assert result["runtime_version"] is None
    assert result["backend_stack"] is None


def test_resolve_stack_partial_gpu_only() -> None:
    entry = {
        "name": "gpu-box",
        "host": "http://10.0.0.5:11434",
        "stack": {"gpu_arch": "sm_89"},
    }
    result = resolve_stack(entry)
    assert result["gpu_arch"] == "sm_89"
    assert result["runtime_version"] is None
    assert result["backend_stack"] == "sm_89"


def test_resolve_stack_partial_runtime_only() -> None:
    entry = {
        "name": "gpu-box",
        "host": "http://10.0.0.5:11434",
        "stack": {"runtime_version": "CUDA 12.8"},
    }
    result = resolve_stack(entry)
    assert result["gpu_arch"] is None
    assert result["runtime_version"] == "CUDA 12.8"
    assert result["backend_stack"] == "CUDA 12.8"


def test_resolve_stack_non_dict_stack() -> None:
    entry = {
        "name": "gpu-box",
        "host": "http://10.0.0.5:11434",
        "stack": "not a dict",
    }
    result = resolve_stack(entry)
    assert result["gpu_arch"] is None
    assert result["runtime_version"] is None
    assert result["backend_stack"] is None


def test_resolve_stack_non_string_gpu_arch() -> None:
    entry = {
        "name": "gpu-box",
        "host": "http://10.0.0.5:11434",
        "stack": {"gpu_arch": 123},
    }
    result = resolve_stack(entry)
    assert result["gpu_arch"] is None


def test_resolve_stack_non_string_runtime_version() -> None:
    entry = {
        "name": "gpu-box",
        "host": "http://10.0.0.5:11434",
        "stack": {"runtime_version": ["CUDA"]},
    }
    result = resolve_stack(entry)
    assert result["runtime_version"] is None


def test_backend_stack_string_format() -> None:
    entry = {
        "name": "gpu-box",
        "host": "http://10.0.0.5:11434",
        "stack": {"gpu_arch": "sm_89", "runtime_version": "CUDA 12.8"},
    }
    result = resolve_stack(entry, "0.24.0")
    assert result["backend_stack"] == "0.24.0 | sm_89 | CUDA 12.8"


def test_backend_stack_all_none() -> None:
    entry = {"name": "gpu-box", "host": "http://10.0.0.5:11434"}
    result = resolve_stack(entry)
    assert result["backend_stack"] is None


def test_backend_stack_only_orchestration_version() -> None:
    entry = {"name": "gpu-box", "host": "http://10.0.0.5:11434"}
    result = resolve_stack(entry, "0.24.0")
    assert result["backend_stack"] == "0.24.0"
