#!/usr/bin/python3

"""
    @file   commmunicationHandler.py
    
    @brief  
    @date   10.03.23 
    @author Thomas Matre
"""

#todo test if all datatypes is converted correctly
import can
import struct
import time
import json
import threading
import sys
import os
import subprocess
from drivers.network_handler import Network
from drivers.STTS75_driver import STTS75


can_types = {
    "int8": "<b",
    "uint8": "<B",
    "int16": "<h",
    "uint16": "<H",
    "int32": "<i",
    "uint32": "<I",
    "int64": "<q",
    "uint64": "<Q",
    "float": "<f"
}


def getByte(can_format:str, number):
    return list(struct.pack(can_types[can_format], number))

def getNum(can_format:str, byt):
    if isinstance(byt, int):
        byt = byt.to_bytes(1, byteorder="big")
    return struct.unpack(can_types[can_format], byt)[0]

def getBit(num, bit_nr):
    return (num >> bit_nr) & 1

def setBit(bits: tuple):
    return sum(bit << k for k, bit in enumerate(bits))
#formats to json format in agreed upon formating
def toJson(input):
    packet_sep = json.dumps("*")
    return bytes(packet_sep + json.dumps(input) + packet_sep, "utf-8")

#builds packs for canbus
def packetBuild(tags):
  if tags in [63, 95, 125, 126, 127]: 
    canID = tags
    msg = bytearray('marco/n', 'utf-8')
  else:
    try:
      canID, *idData = tags
      idDataByte = []
      for data in idData:
        try:
          idDataByte += struct.pack(can_types[data[0]], *data[1:])
        except struct.error as e:
          print(f"Error: {e}")
          print(f"data={data}, format={data[0]}, value={data[1:]}")
          print(f"idDataByte={idDataByte}")
        msg = idDataByte
    except ValueError as error:
       return f"Error in building can message: {tags} "
    print(msg)
  return can.Message(arbitration_id=canID, data=msg, is_extended_id=False)

#decodes packs
def packetDecode(msg, ucFlags):
  canID = msg.arbitration_id
  dataByte = msg.data
  hbIds     = [155, 156, 157, 158, 159]
  int8Ids   = [1,2,3,4,5,6,7,8]
  uint8Ids  = [9,10,11]
  int16Ids  = [50,51,52]
  uint16Ids = [12,13,14,15]

  try:
    if canID in hbIds:
      pack = dataByte[0:6].decode('utf-8')
      jsonDict = {canID: (pack)}
      if canID == 155:
        ucFlags['Reg'] = True
      elif canID == 156:
        ucFlags['Sensor'] = True
      elif canID == 157:
        ucFlags['12Vman'] = True
      elif canID == 158:
        ucFlags['12Vthr'] = True
      elif canID == 159:
        ucFlags['5V'] = True
    elif canID in int16Ids:
      pack1 = getNum("int16", dataByte[0:2])
      pack2 = getNum("int16", dataByte[2:4])
      pack3 = getNum("int16", dataByte[4:6])
      pack4 = getNum("int16", dataByte[6:8])
      jsonDict = {canID: (pack1, pack2, pack3, pack4)}
    elif canID in uint16Ids:
      pack1 = getNum("uint16", dataByte[0:2])
      pack2 = getNum("uint16", dataByte[2:4])
      pack3 = getNum("uint16", dataByte[4:6])
      pack4 = getNum("uint16", dataByte[6:8])
      jsonDict = {canID: (pack1, pack2, pack3, pack4)}
    elif canID in int8Ids:
      pack1 = getNum("int8", dataByte[0])
      pack2 = getNum("int8", dataByte[1])
      pack3 = getNum("int8", dataByte[2])
      pack4 = getNum("int8", dataByte[3])
      pack5 = getNum("int8", dataByte[4])
      pack6 = getNum("int8", dataByte[5])
      pack7 = getNum("int8", dataByte[6])
      pack8 = getNum("int8", dataByte[7])
      jsonDict = {canID: (pack1, pack2, pack3, pack4, pack5, pack6, pack7, pack8)}
    elif canID in uint8Ids:
      pack1 = getNum("uint8", dataByte[0])
      pack2 = getNum("uint8", dataByte[1])
      pack3 = getNum("uint8", dataByte[2])
      pack4 = getNum("uint8", dataByte[3])
      pack5 = getNum("uint8", dataByte[4])
      pack6 = getNum("uint8", dataByte[5])
      pack7 = getNum("uint8", dataByte[6])
      pack8 = getNum("uint8", dataByte[7])
      jsonDict = {canID: (pack1, pack2, pack3, pack4, pack5, pack6, pack7, pack8)}
    elif canID == 52:
      pack1 = getNum("int32", dataByte[0:4])
      pack2 = getNum("int8",  dataByte[4])
      pack3 = getNum("uint8", dataByte[5])
      pack4 = getNum("uint16", dataByte[6:8])
      jsonDict = {canID: (pack1, pack2, pack3, pack4)}
    else:
      print(f"Unknown CanID: {canID} recived from ROV system")
      jsonDict = {"Error": f"Unknown CanID: {canID} recived from ROV system"}
  except TypeError as e:
     jsonDict = {"Error": e}
  return toJson(jsonDict)


