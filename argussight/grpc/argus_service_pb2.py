# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: argus_service.proto
# Protobuf Python Version: 5.26.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x13\x61rgus_service.proto\x12\nargussight\"C\n\x15StartProcessesRequest\x12*\n\tprocesses\x18\x01 \x03(\x0b\x32\x17.argussight.ProcessInfo\"?\n\x16StartProcessesResponse\x12\x0e\n\x06status\x18\x01 \x01(\t\x12\x15\n\rerror_message\x18\x02 \x01(\t\"*\n\x19TerminateProcessesRequest\x12\r\n\x05names\x18\x01 \x03(\t\"C\n\x1aTerminateProcessesResponse\x12\x0e\n\x06status\x18\x01 \x01(\t\x12\x15\n\rerror_message\x18\x02 \x01(\t\"V\n\x16ManageProcessesRequest\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\r\n\x05order\x18\x02 \x01(\t\x12\x11\n\twait_time\x18\x03 \x01(\x05\x12\x0c\n\x04\x61rgs\x18\x04 \x03(\t\"@\n\x17ManageProcessesResponse\x12\x0e\n\x06status\x18\x01 \x01(\t\x12\x15\n\rerror_message\x18\x02 \x01(\t\"\x15\n\x13GetProcessesRequest\"\xa1\x03\n\x14GetProcessesResponse\x12\x0e\n\x06status\x18\x01 \x01(\t\x12Q\n\x11running_processes\x18\x02 \x03(\x0b\x32\x36.argussight.GetProcessesResponse.RunningProcessesEntry\x12\\\n\x17\x61vailable_process_types\x18\x03 \x03(\x0b\x32;.argussight.GetProcessesResponse.AvailableProcessTypesEntry\x12\x15\n\rerror_message\x18\x04 \x01(\t\x1a]\n\x15RunningProcessesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x33\n\x05value\x18\x02 \x01(\x0b\x32$.argussight.RunningProcessDictionary:\x02\x38\x01\x1aR\n\x1a\x41vailableProcessTypesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12#\n\x05value\x18\x02 \x01(\x0b\x32\x14.argussight.InitArgs:\x02\x38\x01\"7\n\x0bProcessInfo\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0c\n\x04type\x18\x02 \x01(\t\x12\x0c\n\x04\x61rgs\x18\x03 \x03(\t\"O\n\x18RunningProcessDictionary\x12\x0c\n\x04type\x18\x01 \x01(\t\x12%\n\x08\x63ommands\x18\x02 \x03(\x0b\x32\x13.argussight.Command\"(\n\x07\x43ommand\x12\x0f\n\x07\x63ommand\x18\x01 \x01(\t\x12\x0c\n\x04\x61rgs\x18\x02 \x03(\t\"\x18\n\x08InitArgs\x12\x0c\n\x04\x61rgs\x18\x01 \x03(\t2\xfd\x02\n\x0eSpawnerService\x12W\n\x0eStartProcesses\x12!.argussight.StartProcessesRequest\x1a\".argussight.StartProcessesResponse\x12\x63\n\x12TerminateProcesses\x12%.argussight.TerminateProcessesRequest\x1a&.argussight.TerminateProcessesResponse\x12Z\n\x0fManageProcesses\x12\".argussight.ManageProcessesRequest\x1a#.argussight.ManageProcessesResponse\x12Q\n\x0cGetProcesses\x12\x1f.argussight.GetProcessesRequest\x1a .argussight.GetProcessesResponseb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'argus_service_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_GETPROCESSESRESPONSE_RUNNINGPROCESSESENTRY']._loaded_options = None
  _globals['_GETPROCESSESRESPONSE_RUNNINGPROCESSESENTRY']._serialized_options = b'8\001'
  _globals['_GETPROCESSESRESPONSE_AVAILABLEPROCESSTYPESENTRY']._loaded_options = None
  _globals['_GETPROCESSESRESPONSE_AVAILABLEPROCESSTYPESENTRY']._serialized_options = b'8\001'
  _globals['_STARTPROCESSESREQUEST']._serialized_start=35
  _globals['_STARTPROCESSESREQUEST']._serialized_end=102
  _globals['_STARTPROCESSESRESPONSE']._serialized_start=104
  _globals['_STARTPROCESSESRESPONSE']._serialized_end=167
  _globals['_TERMINATEPROCESSESREQUEST']._serialized_start=169
  _globals['_TERMINATEPROCESSESREQUEST']._serialized_end=211
  _globals['_TERMINATEPROCESSESRESPONSE']._serialized_start=213
  _globals['_TERMINATEPROCESSESRESPONSE']._serialized_end=280
  _globals['_MANAGEPROCESSESREQUEST']._serialized_start=282
  _globals['_MANAGEPROCESSESREQUEST']._serialized_end=368
  _globals['_MANAGEPROCESSESRESPONSE']._serialized_start=370
  _globals['_MANAGEPROCESSESRESPONSE']._serialized_end=434
  _globals['_GETPROCESSESREQUEST']._serialized_start=436
  _globals['_GETPROCESSESREQUEST']._serialized_end=457
  _globals['_GETPROCESSESRESPONSE']._serialized_start=460
  _globals['_GETPROCESSESRESPONSE']._serialized_end=877
  _globals['_GETPROCESSESRESPONSE_RUNNINGPROCESSESENTRY']._serialized_start=700
  _globals['_GETPROCESSESRESPONSE_RUNNINGPROCESSESENTRY']._serialized_end=793
  _globals['_GETPROCESSESRESPONSE_AVAILABLEPROCESSTYPESENTRY']._serialized_start=795
  _globals['_GETPROCESSESRESPONSE_AVAILABLEPROCESSTYPESENTRY']._serialized_end=877
  _globals['_PROCESSINFO']._serialized_start=879
  _globals['_PROCESSINFO']._serialized_end=934
  _globals['_RUNNINGPROCESSDICTIONARY']._serialized_start=936
  _globals['_RUNNINGPROCESSDICTIONARY']._serialized_end=1015
  _globals['_COMMAND']._serialized_start=1017
  _globals['_COMMAND']._serialized_end=1057
  _globals['_INITARGS']._serialized_start=1059
  _globals['_INITARGS']._serialized_end=1083
  _globals['_SPAWNERSERVICE']._serialized_start=1086
  _globals['_SPAWNERSERVICE']._serialized_end=1467
# @@protoc_insertion_point(module_scope)
