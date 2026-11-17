# Patch Rapide — plug-in Vectorworks Spotlight

Patche en un clic les projecteurs sélectionnés : univers + adresse DMX calculés
à la suite, selon le nombre de canaux de chaque appareil.

## Fonctions

- **Patch rapide** (commande de menu)
  - Univers / adresse de départ, écart entre appareils
  - Ordre de patch : par perche (du lointain vers la face, puis jardin → cour),
    jardin → cour, lointain → face, n° d'unité, canal, ordre du document, avec une option pour inverser l'ordre
  - Empreinte lue dans le champ `Num Channels` (une valeur par défaut est utilisée si le champ est vide,
    ou peut être imposée à tous les appareils)
  - Ne coupe jamais un appareil entre deux univers (option)
  - Nouvel univers à chaque perche (option)
  - Numérotation des canaux en même temps (départ et incrément)
  - À la fin : résumé et **contrôle des conflits** d'adresse sur tout le document
- **Vérifier le patch** (commande de menu) : détecte les chevauchements d'adresses
  et sélectionne les projecteurs concernés, sans rien modifier.

Tout est annulable avec Cmd/Ctrl+Z.

## Installation (Vectorworks 2020 et suivants)

1. Copiez `PatchRapide.py` dans un dossier fixe, par exemple
   `~/Documents/VectorworksScripts/`.
2. *Outils › Plug-ins › Gestionnaire de plug-ins* › onglet *Plug-ins personnalisés* ›
   **Nouveau** › type **Commande de menu**, nom `Patch rapide`.
3. **Modifier le script…** › langage **Python** › collez :

   ```python
   import sys
   sys.path.append(r'/Users/VOUS/Documents/VectorworksScripts')  # dossier de PatchRapide.py
   import importlib, PatchRapide
   importlib.reload(PatchRapide)
   PatchRapide.run()
   ```

4. Recommencez avec une 2e commande `Vérifier le patch`, dont la dernière ligne est
   `PatchRapide.run_check()`.
5. *Outils › Espace de travail › Modifier l'espace de travail actuel* : glissez les deux
   commandes dans un menu (par exemple Spotlight) et assignez-leur un raccourci clavier.

## Utilisation

1. Sélectionnez les projecteurs à patcher (vous pouvez sélectionner toute une perche
   ou tout le plan).
2. Lancez **Patch rapide**, réglez les options, puis cliquez sur **Patcher**.

## Adapter à votre version

Si votre version de Vectorworks utilise d'autres noms de champs, modifiez les
constantes en haut de `PatchRapide.py` (`FIELD_ADDRESS`, `FIELD_FOOTPRINT`, …).
Pour voir les noms exacts, ouvrez la palette Info d'un projecteur, onglet Données,
ou lancez `vs.Message(vs.GetRField(h, 'Lighting Device', 'Dimmer'))`.

## Tests

La logique de calcul est indépendante de Vectorworks :

```bash
python3 -m pytest vectorworks/patch_rapide
```
