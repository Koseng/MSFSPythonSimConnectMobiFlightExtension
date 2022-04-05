import logging, logging.handlers
from simconnect_mobiflight import SimConnectMobiFlight
from mobiflight_variable_requests import MobiFlightVariableRequests
from time import sleep

def setupLogging(logFileName):
    logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)
    fileHandler = logging.handlers.RotatingFileHandler(logFileName, maxBytes=500000, backupCount=7)
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

# MAIN
setupLogging("SimConnectMobiFlight.log")
sm = SimConnectMobiFlight()
vr = MobiFlightVariableRequests(sm)
vr.clear_sim_variables()

# Example write variable
vr.set("0 (>L:A32NX_COCKPIT_DOOR_LOCKED)")

while True:
    alt_ground = vr.get("(A:GROUND ALTITUDE,Meters)")
    alt_plane = vr.get("(A:PLANE ALTITUDE,Feet)")
    # FlyByWire A320
    ap1 = vr.get("(L:A32NX_AUTOPILOT_1_ACTIVE)")
    hdg = vr.get("(L:A32NX_AUTOPILOT_HEADING_SELECTED)")
    mode = vr.get("(L:A32NX_FMA_LATERAL_MODE)")
    sleep(1)