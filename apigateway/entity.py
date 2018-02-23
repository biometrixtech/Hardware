from abc import abstractmethod


class Entity:
    @staticmethod
    @abstractmethod
    def schema():
        raise NotImplementedError

    def _get_required_fields(self):
        return self.schema()['required']

    def _get_mutable_fields(self):
        return [field for field, config in self.schema()['properties'].items() if not config.get('readonly', False)]

    def _get_immutable_fields(self):
        return [field for field, config in self.schema()['properties'].items() if config.get('readonly', False)]
