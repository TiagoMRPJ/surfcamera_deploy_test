import db
import serial
import time
from serial.tools import list_ports


'''
Defines a lower level class to handle communication between the Raspberry Pi and the control electronics which handle the front IO
and communication bridge with the servos.

'''

PAN_GEAR_RATIO = 40
TILT_GEAR_RATIO = 5.6
MAX_PAN_ANGLE = 70 # degrees each WAY from zero
MAX_TILT_ANGLE = 25 # degrees DOWN from zero
DEG_PULSE = 0.088 # 360 degrees is 4096 pulses, so 1 degree is 11.37777 pulses

# This is due to the camera assembly onto the motor.
TILT_OFFSET = 0 # Empyrical offset to get mechanical 0 closer to real 0: manual calibration is stil needed through control panel  

def get_op_codes():
        '''
        Returns a dictionary with different possible operations to ESP32 and respective code ex: 'Firmware':0x20
        '''
        return {
            "Firmware":0x20,
            "Dynamixel Write":0x50,
            "Dynamixel Read":0x51,
            "Group Dynamixel Write":0x56,
            "Group Dynamixel Read":0x57,
            "Bulk Dynamixel Read":0x58,
            "Bulk Temperature Read":0x59,
            "Set Shutdown":0x60,
            "Get Shutdown&PushButton":0x61,
            "Set BackPanel LEDs":0x62,
            "Get Mac Address":0x63,
            "Get Hall Status":0x64,
            "Get Tracker Message":0x65,
            "Start Tracker Pairing":0x66,
            "Check Tracker Pairing":0x67,
            "Cancel Current Pairing":0x68,
            "Reboot both Dynamixel":0x69,
        }

