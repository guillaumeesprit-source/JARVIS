# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest

from PatchRapide import (Fixture, PatchOptions, PatchError, compute_patch,
                         find_conflicts, natural_key, SORT_POSITION, SORT_X,
                         SORT_Y, SORT_UNIT, SORT_DOC)


def refs(fixtures):
    return [f.ref for f in fixtures]


def test_sequential_addresses_use_footprint():
    fx = [Fixture('a', footprint=16, order=0), Fixture('b', footprint=1, order=1),
          Fixture('c', footprint=24, order=2)]
    out = compute_patch(fx, PatchOptions(sort_mode=SORT_DOC))
    assert [(f.universe, f.address) for f in out] == [(1, 1), (1, 17), (1, 18)]


def test_gap_and_start():
    fx = [Fixture(i, footprint=4, order=i) for i in range(3)]
    out = compute_patch(fx, PatchOptions(start_universe=3, start_address=101,
                                         gap=2, sort_mode=SORT_DOC))
    assert [f.address for f in out] == [101, 107, 113]
    assert all(f.universe == 3 for f in out)


def test_no_split_jumps_to_next_universe():
    fx = [Fixture('a', footprint=10, order=0), Fixture('b', footprint=10, order=1)]
    out = compute_patch(fx, PatchOptions(start_address=500, sort_mode=SORT_DOC))
    assert (out[0].universe, out[0].address) == (1, 500)
    assert (out[1].universe, out[1].address) == (2, 1)


def test_split_allowed():
    fx = [Fixture('a', footprint=10, order=0), Fixture('b', footprint=10, order=1)]
    out = compute_patch(fx, PatchOptions(start_address=500, no_split=False,
                                         sort_mode=SORT_DOC))
    assert (out[1].universe, out[1].address) == (1, 510)


def test_default_footprint_when_missing():
    fx = [Fixture('a', footprint=0, order=0), Fixture('b', order=1)]
    out = compute_patch(fx, PatchOptions(default_footprint=8, sort_mode=SORT_DOC))
    assert [f.address for f in out] == [1, 9]


def test_sort_by_position_upstage_first_then_left_to_right():
    fx = [Fixture('face2', x=5, y=0, position='FACE'),
          Fixture('face1', x=-5, y=0, position='FACE'),
          Fixture('p1b', x=3, y=10, position='P1'),
          Fixture('p1a', x=-3, y=10, position='P1')]
    out = compute_patch(fx, PatchOptions(sort_mode=SORT_POSITION))
    assert refs(out) == ['p1a', 'p1b', 'face1', 'face2']


def test_new_universe_per_position():
    fx = [Fixture('a', x=0, y=10, position='P1', footprint=2),
          Fixture('b', x=0, y=0, position='P2', footprint=2)]
    out = compute_patch(fx, PatchOptions(sort_mode=SORT_POSITION,
                                         new_universe_per_position=True))
    assert [(f.universe, f.address) for f in out] == [(1, 1), (2, 1)]


def test_sort_rows_by_y_with_tolerance():
    fx = [Fixture('front_r', x=5, y=0.2), Fixture('back', x=0, y=10),
          Fixture('front_l', x=-5, y=0)]
    out = compute_patch(fx, PatchOptions(sort_mode=SORT_Y))
    assert refs(out) == ['back', 'front_l', 'front_r']


def test_sort_columns_by_x():
    fx = [Fixture('r', x=5, y=0), Fixture('l_front', x=-5, y=0),
          Fixture('l_back', x=-5.1, y=10)]
    out = compute_patch(fx, PatchOptions(sort_mode=SORT_X))
    assert refs(out) == ['l_back', 'l_front', 'r']


def test_sort_unit_natural_and_reverse():
    fx = [Fixture('u10', unit='10'), Fixture('u2', unit='2'), Fixture('u1', unit='1')]
    out = compute_patch(fx, PatchOptions(sort_mode=SORT_UNIT))
    assert refs(out) == ['u1', 'u2', 'u10']
    out = compute_patch(fx, PatchOptions(sort_mode=SORT_UNIT, reverse=True))
    assert refs(out) == ['u10', 'u2', 'u1']


def test_channel_numbering():
    fx = [Fixture(i, order=i) for i in range(3)]
    out = compute_patch(fx, PatchOptions(sort_mode=SORT_DOC, number_channels=True,
                                         start_channel=101, channel_step=10))
    assert [f.channel for f in out] == ['101', '111', '121']


def test_invalid_options():
    with pytest.raises(PatchError):
        compute_patch([Fixture('a')], PatchOptions(start_address=0))
    with pytest.raises(PatchError):
        compute_patch([Fixture('a', footprint=600)], PatchOptions())


def test_conflicts():
    a = Fixture('a', universe=1, address=1, footprint=10)
    b = Fixture('b', universe=1, address=10, footprint=4)
    c = Fixture('c', universe=1, address=14, footprint=1)
    d = Fixture('d', universe=2, address=1, footprint=1)
    e = Fixture('e')  # non patché
    pairs = find_conflicts([a, b, c, d, e])
    assert [(x.ref, y.ref) for x, y in pairs] == [('a', 'b')]


def test_natural_key():
    assert sorted(['A10', 'A2', 'B1'], key=natural_key) == ['A2', 'A10', 'B1']
