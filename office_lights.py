import my_appapi as appapi
             
class office_lights(appapi.my_appapi):

  def initialize(self):
    # self.LOGLEVEL="DEBUG"
    self.log("office_lights App")

    ######################### Values to move to config file or somewhere.
    self.light_max=50
    self.light_dim=25

    self.hi_temp=74
    self.lo_temp=70

    self.targets={"light.office_lights":{"triggers":{"light.office_lights":{"type":"light","bit":64,"onValue":"on"},
                                                        "sensor.office_door_access_control_4_9":{"type":"door","bit":2,"onValue":"on"},
                                                        "media_player.office_directv":{"type":"media","bit":16,"onValue":"playing"},
                                                        "input_boolean.officemotion":{"type":"motion","bit":4,"onValue":"on"},
                                                        "input_boolean.officeishomeoverride":{"type":"override","bit":1,"onValue":"on"}},
                                            "type":"light",
                                            "offState":[0,1,4,5,8,9,12,13,16,17,20,21,24,25,28,29,32,33,36,37,40,41,44,45,48,49,56,57,64,72,73,80,88,96,104,112,120],
                                            "dimState":[50,51,52,53,54,55,58,59,60,61,62,63,81,82,83,84,85,86,87,89,90,91,92,93,94,95,
                                                        114,115,116,117,118,119,122,123,124,125,126,127],
                                            "onState":[2,3,6,7,10,11,14,15,18,29,22,23,26,27,30,31,34,35,38,39,42,43,46,47,50,51,52,53,54,55,58,59,60,61,62,63,
                                                        65,66,67,68,69,70,71,74,75,76,77,78,79,81,82,83,84,85,86,87,89,90,91,92,93,94,95,97,98,99,100,101,102,103,
                                                        104,105,106,107,108,109,110,111,113,114,115,116,117,118,119,121,122,123,124,125,126,127],
                                            "callback":self.light_state_handler},
                 "light.office_fan":{"triggers":{"light.office_fan":{"type":"fan","bit":32,"onValue":"on"},
                                                     "sensor.office_sensor_temperature_11_1":{"type":"temperature","bit":8,"onValue":"on"},
                                                     "input_boolean.officeishomeoverride":{"type":"override","bit":1,"onValue":"on"}},
                                         "type":"fan",
                                         "onState":[8,9,10,11,12,13,14,15,24,25,26,27,28,29,30,31,33,35,37,39,40,41,42,43,44,45,46,47,49,51,53,55,56,57,58,59,60,61,62,
                                                    63,72,73,74,75,76,77,78,79,88,89,90,91,92,93,94,95,97,99,101,103,104,105,106,107,108,109,110,111,113,115,117,119,
                                                    120,121,122,123,124,125,126,127],
                                         "dimState":[0],
                                         "offState":[0,1,2,3,4,5,6,7,16,17,18,19,20,21,22,23,32,34,36,38,48,50,52,54,64,65,66,67,68,69,70,71,80,81,82,83,84,85,86,87,96,98,100,102,112,114,116,118],
                                         "callback":self.light_state_handler}}

    #################End of values to move to config file or somewhere.

    for ent in self.targets:
      for ent_trigger in self.targets[ent]["triggers"]:
        self.log("registering callback for {} on {} for target {}".format(ent_trigger,self.targets[ent]["callback"],ent))
        self.listen_state(self.targets[ent]["callback"],ent_trigger,target=ent)
      self.process_light_state(ent)      # process each light as we register a callback for it's triggers rather than wait for a trigger to fire first.


  ########   
  #
  # state change handler.  All it does is call process_light_state all the work is done there.
  #
  def light_state_handler(self,trigger,attr,old,new,kwargs):
    self.log("trigger = {}, attr={}, old={}, new={}, kwargs={}".format(trigger,attr,old,new,kwargs))
    self.process_light_state(kwargs["target"])

  ########
  #
  # process_light_state.  All the light processing happens in here.
  #
  def process_light_state(self,target,**kwargs):
    # build current state binary flag.
    state=0
    type_bits={}
    
    # here we are building a binary flag/mask that represents the current state of the triggers that impact our target light.
    # one bit for each trigger.
    # bits are assigned in targets dictionary.

    for trigger in self.targets[target]["triggers"]:      # loop through triggers
      trigger_type = self.targets[target]["triggers"][trigger]["type"]
      onValue = self.targets[target]["triggers"][trigger]["onValue"]
      bit = self.targets[target]["triggers"][trigger]["bit"]
      trigger_state = self.normalize_state(target,trigger,trigger_type)
    
      self.log("trigger={} type={} onValue={} bit={} currentvalue={}".format(trigger,trigger_type,onValue,bit,trigger_state))
      # or value for this trigger to existing state bits.
      state = state | ( bit if (trigger_state==onValue) else 0)
      self.log("state = {}".format(state))
      # typebits is a quick access array that takes the friendly type of the trigger and associates it with it's bit
      # it's just to make it easier to search later.
      type_bits[trigger_type]=bit
  

    self.log("state={}".format(state))
    if not state & type_bits["override"]:               # if the override bit is set, then don't evaluate anything else.  Think of it as manual mode.
      if state in self.targets[target]["offState"]:     # these states always result in light being turned off
        self.log("state = {} turning off light".format(state))
        self.turn_off(target)
      elif state in self.targets[target]["onState"]:    # these states always result in light being turned on.
        self.log("state = {} turning on light".format(state))
        if state in self.targets[target]["dimState"]:                      # when turning on lights, media player determines whether to dim or not.
          self.log("media player involved so dim lights")
          self.turn_on(target,brightness=self.light_dim)
        else:                                                   # it wasn't a media player dim situation so it's just a simple turn on the light.
          self.log("state={} turning on light".format(state))
          self.turn_on(target,brightness=self.light_max)
    else:
      self.log("home override set so no automations performed")

  #############
  #
  # normalize_state - take incoming states and convert any that are calculated to on/off values.
  #
  def normalize_state(self,target,trigger,type):
    newstate=self.get_state(trigger,type=type,min=self.lo_temp,max=self.hi_temp)
    self.log("{} newstate={}".format(trigger,newstate))
    if newstate==None:                   # handle a newstate of none, typically means the object didn't exist.
      newstate=self.get_state(target)    # if thats the case, just return the state of the target so nothing changes.
    try:
      currenttemp=int(float(newstate))
    except:
      a=0
    if newstate in ["home","house","Home","House"]:  # deal with having multiple versions of house and home to account for.
      newstate="home"
    elif newstate == "unk":
      newstate=self.get_state(target)
    return newstate
