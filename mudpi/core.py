import os
import enum 
import time
import threading

from mudpi import importer
from mudpi.config import Config
from mudpi.events import EventSystem
from mudpi.constants import DEFAULT_CONFIG_FILE
from mudpi.logger.Logger import Logger, LOG_LEVEL
from mudpi.managers.state_manager import StateManager
from mudpi.exceptions import ConfigNotFoundError, ConfigFormatError
from mudpi.registry import Registry, ActionRegistry, ComponentRegistry

class MudPi:
    """ 
    MudPi Core Class

    The core class of MudPi that holds all the important items
    to run the MudPi system.
    """
    def __init__(self, config_path=None):
        self.config_path = config_path
        self.config = None

        self.state = CoreState.not_running
        
        # Main data storage between extensions
        # eventually change this to helper and backup in redis
        self.cache = {}

        self.threads = []
        self.thread_events = {
            # Event to signal system to shutdown
            'mudpi_running': threading.Event(),
            # Event to tell workers to begin working
            "core_running": threading.Event()
        }

        # Setup the registries
        self.components = ComponentRegistry(self, 'components')
        self.extensions = Registry(self, 'extensions')
        self.workers = Registry(self, 'workers')
        self.actions = ActionRegistry(self, 'actions')

        # System is Running
        self.thread_events['mudpi_running'].set()
        time.sleep(0.1)

    """ Properties """
    @property
    def is_prepared(self):
        """ Return if MudPi is prepared """
        return self.thread_events['mudpi_running'].is_set()

    @property
    def is_loaded(self):
        """ Return if MudPi is loaded or previously was. """
        return self.state in (CoreState.loaded, CoreState.stopped, CoreState.running)

    @property
    def is_loading(self):
        """ Return if MudPi is loaded or previously was. """
        return self.state in (CoreState.loading,)

    @property
    def is_running(self):
        """ Return if MudPi is running. """
        return self.state in (CoreState.running,)

    @property
    def is_stopping(self):
        """ Return if MudPi is stopping. """
        return self.state in (CoreState.stopping,)


    """ Methods """
    def load_config(self, config_path=None):
        """ Load MudPi Configurations """
        if self.state == CoreState.preparing:
            """ Already loading """
            return

        self.state = CoreState.preparing

        config_path = config_path or self.config_path

        self.config = Config(config_path=config_path)

        if self.config.load_from_file(config_path):
            if config_path and config_path != self.config_path:
                self.config_path = config_path

            self.state = CoreState.prepared
            return True
        return False

    def load_core(self):
        """ Init the MudPi Core 
            - Load the State Machine
            - Prepare Event Bus (Drivers)
            - Prepare the Threads / Managers
            - Register Core Actions
        """
        if self.config is None:
            # Error Config not loaded call `load_config()` first
            return

        if self.is_running:
            # Error core already running
            return

        if self.state != CoreState.prepared:
            # Core is not waiting to load likely already loaded
            return

        if self.state == CoreState.loading:
            # Error core is already loading
            return

        self.state = CoreState.loading

        self.states = StateManager(self, self.config.get('mudpi', {}).get('events', {}).get('redis'))
        
        self.events = EventSystem(self.config.get('mudpi', {}).get('events', {}))
        self.events.connect()

        self.actions.register('turn_on', self.start, 'mudpi')
        self.actions.register('turn_off', self.stop, namespace='mudpi')
        self.actions.register('shutdown', self.shutdown, namespace='mudpi')

        self.state = CoreState.loaded
        self.events.publish('core', {'event': 'Loaded'})
        return True

    def start(self, data=None):
        """ Signal MudPi to Start Once Loaded """
        if self.config is None:
            # Error Config not loaded call `load_config()` first
            return

        if self.is_running:
            # Error core already running
            return

        if not self.is_loaded:
            # Error core not loaded call `load_core()` first
            return


        self.events.publish('core', {'event': 'Starting'})
        self.state = CoreState.starting
        self.thread_events['core_running'].set()
        self.state = CoreState.running
        self.events.publish('core', {'event': 'Started'})
        return True

    def stop(self, data=None):
        """ Signal MudPi to Stop but Not UnLoad """
        self.events.publish('core', {'event': 'Stopping'})
        self.state = CoreState.stopping
        self.thread_events['core_running'].clear()
        self.state = CoreState.stopped
        self.events.publish('core', {'event': 'Stopped'})
        return True

    def shutdown(self, data=None):
        """ Signal MudPi to Stop and Unload """
        self.stop()
        self.events.publish('core', {'event': 'ShuttingDown'})
        self.unload_extensions()
        self.thread_events['mudpi_running'].clear()
        self.state = CoreState.not_running

        for thread in self.threads:
            thread.join()

        self.events.publish('core', {'event': 'Shutdown'})
        return True

    def start_workers(self):
        """ Start Workers and Create Threads """
        for key, worker in self.workers.items():
            _thread = worker.run()
            self.threads.append(_thread)
        return True

    def reload_workers(self):
        """ Reload Workers and Configurations """
        pass

    def unload_extensions(self):
        """ Cleanup all extensions for shutdown or restart """
        for key, extension in self.extensions.items():
            extension.unload()
        return True


class CoreState(enum.Enum):
    """ Enums for the current state of MudPi. """

    not_running = "NOT_RUNNING" # New MudPi instance
    preparing = "PREPARING"         # loading configs
    prepared = "PREPARED"         # configs loaded waiting to load core
    loading = "LOADING"           # core is loading
    loaded = "LOADED"           # core is loaded
    starting = "STARTING"       # core is starting
    running = "RUNNING"         # Core loaded and everying running
    stopping = "STOPPING"       # waing to shutdown
    stopped = "STOPPED"         # loaded but stopped (previously running)

    def __str__(self):
        return self.value