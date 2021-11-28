import logging
import struct
import time
import json
from ctypes import sizeof
from ctypes.wintypes import FLOAT
from SimConnect.Enum import SIMCONNECT_CLIENT_DATA_PERIOD, SIMCONNECT_UNUSED

class SimVariable:
    def __init__(self, id, name, float_value = 0):
        self.id = id
        self.name = name
        self.float_value = float_value
    def __str__(self):
        return f"Id={self.id}, value={self.float_value}, name={self.name}"

class MobiClient:

    def __init__(self, client_name):
        self.CLIENT_NAME = client_name
        self.CLIENT_DATA_AREA_LVARS    = None
        self.CLIENT_DATA_AREA_CMD      = None
        self.CLIENT_DATA_AREA_RESPONSE = None
        self.DATA_STRING_DEFINITION_ID = 0
    def __str__(self):
        s = f"Name={self.CLIENT_NAME}, LVARS_ID={self.CLIENT_DATA_AREA_LVARS}, CMD_ID={self.CLIENT_DATA_AREA_CMD}, "
        return s + f"RESPONSE_ID={self.CLIENT_DATA_AREA_RESPONSE}, DEF_ID={self.DATA_STRING_DEFINITION_ID}"


class MobiFlightVariableRequests:

    def __init__(self, client_name, simConnect):
        logging.info("MobiFlightVariableRequests: __init__")
        self.init_ready = False
        self.sm = simConnect
        self.sim_vars = {}
        self.sim_var_name_to_id = {}

        self.init_client = MobiClient("Mobiflight")
        self.init_client.CLIENT_DATA_AREA_LVARS = 0
        self.init_client.CLIENT_DATA_AREA_CMD = 1
        self.init_client.CLIENT_DATA_AREA_RESPONSE = 2
        self.init_client.DATA_STRING_DEFINITION_ID = 0

        self.my_client = MobiClient(client_name)
        self.my_client.CLIENT_DATA_AREA_LVARS = None
        self.my_client.CLIENT_DATA_AREA_CMD = None
        self.my_client.CLIENT_DATA_AREA_RESPONSE = None
        self.my_client.DATA_STRING_DEFINITION_ID = 1

        self.FLAG_DEFAULT = 0
        self.FLAG_CHANGED = 1
        self.DATA_STRING_SIZE = 256
        self.DATA_STRING_OFFSET = 0
        self.SIMVAR_DEF_OFFSET = 1000

        self.sm.register_client_data_handler(self._client_data_callback_handler)
        self._initialize_client_data_areas(self.init_client)

        # Sometimes first command after reconnect is ignored. Therefore send just some arbitrary command.
        self._send_command("Do Nothing", self.init_client)         
        self._send_command(("MF.Clients.Add." + client_name), self.init_client)                  
        # Wait for init ready
        while not self.init_ready:
           time.sleep(0.05)


    def _add_to_client_data_definition(self, definition_id, offset, size):
        logging.info("add_to_client_data_definition: definition_id=%s, offset=%s, size=%s", definition_id, offset, size)
        self.sm.dll.AddToClientDataDefinition(
            self.sm.hSimConnect,
            definition_id, 
            offset,
            size,
            0,  # fEpsilon
            SIMCONNECT_UNUSED) # DatumId

    
    def _subscribe_to_data_change(self, data_area_id, request_id, definition_id, interval=0):
        logging.info("subscribe_to_data_change: data_area_id=%s, request_id=%s, definition_id=%s", data_area_id, request_id, definition_id)
        self.sm.dll.RequestClientData(
            self.sm.hSimConnect,
            data_area_id,
            request_id,
            definition_id, 
            SIMCONNECT_CLIENT_DATA_PERIOD.SIMCONNECT_CLIENT_DATA_PERIOD_ON_SET,
            self.FLAG_CHANGED,
            0, # origin
            interval, # interval
            0) # limit


    def _send_data(self, client, size, dataBytes):
        logging.info("send_data: client=%s, size=%s, dataBytes=%s", client, size, dataBytes)
        self.sm.dll.SetClientData(
            self.sm.hSimConnect,
            client.CLIENT_DATA_AREA_CMD, 
            client.DATA_STRING_DEFINITION_ID,
            self.FLAG_DEFAULT,
            0, # dwReserved
            size, 
            dataBytes)  


    def _send_command(self, command, client):
        logging.info("send_command: command=%s", command)
        data_byte_array = bytearray(command, "ascii")
        data_byte_array.extend(bytearray(self.DATA_STRING_SIZE - len(data_byte_array)))  # extend to fix DATA_STRING_SIZE
        my_bytes = bytes(data_byte_array)
        self._send_data(client, self.DATA_STRING_SIZE, my_bytes)

        
    def _initialize_client_data_areas(self, client):
        logging.info("initialize_client_data_areas: Client: %s", client) 
        # register client data area for receiving simvars, sending commands and receiving responses
        dataAreaLVarsName    = (client.CLIENT_NAME + ".Lvars").encode("ascii")
        dataAreaCmdName      = (client.CLIENT_NAME + ".Command").encode("ascii")
        dataAreaResponseName = (client.CLIENT_NAME + ".Response").encode("ascii")
        self.sm.dll.MapClientDataNameToID(self.sm.hSimConnect, dataAreaLVarsName, client.CLIENT_DATA_AREA_LVARS)
        self.sm.dll.MapClientDataNameToID(self.sm.hSimConnect, dataAreaCmdName, client.CLIENT_DATA_AREA_CMD)
        self.sm.dll.MapClientDataNameToID(self.sm.hSimConnect, dataAreaResponseName, client.CLIENT_DATA_AREA_RESPONSE)
        # subscribe to WASM Module responses
        self._add_to_client_data_definition(client.DATA_STRING_DEFINITION_ID, self.DATA_STRING_OFFSET, self.DATA_STRING_SIZE)
        self._subscribe_to_data_change(client.CLIENT_DATA_AREA_RESPONSE, client.DATA_STRING_DEFINITION_ID, client.DATA_STRING_DEFINITION_ID)


    def _c_string_bytes_to_string(self, data_bytes):
        return data_bytes[0:data_bytes.index(0)].decode(encoding='ascii') # index(0) for end of c string


    def _initialize_execution_client(self, data_json):
        logging.info("initialize_execution_client")
        response_dict = json.loads(data_json)
        self.my_client.CLIENT_DATA_AREA_LVARS = response_dict["SimVars"]
        self.my_client.CLIENT_DATA_AREA_RESPONSE = response_dict["Response"]
        self.my_client.CLIENT_DATA_AREA_CMD = response_dict["Command"]
        self._initialize_client_data_areas(self.my_client)
        self.init_ready = True


    # simconnect library callback
    def _client_data_callback_handler(self, callback_data):

        # SimVar Data
        if callback_data.dwDefineID in self.sim_vars:
            data_bytes = struct.pack("I", callback_data.dwData[0])
            float_data = struct.unpack('<f', data_bytes)[0]   # unpack delivers a tuple -> [0]
            self.sim_vars[callback_data.dwDefineID].float_value = round(float_data, 5)
            logging.debug("client_data_callback_handler: %s", self.sim_vars[callback_data.dwDefineID])

        # Response string of init_client
        elif callback_data.dwDefineID == self.init_client.DATA_STRING_DEFINITION_ID:
            response =  self._c_string_bytes_to_string(bytes(callback_data.dwData))
            logging.debug("client_data_callback_handler: init_client response string: %s", response)
            # Check for response of registering new client
            if (response.startswith("{") and self.my_client.CLIENT_NAME in response):
                self._initialize_execution_client(response)

        # Response string of my_client
        elif callback_data.dwDefineID == self.my_client.DATA_STRING_DEFINITION_ID:
            response =  self._c_string_bytes_to_string(bytes(callback_data.dwData))
            logging.debug("client_data_callback_handler: get my_client response string: %s", response)
        else:
            logging.warning("client_data_callback_handler: DefinitionID %s not found!", callback_data.dwDefineID)


    def get(self, variableString):
        client = self.my_client
        if variableString not in self.sim_var_name_to_id:
            # add new variable
            id = len(self.sim_vars) + self.SIMVAR_DEF_OFFSET
            self.sim_vars[id] = SimVariable(id, variableString)
            self.sim_var_name_to_id[variableString] = id
            # subscribe to variable data change
            offset = (id-self.SIMVAR_DEF_OFFSET)*sizeof(FLOAT)
            self._add_to_client_data_definition(id, offset, sizeof(FLOAT))
            self._subscribe_to_data_change(client.CLIENT_DATA_AREA_LVARS, id, id)
            self._send_command(("MF.SimVars.Add." + variableString), client)  
        # determine id and return value
        variable_id = self.sim_var_name_to_id[variableString]
        float_value = self.sim_vars[variable_id].float_value
        logging.debug("get: %s. Return=%s", variableString, float_value)
        return float_value


    def set(self, variableString):
        logging.debug("set: %s", variableString)
        self._send_command(("MF.SimVars.Set." + variableString), self.my_client)
        

    def _list_sim_variables(self):
        logging.info("list_sim_variables MF.LVars.List")
        self._send_command("MF.LVars.List", self.my_client)


    def clear_sim_variables(self):
        logging.info("clear_sim_variables")
        self.sim_vars.clear()
        self.sim_var_name_to_id.clear()
        self._send_command("MF.SimVars.Clear", self.my_client)
        

       