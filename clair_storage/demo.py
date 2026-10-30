"""Fictitious folder tree; no filesystem traversal or document read."""
import os
import time
from .scanner import Node, ScanResult

G = 1024**3


def example():
    nodes = [Node(0, '', 'Ce PC', None, scanned=True)]
    def add(name, parent, types=None):
        parent_node = nodes[parent]
        path = os.path.join(parent_node.path, name) if parent_node.path else name
        node = Node(len(nodes), path, name, parent, scanned=True)
        nodes.append(node)
        parent_node.children.append(node.id)
        for ext, amount in (types or {}).items():
            size = int(amount*G)
            node.direct_bytes += size
            node.direct_files += 120
            node.direct_extensions[ext] += size
            node.extension_counts[ext] += 120
            node.largest_files.append((size//3, 'exemple-fictif'+ext, time.time()))
        return node.id
    drive = add('C: (DÉMO)', 0, {'.sys': 8})
    users = add('Users', drive)
    user = add('Utilisateur démo', users)
    add('Vidéos', user, {'.mp4': 36, '.mkv': 18})
    add('Téléchargements', user, {'.iso': 8, '.zip': 5, '.pdf': 0.4})
    projects = add('Projets', user)
    surf = add('Surf_Project', projects)
    add('data', surf, {'.csv': 4.5, '.parquet': 2})
    add('.venv', surf, {'.pyd': 1, '.py': 0.3})
    add('node_modules', surf, {'.js': 1.4, '.map': 0.6, '.json': 0.2})
    add('Modèles locaux', user, {'.gguf': 14})
    add('Images', user, {'.jpg': 3, '.png': 1.5})
    windows = add('Windows', drive)
    add('System32', windows, {'.dll': 12, '.sys': 8})
    add('WinSxS', windows, {'.dll': 6})
    add('Logs', windows, {'.log': 0.6})
    protected = add('Dossier protégé (démo)', windows)
    nodes[protected].errors = 1
    nodes[protected].scanned = False
    programs = add('Program Files', drive)
    add('Jeux', programs, {'.pak': 42, '.bin': 18})
    add('Applications', programs, {'.exe': 1.5, '.dll': 2.5})
    for node in reversed(nodes):
        node.total_bytes = node.direct_bytes
        node.files = node.direct_files
        node.directories = len(node.children)
        node.extensions = node.direct_extensions.copy()
        node.complete = node.scanned and not node.errors
        node.largest_files.sort(reverse=True)
        for key in node.children:
            c = nodes[key]
            node.total_bytes += c.total_bytes
            node.files += c.files
            node.directories += c.directories
            node.errors += c.errors
            node.extensions.update(c.extensions)
            node.extension_counts.update(c.extension_counts)
            node.complete &= c.complete
    now = time.time()
    return ScanResult(nodes, now-30, now, 'complete', nodes[0].files+len(nodes),
                      [{'path': 'Dossier protégé fictif', 'reason': 'Accès refusé simulé'}],
                      [{'root': 'C: (DÉMO)', 'total': 512*G, 'used': 300*G, 'free': 212*G}], True)
