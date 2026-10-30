# Validation et limites

Ce document est destiné aux mainteneurs. Il décrit ce que les tests vérifient et ce qui reste à contrôler avant une diffusion publique ; il ne constitue ni une certification ni une garantie d’exhaustivité.

## Tests automatisés

Lancer la suite depuis la racine du dépôt :

```powershell
py -3.12 -m unittest discover -s tests -v
```

La suite utilise la bibliothèque standard de Python et ne nécessite ni paquet tiers ni modèle Ollama. Elle couvre notamment :

- le calcul des tailles, les extensions, les pourcentages et leur propagation dans l’arborescence ;
- les erreurs d’accès, les mesures partielles, l’annulation et les liens de dossiers ;
- la navigation et le tri des éléments, sans ouverture du contenu des fichiers ;
- l’exploration bornée des noms et marqueurs, la désactivation de l’échantillonnage des noms et l’annulation ;
- les échanges avec un serveur HTTP local simulé pour Ollama, y compris les erreurs et les réponses incomplètes.

**Dernière exécution enregistrée :** 71 tests réussis le 30 octobre 2026 avec Python 3.14.7 (`python -B -m unittest discover -s tests -v`). Cet interpréteur n’est pas celui indiqué comme prérequis dans le lanceur ; cette exécution ne certifie donc pas la compatibilité avec Python 3.11 ou 3.12.

## Ce que les tests ne valident pas

- La qualité, la justesse ou les niveaux de confiance des interprétations produites par un vrai modèle.
- Le fonctionnement avec une installation réelle d’Ollama, un modèle donné, un GPU ou une configuration matérielle particulière. Les tests réseau utilisent des réponses simulées.
- L’affichage Tk natif, les différentes configurations Windows, la demande UAC et les cas réels de permissions NTFS.
- La durée, la mémoire et l’exhaustivité d’un scan sur un volume utilisateur complet ou en évolution.
- Le fait qu’une taille logique corresponde à l’espace physique réellement occupé sur le disque.

## Contrôles manuels recommandés avant publication

- Lancer `Launch-Admin.cmd`, accepter puis annuler la demande UAC, et vérifier que les deux parcours donnent un résultat compréhensible.
- Essayer la commande de démonstration du [README](../README.md) et confirmer qu’elle ne parcourt aucun disque.
- Tester un dossier accessible, un dossier protégé, un scan interrompu et un volume contenant des liens ou jonctions, puis contrôler les indicateurs de couverture.
- Si Ollama est présenté comme fonction disponible, tester une instance locale avec un modèle local et vérifier l’inspection des données envoyées, l’option d’exclusion des noms individuels et l’export JSON.
- Avant toute publication publique, ajouter une licence choisie par le propriétaire du projet ; la visibilité publique seule ne définit pas les droits de réutilisation.
