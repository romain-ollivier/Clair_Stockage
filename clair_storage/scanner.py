from __future__ import annotations

import heapq
import os
import shutil
import stat
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Node:
    id: int
    path: str
    name: str
    parent: int | None
    children: list[int] = field(default_factory=list)
    direct_bytes: int = 0
    direct_files: int = 0
    total_bytes: int = 0
    files: int = 0
    directories: int = 0
    extensions: Counter = field(default_factory=Counter)
    extension_counts: Counter = field(default_factory=Counter)
    direct_extensions: Counter = field(default_factory=Counter)
    largest_files: list[tuple[int, str, float]] = field(default_factory=list)
    scanned: bool = False
    complete: bool = False
    errors: int = 0
    skipped: int = 0
    excluded: str = ''
    reference: int | None = None


@dataclass
class ScanResult:
    nodes: list[Node]
    started_at: float
    finished_at: float
    reason: str = 'complete'
    entries: int = 0
    error_examples: list[dict] = field(default_factory=list)
    volumes: list[dict] = field(default_factory=list)
    demo: bool = False

    @property
    def root(self):
        return self.nodes[0]


def normalize_roots(roots):
    paths = sorted({os.path.abspath(os.path.expanduser(str(p))) for p in roots}, key=len)
    selected = []
    for path in paths:
        overlap = False
        for existing in selected:
            try:
                overlap = os.path.normcase(os.path.commonpath([path, existing])) == os.path.normcase(existing)
            except ValueError:
                overlap = False
            if overlap:
                break
        if not overlap:
            selected.append(path)
    return selected


