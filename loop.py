#!/usr/bin/python3.4
"""
# -*- coding: utf-8 -*-
"""

"""
Formattazione argomenti passati come parametro da DOMOTICZ:
Parametri separati da ',' virgola
1) indirizzo scheda
2) IO arduino
3) valore

IO scheda standard ZARD:
1, 2, 3 ingressi
4, 5, 6 uscite LED
7, 8, 9 uscite PWM
48, 49 ingressi allarmi
50: tensione alimentazione
51: tensione ingresso Analog IN
52: temperatura + umidità AM2320
54: temperatura ATMEGA
55: temperatura + umidità SHT21
"""
import serial
import time
import datetime
import sys, os
if sys.version_info[0] == 3:
    import codecs
import configparser
import ast # For configparser
import base64
import urllib.request as urllib2
import binascii
import json
from pprint import pprint
import schedule

class Log():
    """
    Class to write Log File.
    Initializing:Filename, max row dimensions, path log file
    """
    def __init__(self, filename='logfile.log', dimension=1000000, path='/home/pi/domocontrol/'):
        """
        Classe istanziata con Nome_File, Dimensione_MAX_righe_file
        """
        self.logFilename = filename
        self.logPath = path
        self.logDimension = dimension

    def write(self,message=''):
        """
        Scrive sul file di LOG
        """
        f = open(self.logPath+self.logFilename, 'a')
        sttime = datetime.datetime.now().strftime('%Y%m%d_%H:%M:%S -')
        f.write("%s %s\n" %(sttime, message))
        f.flush()
        f.close()

    def crop(self):
        """
        Riduce il file di LOG se la dimensione > dimension_log_file
        """
        f = open(self.logFilename,"r+")
        d = f.readlines()
        dim = len(d)
        self.write("Call clopFileLog: Righe file di LOG: %s, dimensione max: %s righe" %(dim, self.logDimension))
        if dim > self.logDimension:
            f = open(self.logFilename,"r+")
            d = f.readlines()
            f = open(self.logFilename, "w")
            for l in d[self.logDimension*-1:] :
                f.write(l)
            f.close()

class Config():
    """
    Configurazione ZARD.CONF + Zard.log
    """
    def __init__(self):
        self.config = self.getConfig()
        self.fileConfig = self.readFile()
        # print(self.config)
        # print(self.fileConfig)

    def readFile(self):
        config = configparser.ConfigParser()
        config.read('/home/pi/domocontrol/zard.conf')
        return config


    def getConfig(self):
        """
        Create dict self.config from file zard.conf
        """
        config = configparser.ConfigParser()
        config.read('/home/pi/domocontrol/zard.conf')
        return dict(config._sections)

    def getConfigSection(self, device, io):
        """
        Return IO configuration from section
        example: getConfigSection('DEVICE_4', 'IO1')
        """
        a = self.fileConfig
        a = ast.literal_eval(a.get(device, io))
        return a

    def getDeviceAddress(self):
        """
        Popola il dict self.address id: device da zard.conf
        """
        deviceAddress = {}
        for k in self.config:
            if k[0:len('DEVICE')] == 'DEVICE':
                deviceAddress.update({int(k[7:]): k})
        return deviceAddress



    def getLogFilename(self):
        return self.config['COMMUNICATION']['log_filename']

    def getLogDimension(self):
        return int(self.config['COMMUNICATION']['log_dimension'])


