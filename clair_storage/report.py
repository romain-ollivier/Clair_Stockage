from __future__ import annotations

import hashlib
import heapq
import json
import os
import re

from .layout import size_text


def describe(result, node_id, include_files=False, max_nodes=12):
    """Bounded hierarchy, not document contents. All quantities come from the scan."""
    node = result.nodes[node_id]
    records = []
    pending = [(-node.total_bytes, node.id)]
    while pending and len(records) < max_nodes:
        _, key = heapq.heappop(pending)
        item = result.nodes[key]
        relative = '.' if key == node_id else os.path.relpath(item.path, node.path) if node.path else item.name
        if not node.path and key != node_id:
            drive = item
            while drive.parent not in (None, 0):
                drive = result.nodes[drive.parent]
            relative = drive.name if item.id == drive.id else os.path.join(drive.name, os.path.relpath(item.path, drive.path))
        types = [{'extension': ext, 'bytes': amount, 'files': item.extension_counts[ext]}
                 for ext, amount in item.extensions.most_common(5)]
        record = {'id': f'D{key}', 'parent_id': f'D{item.parent}' if item.parent is not None and key != node_id else None,
                  'folder': 'Dossier sélectionné' if key == node_id else relative,
                  'bytes': item.total_bytes, 'files': item.files, 'direct_bytes': item.direct_bytes,
                  'directories': item.directories, 'complete': item.complete, 'errors': item.errors,
                  'skipped': item.skipped, 'top_extensions': types}
        if include_files:
            record['largest_direct_files'] = [{'name': name, 'bytes': size} for size, name, _ in item.largest_files[:3]]
        records.append(record)
        for child in item.children:
            heapq.heappush(pending, (-result.nodes[child].total_bytes, child))
    data = {'scope': 'Sous-arbre sélectionné, tailles logiques, métadonnées seulement',
            'demo': result.demo, 'scan_finished_at': result.finished_at, 'scan_reason': result.reason,
            'hierarchy_note': 'Les totaux parent/enfant se recouvrent ; ne pas les additionner.',
            'limits': ['Accès refusés ou lectures impossibles : données partielles possibles ; références de dossiers non recomptées.',
                       'Extensions de noms, pas inspection du contenu.',
                       'Tailles logiques : compression, fichiers cloud et liens physiques peuvent différer de l’espace alloué.',
                       'La taille ne prouve ni inutilité ni possibilité de suppression.'],
            'file_names_included': include_files, 'folders': records,
            'folders_in_selection': node.directories+1}
    # Keep prompts small enough for an 8B model; omitted hierarchy stays navigable in UI.
    while len(json.dumps(data, ensure_ascii=False)) > 9500 and len(data['folders']) > 1:
        data['folders'].pop()
    data['summary_limited'] = len(data['folders']) < data['folders_in_selection']
    data['snapshot_id'] = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return data


def factual_report(snapshot):
    lines = ['BILAN MESURÉ · données fictives' if snapshot['demo'] else 'BILAN MESURÉ · métadonnées locales',
             f"Instantané {snapshot['snapshot_id']} · {len(snapshot['folders'])} dossiers résumés.",
             'Tailles logiques recensées ; les totaux parent/enfant ne doivent pas être additionnés.']
    for folder in snapshot['folders'][:8]:
        qualifier = '' if folder['complete'] else 'AU MOINS · PARTIEL · '
        lines.extend([f"\n[{folder['id']}] {folder['folder']}",
                      f"{qualifier}{size_text(folder['bytes'])} · {folder['files']:,} fichiers recensés · {folder['directories']:,} sous-dossiers.",
                      f"Fichiers directement dans ce dossier : {size_text(folder['direct_bytes'])}."])
        if folder['bytes']:
            lines.append('Principales extensions : ' + '; '.join(
                f"{t['extension']} : {size_text(t['bytes'])} ({100*t['bytes']/folder['bytes']:.0f} %)" for t in folder['top_extensions']) + '.')
        if folder['errors'] or folder['skipped']:
            lines.append(f"{folder['errors']} accès/lectures en erreur ; {folder['skipped']} liens ou éléments exclus.")
    if snapshot['summary_limited']:
        lines.append('\nRésumé limité aux dossiers dominants. Naviguer dans une branche pour obtenir son bilan détaillé.')
    lines.append('\nAucun contenu de fichier lu. Aucun nettoyage proposé automatiquement et aucune suppression possible depuis l’application.')
    return '\n'.join(lines)


