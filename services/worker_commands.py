from __future__ import annotations

from enum import StrEnum


# ------------------------------------------------------------------ Script Worker

class ScriptWorkerCommands(StrEnum):
	START_CHAIN = "script.start_chain"
	STOP_CHAIN = "script.stop_chain"
	PAUSE_CHAIN = "script.pause_chain"
	RESUME_CHAIN = "script.resume_chain"
	RELOAD_SCRIPT = "script.reload_script"
	RELOAD_ALL = "script.reload_all"
	LIST_SCRIPTS = "script.list_scripts"
	LIST_CHAINS = "script.list_chains"


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
