# -*- coding: utf-8 -*-
"""
Patch Rapide - plug-in Vectorworks Spotlight
=============================================

Patche en un clic les projecteurs (objets « Lighting Device ») sélectionnés :
univers + adresse DMX calculés à la suite en tenant compte de l'empreinte
(nombre de canaux) de chaque appareil, avec tri automatique (par perche,
jardin → cour, lointain → face, n° d'unité, canal…), et contrôle des
conflits d'adresses sur tout le document.

Le fichier est découpé en deux parties :
  1. Logique pure (aucune dépendance à Vectorworks) -> testable hors VW.
  2. Interface Vectorworks (module `vs`), utilisée seulement par `run()`.
"""

import re

# ---------------------------------------------------------------------------
# Configuration : noms des champs de l'objet « Lighting Device »
# (à adapter si votre version de Vectorworks utilise d'autres noms)
# ---------------------------------------------------------------------------
LD_RECORD = 'Lighting Device'
FIELD_UNIVERSE = 'Universe'
FIELD_ADDRESS = 'Dimmer'          # affiché « Adresse » dans la palette Info
FIELD_FOOTPRINT = 'Num Channels'  # nombre de canaux DMX de l'appareil
FIELD_CHANNEL = 'Channel'
FIELD_UNIT = 'Unit Number'
FIELD_POSITION = 'Position'

UNIVERSE_SIZE = 512

SORT_MODES = [
    'Par perche, puis jardin → cour',
    'Jardin → cour, puis lointain → face',
    'Lointain → face, puis jardin → cour',
    "Par n° d'unité",
    'Par canal',
    'Ordre du document',
]
SORT_POSITION, SORT_X, SORT_Y, SORT_UNIT, SORT_CHANNEL, SORT_DOC = range(6)


# ===========================================================================
# 1. LOGIQUE PURE
# ===========================================================================
class Fixture(object):
    """Représentation minimale d'un projecteur pour le calcul du patch."""

    def __init__(self, ref, x=0.0, y=0.0, position='', unit='', channel='',
                 footprint=0, universe=None, address=None, order=0):
        self.ref = ref              # handle Vectorworks ou identifiant
        self.x = x
        self.y = y
        self.position = position or ''
        self.unit = unit or ''
        self.channel = channel or ''
        self.footprint = footprint
        self.universe = universe
        self.address = address
        self.order = order          # ordre d'origine dans le document

    def __repr__(self):
        return 'Fixture(%r, U%s.%s)' % (self.ref, self.universe, self.address)


class PatchOptions(object):
    def __init__(self, start_universe=1, start_address=1, gap=0,
                 sort_mode=SORT_POSITION, reverse=False, default_footprint=1,
                 force_default_footprint=False, no_split=True,
                 new_universe_per_position=False, number_channels=False,
                 start_channel=1, channel_step=1, row_tolerance=0.5):
        self.start_universe = start_universe
        self.start_address = start_address
        self.gap = gap
        self.sort_mode = sort_mode
        self.reverse = reverse
        self.default_footprint = default_footprint
        self.force_default_footprint = force_default_footprint
        self.no_split = no_split
        self.new_universe_per_position = new_universe_per_position
        self.number_channels = number_channels
        self.start_channel = start_channel
        self.channel_step = channel_step
        self.row_tolerance = row_tolerance   # tolérance d'alignement (unités doc)


class PatchError(Exception):
    pass


def natural_key(value):
    """Clé de tri « naturel » : '2' < '10', 'A2' < 'A10'."""
    parts = re.split(r'(\d+)', str(value).strip().lower())
    return [(0, int(p)) if p.isdigit() else (1, p) for p in parts if p != '']


def parse_int(value, default=0):
    try:
        return int(float(str(value).strip().replace(',', '.')))
    except (TypeError, ValueError):
        return default


def _rows(fixtures, key, tolerance):
    """Regroupe en rangées les objets dont `key` diffère de moins de tolerance."""
    rows = []
    for f in sorted(fixtures, key=key):
        if rows and abs(key(f) - key(rows[-1][0])) <= tolerance:
            rows[-1].append(f)
        else:
            rows.append([f])
    return rows


