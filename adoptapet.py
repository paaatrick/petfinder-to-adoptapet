from collections import OrderedDict
import re

try:
    from io import StringIO
except ImportError:
    from cStringIO import StringIO


class ImportConfigParser:
    COLUMN_PATTERN = '#(?P<num>\d+):(?P<shelter>\w+)=(?P<adoptapet>\w+)'

    def __init__(self):
        self._columns = OrderedDict()
        self._column_re = re.compile(self.COLUMN_PATTERN)

    def read(self, filename):
        with open(filename) as file:
            self._read(file)

    def read_file(self, file):
        self._read(file)

    def read_string(self, string):
        self._read(StringIO(string))

    def _read(self, file):
        added_col_nums = set()
        current_col = None
        for lineno, line in enumerate(file, start=1):
            if line.isspace() or line.startswith(';'):
                continue
            col = self._column_re.match(line)
            if col:
                if col.group('num') in added_col_nums:
                    raise Exception('Duplicate column number found on line {0}: {1}'.format(lineno, line))
                added_col_nums.add(col.group('num'))
                self._columns[col.group('shelter')] = dict()
                current_col = self._columns[col.group('shelter')]
                continue
            try:
                (shelter_val, adoptapet_val) = line.split("=")
            except ValueError:
                raise Exception("Invalid syntax on line {0}: {1}".format(lineno, line))
            if current_col is None:
                raise Exception("Mapping data found before field assignment line {0}: {1}".format(lineno, line))
            current_col[shelter_val] = adoptapet_val.strip()

    def get_shelter_values(self, column):
        try:
            return self._columns[column].keys()
        except KeyError:
            raise Exception("No such column " + column)

    def get_mapped_value(self, column, shelter_value):
        try:
            col = self._columns[column]
        except KeyError:
            raise Exception("No such column " + column)

        try:
            return col[shelter_value]
        except KeyError:
            return shelter_value

    def get_columns(self):
        return self._columns.keys()