class Domoticz(Config):
    def __init__(self):
        super(Domoticz, self).__init__()
        self.config = self.getConfig()
        self.log = Log(self.getLogFilename(), self.getLogDimension())
        self.deviceAddress = self.getDeviceAddress() # dict with all ZARD address (not remove)
        self.D = {} # Dict with all data (NEW)
        self.setD() #Dict with IDZ <-> IDA (IDZ=ID domoticz, IDA=ID arduino)
        print(self.D)
        self.ser = self.serOpen()
        self.EEaddressStart = (0) #Start EE address (per evitare problemi con 0X0A)
        self.EEaddress = 0
        self.EEaddressApp = 0 # EEeprom address appoggio
        self.deviceReady = [] # List con i device in rete
        self.base64string = self.getEncode() # Base64string to connect DOMOTICZ

    def __del__(self):
        # self.ser.close()
        print( "**END**" )


    def calc_time(func):
        """
        Restituisce il tempo di esecuzione di una certa funzione
        """
        name = func.__name__
        def inner(self, *args, **kwargs):
            start = time.time()
            res = func(self, *args, **kwargs)
            end = time.time()
            print("Tempo esecuzione funzione %s: %s seconds " %(name, end-start))
            return res
        return inner



    def getEncode(self):
        """
        Base 64 encode to connect DOMOTICZ
        """
        password = self.config['DOMOTICZ']['password']
        username = self.config['DOMOTICZ']['username']
        self.port = self.config['DOMOTICZ']['port']
        self.url = self.config['DOMOTICZ']['url']
        baseval =  base64.b64encode(bytes('%s:%s' %(username, password), "utf-8"))
        self.boardReady = []
        return baseval

    @calc_time
    def setD(self):
        """
        Popola il DICT self.D con tutta la configurazione e gli stati di IO
        """
        # Definizioni USCITE da 1 a 127:
        dict_replace = {
            'not_used': 0,
            'toggle': 1,
            'timer_with_reset': 2,
            'timer_scale': 3,
            'timer_scale_with_recount': 4,
            'blink': 9,
            'touch': 15,
            'switch': 14,
            'power_supply_voltage': 20,
            'voltage_input': 21,
            'AM2320_T': 30,
            'AM2320_H': 31,
            'ATMEGA_T': 32,
            'DS18x20_T': 33,
            'SHT21_T': 34,
            'SHT21_H': 35,
            'BME280_T': 36,
            'BME280_H': 37,
            'BME280_B': 38,
            'TSL2561_L': 39,
            'VIN': 40,
            'ADC': 41,
        }

        self.D.update({'board_address': []})
        for board_address in self.deviceAddress:
            self.D.update({board_address: {}})

            self.D[board_address].update({'board_address': int(board_address)})
            self.D['board_address'].append(board_address)

            if not 'status_at_boot' in self.D[board_address]:
                self.D[board_address].update({'status_at_boot': []})
            if not 'Drequest' in self.D[board_address]:
                self.D[board_address].update({'Drequest': []})
            if not 'Znow' in self.D[board_address]:
                self.D[board_address].update({'Znow': []})
            if not 'def_io_type' in self.D[board_address]:
                self.D[board_address].update({'def_io_type': []})
            if not 'def_io_type_name' in self.D[board_address]:
                self.D[board_address].update({'def_io_type_name': []})
            if not 'io_enable' in self.D[board_address]:
                self.D[board_address].update({'io_enable': []})
            if not 'Did' in self.D[board_address]:
                self.D[board_address].update({'Did': []})
            if not 'Dname' in self.D[board_address]:
                self.D[board_address].update({'Dname': []})
            if not 'io_timer' in self.D[board_address]:
                self.D[board_address].update({'io_timer': []})
            if not 'in_board_address' in self.D[board_address]:
                self.D[board_address].update({'in_board_address': []})
            if not 'in_address' in self.D[board_address]:
                self.D[board_address].update({'in_address': []})
            if not 'refresh_timeout' in self.D[board_address]:
                self.D[board_address].update({'refresh_timeout': []})
            if not 'sensor_enable' in self.D[board_address]:
                self.D[board_address].update({'sensor_enable': []})
            if not 'def_sensor_type' in self.D[board_address]:
                self.D[board_address].update({'def_sensor_type': []})
            if not 'def_sensor_name' in self.D[board_address]:
                self.D[board_address].update({'def_sensor_name': []})
            if not 'sensor_refresh_timeout' in self.D[board_address]:
                self.D[board_address].update({'sensor_refresh_timeout': []})
            if not 'sensor_domoticz_id' in self.D[board_address]:
                self.D[board_address].update({'sensor_domoticz_id': []})
            if not 'sensor_domoticz_name' in self.D[board_address]:
                self.D[board_address].update({'sensor_domoticz_name': []})



            device = "DEVICE_%s" % board_address

            # Add sensors list from configutation file
            for n in range(1,10):
                sensor = "SENSOR%s" %n
                try:
                    sensor_conf = self.getConfigSection(device, sensor)
                    sensor_enable = 1 if sensor_conf.get('enable', 'no') == 'yes' else 0
                    self.D[board_address]['sensor_enable'].append(sensor_enable)

                    def_sensor_name = sensor_conf.get('sensor_name', 'not_used')
                    self.D[board_address]['def_sensor_name'].append(dict_replace[def_sensor_name])

                    def_sensor_type = sensor_conf.get('sensor_type', '')
                    self.D[board_address]['def_sensor_type'].append(sensor_conf.get('sensor_type', ''))

                    self.D[board_address]['sensor_refresh_timeout'].append(int(sensor_conf.get('refresh_timeout', 0)))

                    sensorDomoticzId =  int(sensor_conf.get('domoticz_id', 0))
                    sensorDomoticzName =  sensor_conf.get('domoticz_name', '')
                    self.D[board_address]['sensor_domoticz_id'].append(sensorDomoticzId)
                    self.D[board_address]['sensor_domoticz_name'].append(sensorDomoticzName)

                    pass
                except:
                    pass

            """
            sensors_conf = self.getConfigSection(device, 'sensors')
            for key in sensors_conf:
                self.D[board_address]['sensors'].append(dict_replace.get(key, 0))
                self.D[board_address]['sensors_timeout'].append(int(sensors_conf[key]))

            """

            # Add list and dict of IOx from configutation file
            for n in range(1,15): # Total number IO devices for each board zard
                io = "IO%s" %n
                try:
                    io_conf = self.getConfigSection(device, io)
                    # print(io_conf)
                    io_enable = 1 if io_conf.get('enable', 'no') == 'yes' else 0
                    self.D[board_address]['io_enable'].append(io_enable)

                    def_io_type = io_conf.get('io_type', 'not_used')
                    self.D[board_address]['def_io_type'].append(dict_replace[def_io_type])
                    self.D[board_address]['def_io_type_name'].append(def_io_type)

                    Did =  int(io_conf.get('domoticz_id', 0))
                    Dname =  io_conf.get('domoticz_name', '')
                    self.D[board_address]['Did'].append(Did)
                    self.D[board_address]['Dname'].append(Dname)
                    self.D[board_address]['status_at_boot'].append(int(io_conf.get('status_at_boot', 0)))
                    self.D[board_address]['io_timer'].append(int(io_conf.get('timer', 0)))
                    self.D[board_address]['Drequest'].append(0)
                    self.D[board_address]['Znow'].append(0)
                    self.D[board_address]['in_board_address'].append(int(io_conf.get('in_board_address', 0)))
                    self.D[board_address]['in_address'].append(int(io_conf.get('in_address', 0)))
                    self.D[board_address]['refresh_timeout'].append(int(io_conf.get('refresh_timeout', 0)))


                except:
                    self.D[board_address]['io_enable'].append(0)
                    self.D[board_address]['def_io_type'].append(0)
                    self.D[board_address]['def_io_type_name'].append('')
                    self.D[board_address]['Did'].append(0)
                    self.D[board_address]['io_timer'].append(0)
                    self.D[board_address]['status_at_boot'].append(0)
                    self.D[board_address]['Drequest'].append(0)
                    self.D[board_address]['Znow'].append(0)
                    self.D[board_address]['in_board_address'].append(0)
                    self.D[board_address]['in_address'].append(0)
                    self.D[board_address]['refresh_timeout'].append(0)

    def sendURL(self, url):
        """
        Send url to DOMOTICZ to set state of IO
        """
        try:
            urld = self.url + ':' + self.port + '/json.htm?' + url
            # print("**** %s" %urld)
            request = urllib2.Request(urld)
            request.add_header("Authorization", "Basic %s" % self.base64string.decode('utf-8'))
            result = urllib2.urlopen(request)

            resulttext = result.read().decode('utf-8')
            # print(resulttext)
            dictres = json.loads(resulttext)
            # print(dictres)
            return dictres
        except:
            print("NONONONONO")
            return 0


    def getUserVariable(self):
        """
        Get Domoticz User Variable
        """
        url = "type=command&param=getuservariables"

        return url

    def updateUserVariable(self, name, type, value):
        """
        Update Domoticz User Variable
        """
        url = "type=command&param=updateuservariable&vname=%s&vtype=%s&vvalue=%s" %(name, type, value)
        return url

    def addUserVariable(self, name, type, value):
        """
        Create User Variable to Domoticz
        """
        url = "type=command&param=saveuservariable&vname=%s&vtype=%s&vvalue=%s" %(name, type, value)
        return url

    def getStatusDeviceDomoticz(self, Did):
        url = "type=devices&rid=%s" %Did
        return url

    def serOpen(self):
        # print "Serial Open"
        # print self.config['COMMUNICATION']
        RS485_device = self.config['COMMUNICATION']['rs485_device']
        RS485_speed = self.config['COMMUNICATION']['rs485_speed']
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS
        # print(RS485_device, RS485_speed)
        ser = serial.Serial(RS485_device, RS485_speed, timeout=0.1, xonxoff=False, rtscts=True, dsrdtr=False) #Tried with and without the last 3 parameters, and also at 1Mbps, same happens.
        ser.flush()
        ser.flushInput()
        ser.flushOutput()
        return ser

    def rx485(self):
        line = []
        a = 1
        while 1:
            c = self.ser.read()
            # print("SERIALE:", c, end=" ")
            try:
                line.append(ord(c))
                if not 0x2A in line:
                    line = []
                if len(line) >= 3 and line[-2] == 13 and line[-1] == 10:
                    # print("===>>>", line)
                    return line
            except:
                return []

    def tx485(self, serialtx):
        self.ser.write(serialtx)
        # self.log.write("==>tx485 %s" %serialtx)
        # self.ser.flush()

    def serClose(self):
        print( "Serial Close" )
        self.ser.close()

    def check(self, comandTX, comandRX=""):
        l = len(comandRX)
        if l <= 3:
            return 0
        # print l, comandTX[0:4], comandRX[0:l-2], comandRX[-3], comandRX[-4]
        if comandTX[0:4] == comandRX[0:4] and comandRX[-3]=="#" and comandRX[-4]=="#":
            return 1
        else:
            return 0

    # incoming = char ex. 0x3431 = 41
    def calcCheckSum(self, incoming):
        # msgByte = self.hexStr2Byte(incoming)
        # print(type(incoming))
        if type(incoming) == str:
            msgByte = bytearray(incoming, 'utf-8')
        elif  type(incoming) == bytes:
            # print("*********")
            msgByte = []
            for x in incoming:
                msgByte.append(x)
            # print(msgByte)
        else:
            msgByte = incoming
        check = 0
        for i in msgByte:
            check = self.AddToCRC(i, check)
        return check

    def AddToCRC(self, b, crc):
        b2 = b
        if (b < 0):
            b2 = b + 256
        for i in range(8):
            odd = ((b2^crc) & 1) == 1
            crc >>= 1
            b2 >>= 1
            if (odd):
                crc ^= 0x8C # this means crc ^= 140
        return crc

    def hexStr2Byte(self, msg):
        hex_data = msg.decode("hex")
        msg = bytearray(hex_data)
        return msg

    def toHex(self, msg):
        return hex(self.calcCheckSum(msg))

    def sendAck(self, res, address, comand, io, value, addr):
        """
        Spedisce conferma ricezione msg.
        """
        if res['status'] == "OK":
            cmd = bytes([0x2A]) # Primo carattere
            cmd += bytes([0x06]) # 6 = ACK
            cmd += bytes([address])
            cmd += bytes([io])
            crc = self.calcCheckSum(cmd)
            cmd += bytes([crc])
            cmd += bytes([0x0d, 0x0a])
            # print("ACK:", cmd)
            self.tx485(cmd)

    def sendProva(self):
        cmd = '\x04'
        cmd += '\x03'
        cmd += '\x00'
        cmd += '\xcb'
        cmd += '\x0d'
        cmd += '\x0a'
        # print "ACK: ",address, comand, cmd, crc
        # print rx[0:-3]
        # print(cmd)
        # self.tx485(cmd)

    def getValDict(self, d, k):
        """
        Ritorna il valore da un DICT.
        self.getValDict(dict, [key1,key2,....,keyn])
        """
        for x in k:
            if type(d) == dict and x in d:
                val = d[x]
                del k[0]
                return self.getValDict(val, k)
            elif type(d) == list and len(d) > x:
                val = d[x]
                if len(k) > 1:
                    del k[0]
                    return self.getValDict(val, k)
                else:
                    return d[x]
        return d

    def setDomoticzSensorVariato(self, board_address, io, value):
        val = value[0] << 8 | value[1]
        Did = self.D[board_address]['sensor_domoticz_id'][io-1]
        # print("Sensor: ",board_address, io, value, self.D[board_address]['sensor_domoticz_id'][io-1], self.D[board_address]['def_sensor_type'][io-1])

        url=''

        if self.D[board_address]['def_sensor_type'][io-1] == 'Temperature':
            url = "type=command&param=udevice&idx=%s&nvalue=0&svalue=%s" %(Did, round( (val)/10.0, 1))

        elif self.D[board_address]['def_sensor_type'][io-1] == 'Humidity':
            val = value[0] << 8 | value[1]
            hum = round( (val)/10.0, 0)
            #Calc confort humidity: <40:dry; 40-50:normal; 50-60:confort; 60-70:normal; >70:wet
            stat = 0
            if hum < 40:
                stat = 2
            elif hum >= 40 and hum < 50:
                stat = 0
            elif  hum >= 50 and hum < 60:
                stat = 1
            elif hum >= 60 and hum < 70:
                stat = 0
            elif hum >= 70:
                stat = 3
            # print("HUM",board_address, Did, hum, stat, val)
            url = "type=command&param=udevice&idx=%s&nvalue=%s&svalue=%s" %(Did, hum, stat)

        elif self.D[board_address]['def_sensor_type'][io-1] == 'Voltage': #Ingresso ADC / Voltage
            # print('Voltage Value:', val, val/10)
            url = "type=command&param=udevice&idx=%s&nvalue=0&svalue=%s" %(Did, val/10.0)


        try:
            res = self.sendURL(url)
            # print("URL: ", url, res)
            # print("RES: ", res)

        except:
            print("self.sendURL(%s) NOT WORKING" %url)
            pass


    # @calc_time
    def setDomoticzIOvariato(self, board_address, io, value):
        # print("setDomoticzIOvariato",board_address, io, value)
        val = value[0] << 8 | value[1]
        # print("Valore:", val)

        def_io_type = self.getValDict(self.D, [board_address, 'def_io_type', io-1]) # arduino ID io
        # print("def_io_type", def_io_type)
        if not def_io_type: # Non c'è alcun ID arduino corrispondente
            l = "ERROR KEY: board_address:%s, def_io_type:%s, io:%s" %(board_address, 'def_io_type', io-1)
            self.log.write(l)
            return

        Did = self.getValDict(self.D, [board_address,'Did',io-1]) # Domoticz ID
        # print("Did", Did)
        if not Did:
            l = "ERROR KEY: board_address:%s, def_io_type:%s, io:%s" %(board_address, 'Did', io-1)
            self.log.write(l)
            return

        # print('setDomoticzIOvariato board_address:%s, io:%s, value:%s' %(board_address, io, val))
        # print('addr:%s, io:%s, def_io_type:%s, Did:%s, value:%s' %(board_address, io, def_io_type, Did, val))
        res = {}

        # print("test", def_io_type, Did, type(val))
        if def_io_type in [1, 2, 3, 4, 9, 14, 15, 'switch', 'touch']: # in / out
            """
            Send switchLight status
            """
            url = "type=command&param=switchlight&idx=%s&switchcmd=%s" %(Did, {1: 'On', 0: 'Off'}[val])
            # print("url:", url)

        # elif def_io_type == 3 or def_io_type == 7: #AM2320 / SHT21 Temp
            # url = "type=command&param=udevice&idx=%s&nvalue=0&svalue=%s" %(Did, round( (val)/10.0, 1))

        # elif def_io_type == 5: #ATMEGA temp
            # url = "type=command&param=udevice&idx=%s&nvalue=%s&svalue=%s" %(Did, round( (val)/10.0, 0), 0)
            # url = self.temperature(Did, round( (val)/10.0, 0))
        # elif def_io_type == 6: #Alarm
            # Get Alarm: 1=Short Circuit; 2=Alarm status; 3=Normal; 4=PIR sconnected
            # Did = self.D[board_address]['Did'][io-1]
            # Dname = self.D[board_address]['Dname'][Did]
            # self.updateUserVariable(Dname  ,'Integer', val)

            # if val == 1:
                # value = 'CAVI_IN_CORTO'
            # elif val == 2:
                # value = 'ALARM'
            # elif val == 3:
                # value = 'NORMALE'
            # else:
                # value = 'CAVO_SCOLLEGATO'

            # print idx, value
            # type=command&param=udevice&idx=IDX&nvalue=LEVEL&svalue=TEXT
            # url = "type=command&param=udevice&idx=%s&nvalue=LEVEL&svalue=%s" %(Did, value)
            # url = self.sendAlarm(Did, val)

        # else:
            # pass
            # print("def_io_type non presente: ", board_address, int(io), value, def_io_type)


        try:
            res = self.sendURL(url)
            # print("URL: ", url, res)
            # print("RES: ", res)

        except:
            print("self.sendURL(%s) NOT WORKING" %url)
            pass


        if self.getValDict(res, ['status']) == 'OK':
            self.D[board_address]['Znow'][io-1] = val
            try:
                # print(self.D[board_address]['Dname'][io-1], 'Integer', val)
                url = self.updateUserVariable(self.D[board_address]['Dname'][io-1], 'Integer', val)
                self.sendURL(url)
            except:
                print("update variable NOT working", res)

        elif self.getValDict(res, ['status']) == 'ERR':
            self.log.write("ERROR update Domoticz Did:%s value:%s" %(Did, val))

    # @calc_time
    def setComand(self, cmd):
        """
        Si occupa di trasmettere l'input proveniente da arduino a domoticz
        """
        comand = cmd[1] #Comand to do
        board_address = cmd[2] #Device address
        io = cmd[3] # Comand
        value = cmd[4:-3] # Value
        #print("comand:%s, addr:%s, io:%s, value:%s" %(comand, addr, io, value))

        if comand==1: # IO variato
            # print("SET IO VARIATO", io, value)
            self.setDomoticzIOvariato(board_address, io, value)

        if comand==8: # sensor variato
            # print(board_address, io, value)
            self.setDomoticzSensorVariato(board_address, io, value)

        elif comand==14: # Request value IO of ZARD from DOMOTICZ. If equal: pass, otherwise change value of ZARD

            Did = self.getValDict(self.D, [board_address, 'Did', io-1])
            print("comand=14: board_address: %s, io: %s, Did: %s" %(board_address, io-1, Did))

            if Did:
                url = self.getStatusDeviceDomoticz(Did)
                print("Did:", Did, " url: ", url)

                try:
                    res = self.sendURL(url)['result'][0]['Status']
                    # print("////// ", res['result'][0]['Status'])
                    res = 1 if res == 'On' else 0

                except:
                    l = "Error 14: %s %s " %(self.getStatusDeviceDomoticz, Did)
                    # print(l)
                    self.log.write(l)
                    return


                # print("Valore Domoticz:%s, Valore ZARD corrente:%s" %(res, cmd[5]))
                if res != cmd[5]:
                    vtx = [2, board_address, io, 0, res]
                    # print("Comando inviato a ZARD: %s" %vtx)
                    self.txSend(vtx)
            else:
                l = "TypeError: 'int' object is not subscriptable: cmd:%s " %(cmd)
                self.log.write(l)

            """
            try:
                # print(cmd)
                Did = self.D[board_address]['Did'][io-1]
                vald = self.getStatusDeviceDomoticz(Did)['result'][0]['Status']
                vald = 1 if vald == 'On' else 0
                print("Valore Domoticz:%s, Valore ZARD corrente:%s" %(vald, cmd[5]))
                if vald != cmd[5]:
                    vtx = [2, board_address, io, 0, vald]
                    print("Comando inviato a ZARD: %s" %vtx)
                    self.txSend(vtx)
            except:
                l = "TypeError: 'int' object is not subscriptable\n \
                    cmd:%s " %(cmd)
                self.log.write(l)
            """

    def storeEE(self, cmd, crc):
        print("=>>",cmd)
        app = []
        self.tx485(cmd)
        time.sleep(0.01) # Importante
        rxComand = self.rx485()
        # print(cmd, self.rxReady, self.rxComand)
        #~ print(self.rxReady)
        #print(rxComand)
        if rxComand:
            checkAck = self.calcCheckSum(rxComand[0:-3])
            # print (checkAck)
            # for x in self.rxComand:
                # print(x, sep=' ')
            # print()
            #~ print(checkAck, self.rxComand[-3], len(self.rxComand))

            if len(rxComand) > 4 and (rxComand[-3] == checkAck):
                # print("OK")
                pass
            else:
                time.sleep(0.5)
                #print("RE StoreEE", cmd, crc)

                self.storeEE(cmd, crc)
        else:
            time.sleep(0.5)
            # print("RE StoreEE")
            self.storeEE(cmd, crc)

    def writeEE(self, board_address, EEcomand):
        """
        Scrive la EEPROM di ZARD
        Board_address, Commento, EEaddress, value
        """

        if self.EEaddressApp != board_address:
            self.EEaddressApp = board_address
            self.EEaddress = 0


        # print('*****************', self.EEaddress, EEcomand)

        l = len(EEcomand)
        # print(board_address, EEcomand, l)
        cmd = bytes([0x2A]) #primo carattere
        cmd += bytes([0x04]) #write EE
        cmd += bytes([board_address])
        cmd += bytes([self.EEaddress])
        cmd += bytes([l])
        crc = self.calcCheckSum(cmd)
        cmd += bytes([crc])
        cmd += bytes([0x0d, 0x0a])
        self.storeEE(cmd, crc)
        self.EEaddress += 1

        for n in EEcomand:
            cmd = bytes([0x2A]) #primo carattere
            cmd += bytes([0x04]) #Write EE
            cmd += bytes([board_address])
            cmd += bytes([self.EEaddress])
            cmd += bytes([n])
            crc = self.calcCheckSum(cmd)
            cmd += bytes([crc])
            cmd += bytes([0x0d, 0x0a])
            self.storeEE(cmd, crc)
            self.EEaddress += 1


    def sendParameter(self):
        """
        Send Paramenter to EEPROM by RS485
        """
        ll = []
        for board_address in self.deviceReady: # Fa la scansione di tutte le schede ZARD
            # print(board_address)
            EEcomand = []
            # print(dir(self.config))


            board_firmware_version =  self.config[self.deviceAddress[board_address]].get("board_firmware_version", 0)
            EEcomand.append(0xF7)
            EEcomand.append(int(board_firmware_version))

            # for key in self.config[self.deviceAddress[board_address]]:
            for key in self.D[board_address]:
                print("EE: ", board_address, key)

                if key[0:len(key)] == 'in_address':
                    value = self.D[board_address]['in_address']
                    EEcomand.append(0xF8)
                    EEcomand.extend(value)
                    if not '0xF8' in ll: ll.append('0xF8')
                    # print('0xF8 in_address:', EEcomand)

                elif key[0:len(key)] == 'in_board_address':
                    value = self.D[board_address]['in_board_address']
                    EEcomand.append(0xF9)
                    EEcomand.extend(value)
                    if not '0xF9' in ll: ll.append('0xF9')
                    # print('0xF9 in_board_address:', EEcomand)

                elif key[0:len(key)] == 'def_io_type':
                    value = self.D[board_address]['def_io_type']
                    EEcomand.append(0xFA)
                    EEcomand.extend(value)
                    if not '0xFA' in ll: ll.append('0xFA')
                    # print('0xFA def_io_type:', EEcomand)

                elif key[0:len(key)] == 'refresh_timeout':
                    value = self.D[board_address]['refresh_timeout']
                    EEcomand.append(0xFB)
                    EEcomand.extend(value)
                    if not '0xFB' in ll: ll.append('0xFB')
                    # print('0xFB refresh_timeout:', EEcomand)

                elif key[0:len(key)] == 'status_at_boot':
                    value = self.D[board_address]['status_at_boot']
                    EEcomand.append(0xFC)
                    EEcomand.extend(value)
                    if not '0xFC' in ll: ll.append('0xFC')
                    # print('0xFC status_at_boot:', EEcomand)

                elif key[0:len(key)] == 'io_timer':
                    value = self.D[board_address]['io_timer']
                    EEcomand.append(0xFE)
                    EEcomand.extend(value)
                    if not '0xFE' in ll: ll.append('0xFE')
                    # print('0xFE io_timer:', EEcomand)

                elif key[0:len(key)] == 'def_sensor_name':
                    value = self.D[board_address]['def_sensor_name']
                    EEcomand.append(0xF4)
                    EEcomand.extend(value)
                    if not '0xF4' in ll: ll.append('0xF4')
                    # print('0xFE io_timer:', EEcomand)

                elif key[0:len(key)] == 'sensor_refresh_timeout':
                    value = self.D[board_address]['sensor_refresh_timeout']
                    EEcomand.append(0xF3)
                    EEcomand.extend(value)
                    if not '0xF3' in ll: ll.append('0xF3')
                    # print('0xFE io_timer:', EEcomand)

                elif key[0:len(key)] == 'sensor_enable':
                    value = self.D[board_address]['sensor_enable']
                    EEcomand.append(0xF2)
                    EEcomand.extend(value)
                    if not '0xF2' in ll: ll.append('0xF2')
                    # print('0xFE io_timer:', EEcomand)

                if len(EEcomand) > 0 :
                    self.writeEE(board_address, EEcomand)

                EEcomand = []

            self.writeEE(board_address, [0xF5, 18]) # Setta a fine seq. 0
            self.writeEE(board_address, [0xF5, 19]) # Setta a fine seq. 0
            self.writeEE(board_address, [0xF5, 20]) # Setta a fine seq. 0

            self.arduinoReboot(board_address)

    def arduinoReboot(self, board_address):
        cmd = bytes([0x2A]) #primo carattere
        cmd += bytes([0x09]) #write EE
        cmd += bytes([board_address])
        crc = self.calcCheckSum(cmd)
        cmd += bytes([crc])
        cmd += bytes([0x0d, 0x0a])
        self.tx485(cmd)

    def getBoardReady(self):
        """
        Cerca se i dispositivi presenti in ZARD.conf sono attivi!!!
        """
        for i in self.deviceAddress:
            print("DEVICE pronti:", i, self.deviceReady)
            for x in range(10): # Prova varie volte a cercare i dispositivi presenti in ZARD.conf
                if i in self.deviceReady: # Salta se device presente
                    break
                self.txSend([11, i])
                time.sleep(0.005) # Importante
                rxComand =  self.rx485()
                # print("=>>",rxComand)
                if rxComand:
                    checkAck = self.calcCheckSum(rxComand[0:-3])
                    # print(rxComand, checkAck)
                    if len(rxComand) > 5 and (rxComand[-3] == checkAck) and rxComand[1] == 12:
                        if not rxComand[2] in self.deviceReady:
                            self.deviceReady.append( rxComand[2] )
                time.sleep(0.1)
            self.log.write("Dispositivi presenti: %s" %self.deviceReady)

    def deviceDomoticz(self):
        """
        Crea e mappa di device tra Domoticz e Arduino
        ***** NON IMPLEMENTATO ******
        """
        for k in self.config:
            if k[0:6] == "DEVICE":
                Zdef_io_type  = eval(self.config[k]['def_io_type'])

        l = len(Zdef_io_type) #Lenght list
        #for addr in range(l):
            #print(addr, end=" ")
        #print()
        print(Zdef_io_type)

        url = "type=devices&used=true&filter=all"
        d = self.sendURL(url)
        #for d1 in d:
            #print(d1)
        #print()
        pprint.pprint(d['status'])
        pprint.pprint(d['ServerTime'])
        pprint.pprint(d['ActTime'])
        pprint.pprint(d['Sunset'])
        pprint.pprint(d['Sunrise'])
        pprint.pprint(d['title'])
        print()

        for x in d['result']:
            pprint.pprint(x['idx'])
            if x['idx'] == '26':
                pprint.pprint(x)

    def clearEEPROM(self, address):
        cmd = bytes([0x2A]) # Primo carattere
        cmd += bytes([10]) # 6 = ACK
        cmd += bytes([address])
        crc = self.calcCheckSum(cmd)
        cmd += bytes([crc])
        cmd += bytes([0x0d, 0x0a])
        self.tx485(cmd)
        pass

    def txSend(self, *args):
        """
        Return formatted string to send by tx485
        """
        val = bytes([0x2A])
        for x in args[0]:
            val += bytes([x])
        crc = self.calcCheckSum(val)
        val += bytes([crc])
        val += bytes([0x0d])
        val += bytes([0x0a])
        # print(val)
        # self.log.write("tx485: %s" %val)
        self.tx485(val)

    def createUserVariables(self):
        """
        Crea le variabili su domoticz (una per ogni IO di zard). Vedi file configurazione
        """
        for board_address in self.D['board_address']:
            for Dname in self.D[board_address]['Dname']:
                res = self.addUserVariable(Dname, 'Integer', 0)
                res = self.sendURL(res)
                # print(res)

