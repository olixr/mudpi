import time
import datetime
import json
import redis
import threading
import sys
sys.path.append('..')

import variables
import importlib

class TriggerWorker():
	def __init__(self, config, main_thread_running, system_ready):
		#self.config = {**config, **self.config}
		self.config = config
		self.main_thread_running = main_thread_running
		self.system_ready = system_ready
		self.channel = "triggers"
		self.triggers = []
		self.trigger_events = {}
		self.init_triggers()
		return

	def dynamic_import(self, path):
		components = path.split('.')

		s = ''
		for component in components[:-1]:
			s += component + '.'

		parent = importlib.import_module(s[:-1])
		sensor = getattr(parent, components[-1])

		return sensor

	def init_triggers(self):
		trigger_index = 0
		for trigger in self.config:
			if trigger.get('type', None) is not None:
				#Get the trigger from the triggers folder {trigger name}_trigger.{SensorName}Sensor
				trigger_type = 'triggers.' + trigger.get('type').lower() + '_trigger.' + trigger.get('type').capitalize() + 'Trigger'

				imported_trigger = self.dynamic_import(trigger_type)

				trigger_state = {
					"active": threading.Event() #Event to signal relay to open/close
				}

				self.trigger_events[trigger.get("key", trigger_index)] = trigger_state

				# Define default kwargs for all trigger types, conditionally include optional variables below if they exist
				trigger_kwargs = { 
					'name' : trigger.get('name', trigger.get('type')),
					'key'  : trigger.get('key', None),
					'trigger_active' : trigger_state["active"]
				}

				# optional trigger variables 
				if trigger.get('options'):
					trigger_kwargs['options'] = trigger.get('options')

				if trigger.get('schedule'):
					trigger_kwargs['schedule'] = trigger.get('schedule')

				if trigger.get('source'):
					trigger_kwargs['source'] = trigger.get('source')

				if trigger.get('thresholds'):
					trigger_kwargs['thresholds'] = trigger.get('thresholds')

				new_trigger = imported_trigger(**trigger_kwargs)
				new_trigger.init_trigger()

				#Set the trigger type and determine if the readings are critical to operations
				new_trigger.type = trigger.get('type').lower()

				self.triggers.append(new_trigger)
				trigger_index += 1
				# print('{type} - {name}...\t\t\033[1;32m Listening\033[0;0m'.format(**trigger))
		return

	def run(self): 
		t = threading.Thread(target=self.work, args=())
		t.start()
		print('Trigger Worker [' + str(len(self.config)) + ' Triggers]...\t\t\033[1;32m Running\033[0;0m')
		return t

	def work(self):

		while self.main_thread_running.is_set():
			if self.system_ready.is_set():
				for trigger in self.triggers:
					trigger.check()
				time.sleep(0.01)
				
			time.sleep(2)
		#This is only ran after the main thread is shut down
		for trigger in self.triggers:
			trigger.shutdown()
		print("Trigger Worker Shutting Down...\t\t\033[1;32m Complete\033[0;0m")