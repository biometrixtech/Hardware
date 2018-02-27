class DynamodbUpdate:
    def __init__(self):
        self._add = set([])
        self._set = set([])
        self._parameters = {}

    def set(self, field, value):
        self._set.add("{field} = :{field}".format(field=field))
        self._parameters[':' + field] = value

    def add(self, field, value):
        self._add.add("{field} :{field}".format(field=field))
        self._parameters[':' + field] = value

    @property
    def update_expression(self):
        set = 'SET {}'.format(', '.join(self._set)) if len(self._set) else ''
        add = 'ADD {}'.format(', '.join(self._add)) if len(self._add) else ''
        return set + ' ' + add

    @property
    def parameters(self):
        return self._parameters