class Presence(Domoticz):

    def __init__(self):
        super().__init__()
        # a = self.getConfig()['PRESENCE']
        # print(a)
        self.presence = self.getConfig()['PRESENCE']
        self.P = {}
        self.getIP()
        self.process()

    def getIP(self):
        self.P.update({'n': [], 'ip': [], 'name': [], 'idx': []})
        x = 0
        for i in self.presence:
            if i[0:2] == 'ip':
                self.P['n'].append(x)
                x += 1
                self.P['ip'].append(self.presence[i])
            elif i[0:4] == 'name':
                self.P['name'].append(self.presence[i])
            elif i[0:3] == 'idx':
                self.P['idx'].append(self.presence[i])


    def process(self):
        import subprocess
        for x in self.P['n']:
            currentstate = subprocess.call('ping -q -c1 -W 1 '+ self.P['ip'][x] + ' > /dev/null', shell=True)
            if currentstate == 0: #IP present
                state = 1
                # print("IP:", self.P['ip'][x], " PRESENT", state)
                # url = self.sendInputOutput(self.P['idx'][x], state)
                url = "type=command&param=switchlight&idx=%s&switchcmd=%s" %(self.P['idx'][x], state)

            elif currentstate == 1: #IP NOT present
                state = 0
                # print("IP:", self.P['ip'][x], " NOT PRESENT", state)
                url = "type=command&param=switchlight&idx=%s&switchcmd=%s" %(self.P['idx'][x], state)
                # url = self.sendInputOutput(self.P['idx'][x], state)
            else:
                print("IP:", self.P['ip'][x], " UNDEFINED STATE", currentstate)
            res = self.sendURL(url)
            # print(res)

