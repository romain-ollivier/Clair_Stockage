"""Read-only, on-demand folder listing and navigation state."""
from __future__ import annotations
import os
import stat
from dataclasses import dataclass


@dataclass
class Entry:
    key: str
    name: str
    size: int | None
    kind: str
    path: str
    node_id: int | None = None
    complete: bool = True
    reason: str = ""
    counted: bool = True


def folders(result, node_id):
    return [Entry('d'+str(i), result.nodes[i].name, (result.nodes[i].total_bytes if result.nodes[i].scanned or result.nodes[i].total_bytes else None),
                  'folder', result.nodes[i].path, i, result.nodes[i].complete, result.nodes[i].excluded, result.nodes[i].reference is None)
            for i in result.nodes[node_id].children]


def list_directory(result, node_id, stop, limit=float("inf")):
    node = result.nodes[node_id]
    entries = folders(result, node_id)
    known = {os.path.normcase(e.path) for e in entries}
    if result.demo:
        for index, (size, name, _) in enumerate(node.largest_files):
            entries.append(Entry('f'+str(index), name, size, 'file', os.path.join(node.path, name)))
        return entries, 'Démonstration : les fichiers individuels sont un extrait fictif.'
    if not node.path:
        return entries, ''
    note, count = '', 0
    try:
        with os.scandir(node.path) as directory:
            for item in directory:
                if stop.is_set():
                    return entries, 'Chargement interrompu.'
                count += 1
                if count > limit:
                    note = f'Liste limitée à {limit:,} entrées ; affiner la racine pour explorer davantage.'
                    break
                try:
                    info = item.stat(follow_symlinks=False)
                    if os.path.normcase(item.path) in known:
                        continue
                    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                        info = item.stat(follow_symlinks=True)
                    if stat.S_ISREG(info.st_mode):
                        entries.append(Entry('f'+item.name, item.name, max(0, info.st_size), 'file', item.path))
                    elif stat.S_ISDIR(info.st_mode) and os.path.normcase(item.path) not in known:
                        entries.append(Entry('new'+item.name, item.name, None, 'folder', item.path, complete=False))
                except OSError as exc:
                    entries.append(Entry('e'+item.name, item.name, None, 'unknown', item.path, complete=False, reason=type(exc).__name__+': '+str(exc)))
    except OSError as exc:
        note = 'Accès aux fichiers directs indisponible : ' + type(exc).__name__ + '.'
    return entries, note


class Navigation:
    def __init__(self, initial=0):
        self.history = [initial]
        self.position = 0

    @property
    def current(self):
        return self.history[self.position]

    def visit(self, node_id):
        if node_id != self.current:
            self.history = self.history[:self.position+1]+[node_id]
            self.position += 1
        return self.current

    def back(self):
        self.position = max(0, self.position-1)
        return self.current

    def forward(self):
        self.position = min(len(self.history)-1, self.position+1)
        return self.current


def sorted_entries(entries, query='', by='size', descending=True):
    filtered = [e for e in entries if query.casefold() in e.name.casefold()]
    # Explorer convention: folders first; sort independently inside each kind.
    groups = ([e for e in filtered if e.kind == 'folder'], [e for e in filtered if e.kind != 'folder'])
    out = []
    for group in groups:
        known = [e for e in group if e.size is not None]
        unknown = [e for e in group if e.size is None]
        if by == 'name':
            out.extend(sorted(group, key=lambda e:e.name.casefold(), reverse=descending))
        else:
            out.extend(sorted(known, key=lambda e:(e.size,e.name.casefold()), reverse=descending))
            out.extend(sorted(unknown,key=lambda e:e.name.casefold()))
    return out