def response_schema(snapshot):
    return {'type': 'object', 'additionalProperties': False,
            'properties': {'snapshot_id': {'type': 'string', 'const': snapshot['snapshot_id']},
                           'folders': {'type': 'array', 'maxItems': 4, 'items': {
                               'type': 'object', 'additionalProperties': False,
                               'properties': {'id': {'type': 'string', 'enum': [r['id'] for r in snapshot['folders']]},
                                              'hypothesis': {'type': 'string', 'maxLength': 450},
                                              'manual_check': {'type': 'string', 'maxLength': 350}},
                               'required': ['id', 'hypothesis', 'manual_check']}}},
            'required': ['snapshot_id', 'folders']}


def validate_response(raw, snapshot):
    output = {'valid': False, 'accepted': [], 'rejected': 0}
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError('duplicate key')
            obj[k] = v
        return obj
    try:
        if not isinstance(raw, str) or len(raw) > 12000:
            raise ValueError('size')
        value = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != {'snapshot_id', 'folders'} or value['snapshot_id'] != snapshot['snapshot_id']:
            raise ValueError('snapshot')
        if not isinstance(value['folders'], list) or len(value['folders']) > 4:
            raise ValueError('folders')
    except (ValueError, TypeError, RecursionError):
        output['rejected'] = 1
        return output
    output['valid'] = True
    allowed, seen = {f['id'] for f in snapshot['folders']}, set()
    known_formats = {t['extension'].lstrip('.') for f in snapshot['folders'] for t in f['top_extensions'] if any(c.isdigit() for c in t['extension'])}
    forbidden = re.compile(r'```|\b(remove-item|rmdir|format|powershell|cmd\.exe|supprim\w*|effac\w*|désactiv\w*)\b', re.I)
    for item in value['folders']:
        if not isinstance(item, dict) or set(item) != {'id', 'hypothesis', 'manual_check'}:
            output['rejected'] += 1
            continue
        key = item['id']
        fields = (item['hypothesis'], item['manual_check'])
        if (not isinstance(key, str) or key not in allowed or key in seen or
                not all(isinstance(t, str) and t.strip() and len(t) <= 500 for t in fields)):
            output['rejected'] += 1
            continue
        # Numerical facts are displayed only by the scanner, not re-generated by AI.
        def unsupported_digits(text):
            for token in known_formats:
                text = re.sub(r'(?<!\w)' + re.escape(token) + r'(?!\w)', '', text, flags=re.I)
            return re.search(r'\d', text)
        if any(unsupported_digits(t) or forbidden.search(t) or any(ord(c) < 32 and c not in '\n\t' for c in t) for t in fields):
            output['rejected'] += 1
            continue
        seen.add(key)
        output['accepted'].append(item)
    return output


def ai_report(snapshot, validation):
    lines = [factual_report(snapshot), '\n\nINTERPRÉTATION IA · HYPOTHÈSES NON VÉRIFIÉES']
    if not validation['valid']:
        lines.append('Réponse non conforme : seul le bilan mesuré est conservé.')
    folders = {f['id']: f for f in snapshot['folders']}
    for item in validation['accepted']:
        lines.extend([f"\n[{item['id']}] {folders[item['id']]['folder']}",
                      'Hypothèse : ' + item['hypothesis'], 'Vérification manuelle : ' + item['manual_check']])
    if validation['rejected']:
        lines.append(f"\n{validation['rejected']} élément(s) non conforme(s) écarté(s).")
    lines.append('\nLes références et la structure sont contrôlées ; la justesse des hypothèses du modèle n’est pas garantie. Aucune action système disponible.')
    return '\n'.join(lines)