def cron():

    """
    Schedule usage:
    schedule.every(10).minutes.do(job)
    schedule.every().hour.do(job)
    schedule.every().day.at("10:30").do(job)
    schedule.every().monday.do(job)
    schedule.every().wednesday.at("13:15").do(job)
    """

    C = Config()
    log_filename = C.getLogFilename()
    log_dimension = C.getLogDimension()
    L = Log(log_filename, log_dimension)

    presence_timecheck = int(C.getConfig()['PRESENCE']['timecheck'])

    def cropFileLog():
        """
        Call crop from Log class. Delete lines
        """
        L.crop()
    cropFileLog()
    schedule.every().day.do(cropFileLog)

    def presence():
        """
        Call presence function
        """
        L.write("CRON presence")
        P = Presence()
    presence()
    schedule.every(presence_timecheck).seconds.do(presence)

    while 1:
        schedule.run_pending()
        time.sleep(1)


def receive():
    print('init loop.py')
    s = Domoticz()
    for x in range(1): # Cancella la EEPROM
        pass
        # s.clearEEPROM(4) #Per cancellare la EEPROM
    s.getBoardReady() # Popola la lista con le board attive
    s.createUserVariables() # Create user varialbes how Alarm4-1, Alarm4-2
    s.sendParameter() # Invia file configurazione ZARD.conf
    s.createUserVariables() # Crea le variabili su domoticz (una per ogni IO di zard)
    while 1:
        try:
            rxComand = s.rx485()
            if len(rxComand) == 0:
                continue
            # print("comand:", rxComand)
            crcPy = s.calcCheckSum(rxComand[0:-3])
            # print( "Comand:", s.ser.inWaiting(), s.rxComand, crcPy, s.rxComand[-3:-2] )
            if len(rxComand) > 2 and rxComand[-3:-2][0] == crcPy: # check is CRC is right
                print(rxComand)
                # print(s.D[4]['Znow'], s.D[5]['Znow'])
                try:
                    s.setComand(rxComand)
                except OSError as err:
                    print("OS error: {0}".format(err))
                    s.log.write("OS error: {0}".format(err))
                except ValueError:
                    print("Could not convert data to an integer.")
                    s.log.write("Could not convert data to an integer.")
                except:
                    print("Unexpected error:", sys.exc_info()[0])
                    s.log.write("Unexpected error: %s" %sys.exc_info()[0])
                    raise

                    # print(inst.args)     # arguments stored in .args
                    # print(inst)          # __str__ allows args to be printed directly,
        except OSError as err:
            print("OS error: {0}".format(err))
            s.log.write("OS error: {0}".format(err))
        except ValueError:
            s.log.write("Could not convert data to an integer.")
        except:
            s.log.write("Unexpected error: %s" %sys.exc_info()[0])
            raise

