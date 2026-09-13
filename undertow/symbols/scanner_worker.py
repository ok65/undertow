"""The separate process which performs cached symbol scans."""

from __future__ import annotations

from multiprocessing.synchronize import Event
from pathlib import Path

from .package_cache import PackageSymbolCache


def run_scanner_worker(database_path: str, stop_event: Event) -> None:
    """Run persisted jobs until the GUI asks the worker to stop."""
    cache = PackageSymbolCache(Path(database_path))
    while not stop_event.is_set():
        job = cache.claim_next_job()
        if job is None:
            stop_event.wait(0.25)
            continue
        try:
            cache.cache_package(job.package_name, job.site_packages, job.python_tag, job.platform_tag)
        except Exception as error:  # Worker failures belong in the durable job log.
            cache.finish_job(job.id, str(error))
        else:
            cache.finish_job(job.id)
