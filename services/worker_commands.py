from __future__ import annotations

from enum import StrEnum


# ------------------------------------------------------------------ Script Worker

class ScriptWorkerCommands(StrEnum):
	START_CHAIN = "script.start_chain"
	STOP_CHAIN = "script.stop_chain"
	PAUSE_CHAIN = "script.pause_chain"
	RESUME_CHAIN = "script.resume_chain"
	RETRY_CHAIN = "script.retry_chain"
	RELOAD_SCRIPT = "script.reload_script"
	RELOAD_ALL = "script.reload_all"
	LIST_SCRIPTS = "script.scripts_list"
	LIST_CHAINS = "script.chains_list"
	UPDATE_CHAIN_STATE = "script.chain_state"
	UPDATE_LOG = "script.log"
	SET_HOT_RELOAD = "script.set_hot_reload"


# ------------------------------------------------------------------ iTAC (IMSApi REST) Worker

class ItacCommands(StrEnum):
	ADD_CONNECTION = "itac.add_connection"
	REMOVE_CONNECTION = "itac.remove_connection"

	LOGIN = "itac.login"
	LOGOUT = "itac.logout"

	CALL_CUSTOM_FUNCTION = "itac.custom_function"
	GET_STATION_SETTING = "itac.get_station_setting"

	RAW_CALL = "itac.raw_call"
	STOP = "itac.stop"


# ------------------------------------------------------------------ TCP Client Worker

class TcpClientCommands(StrEnum):
	ADD_CLIENT = "tcp.add_client"
	REMOVE_CLIENT = "tcp.remove_client"
	CONNECT = "tcp.connect"
	DISCONNECT = "tcp.disconnect"
	SEND = "tcp.send"
	BROADCAST = "tcp.broadcast"
	STOP = "tcp.stop"


# ------------------------------------------------------------------ REST API Worker

class RestApiCommands(StrEnum):
	ADD_ENDPOINT = "rest.add_endpoint"
	REMOVE_ENDPOINT = "rest.remove_endpoint"
	REQUEST = "rest.request"
	STOP = "rest.stop"


# ------------------------------------------------------------------ Device Worker

class DeviceWorkerCommands(StrEnum):
	CONNECT = "device.connect"
	DISCONNECT = "device.disconnect"
	TRIGGER = "device.trigger"


# ------------------------------------------------------------------ Job Worker

class JobWorkerCommands(StrEnum):
	START = "job.start"
	STOP = "job.stop"
	RUN_JOB = "job.run_job"


# ------------------------------------------------------------------ TwinCAT Worker

class TwinCatCommands(StrEnum):
	CONNECT = "twincat.connect"
	DISCONNECT = "twincat.disconnect"
	WRITE = "twincat.write"
	ADD_PLC = "twincat.add_plc"
	STOP = "twincat.stop"


# ------------------------------------------------------------------ COM Device Worker

class ComDeviceCommands(StrEnum):
	ADD_DEVICE = "com.add_device"
	REMOVE_DEVICE = "com.remove_device"
	LIST_DEVICES = "com.list_devices"
	SEND = "com.send"
	STOP = "com.stop"