# Reads data from network port
def netThread(netHandler, netCallback, flag):
    print("Server started\n")
    flag['Net'] = True
    while flag['Net']:
        try:
            msg = netHandler.receive()
            if msg == b"" or msg is None:
                continue
            else:
                netCallback(msg)
        except ValueError as e:
            print(f'Feilkode i network thread feilmelding: {e}\n\t{msg}')
            break
    netHandler.exit()
    print(f'Network thread stopped')

def hbThread(netHandler, canSend, systemFlag, ucFlags):
    print("Heartbeat thread started")
    hbIds = [63, 95 ,125, 126, 127]
    while systemFlag['Can']:
      for flag in ucFlags:
         ucFlags[flag] = False
      for id in hbIds:
         canSend(id)
         time.sleep(0.1)
      time.sleep(1)
      for flag in ucFlags:
        if not ucFlags[flag]:
          msg = toJson({"Alarm": f"uC {flag} not responding on CANBus"})
          netHandler.send(msg)
          time.sleep(0.2)
    print("Heartbeat thread stopped")

def i2cThread(netHandler, STTS75, systemFlag):
    print("i2c Thread started")
    while systemFlag['Net']:
       temp = STTS75.read_temp()
       msg = toJson({"Temp on Jetson": temp})
       netHandler.send(msg)
       time.sleep(2)
    print("i2c Thread stopped")

class ComHandler:
  def __init__(self, 
               ip:str='0.0.0.0',
               port:int=6900,
               canifaceType:str='socketcan',
               canifaceName:str='can0') -> None:
    self.canifaceType  = canifaceType
    self.canifaceName  = canifaceName
    self.status = {'Net': False, 'Can': False}
    self.uCstatus = {'Reg': False, 'Sensor': False, '12Vman': False, '12Vthr': False, '5V': False}
    #self.canFilters = [{"can_id" : 0x60 , "can_mask" : 0xF8, "extended" : False }]
    self.canFilters = [{"can_id" : 0x00 , "can_mask" : 0x00, "extended" : False }]
    #activate can in os sudo ip link set can0 type can bitrate 500000 etc.
    #check if can is in ifconfig then
    self.canInit()
    self.connectIp = ip
    self.connectPort = port
    self.netInit()
    self.heartBeat()
    self.i2cInit()

  def netInit(self):
    self.netHandler = Network(is_server=True, 
                              bind_addr=self.connectIp,
                              port     =self.connectPort)
    while self.netHandler.waiting_for_conn:
        time.sleep(1)
    self.toggleNet()

  def toggleNet(self):
    if self.status['Net']:
        # This will stop network thread
        self.status['Net'] = False
    else:
        self.netTrad = threading.Thread(name="Network_thread",target=netThread, daemon=True, args=(self.netHandler, self.netCallback, self.status))
        self.netTrad.start()

  def netCallback(self, data: bytes) -> None:
    data:str = bytes.decode(data, 'utf-8')
    for message in data.split(json.dumps("*")):
        try:
            if message == json.dumps('heartbeat') or message == "":
                if message is None:
                    message = ""
                continue
            else:
                message = json.loads(message)
                for item in message:
                    if item[0] < 200:
                        if self.status['Can']:
                            if item[0] == 100: 
                                msg = {item[0],
                                   {'int16', int(item[1])},
                                   {'int16', int(item[2])},
                                   {'int16', int(item[3])},
                                   {'int16', int(item[4])}}
                                self.sendPacket(msg)
                            elif item[0] == 64:
                                msg = {item[0],
                                   {'int16', int(item[1])}, {'int16', int(item[2])}, {'int16', int(item[3])}, {'int16', int(item[4])}
                                   }
                                self.sendPacket(msg)
                        else:
                            self.netHandler.send(toJson("Error: Canbus not initialised"))
        except Exception as e:
            print(f'Feilkode i netCallback, feilmelding: {e}\n\t{message}')

  def canInit(self):
    self.bus = can.Bus(
      interface             = self.canifaceType,
      channel               = self.canifaceName,
      receive_own_messages  = False,
      fd                    = False)
    self.bus.set_filters(self.canFilters)
    self.status['Can'] = True
    self.notifier = can.Notifier(self.bus, [self.readPacket])
    #self.timeout = 0.1 # todo kan denne fjernes?

  
  def sendPacket(self, tag):
    packet = packetBuild(tag)
    assert self.bus is not None
    try:
      self.bus.send(packet)
    except Exception as e:
      raise e

  def readPacket(self, can):
        self.bus.socket.settimeout(0)
        try:
          msg = packetDecode(can, self.uCstatus)
          self.netHandler.send(msg)
        except Exception as e:
          raise e
        
  def heartBeat(self):
    self.heartBeatThread = threading.Thread(name="hbThread",target=hbThread, daemon=True, args=(self.netHandler, self.sendPacket, self.status, self.uCstatus))
    self.heartBeatThread.start()
  
  def i2cInit(self):
     self.STTS75 = STTS75() 
     self.i2cThread = threading.Thread(name="i2cThread" ,target=i2cThread,daemon=True, args=(self.netHandler, self.STTS75, self.status))
     self.i2cThread.start()


if __name__ == "__main__":
# tag = (type, value)
# tags = (id, tag0, tag1, tag2, tag3, tag4, tag5, tag6, tag7) ex. with int8 or uint8
  c = ComHandler()
  while True:
    time.sleep(0.1)