def send(argoment):
    """
    Funzione chiamata da Domoticz quando un IO cambia.
    Argoment: ID scheda, Nimero IO, stato IO
    """
    s = Domoticz()
    val = [13, int(argoment[1]), int(argoment[2]), int(argoment[3])]
    s.log.write("Request Modify IO form DOMOTICZ: %s" %val)
    s.txSend(val)
    return

def debug(argoment):
    D = Domoticz()
    # print(dir(D))

    #url = D.getStatusDeviceDomoticz(26)
    #print("url: ", url)

    #res = D.sendURL(url)
    #print(res)

    # s.serOpen()
    # s.sendParameter()

    # cmd =  '\x01'
    # cmd += '\x02'
    # cmd += '\x03'
    # cmd += '\xD8'
    # cmd += '\x0D'
    # cmd += '\x0A'
    # print cmd
    for i in range(10000):
        D.tx485(b'x01x02x03x04')
        print(i)

def serialRead():
    ser = serial.Serial(
        port='/dev/serial0',
        baudrate = 57600,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=1
    )
    counter=0
    while 1:
         x=ser.readline()
         print(x)


if __name__ == '__main__':
    argoment = sys.argv
    # print(argoment)
    if len(argoment) > 1:
        if argoment[1] == 'debug':
            debug(argoment)
        elif argoment[1] == 'serial': # Legge i dati dalla seriale
            serialRead()
        elif argoment[1] == 'Z': # Popola self.D e poi termina
            d = Domoticz()
        elif argoment[1] == 'V': # Get variablile from domoticz
            d = Domoticz()
            var = d.getUserVariable()
            print(var)
            a = d.sendURL(var)
            print(a)
            d.createUserVariables()
        else:
            send(argoment)
    else:
        import multiprocessing
        p = multiprocessing.Process(target=receive)
        p.start()
        p = multiprocessing.Process(target=cron)
        p.start()
