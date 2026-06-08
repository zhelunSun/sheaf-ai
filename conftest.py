"""Root conftest — exclude non-test directories from pytest collection."""
collect_ignore_glob = ["scripts/*", "internal/*"]