def sort_fixtures(fixtures, options):
    mode = options.sort_mode
    tol = options.row_tolerance

    if mode == SORT_POSITION:
        groups = {}
        for f in fixtures:
            groups.setdefault(f.position, []).append(f)
        # perches ordonnées du lointain (Y élevé) vers la face
        ordered = sorted(groups.values(),
                         key=lambda g: (-sum(f.y for f in g) / len(g),
                                        natural_key(g[0].position)))
        result = []
        for g in ordered:
            result.extend(sorted(g, key=lambda f: (f.x, natural_key(f.unit))))
    elif mode == SORT_X:
        result = []
        for col in _rows(fixtures, lambda f: f.x, tol):
            result.extend(sorted(col, key=lambda f: -f.y))
    elif mode == SORT_Y:
        result = []
        for row in reversed(_rows(fixtures, lambda f: f.y, tol)):
            result.extend(sorted(row, key=lambda f: f.x))
    elif mode == SORT_UNIT:
        result = sorted(fixtures, key=lambda f: (natural_key(f.position),
                                                 natural_key(f.unit)))
    elif mode == SORT_CHANNEL:
        result = sorted(fixtures, key=lambda f: natural_key(f.channel))
    else:
        result = sorted(fixtures, key=lambda f: f.order)

    if options.reverse:
        result.reverse()
    return result


def compute_patch(fixtures, options):
    """Calcule univers/adresse (et canal) pour chaque projecteur.

    Retourne la liste triée des projecteurs avec .universe/.address/.channel
    mis à jour. Ne modifie rien dans Vectorworks.
    """
    if not 1 <= options.start_address <= UNIVERSE_SIZE:
        raise PatchError("L'adresse de départ doit être comprise entre 1 et %d."
                         % UNIVERSE_SIZE)
    if options.start_universe < 1:
        raise PatchError("L'univers de départ doit être ≥ 1.")
    if options.gap < 0:
        raise PatchError("L'écart entre appareils ne peut pas être négatif.")

    ordered = sort_fixtures(fixtures, options)
    universe = options.start_universe
    address = options.start_address
    channel = options.start_channel
    previous_position = None

    for f in ordered:
        fp = f.footprint
        if options.force_default_footprint or not fp or fp < 1:
            fp = options.default_footprint
        if fp > UNIVERSE_SIZE:
            raise PatchError("Un appareil a une empreinte de %d canaux (> %d)."
                             % (fp, UNIVERSE_SIZE))
        f.footprint = fp

        if (options.new_universe_per_position and previous_position is not None
                and f.position != previous_position and address != 1):
            universe += 1
            address = 1
        previous_position = f.position

        if address > UNIVERSE_SIZE or (
                options.no_split and address + fp - 1 > UNIVERSE_SIZE):
            universe += 1
            address = 1

        f.universe = universe
        f.address = address
        address += fp + options.gap

        if options.number_channels:
            f.channel = str(channel)
            channel += options.channel_step

    return ordered


def absolute_range(universe, address, footprint):
    start = (universe - 1) * UNIVERSE_SIZE + address
    return start, start + max(footprint, 1) - 1


def find_conflicts(fixtures):
    """Retourne les paires de projecteurs dont les plages DMX se chevauchent.

    Les projecteurs sans univers/adresse sont ignorés.
    """
    spans = []
    for f in fixtures:
        if not f.universe or not f.address:
            continue
        start, end = absolute_range(f.universe, f.address, f.footprint)
        spans.append((start, end, f))
    spans.sort(key=lambda s: s[0])

    conflicts = []
    active = []
    for start, end, f in spans:
        active = [a for a in active if a[1] >= start]
        for a in active:
            conflicts.append((a[2], f))
        active.append((start, end, f))
    return conflicts


def format_address(universe, address):
    return '%d.%03d' % (universe, address)


# ===========================================================================
# 2. INTERFACE VECTORWORKS
# ===========================================================================
SETUP_EVENT = 12255
OK_BUTTON = 1


def _collect(vs, only_selected):
    criteria = "(PON='%s')" % LD_RECORD
    if only_selected:
        criteria = "((PON='%s') & (SEL=TRUE))" % LD_RECORD
    fixtures = []

    def visit(h):
        get = lambda field: vs.GetRField(h, LD_RECORD, field)
        try:
            x, y = vs.GetSymLoc(h)
        except Exception:
            x, y = 0.0, 0.0
        fixtures.append(Fixture(
            ref=h, x=x, y=y,
            position=get(FIELD_POSITION),
            unit=get(FIELD_UNIT),
            channel=get(FIELD_CHANNEL),
            footprint=parse_int(get(FIELD_FOOTPRINT), 0),
            universe=parse_int(get(FIELD_UNIVERSE), 0) or None,
            address=parse_int(get(FIELD_ADDRESS), 0) or None,
            order=len(fixtures)))

    vs.ForEachObject(visit, criteria)
    return fixtures


