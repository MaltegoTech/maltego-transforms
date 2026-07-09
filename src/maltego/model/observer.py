# Copyright (c) Maltego Technologies GmbH.
from typing import List, Any
import logging
from abc import ABC, abstractmethod


log = logging.getLogger(__name__)


class Observer(ABC):

    @abstractmethod
    def add(self, add_item: "Observable") -> None:
        pass

    @abstractmethod
    def update(self, update_item: "Observable", updated_property_name: str, updated_property_value: Any) -> None:
        pass

    @abstractmethod
    def delete(self, delete_item: "Observable") -> None:
        pass


class Observable:

    def __init__(self) -> None:
        self._observers: List[Observer] = []

    def register(self, observer: Observer) -> None:
        if observer in self._observers:
            log.error(f"Observer {observer} already registered to observable {self}")
            return
        self._observers.append(observer)

    def unregister(self, observer: Observer) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def get_observers(self) -> List[Observer]:
        return self._observers

    def notify_add(self, edit_item: "Observable") -> None:
        for observer in self._observers:
            observer.add(edit_item)

    def notify_delete(self, edit_item: "Observable") -> None:
        for observer in self._observers:
            observer.delete(edit_item)

    def notify_update(self, edit_item: "Observable", updated_field_name: str, updated_field_value: Any) -> None:
        for observer in self._observers:
            observer.update(edit_item, updated_field_name, updated_field_value)