class FrontBoardDriver:
    def __init__(self):
        conn = db.get_connection()
        self.gps_points = db.GPSData(conn)
        self.command_codes = get_op_codes()
        connected = False
        while not connected:
            ports = serial.tools.list_ports.comports()
            print("Searching for GPIO Front Board ")
            for port in ports:
                if "Surf Front Board" in port.description:
                    try:
                        self.serial = serial.Serial(port.device, baudrate=1000000, timeout=2.0)
                        connected = True
                        print("ESP CONNECTED")
                    except Exception as e:
                        print(f"Connection error: {e}")
            time.sleep(0.1)
        
        self.setBackPanelLEDs(False, False)
        self.dynamixelWrite(1, 10, 1)
        self.dynamixelWrite(2, 10, 0)    # Pan drive mode to velocity profile 
        self.setTiltPID(1000, 200, 800)
        self.dynamixelWrite(1, 108, 20) # Set Tilt profile acceleration 
        self.turnOnTorque()
        self.setTiltAngle(0, 1) 
        time.sleep(1)
        
        self.PanCenterPulse = self.dynamixelRead(2, 132) 
        self.current_pan_mode = ""
        
        self.tiltIntendedPlayTime = 0.75
        self.panIntendedPlayTime = 0.5 # How much time we want each pan movement to take  
        
        self.lastLat = 0
        self.lastLon = 0
        
        self.calibratePanCenter()
        
    def send_message(self, msg):
        """
            Writes a pre-built Message to the serial port and checks for successful transmission
            Returns: [True]
            Receives: [0xff ,0xff ,op_code ,data_lenght ,data ,high_value ,low_value]
        """      
        sent_msg = self.serial.write(msg)

        if (sent_msg != len(msg)):
            err_msg = "Error writing message to buffer (sent {} bytes of {})".format(sent_msg, len(msg))
            raise Exception("send_message()", err_msg)   
        
        return True
    
    def parsing_message(self):
        """
            Reads serial port data and parses the returned message
            Returns: [0xff ,0xff ,op_code ,data_lenght ,data ,high_value ,low_value]
            Receives: 
        """
        header = self.serial.read(2)                              # HEADERS (0xff, 0xff)
        
        if len(header) < 2 or header[:2] != b'\xff\xff' :         # Check if header corresponds to expected
            err_msg = "Error with headers {}".format(header)
            raise Exception("parsing_message()", err_msg)
        
        op_code = self.serial.read(1)                             #OP_CODE  

        data_len = self.serial.read(2)                            #DATA_LENGTH      
        if data_len[1] > 255:
            err_msg = "Data Length exceeded (received {})".format(data_len)
            raise Exception("parsing_message()", err_msg)
                
        if data_len[1] > 0:
            data = self.serial.read(data_len[1])                  #DATA    

        high_value = self.serial.read(1)                          #MSB
        low_value = self.serial.read(1)                           #LSB   

        if data_len[1] > 0:
            read_message = header + op_code + data_len + data + high_value + low_value

        else:
            read_message = header + op_code + data_len + high_value + low_value

        return read_message
 
    def read_message(self, msg):
        """
            Verifies if the parsed message is valid and returns just the data portion 
            Returns: [data]
            Receives: [read_message] 
        """
        cmd_buffer = self.parsing_message()

        checksum = int.from_bytes((cmd_buffer[-2:]))
        bytesum = sum(cmd_buffer[2:-2])
        
        if sum(cmd_buffer[:2]) == sum(msg[:2]) and bytesum == checksum:
            return cmd_buffer[4:-2]    # [data]
        else: 
            err_msg = "Error with response validity {}".format(cmd_buffer)
            raise Exception("read_message()", err_msg)
        
    def build_message(self, op_code, data=[ ]):
        """
            Build a Message Respecting Communication Protocol with the Board
            Sending Message Structure: [0xff ,0xff ,op_code ,data_lenght ,data ,high_chksum ,low_chksum]
            Receiving Message Structure: [op_code][data]
        """
        msg = [0xff, 0xff]
        
        if op_code not in self.command_codes.values():
            err_msg = "Incorrect op_code (received {})".format(op_code)
            raise Exception("build_message()", err_msg)
        
        if len(data) > 255:
            err_msg = "Data Length exceeded (received {})".format(len(data))
            raise Exception("build_message()", err_msg)

        msg.append(op_code)
        msg.append(0) # high byte is always 0
        msg.append(len(data))

        for d in data:
            msg.append(d)

        chk = sum(msg[2:])
        chk_low = chk & 0xff
        chk_high = (chk >> 8) & 0xff
        msg.append(chk_high)
        msg.append(chk_low)
        return msg   
        
    def bsr_message(self, op_code, data):
        """
            Build, Send and Read Message
            Send: [data]
            Receives: [op_code] [data]
        """
        try:
            msg = self.build_message(op_code, data)
            self.send_message(msg)
            time.sleep(0.01)
            read_msg = self.read_message(msg)
            return read_msg
        except Exception as e:
            print(f"Error in comm with front board {e} ")
        
    def getFirmware(self):
        return self.bsr_message(0x20, [])
    
    def setBackPanelLEDs(self, first = False, second = False):
        if not first and not second:
            self.bsr_message(self.command_codes["Set BackPanel LEDs"], [0x00])
        elif first and not second:
            self.bsr_message(self.command_codes["Set BackPanel LEDs"], [0x01])
        elif not first and second:
            self.bsr_message(self.command_codes["Set BackPanel LEDs"], [0x02])    
        else:
            self.bsr_message(self.command_codes["Set BackPanel LEDs"], [0x03])
        
    def getShutdownState(self):
        response = self.bsr_message(self.command_codes["Get Shutdown&PushButton"], [])
        msg = int.from_bytes(response, byteorder='big')
        # Extracting the last 2 bits
        last_2_bits = msg & 0b11

        # Extracting individual bits
        ButtonPressed = (msg >> 1) & 1  # Extracting the second last bit
        ShutdownSequence = msg & 1          # Extracting the last bit
        #print(f"Is the button pressed: {ButtonPressed} and Is Shutting Down?: {ShutdownSequence}")
        return ShutdownSequence
    
    def setShutdown(self, seconds=15):
        bytes_val = seconds.to_bytes(2, 'little') 
        self.bsr_message(self.command_codes["Set Shutdown"], [bytes_val])
        time.sleep(0.05)
        
    def bulkReadTemp(self):
        response = self.bsr_message(self.command_codes["Bulk Temperature Read"], [0x00])
        nReadings = response[0]
        IDTILT = response[1]
        ERRORTILT = response[2]
        TEMPTILT = response[3]
        IDPAN = response[4]
        ERRORPAN = response[5]
        TEMPPAN = response[6]
        print(f"Motor {IDTILT} has {ERRORTILT} errors and Temp {TEMPTILT} C")
        print(f"Motor {IDPAN} has {ERRORPAN} errors and Temp {TEMPPAN} C")
        return TEMPTILT, TEMPPAN
        
    def bulkReadPosVel(self):
        response = self.bsr_message(self.command_codes["Bulk Dynamixel Read"], [0x00])
        nLen = response[0]
        IDTILT = response[1]
        ERRORTILT = response[2]
        
        tiltpos_h = response[3]
        tiltpos_l = response[4]
        bytelist = [tiltpos_h, tiltpos_l]
        tiltpos_int = int.from_bytes(bytearray(bytelist), "big")
        
        tiltvel_h = response[5]
        tiltvel_l = response[6]
        bytelist = [tiltvel_h, tiltvel_l]
        tiltvel_int = int.from_bytes(bytearray(bytelist), "big")
        
        IDPAN = response[7]
        ERRORPAN = response[8]
        
        panpos_h = response[9]
        panpos_l = response[10]
        bytelist = [panpos_h, panpos_l]
        panpos_int = int.from_bytes(bytearray(bytelist), "big")
        
        panvel_h = response[11]
        panvel_l = response[12]
        bytelist = [panvel_h, panvel_l]
        panvel_int = int.from_bytes(bytearray(bytelist), "big")
        
        return tiltpos_int, tiltvel_int, panpos_int, panvel_int        
        
    def dynamixelRead(self, ID,  ADDR):
        ADDR_bytes = ADDR.to_bytes(2, byteorder="little")
        ADDR_H = ADDR_bytes[1]
        ADDR_L = ADDR_bytes[0]
        data2send = bytearray([ID, ADDR_H, ADDR_L])
        response = self.bsr_message(self.command_codes["Dynamixel Read"], data2send)
        
        data_bytes = response[-4:]
        result = int.from_bytes(data_bytes, byteorder='big', signed=True)
        return result
        
    def dynamixelWrite(self, ID, ADDR, data):
        ADDR_bytes = ADDR.to_bytes(2, byteorder="little")
        ADDR_H = ADDR_bytes[1]
        ADDR_L = ADDR_bytes[0]
        
        data_bytes = data.to_bytes(4, byteorder='little', signed=True)
        # Extract Data bytes
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        
        data2send = bytearray([ID, ADDR_H, ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        response = self.bsr_message(self.command_codes["Dynamixel Write"], data2send)
        
    def turnOnTorque(self):
        ID1 = 0x01
        ID2 = 0x02
        
        ADDR = 64
        data = 1
        
        ADDR_bytes = ADDR.to_bytes(2, byteorder="little")
        ADDR_H = ADDR_bytes[1]
        ADDR_L = ADDR_bytes[0]
        
        data_bytes = data.to_bytes(4, byteorder='little')
        # Extract Data bytes
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        
        NCOMMANDS = 2
        
        data2send = bytearray([NCOMMANDS, ID1, ADDR_H, ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0, ID2, ADDR_H, ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        response = self.bsr_message(self.command_codes["Group Dynamixel Write"], data2send)
        #print("Torque Turned ON on both Axis")
        
    def turnOffTorque(self):
        ID1 = 0x01
        ID2 = 0x02
        
        ADDR = 64
        data = 0
        
        ADDR_bytes = ADDR.to_bytes(2, byteorder="little")
        ADDR_H = ADDR_bytes[1]
        ADDR_L = ADDR_bytes[0]
        
        data_bytes = data.to_bytes(4, byteorder='little')
        # Extract Data bytes
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        
        data2send = bytearray([2, ID1, ADDR_H, ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0, ID2, ADDR_H, ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        response = self.bsr_message(self.command_codes["Group Dynamixel Write"], data2send)
        #print("Torque Turned OFF on both Axis")
        
    def getPanPID(self):
        ADDR = [80, 82, 84]
        NCOMMANDS = 3
        ID = 2
        msg = [NCOMMANDS]
        
        for addr in ADDR:
            ADDR_bytes = addr.to_bytes(2, byteorder="little")
            ADDR_H = ADDR_bytes[1]
            ADDR_L = ADDR_bytes[0]
            msg.extend([ID, ADDR_H, ADDR_L])
            
        data2send = bytearray(msg)
        response = self.bsr_message(self.command_codes["Group Dynamixel Read"], data2send)
        
        D = int.from_bytes(response[1:5], byteorder='big')
        I = int.from_bytes(response[5:9], byteorder='big')
        P = int.from_bytes(response[9:13], byteorder='big')
        
        print("     Pan PID Parameters")
        print(f"    P: {P}   I: {I}   D: {D}")
        
        return P, I, D
    
    def getPanVelocityPI(self):
        ADDR = [76, 78]
        NCOMMANDS = 2
        ID = 2
        msg = [NCOMMANDS]
        
        for addr in ADDR:
            ADDR_bytes = addr.to_bytes(2, byteorder="little")
            ADDR_H = ADDR_bytes[1]
            ADDR_L = ADDR_bytes[0]
            msg.extend([ID, ADDR_H, ADDR_L])
            
        data2send = bytearray(msg)
        response = self.bsr_message(self.command_codes["Group Dynamixel Read"], data2send)
        
        I = int.from_bytes(response[1:5], byteorder='big')
        P = int.from_bytes(response[5:9], byteorder='big')
        
        print("     Pan Velocity PI Parameters")
        print(f"    P: {P}   I: {I}   ")
        
        return P, I
    
    def getTiltPID(self):
        ADDR = [80, 82, 84]
        NCOMMANDS = 3
        ID = 1
        msg = [NCOMMANDS]
        
        for addr in ADDR:
            ADDR_bytes = addr.to_bytes(2, byteorder="little")
            ADDR_H = ADDR_bytes[1]
            ADDR_L = ADDR_bytes[0]
            msg.extend([ID, ADDR_H, ADDR_L])
            
        data2send = bytearray(msg)
        response = self.bsr_message(self.command_codes["Group Dynamixel Read"], data2send)
        
        D = int.from_bytes(response[1:5], byteorder='big')
        I = int.from_bytes(response[5:9], byteorder='big')
        P = int.from_bytes(response[9:13], byteorder='big')
        
        print("     Tilt PID Parameters")
        print(f"    P: {P}   I: {I}   D: {D}")
        
        return P, I, D
            
    def setPanPID(self, P, I, D):
        ID = 2
        NCOMMANDS = 3
        msg = [NCOMMANDS]
        
        ADDR = [84, 82, 80]
        
        P_ADDR_BYTES = ADDR[0].to_bytes(2, byteorder="little")
        P_ADDR_H = P_ADDR_BYTES[1]
        P_ADDR_L = P_ADDR_BYTES[0]
        data_bytes = P.to_bytes(4, byteorder="little")
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        msg.extend([ID, P_ADDR_H, P_ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        
        I_ADDR_BYTES = ADDR[1].to_bytes(2, byteorder="little")
        I_ADDR_H = I_ADDR_BYTES[1]
        I_ADDR_L = I_ADDR_BYTES[0]
        data_bytes = I.to_bytes(4, byteorder="little")
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        msg.extend([ID, I_ADDR_H, I_ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        
        D_ADDR_BYTES = ADDR[2].to_bytes(2, byteorder="little")
        D_ADDR_H = D_ADDR_BYTES[1]
        D_ADDR_L = D_ADDR_BYTES[0]
        data_bytes = D.to_bytes(4, byteorder="little")
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        msg.extend([ID, D_ADDR_H, D_ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        
        data2send = bytearray(msg)
        response = self.bsr_message(self.command_codes["Group Dynamixel Write"], data2send)
        #print("Pan PID Parameters Updated")
        
    def setPanVelocityPI(self, P, I):
        ID = 2
        NCOMMANDS = 2
        msg = [NCOMMANDS]
        
        ADDR = [78, 76]
        
        P_ADDR_BYTES = ADDR[0].to_bytes(2, byteorder="little")
        P_ADDR_H = P_ADDR_BYTES[1]
        P_ADDR_L = P_ADDR_BYTES[0]
        data_bytes = P.to_bytes(4, byteorder="little")
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        msg.extend([ID, P_ADDR_H, P_ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        
        I_ADDR_BYTES = ADDR[1].to_bytes(2, byteorder="little")
        I_ADDR_H = I_ADDR_BYTES[1]
        I_ADDR_L = I_ADDR_BYTES[0]
        data_bytes = I.to_bytes(4, byteorder="little")
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        msg.extend([ID, I_ADDR_H, I_ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        
        data2send = bytearray(msg)
        response = self.bsr_message(self.command_codes["Group Dynamixel Write"], data2send)
        #print("Pan PID Parameters Updated")

    def setTiltPID(self, P, I, D):
        ID = 1
        NCOMMANDS = 3
        msg = [NCOMMANDS]
        
        ADDR = [84, 82, 80]
        
        P_ADDR_BYTES = ADDR[0].to_bytes(2, byteorder="little")
        P_ADDR_H = P_ADDR_BYTES[1]
        P_ADDR_L = P_ADDR_BYTES[0]
        data_bytes = P.to_bytes(4, byteorder="little")
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        msg.extend([ID, P_ADDR_H, P_ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        
        I_ADDR_BYTES = ADDR[1].to_bytes(2, byteorder="little")
        I_ADDR_H = I_ADDR_BYTES[1]
        I_ADDR_L = I_ADDR_BYTES[0]
        data_bytes = I.to_bytes(4, byteorder="little")
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        msg.extend([ID, I_ADDR_H, I_ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        
        D_ADDR_BYTES = ADDR[2].to_bytes(2, byteorder="little")
        D_ADDR_H = D_ADDR_BYTES[1]
        D_ADDR_L = D_ADDR_BYTES[0]
        data_bytes = D.to_bytes(4, byteorder="little")
        data_31_24 = data_bytes[3]
        data_23_16 = data_bytes[2]
        data_15_8 = data_bytes[1]
        data_7_0 = data_bytes[0]
        msg.extend([ID, D_ADDR_H, D_ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
        
        data2send = bytearray(msg)
        response = self.bsr_message(self.command_codes["Group Dynamixel Write"], data2send)
        #print("Tilt PID Parameters Updated")
        
    def int_to_signed_bytes(self, value, length):
        # Check if the integer is negative
        if value < 0:
            # Calculate the two's complement of the negative number
            value = (1 << (length * 8)) + value
        return value.to_bytes(length, byteorder='little')

    def groupDynamixelSetPosition(self, tiltpos=None, tiltvel=None, panpos=None, panvel=None):
        NCOMMANDS = 0
        msg = []
        if tiltpos:
            ID = 1
            ADDR = 116
            ADDR_BYTES = ADDR.to_bytes(2, byteorder="little")
            ADDR_H = ADDR_BYTES[1]
            ADDR_L = ADDR_BYTES[0]
            data_bytes = tiltpos.to_bytes(4, byteorder="little")
            data_31_24 = data_bytes[3]
            data_23_16 = data_bytes[2]
            data_15_8 = data_bytes[1]
            data_7_0 = data_bytes[0]
            msg.extend([ID, ADDR_H, ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
            NCOMMANDS += 1
        if tiltvel:
            ID = 1
            ADDR = 112
            ADDR_BYTES = ADDR.to_bytes(2, byteorder="little")
            ADDR_H = ADDR_BYTES[1]
            ADDR_L = ADDR_BYTES[0]
            data_bytes = tiltvel.to_bytes(4, byteorder="little")
            data_31_24 = data_bytes[3]
            data_23_16 = data_bytes[2]
            data_15_8 = data_bytes[1]
            data_7_0 = data_bytes[0]
            msg.extend([ID, ADDR_H, ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
            NCOMMANDS += 1
        if panpos:
            ID = 2
            ADDR = 116
            ADDR_BYTES = ADDR.to_bytes(2, byteorder="little")
            ADDR_H = ADDR_BYTES[1]
            ADDR_L = ADDR_BYTES[0]
            data_bytes = panpos.to_bytes(4, byteorder="little", signed=True)
            data_31_24 = data_bytes[3]
            data_23_16 = data_bytes[2]
            data_15_8 = data_bytes[1]
            data_7_0 = data_bytes[0]
            msg.extend([ID, ADDR_H, ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
            NCOMMANDS += 1
        if panvel:
            ID = 2
            ADDR = 112
            ADDR_BYTES = ADDR.to_bytes(2, byteorder="little")
            ADDR_H = ADDR_BYTES[1]
            ADDR_L = ADDR_BYTES[0]
            data_bytes = panvel.to_bytes(4, byteorder="little")
            data_31_24 = data_bytes[3]
            data_23_16 = data_bytes[2]
            data_15_8 = data_bytes[1]
            data_7_0 = data_bytes[0]
            msg.extend([ID, ADDR_H, ADDR_L, data_31_24, data_23_16, data_15_8, data_7_0])
            NCOMMANDS += 1
            
        if NCOMMANDS > 0:
            msg.insert(0, NCOMMANDS)
            data2send = bytearray(msg)
            response = self.bsr_message(self.command_codes["Group Dynamixel Write"], data2send)
        else:
            return

    def setAngles(self, pan, tilt, pan_speed=None, tilt_speed=None):        

        pan = min(max(-MAX_PAN_ANGLE, pan), MAX_PAN_ANGLE)
        tilt = min(max(0, tilt), MAX_TILT_ANGLE)
        
        tilt_output_min = 750 # Tilt servo pulse posiition at 0 degrees
        tilt_output_max = tilt_output_min + TILT_GEAR_RATIO * MAX_TILT_ANGLE / DEG_PULSE # Tilt servo pulse position at max tilt angle 

        pan_dynamixel_value = int(round(pan * PAN_GEAR_RATIO / DEG_PULSE) + self.PanCenterPulse)
        tilt_dynamixel_value = int(round(tilt * (tilt_output_max - tilt_output_min) / MAX_TILT_ANGLE + tilt_output_min))

        if pan_speed:   # If pan_speed value is provided, use the given value
            pan_speed = pan_speed
        else:           # If not pan_speed value is provided, calculate the speed to achieve the desired playtime
            anglediff = pan - self.getCurrentPanAngle()
            pan_speed = anglediff / self.panIntendedPlayTime
        pan_speed = min(abs(pan_speed), 2) #max pan speed
            
        if tilt_speed:
            tilt_speed = tilt_speed
        else:
            anglediff = tilt - self.lastTiltAngle
            tilt_speed = anglediff / self.tiltIntendedPlayTime
        tilt_speed = min(abs(tilt_speed), 2) #max tilt speed

        self.lastTiltAngle = tilt
        self.groupDynamixelSetPosition(panpos = pan_dynamixel_value, tiltpos = tilt_dynamixel_value, panvel=self.toDynamixelVelocity(pan_speed * PAN_GEAR_RATIO), tiltvel=self.toDynamixelVelocity(tilt_speed * TILT_GEAR_RATIO))
        return True
    
    def setTiltAngle(self, tilt, tilt_speed = None):    
        tilt = min(max(0, tilt), MAX_TILT_ANGLE)
        tilt_output_min = 750 # Tilt servo pulse posiition at 0 degrees
        tilt_output_max = tilt_output_min + TILT_GEAR_RATIO * MAX_TILT_ANGLE / DEG_PULSE # Tilt servo pulse position at max tilt angle 
        tilt_dynamixel_value = int(round(tilt * (tilt_output_max - tilt_output_min) / MAX_TILT_ANGLE + tilt_output_min))

        if tilt_speed:
            tilt_speed = tilt_speed
        else:
            anglediff = tilt - self.lastTiltAngle
            tilt_speed = anglediff / self.tiltIntendedPlayTime
        tilt_speed = min(abs(tilt_speed), 2)
        
        self.lastTiltAngle = tilt
        self.dynamixelWrite(1, 112, self.toDynamixelVelocity(tilt_speed * TILT_GEAR_RATIO ))   # Set profile velocity
        self.dynamixelWrite(1, 116, tilt_dynamixel_value)                                      # Set angle
            
    def toDynamixelVelocity(self, degrees_per_second):
        ''' Takes a velocity in º/s and converts it to the dynamixel units (integer multiples of 0.229 rpm) '''
        to_rpm = degrees_per_second / 6 
        unit = 0.229 # Dynamixel base unit in RPM. The servos work in integer multiples of this value
        dynamixel_val = to_rpm / unit
        dynamixel_val = max(min(abs(dynamixel_val), 2047), 0) # value range is 0 to 2047, but value will be limited by the velocity limit
        if degrees_per_second < 0:
            return -round(dynamixel_val) 
        return round(dynamixel_val)
    
    def setPanVelocityControl(self, velocityLimit = 4):  
        if self.current_pan_mode != "velocity":
            self.current_pan_mode = "velocity"
            self.dynamixelWrite(2, 64, 0)   # Turn OFF pan torque
            self.setPanGoalVelocity(0)
            self.dynamixelWrite(2, 11, 1)   # Set operating Mode (11) to Velocity Mode (1)
            dyna_val = self.toDynamixelVelocity(velocityLimit * PAN_GEAR_RATIO) # Max speed of the motor: 250/40 ~ 6º/s pan speed
            self.dynamixelWrite(2, 44, dyna_val)    # Set Velocity Limit (44)
            self.setPanVelocityPI(160, 1600)
            self.dynamixelWrite(2, 108, 40)  # Set profile acceleration 
            self.dynamixelWrite(2, 64, 1)   # Turn ON the torque on the pan motor
        
    def setPanPositionControl(self):
        if self.current_pan_mode != "position":
            self.current_pan_mode = "position"
            self.dynamixelWrite(2, 64, 0)   # Turn OFF pan torque
            self.setPanGoalVelocity(0)
            self.dynamixelWrite(2, 11, 4)  # Set operating mode to Extended position
            self.setPanPID(400, 0, 100) 
            self.dynamixelWrite(2, 108, 40) # Set profile acceleration 
            self.dynamixelWrite(2, 64, 1)
            
    def setPanProfileVelocity(self, velocity):
        dval = self.toDynamixelVelocity(velocity * PAN_GEAR_RATIO)
        self.dynamixelWrite(2, 112, dval)
        
    def setPanGoalVelocity(self, degreespersecond):
        ''' Sets the camera pan rotation speed in º/s when in velocity control mode'''
        dyna_val = self.toDynamixelVelocity(degreespersecond * PAN_GEAR_RATIO)
        self.dynamixelWrite(2, 104, dyna_val)    # Set Goal Velocity (104)
        
    def getCurrentPanAngle(self):
        currentpulse = self.dynamixelRead(2, 132) 
        dif = currentpulse - self.PanCenterPulse
        angle = dif * 90 / 1024 / 40
        return round(angle, 2)
        
    def getMacAddress(self):
        return self.bsr_message(0x63, [])
    
    def getHallStatus(self):
        return self.bsr_message(0x64, [])
    
    def getTrackerMessage(self):
        response = self.bsr_message(0x65, [])
        if not response:
            return 0
        if response[0] == 0x08:
            lat = int.from_bytes(response[1:5], byteorder='little', signed=True) / 10000000 # Coordinates are sent with a scale factor to eliminate decimal places to reduce the nr of bytes
            lon = int.from_bytes(response[5:9], byteorder='little', signed=True) / 10000000
            if self.isValidGPSData(lat, lon):
                if lat != self.lastLat or lon != self.lastLon:
                    position = {"latitude": float(lat), "longitude": float(lon)}
                    self.gps_points.latest_gps_data = position
                    self.lastLat = lat
                    self.lastLon = lon
                    return 1
        else:
            # No valid GPS data
            return 0
            
    def isValidGPSData(self, lat, lon):
        if int(lat) == 38 and int(lon) == -9: # This means the incoming data is valid gps data with proper lock (PT Lisbon Area)
            return True
        else:
            return False
        
    def startTrackerPairing(self):
        response = self.bsr_message(0x66, [])
        if response[0] == 0x01:
            if response[1] == 0x01:
                return 1
            else:
                return 0
        else:
            return 0
        
    def checkTrackerPairing(self):
        """ 
        byte[1] = 0x01 if camera is paired, 0x00 if not paired 
        byte[2] = 0x01 if camera is pairing, 0x00 if not pairing
        """
        response = self.bsr_message(0x67, [])
        if response[0] == 0x02:
            return response[1], response[2]

    def cancelTrackerPairing(self):
        response = self.bsr_message(0x68, [])        
        if response[1] == 0x01:
            return 1
        else:
            return 0
        
    def rebootDynamixel(self):
        response = self.bsr_message(0x69, [])
        # now we need to reapply configurations
        self.dynamixelWrite(2, 10, 0)    # Pan drive mode to velocity profile 
        self.setTiltPID(1000, 200, 800)
        self.dynamixelWrite(1, 108, 20) # Set Tilt profile acceleration 
        self.current_pan_mode = ""
        self.setPanPositionControl()
        
    def calibratePanCenter(self):
        print("Calibrating Pan Center. Please do not move the camera.")
        # Start rotating faster and we will slowdown 
        initial_speed = 6
        self.setPanPositionControl() # First we try to go to position mode so we are sure velocity control overrides the new speed
        self.setPanVelocityControl(initial_speed) # Temporarily override the velocity limit
        self.setPanGoalVelocity(initial_speed) # Rotate slowly to the right
        # Timeout for searching 
        start = time.time()
        while self.getHallStatus()[1] == 1:
            time.sleep(0.05)
            new_speed = initial_speed - (time.time() - start) / 10 # Decrease speed by 0.1 every second
            new_speed = max(new_speed, 1.5)
            self.setPanGoalVelocity(new_speed)
            if time.time() - start >= 130: # If a minute passes and cant find the sensor, stop trying
                print("Timeout reached. Could not find Hall Effect Sensor")
                self.setPanGoalVelocity(0)
                return False
            
        print("Right Hall Effect Sensor Triggered")
        self.setPanGoalVelocity(0)
        self.PanCenterPulse = self.dynamixelRead(2, 132)
        time.sleep(0.5)
        self.setPanPositionControl()
        self.setPanAngle(-120, 10) # This will move us back to the mechanical center position (120 degrees offset between sensor and mechanical 0)
        # Wait until position is reached
        time.sleep(1)
        wait_start = time.time()
        while True:
            velocity = abs(self.dynamixelRead(2, 128))
            print(f"Waiting to reach center position. Current Velocity: {velocity}")
            if velocity <= 2:
                break
            if time.time() - wait_start > 25:  # 15s safety
                print("Warning: servo did not settle in time")
                self.setPanVelocityControl()
                self.setPanGoalVelocity(0)
                break
            time.sleep(0.1)
        self.PanCenterPulse = self.dynamixelRead(2, 132)
        self.setTiltAngle(0, 1)
        print(f"Pan Center Calibrated. New Center Pulse: {self.PanCenterPulse}")
        return True
        
    def setPanAngle(self, angle, speed=None):
        # Function to set pan angle bypassing the min/max limits
        deg_pulse = 0.088 # 360 degrees is 4096 pulses, so 1 degree is 11.37777 pulses
        pan_dynamixel_value = self.PanCenterPulse + round(angle * PAN_GEAR_RATIO / deg_pulse )
        if speed:
            speed = speed
        else:
            speed = 1
        speed = min(abs(speed), 10)
        #print(f"Setting Pan to {angle} degrees at speed {speed}º/s")
        #print(f"Center Pulse: {self.PanCenterPulse}")
        #print(f"Current Dynamixel Value: {self.dynamixelRead(2, 132)}")
        #print(f"Pan Dynamixel Value: {pan_dynamixel_value}")
        self.dynamixelWrite(2, 112, self.toDynamixelVelocity(speed * PAN_GEAR_RATIO)) # Set the speed
        self.dynamixelWrite(2, 116, pan_dynamixel_value) # Set the angle
        return True    
        
def testAutoPairing():        
    io = FrontBoardDriver()

    io.cancelTrackerPairing()

    io.checkTrackerPairing()
    io.startTrackerPairing()

    paired, pairing = io.checkTrackerPairing()
    print(paired)
    print(pairing)
    while not paired:
        time.sleep(1)
        paired, pairing = io.checkTrackerPairing()
        print(f"Paired: {paired} Pairing: {pairing}")
        
    while paired:
        time.sleep(0.1)
        io.getTrackerMessage()
 
#testAutoPairing()

#io = FrontBoardDriver()
#io.calibratePanCenter()

#while True:
#    print(io.getHallStatus())
#    time.sleep(0.5)



        