def _ask_options(vs):
    """Affiche la boîte de dialogue. Retourne PatchOptions ou None."""
    d = vs.CreateLayout('Patch rapide', True, 'Patcher', 'Annuler')

    # identifiants des contrôles
    L_U, E_U, L_A, E_A, L_GAP, E_GAP = 10, 11, 12, 13, 14, 15
    L_SORT, P_SORT, C_REV = 20, 21, 22
    L_FP, E_FP, C_FORCE = 30, 31, 32
    C_SPLIT, C_NEWU = 40, 41
    C_CH, L_CH, E_CH, L_STEP, E_STEP = 50, 51, 52, 53, 54

    vs.CreateStaticText(d, L_U, 'Univers de départ :', 24)
    vs.CreateEditInteger(d, E_U, 1, 6)
    vs.CreateStaticText(d, L_A, 'Adresse de départ :', 24)
    vs.CreateEditInteger(d, E_A, 1, 6)
    vs.CreateStaticText(d, L_GAP, 'Écart entre appareils :', 24)
    vs.CreateEditInteger(d, E_GAP, 0, 6)

    vs.CreateStaticText(d, L_SORT, 'Ordre de patch :', 24)
    vs.CreatePullDownMenu(d, P_SORT, 34)
    vs.CreateCheckBox(d, C_REV, "Inverser l'ordre")

    vs.CreateStaticText(d, L_FP, 'Empreinte par défaut :', 24)
    vs.CreateEditInteger(d, E_FP, 1, 6)
    vs.CreateCheckBox(d, C_FORCE, 'Forcer pour tous les appareils')

    vs.CreateCheckBox(d, C_SPLIT, "Ne jamais couper un appareil entre deux univers")
    vs.CreateCheckBox(d, C_NEWU, 'Nouvel univers à chaque perche')

    vs.CreateCheckBox(d, C_CH, 'Numéroter aussi les canaux')
    vs.CreateStaticText(d, L_CH, 'Canal de départ :', 24)
    vs.CreateEditInteger(d, E_CH, 1, 6)
    vs.CreateStaticText(d, L_STEP, 'Incrément :', 24)
    vs.CreateEditInteger(d, E_STEP, 1, 6)

    vs.SetFirstLayoutItem(d, L_U)
    vs.SetRightItem(d, L_U, E_U, 0, 0)
    vs.SetBelowItem(d, L_U, L_A, 0, 0)
    vs.SetRightItem(d, L_A, E_A, 0, 0)
    vs.SetBelowItem(d, L_A, L_GAP, 0, 0)
    vs.SetRightItem(d, L_GAP, E_GAP, 0, 0)
    vs.SetBelowItem(d, L_GAP, L_SORT, 0, 1)
    vs.SetRightItem(d, L_SORT, P_SORT, 0, 0)
    vs.SetBelowItem(d, L_SORT, C_REV, 0, 0)
    vs.SetBelowItem(d, C_REV, L_FP, 0, 1)
    vs.SetRightItem(d, L_FP, E_FP, 0, 0)
    vs.SetBelowItem(d, L_FP, C_FORCE, 0, 0)
    vs.SetBelowItem(d, C_FORCE, C_SPLIT, 0, 1)
    vs.SetBelowItem(d, C_SPLIT, C_NEWU, 0, 0)
    vs.SetBelowItem(d, C_NEWU, C_CH, 0, 1)
    vs.SetBelowItem(d, C_CH, L_CH, 0, 0)
    vs.SetRightItem(d, L_CH, E_CH, 0, 0)
    vs.SetBelowItem(d, L_CH, L_STEP, 0, 0)
    vs.SetRightItem(d, L_STEP, E_STEP, 0, 0)

    vs.SetHelpText(d, E_GAP, "Nombre d'adresses laissées libres entre deux appareils.")
    vs.SetHelpText(d, E_FP, "Utilisée quand le champ « Num Channels » de l'appareil est vide.")

    result = {}

    def handler(item, data):
        if item == SETUP_EVENT:
            for i, label in enumerate(SORT_MODES):
                vs.AddChoice(d, P_SORT, label, i)
            vs.SelectChoice(d, P_SORT, 0, True)
            vs.SetBooleanItem(d, C_SPLIT, True)
            for ctl in (L_CH, E_CH, L_STEP, E_STEP):
                vs.EnableItem(d, ctl, False)
        elif item == C_CH:
            on = vs.GetBooleanItem(d, C_CH)
            for ctl in (L_CH, E_CH, L_STEP, E_STEP):
                vs.EnableItem(d, ctl, on)
        elif item == OK_BUTTON:
            ival = lambda ctl: vs.GetEditInteger(d, ctl)[1]
            result['options'] = PatchOptions(
                start_universe=ival(E_U),
                start_address=ival(E_A),
                gap=ival(E_GAP),
                sort_mode=vs.GetSelectedChoiceInfo(d, P_SORT, 0)[0],
                reverse=vs.GetBooleanItem(d, C_REV),
                default_footprint=max(1, ival(E_FP)),
                force_default_footprint=vs.GetBooleanItem(d, C_FORCE),
                no_split=vs.GetBooleanItem(d, C_SPLIT),
                new_universe_per_position=vs.GetBooleanItem(d, C_NEWU),
                number_channels=vs.GetBooleanItem(d, C_CH),
                start_channel=ival(E_CH),
                channel_step=ival(E_STEP) or 1,
            )

    if vs.RunLayoutDialog(d, handler) == OK_BUTTON:
        return result.get('options')
    return None


