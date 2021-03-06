# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, division


import operator
from petl.compat import text_type


from petl.util.base import Table, asindices, Record


def validate(table, constraints=None, header=None):
    """
    Validate a `table` against a set of `constraints` and/or an expected
    `header`, e.g.::

        >>> import petl as etl
        >>> # define some validation constraints
        ... header = ('foo', 'bar', 'baz')
        >>> constraints = [
        ...     dict(name='foo_int', field='foo', test=int),
        ...     dict(name='bar_date', field='bar', test=etl.dateparser('%Y-%m-%d')),
        ...     dict(name='baz_enum', field='baz', assertion=lambda v: v in ['Y', 'N']),
        ...     dict(name='not_none', assertion=lambda row: None not in row)
        ... ]
        >>> # now validate a table
        ... table = (('foo', 'bar', 'bazzz'),
        ...          (1, '2000-01-01', 'Y'),
        ...          ('x', '2010-10-10', 'N'),
        ...          (2, '2000/01/01', 'Y'),
        ...          (3, '2015-12-12', 'x'),
        ...          (4, None, 'N'),
        ...          ('y', '1999-99-99', 'z'),
        ...          (6, '2000-01-01'),
        ...          (7, '2001-02-02', 'N', True))
        >>> problems = etl.validate(table, constraints=constraints, header=header)
        >>> problems.lookall()
        +--------------+-----+-------+--------------+------------------+
        | name         | row | field | value        | error            |
        +==============+=====+=======+==============+==================+
        | '__header__' |   0 | None  | None         | 'AssertionError' |
        +--------------+-----+-------+--------------+------------------+
        | 'foo_int'    |   2 | 'foo' | 'x'          | 'ValueError'     |
        +--------------+-----+-------+--------------+------------------+
        | 'bar_date'   |   3 | 'bar' | '2000/01/01' | 'ValueError'     |
        +--------------+-----+-------+--------------+------------------+
        | 'baz_enum'   |   4 | 'baz' | 'x'          | 'AssertionError' |
        +--------------+-----+-------+--------------+------------------+
        | 'bar_date'   |   5 | 'bar' | None         | 'AttributeError' |
        +--------------+-----+-------+--------------+------------------+
        | 'not_none'   |   5 | None  | None         | 'AssertionError' |
        +--------------+-----+-------+--------------+------------------+
        | 'foo_int'    |   6 | 'foo' | 'y'          | 'ValueError'     |
        +--------------+-----+-------+--------------+------------------+
        | 'bar_date'   |   6 | 'bar' | '1999-99-99' | 'ValueError'     |
        +--------------+-----+-------+--------------+------------------+
        | 'baz_enum'   |   6 | 'baz' | 'z'          | 'AssertionError' |
        +--------------+-----+-------+--------------+------------------+
        | '__len__'    |   7 | None  |            2 | 'AssertionError' |
        +--------------+-----+-------+--------------+------------------+
        | 'baz_enum'   |   7 | 'baz' | None         | 'AssertionError' |
        +--------------+-----+-------+--------------+------------------+
        | '__len__'    |   8 | None  |            4 | 'AssertionError' |
        +--------------+-----+-------+--------------+------------------+

    Returns a table of validation problems.

    """

    return ProblemsView(table, constraints=constraints, header=header)


Table.validate = validate


class ProblemsView(Table):

    def __init__(self, table, constraints, header):
        self.table = table
        self.constraints = constraints
        self.header = header

    def __iter__(self):
        return iterproblems(self.table, self.constraints, self.header)


def iterproblems(table, constraints, expected_header):

    outhdr = ('name', 'row', 'field', 'value', 'error')
    yield outhdr

    it = iter(table)
    actual_header = next(it)

    if expected_header is None:
        flds = list(map(text_type, actual_header))
    else:
        expected_flds = list(map(text_type, expected_header))
        actual_flds = list(map(text_type, actual_header))
        try:
            assert expected_flds == actual_flds
        except Exception as e:
            yield ('__header__', 0, None, None, type(e).__name__)
        flds = expected_flds

    # setup getters
    if constraints:
        constraints = [dict(**c) for c in constraints]  # ensure list of dicts
        for constraint in constraints:
            if 'getter' not in constraint:
                if 'field' in constraint:
                    if constraint['field'] not in flds and constraint['optional']:
                        continue
                    # should ensure FieldSelectionError if bad field in
                    # constraint
                    indices = asindices(flds, constraint['field'])
                    getter = operator.itemgetter(*indices)
                    constraint['getter'] = getter

    # generate problems
    expected_len = len(flds)
    for i, row in enumerate(it):
        row = tuple(row)

        # row length constraint
        l = None
        try:
            l = len(row)
            assert l == expected_len
        except Exception as e:
            yield ('__len__', i+1, None, l, type(e).__name__)

        # user defined constraints
        if constraints:
            row = Record(row, flds)
            for constraint in constraints:
                name = constraint.get('name', None)
                field = constraint.get('field', None)
                assertion = constraint.get('assertion', None)
                test = constraint.get('test', None)
                getter = constraint.get('getter', lambda x: x)
                try:
                    target = getter(row)
                except Exception as e:
                    # getting target value failed, report problem
                    yield (name, i+1, field, None, type(e).__name__)
                else:
                    value = target if field else None
                    if test is not None:
                        try:
                            test(target)
                        except Exception as e:
                            # test raised exception, report problem
                            yield (name, i+1, field, value, type(e).__name__)
                    if assertion is not None:
                        try:
                            assert assertion(target)
                        except Exception as e:
                            # assertion raised exception, report problem
                            yield (name, i+1, field, value, type(e).__name__)