def scan(roots, stop: threading.Event, progress: Callable | None = None,
         max_entries=float("inf"), max_directories=float("inf"), max_seconds=float("inf")):
    """Read directory metadata only. No content reads, deletion or permission changes.

    Result sizes are logical, not allocated bytes. Accessible links are resolved; directory identities prevent cycles.
    A cancelled/limited/inaccessible subtree is explicitly partial, never an exact zero.
    """
    roots = normalize_roots(roots)
    if not roots:
        raise ValueError('Choisissez au moins un disque ou dossier.')
    if max_directories < len(roots) + 1:
        raise ValueError('La limite de dossiers est trop faible pour les racines sélectionnées.')
    started, wall = time.monotonic(), time.time()
    nodes = [Node(0, '', 'Ce PC' if len(roots) > 1 else 'Analyse', None, scanned=True)]
    pending = deque()
    links = deque()
    visited = {}
    volumes = []
    for path in roots:
        n = Node(len(nodes), path, Path(path).name or path, 0)
        nodes.append(n)
        nodes[0].children.append(n.id)
        pending.append(n.id)
        try:
            usage = shutil.disk_usage(path)
            volumes.append({'root': path, 'total': usage.total, 'free': usage.free, 'used': usage.used})
        except OSError:
            pass
    entries = known_bytes = files = 0
    reason, errors = 'complete', []
    last_progress = 0.0
    live_bytes = Counter()
    buckets = {}
    for root_id in nodes[0].children:
        buckets[root_id] = root_id if len(roots)>1 else None
    extension_names = set()

    def extension(name):
        ext = Path(name).suffix.casefold() or '(sans extension)'
        if len(ext) > 20 or (ext not in extension_names and len(extension_names) >= 128):
            return '(autres extensions)'
        extension_names.add(ext)
        return ext

    def error(node, path, kind):
        node.errors += 1
        if len(errors) < 30:
            errors.append({'path': str(path), 'reason': kind})

    def boundary():
        if stop.is_set():
            return 'cancelled'
        if entries >= max_entries:
            return 'entry_limit'
        if time.monotonic() - started >= max_seconds:
            return 'time_limit'
        return ''

    while pending or links:
        limit = boundary()
        if limit:
            reason = limit
            break
        node = nodes[pending.popleft() if pending else links.popleft()]
        try:
            metadata = os.stat(node.path, follow_symlinks=True)
            identity = (metadata.st_dev, metadata.st_ino) if metadata.st_ino else os.path.normcase(os.path.realpath(node.path))
            if identity in visited:
                node.reference = visited[identity]
                node.excluded = 'Même dossier que : ' + nodes[node.reference].path + ' · taille affichée, non recomptée'
                node.scanned = True
                continue
            visited[identity] = node.id
            if not stat.S_ISDIR(metadata.st_mode):
                error(node, node.path, 'Ce chemin n’est pas un dossier')
                continue
            with os.scandir(node.path) as directory:
                interrupted = False
                for entry in directory:
                    limit = boundary()
                    if limit:
                        reason, interrupted = limit, True
                        break
                    entries += 1
                    try:
                        info = entry.stat(follow_symlinks=False)
                        linked = stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)
                        if linked:
                            info = entry.stat(follow_symlinks=True)
                        if stat.S_ISDIR(info.st_mode):
                            if len(nodes) >= max_directories:
                                reason, interrupted = 'directory_limit', True
                                break
                            child = Node(len(nodes), entry.path, entry.name, node.id)
                            nodes.append(child)
                            node.children.append(child.id)
                            buckets[child.id] = child.id if node.parent == 0 and len(roots)==1 else buckets.get(node.id)
                            (links if linked else pending).append(child.id)
                        elif stat.S_ISREG(info.st_mode):
                            size = max(0, info.st_size)
                            ext = extension(entry.name)
                            node.direct_bytes += size
                            node.direct_files += 1
                            node.direct_extensions[ext] += size
                            node.extension_counts[ext] += 1
                            known_bytes += size
                            bucket = buckets.get(node.id)
                            if bucket is not None: live_bytes[bucket] += size
                            files += 1
                            file = (size, entry.name, info.st_mtime)
                            if len(node.largest_files) < 12:
                                heapq.heappush(node.largest_files, file)
                            elif file > node.largest_files[0]:
                                heapq.heapreplace(node.largest_files, file)
                        else:
                            node.skipped += 1
                    except OSError as exc:
                        error(node, entry.path, type(exc).__name__ + ': ' + str(exc))
                    now = time.monotonic()
                    if progress and now - last_progress >= 0.25:
                        last_progress = now
                        progress({'files': files, 'directories': len(nodes)-1, 'bytes': known_bytes,
                                  'current': node.path, 'elapsed': now-started,
                                  'folders': [{'id': n.id, 'name': n.name, 'path': n.path,
                                               'bytes': live_bytes[n.id]} for n in
                                              (nodes[i] for i in (nodes[1].children if len(roots)==1 else nodes[0].children))]})
                node.scanned = not interrupted
                if interrupted:
                    break
        except OSError as exc:
            node.excluded = type(exc).__name__ + ': ' + str(exc)
            error(node, node.path, node.excluded)
    # Parent IDs precede descendants, making reverse aggregation non-recursive.
    for node in reversed(nodes):
        node.total_bytes = node.direct_bytes
        node.files = node.direct_files
        node.directories = len(node.children)
        node.extensions = node.direct_extensions.copy()
        node.complete = node.scanned and not node.errors and not node.skipped and (not node.excluded or node.reference is not None)
        node.largest_files.sort(reverse=True)
        for child_id in node.children:
            child = nodes[child_id]
            if child.reference is not None:
                continue
            node.total_bytes += child.total_bytes
            node.files += child.files
            node.directories += child.directories
            node.extensions.update(child.extensions)
            node.extension_counts.update(child.extension_counts)
            node.errors += child.errors
            node.skipped += child.skipped
            node.complete = node.complete and child.complete
    # References display their measured target without contributing a second time.
    for node in nodes:
        if node.reference is not None:
            target = nodes[node.reference]
            node.total_bytes, node.files, node.directories = target.total_bytes, target.files, target.directories
            node.complete = target.complete
    return ScanResult(nodes, wall, time.time(), reason, entries, errors, volumes)


def local_drives():
    if os.name != 'nt':
        return [str(Path.home())]
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetLogicalDriveStringsW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    kernel.GetLogicalDriveStringsW.restype = wintypes.DWORD
    kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel.GetDriveTypeW.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(512)
    if not kernel.GetLogicalDriveStringsW(len(buffer), buffer):
        return []
    return [p for p in buffer[:].split('\0') if p and kernel.GetDriveTypeW(p) == 3]