def _apply(vs, fixtures, options):
    for f in fixtures:
        h = f.ref
        vs.SetRField(h, LD_RECORD, FIELD_UNIVERSE, str(f.universe))
        vs.SetRField(h, LD_RECORD, FIELD_ADDRESS, str(f.address))
        if options.force_default_footprint:
            vs.SetRField(h, LD_RECORD, FIELD_FOOTPRINT, str(f.footprint))
        if options.number_channels:
            vs.SetRField(h, LD_RECORD, FIELD_CHANNEL, f.channel)
        vs.ResetObject(h)


def _conflict_report(conflicts, limit=10):
    lines = []
    for a, b in conflicts[:limit]:
        lines.append('%s (%s) ↔ %s (%s)' % (
            a.position or '?', format_address(a.universe, a.address),
            b.position or '?', format_address(b.universe, b.address)))
    if len(conflicts) > limit:
        lines.append('… et %d autre(s)' % (len(conflicts) - limit))
    return '\n'.join(lines)


def run():
    """Commande « Patch rapide » : patche les projecteurs sélectionnés."""
    import vs

    fixtures = _collect(vs, only_selected=True)
    if not fixtures:
        vs.AlrtDialog('Sélectionnez au moins un projecteur (Lighting Device).')
        return

    options = _ask_options(vs)
    if options is None:
        return

    try:
        patched = compute_patch(fixtures, options)
    except PatchError as e:
        vs.AlrtDialog(str(e))
        return

    _apply(vs, patched, options)

    first, last = patched[0], patched[-1]
    used_end = last.address + last.footprint - 1
    message = '%d projecteur(s) patché(s) : %s → %s' % (
        len(patched), format_address(first.universe, first.address),
        format_address(last.universe, used_end))

    conflicts = find_conflicts(_collect(vs, only_selected=False))
    if conflicts:
        vs.AlrtDialog(message + '\n\n⚠ %d conflit(s) d\'adresse dans le document :\n%s'
                      % (len(conflicts), _conflict_report(conflicts)))
    else:
        vs.AlrtDialog(message + '\n\nAucun conflit d\'adresse dans le document.')


def run_check():
    """Commande « Vérifier le patch » : recherche les conflits sans rien modifier."""
    import vs

    fixtures = _collect(vs, only_selected=False)
    conflicts = find_conflicts(fixtures)
    if not conflicts:
        vs.AlrtDialog('Aucun conflit d\'adresse (%d projecteurs analysés).'
                      % len(fixtures))
        return
    # sélectionne les projecteurs en conflit pour les retrouver facilement
    vs.DSelectAll()
    for a, b in conflicts:
        vs.SetSelect(a.ref)
        vs.SetSelect(b.ref)
    vs.AlrtDialog('%d conflit(s) trouvé(s) — les projecteurs concernés sont '
                  'sélectionnés.\n\n%s' % (len(conflicts), _conflict_report(conflicts)))
