"""Bounded, read-only evidence for interpreting an indexed storage subtree."""
import hashlib
import heapq
import json
import os

MARKERS = {
    'package.json': 'manifeste de projet JavaScript/Node.js',
    'package-lock.json': 'verrouillage des dépendances npm',
    'pyproject.toml': 'configuration de projet Python',
    'requirements.txt': 'liste de dépendances Python',
    'docker-compose.yml': 'configuration de services Docker Compose',
    'compose.yaml': 'configuration de services Docker Compose',
    'dockerfile': 'recette de construction Docker',
    'cargo.toml': 'manifeste de projet Rust',
    'pom.xml': 'manifeste de projet Java/Maven',
    'go.mod': 'manifeste de projet Go',
    '.git': 'métadonnées de gestion de versions Git',
    'node_modules': 'dépendances Node.js installées',
    '.venv': 'environnement virtuel Python probable',
    'venv': 'environnement virtuel Python probable',
    '__pycache__': 'cache de bytecode Python',
}


def explore(result, node_id, include_files=True, stop=None, max_nodes=18, per_directory=2000):
    root=result.nodes[node_id]
    # Cover several immediate branches before following the heaviest descendants.
    selected=[root]
    children=sorted((result.nodes[i] for i in root.children),key=lambda n:n.total_bytes,reverse=True)
    selected.extend(n for n in children[:min(7,max(0,max_nodes-1))] if n.reference is None)
    seen={n.id for n in selected}
    pending=[(-n.total_bytes,n.id) for n in selected]
    heapq.heapify(pending)
    expanded=set()
    while pending and len(selected)<max_nodes:
        _,key=heapq.heappop(pending)
        if key in expanded:continue
        expanded.add(key)
        for i in sorted(result.nodes[key].children,key=lambda i:result.nodes[i].total_bytes,reverse=True):
            n=result.nodes[i]
            if n.reference is not None:continue
            heapq.heappush(pending,(-n.total_bytes,n.id))
            if i not in seen and len(selected)<max_nodes:
                seen.add(i);selected.append(n)
    records=[]
    for node in selected:
        if stop is not None and stop.is_set():
            from .ai import Cancelled
            raise Cancelled()
        relative='.' if node.id==node_id else os.path.relpath(node.path,root.path) if root.path else node.name
        record={'id':f'D{node.id}','path':relative[:350], 'name':node.name[:120],
                'bytes':node.total_bytes,'direct_bytes':node.direct_bytes,'files':node.files,
                'complete':node.complete,'errors':node.errors,
                'extensions':[{'name':ext,'bytes':size,'files':node.extension_counts[ext]}
                              for ext,size in node.extensions.most_common(6)],
                'children':[{'name':result.nodes[i].name[:100],'bytes':result.nodes[i].total_bytes,
                             'reference':result.nodes[i].reference is not None}
                            for i in sorted(node.children,key=lambda i:result.nodes[i].total_bytes,reverse=True)[:8]],
                'markers':[]}
        if include_files:
            record['largest_files']=[{'name':name[:120],'bytes':size} for size,name,_ in node.largest_files[:4]]
            if result.demo:
                record['name_sample_note']='Démonstration fictive ; aucun accès disque.'
            elif node.path:
                count=0; names=[];markers=[]
                try:
                    with os.scandir(node.path) as entries:
                        for entry in entries:
                            if stop is not None and stop.is_set():
                                from .ai import Cancelled
                                raise Cancelled()
                            count+=1
                            if count>per_directory:break
                            key=entry.name.casefold()
                            if key in MARKERS and len(markers)<12:
                                markers.append({'name':entry.name,'suggests':MARKERS[key]})
                            if len(names)<8:names.append(entry.name[:100])
                    record['markers']=markers
                    record['sample_names']=names
                    record['name_sample_note']=f'{min(count,per_directory)} noms examinés ; '+('échantillon limité' if count>per_directory else 'liste parcourue')
                except OSError as exc:
                    record['name_sample_note']='Lecture des noms indisponible : '+type(exc).__name__
        records.append(record)
    return {'folders':records,'selected_folder_name':root.name,'scope_note':
            'Métadonnées uniquement, jamais le contenu. Sélection de branches et sous-dossiers dominants ; pas un inventaire exhaustif transmis à l’IA.',
            'names_enabled':include_files,'folder_count':len(records),'indexed_folder_count':root.directories+1,
            'limited':len(records)<root.directories+1,
            'origin_note':'Le nom et les extensions suggèrent un usage, mais ne prouvent ni auteur, ni date d’installation, ni application d’origine.'}


def attach(snapshot, exploration):
    enriched=dict(snapshot,exploration=exploration)
    enriched['snapshot_id']=hashlib.sha256(json.dumps(enriched,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    return enriched


def batches(exploration):
    # Short contexts keep multi-pass analysis feasible on a local 8B model.
    result=[];current=[]
    for record in exploration['folders']:
        if current and (len(current)>=6 or len(json.dumps(current+[record],ensure_ascii=False))>7200):
            result.append(current);current=[]
        current.append(record)
    if current:result.append(current)
    return result
