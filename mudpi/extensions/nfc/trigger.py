""" 
    NFC Trigger Interface
    Monitors NFC for scans and
    listens to specific NFC events.
"""
from . import NAMESPACE
from mudpi.utils import decode_event_data
from mudpi.exceptions import ConfigError
from mudpi.extensions import BaseInterface
from mudpi.extensions.trigger import Trigger
from mudpi.logger.Logger import Logger, LOG_LEVEL


class Interface(BaseInterface):

    def load(self, config):
        """ Load Trigger component from configs """
        trigger = NFCTrigger(self.mudpi, config)
        if trigger:
            self.add_component(trigger)
        return True

    def validate(self, config):
        """ Validate the trigger config """
        if not isinstance(config, list):
            config = [config]

        for conf in config:
            if not conf.get('source'):
                # raise ConfigError('Missing `source` key in NFC Trigger config.')
                pass
            
        return config


class NFCTrigger(Trigger):
    """ A trigger that listens to states
        and checks for new state that 
        matches any thresholds.
    """

    # Used for onetime subscribe
    _listening = False

    # Type of events to listen to
    _events = {
        'tag_scanned': "NFCTagScanned",
        'new_tag': "NFCNewTagScanned"
        'removed': "NFCTagRemoved"
    }
    
    @property
    def type(self):
        """ Return Trigger Type """
        return self.config.get("type", "tag_scanned")
    
    
    def init(self):
        """ Listen to the state for changes """
        super().init()
        if self.mudpi.is_prepared:
            if not self._listening:
                # TODO: Eventually get a handler returned to unsub just this listener
                self.mudpi.events.subscribe(NAMESPACE, self.handle_event)
                self._listening = True
        return True

    """ Methods """
    def handle_event(self, event):
        """ Handle the event data from the event system """
        _event_data = decode_event_data(event)

        if _event_data == self._last_event:
            # Event already handled
            return

        self._last_event = _event_data
        if _event_data.get('event'):
            try:
                if _event_data['event'] == self._events[self.type]:
                    if _event_data['tag_id'] == self.source or _event_data['key'] == self.source:
                        _value = self._parse_data(_event_data)
                        if self.evaluate_thresholds(_value):
                            self.active = True
                            if self._previous_state != self.active:
                                # Trigger is reset, Fire
                                self.trigger(_event_data)
                            else:
                                # Trigger not reset check if its multi fire
                                if self.frequency == 'many':
                                    self.trigger(_event_data)
                        else:
                            self.active = False
            except Exception as error:
                Logger.log(LOG_LEVEL["error"],
                           f'Error evaluating thresholds for trigger {self.id}')
                Logger.log(LOG_LEVEL["debug"], error)
            self._previous_state = self.active

    def unload(self):
        # Unsubscribe once bus supports single handler unsubscribes
        return

    def _parse_data(self, data):
        """ Get nested data if set otherwise return the data """
        if isinstance(data, dict):
            return data.get('tag_id') if not self.nested_source else data.get(self.nested_source, None)
        return data

