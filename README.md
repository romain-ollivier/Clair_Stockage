# Clair Stockage

Explorateur visuel de stockage local pour Windows — **version 0.6.0**.

**Comprendre ce qui occupe l’espace sur son PC, sans ouvrir ses fichiers ni rien supprimer.**

Clair Stockage est un explorateur de stockage local pour Windows. Il parcourt les dossiers choisis, calcule leur taille et présente les résultats sous forme de liste ou de carte visuelle. Son objectif : aider à comprendre où se trouve l’espace utilisé, tout en distinguant les mesures réelles des estimations et des interprétations.

## Ce que l’application apporte

- **Voir le stockage par dossier** : comparer les tailles, les extensions et les fichiers, puis naviguer dans l’arborescence.
- **Repérer les éléments volumineux** : la liste et la carte colorée rendent les gros dossiers plus faciles à identifier.
- **Garder le contrôle** : aucun scan ne démarre à l’ouverture. Choisissez un disque ou un dossier, suivez le parcours et arrêtez-le si nécessaire.
- **Comprendre la couverture** : les erreurs d’accès et les scans interrompus sont signalés ; les tailles partielles ne sont pas présentées comme des mesures complètes.
- **Obtenir une explication facultative** : un bilan local peut interpréter les métadonnées et expliquer les indices observés, sans remplacer les mesures.

Clair Stockage est un outil d’exploration et de compréhension, **pas un nettoyeur** : il ne supprime, ne déplace et ne modifie aucun fichier.

## Essayer la démonstration

Pour découvrir l’interface sans analyser le disque :

Depuis la racine du dépôt, lancez :

```powershell
py -3.12 -m clair_storage --demo
```

Cette démonstration utilise une arborescence entièrement fictive ; elle n’analyse aucun disque.

## Installation et lancement

### Prérequis

- Windows
- Python 3.11 ou 3.12 avec Tcl/Tk (inclus dans l’installation Windows standard de Python)
- Aucun paquet Python supplémentaire n’est nécessaire

### Démarrer l’application

Téléchargez ou clonez le dépôt, puis lancez `Launch-Admin.cmd` et confirmez la demande UAC de Windows. L’application s’ouvre sans démarrer de scan ; choisissez ensuite un disque, votre dossier personnel ou **Choisir un dossier**. Ce lancement demande les droits administrateur afin d’élargir l’accès aux dossiers protégés ; les accès refusés restent possibles.

Vous pouvez également la lancer depuis la racine du dépôt :

```powershell
py -3.12 -m clair_storage
```

Pour exécuter manuellement l’application sans élévation depuis PowerShell, utilisez la commande ci-dessus. L’accès à certains dossiers sera alors limité par les permissions de votre compte. Dans les deux cas, aucune permission ni propriété de fichier n’est modifiée.

## Explorer son stockage

- **Liste** : trier les éléments par nom ou par taille, les rechercher dans le dossier courant et naviguer par double-clic.
- **Carte** : visualiser les éléments proportionnellement à leur taille ; les couleurs indiquent une tranche de taille, pas un niveau de danger.
- **Accès et couverture** : consulter les erreurs, les éléments ignorés et savoir si les résultats sont partiels.
- **Arrêter le scan** : demander l’arrêt et conserver les résultats disponibles comme mesures partielles.

Le parcours complet n’a pas de limite automatique de durée ou de nombre d’éléments ; sur un grand volume, il peut donc prendre du temps et utiliser de la mémoire.

## Bilan IA local (facultatif)

Le bilan mesuré fonctionne sans IA. Pour demander une interprétation, installez [Ollama](https://ollama.com/) séparément et téléchargez un modèle local, par exemple :

```powershell
ollama pull qwen3:8b
```

Ouvrez **Bilan IA**, testez la connexion à Ollama, choisissez un modèle disponible puis lancez **Analyser ce dossier**. L’application utilise une instance Ollama locale ; elle ne télécharge pas de logiciel ou de modèle à votre place.

Le bilan IA :

- s’appuie sur des métadonnées, des noms et des indices techniques, jamais sur le contenu des fichiers ;
- examine un échantillon limité de dossiers, pas l’ensemble de l’arborescence ;
- distingue les constats mesurés des interprétations générées, qui restent à vérifier ;
- n’exécute aucune action sur les fichiers.

L’option d’inclusion des noms de fichiers et marqueurs techniques est activée par défaut. La désactiver retire les noms de fichiers individuels et la recherche de marqueurs, mais conserve les noms de dossiers. **Voir les données envoyées** permet d’inspecter les métadonnées préparées pour le bilan ; **Exporter le bilan** enregistre un fichier JSON qui peut contenir ces métadonnées et les notes intermédiaires de l’IA.

## Confidentialité et limites des mesures

- Le scanner lit les métadonnées nécessaires au calcul (noms, tailles et informations de dossiers) ; il n’ouvre pas le contenu des fichiers.
- Les noms de fichiers individuels et les marqueurs techniques ne sont transmis à Ollama local que si l’option correspondante est activée et si vous demandez un bilan IA. Les noms de dossiers et les autres métadonnées utiles au bilan restent inclus.
- Les tailles affichées sont des **tailles logiques** : elles peuvent différer de l’espace réellement occupé sur le disque. Les liens accessibles sont suivis ; une cible externe peut contribuer au total logique, et les liens physiques de fichiers ne sont pas dédupliqués.
- Les dossiers inaccessibles, les erreurs système et l’arrêt d’un scan peuvent rendre les résultats partiels. Lancer l’application en administrateur peut élargir l’accès, sans garantir l’exhaustivité.
- Les résultats représentent l’état observé pendant le scan ; les fichiers peuvent changer entre-temps.

## Tests

Les tests automatisés utilisent la bibliothèque standard de Python :

```powershell
py -3.12 -m unittest discover -s tests -v
```

Le détail de leur couverture et les vérifications manuelles restant à effectuer sont indiqués dans [docs/VALIDATION.md](./docs/VALIDATION.md).

## Licence

Aucun fichier de licence n’est inclus pour le moment. La publication d’un dépôt public sur GitHub ne place pas automatiquement son code sous une licence open source : ajoutez une licence avant d’autoriser sa réutilisation.
