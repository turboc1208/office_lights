import my_appapi as appapi

class office_lights(appapi.my_appapi):

  def initialize(self):
    # self.LOGLEVEL="DEBUG"
    self.log("office_lights App")
    self.fan=["off",0]
    if "targets" in self.args:
      self.targets=eval(self.args["targets"])
    else:
      self.log("targets must be defined in appdaemon.yaml file")
    if "light_max" in self.args:
      self.light_max=self.args["light_max"]
    else:
      self.light_max=254
    if "light_dim" in self.args:
      self.light_dim = self.args["light_dim"]
    else:
      self.light_dim=128
    if "light_off" in self.args:
      self.light_off=self.args["light_off"]
    else:
      self.light_off=0
    if "fan_max" in self.args:
      self.fan_high = self.args["fan_high"]
    else:
      self.fan_high=254
    if "fan_med" in self.args:
      self.fan_med = self.args["fan_med"]
    else:
      self.fan_med=128
    if "fan_low" in self.args:
      self.fan_low=self.args["fan_low"]
    else:
      self.fan_low=64

    self.fan_high_speed="high"
    self.fan_medium_speed="medium"
    self.fan_low_speed="low"

    if "fan_off" in self.args:
      self.fan_off=self.args["fan_off"]
    else:
      self.fan_off=0

    if "high_temp" in self.args:
      self.high_temp=self.args["high_temp"]
    else:
      self.high_temp=74
    if "low_temp" in self.args:
      self.low_temp=self.args["low_temp"]
    else:
      self.low_temp=68
    
    if "high_humidity" in self.args:
      self.high_humidity=self.args["high_humidity"]
    else:
      self.high_humidity=60
    if "low_humidity" in self.args:
      self.low_humidity=self.args["low_humidity"]
    else:
      self.low_humidity=59

    if "fan_on_speed" in self.args:
      try:
        #we got a numeric value
        sfo=int(float(self.args["fan_on_speed"]))
        if (self.fan_on>self.fan_medium):
          sfos=self.fan_high_speed
        elif (self.fan_on>self.fan_low):
          sfos=self.fan_medium_speed
        else:
          sfos=self.fan_low_speed
      except:
        sfos=self.args["fan_on_speed"]
        if (sfos==self.fan_high_speed):
          sfo=self.fan_high
        elif (sfos==self.fan_medium_speed):
          sfo=self.fan_med
        else: 
          sfo=self.fan_low
    else:
      sfo=self.fan_med
      sfos=self.fan_medium_speed

    self.fan[0]=sfos
    self.fan[1]=sfo

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
    target_typ,target_name=self.split_entity(target)
    
    state=self.bit_mask(target)

    self.log("state={}".format(state))
    if (not self.check_override_active(target)):   # if the override bit is set, then don't evaluate anything else.  Think of it as manual mode
      if (not state in self.targets[target]["onState"]) and (not state in self.targets[target]["dimState"]):     # these states always result in light being turned off or ignored
        if state in self.targets[target]["ignoreState"]:
          self.log("state={}, ignoring state".format(state))
        else:  # if we aren't in ignore state, then it must be off state
          self.log("state = {} turning off light".format(state))
          if target_typ=="light":
            self.my_turn_on(target,brightness=self.light_off)
          self.turn_off(target)
      elif state in self.targets[target]["onState"]:    # these states always result in light being turned on.
        if target_typ not in ["light","fan"]:
          self.log("state={} turning on {}".format(state,target))
          self.my_turn_on(target)
        else:
          if state in self.targets[target]["dimState"]:                      # when turning on lights, media player determines whether to dim or not.
            if target_typ=="light":
              if self.targets[target]["type"]=="fan":
                self.log("adjusting fan brightness")
                self.my_turn_on(target,brightness=self.fan_low)
              else:
                self.log("dim lights")
                self.my_turn_on(target,brightness=self.light_dim)
            elif target_typ=="fan":
              self.log("adjusting fan speed")
              self.my_turn_on(target,speed=self.fan_low_speed)
            else:
              self.log("unknown type assuming light")
              self.my_turn_on(target,brightness=self.light_dim)
          else:                                                   # it wasn't a media player dim situation so it's just a simple turn on the light.
            if self.targets[target]["type"]=="fan":
              if target_typ=="fan":
                self.log("state={} turning on fan {} at speed {}".format(state,target,self.fan[0])) 
                self.my_turn_on(target,speed=self.fan[0])
              else:
                self.log("state={} turning on fan {} at brightness {}".format(state,target,self.fan[1]))
                self.my_turn_on(target,brightness=self.fan[1])
            elif self.targets[target]["type"]=="light":
              self.log("state={} turning on light {} at brightness={}".format(state,target,self.light_max))
              self.my_turn_on(target,brightness=self.light_max)
    else:
      self.log("home override set so no automations performed")


  def my_turn_on(self,entity,**kwargs):
    self.log("entity={} kwargs={}".format(entity,kwargs))
    if not kwargs==None:
      current_state=self.get_state(entity,"all")
      attributes=current_state["attributes"]
      current_state=current_state["state"]

      self.log("current_state={}, attributes={}".format(current_state,attributes))
      if "brightness" in kwargs:
        if "brightness" in attributes:
          if not attributes["brightness"]==kwargs["brightness"]:
            self.log("turning on entity {} brightness {}".format(entity,kwargs["brightness"]))
            self.turn_on(entity,brightness=kwargs["brightness"])
          else:
            self.log("brightness unchanged")
        else:
          if current_state=="off":
            self.log("No Brightness assuming light {}")
            self.turn_on(entity,brightness=kwargs["brightness"])
      elif "speed" in kwargs:
        if "speed" in attributes:
          if not attributes["speed"]==kwargs["speed"]:
            self.log("turning on entity {} speed {}".format(entity,kwargs["speed"]))
            self.turn_on(entity,speed=kwargs["speed"])
          else:
            self.log("no change in speed")
        else:
          self.log("No Speed in attribute assuming fan")
          self.turn_on(entity,speed=kwargs["speed"])
      else:
        self.log("unknown attributes {}".format(kwargs))
    else:
      self.log("turning on entity {}".format(entity))
      self.turn_on(entity)

  #############
  #
  # normalize_state - take incoming states and convert any that are calculated to on/off values.
  #
  def normalize_state(self,target,trigger,newstate):
    tmpstate=""
    if newstate==None:                   # handle a newstate of none, typically means the object didn't exist.
      tmpstate=self.get_state(target)    # if thats the case, just return the state of the target so nothing changes.
    else:
      try:
        newstate=int(float(newstate))
        if self.targets[target]["triggers"][trigger]["type"]=="temperature":     # is it a temperature.
          self.log("normalizing temperature")
          currenttemp = newstate           # convert floating point to integer.
          if currenttemp>=self.high_temp:                     # handle temp Hi / Low state setting to on/off.
            tmpstate="on"
          elif currenttemp<=self.low_temp:
            tmpstate="off"
          else:
            tmpstate= self.get_state(target)              # If new state is in between target points, just return current state of target so nothing changes.
        elif self.targets[target]["triggers"][trigger]["type"]=="humidity":
          self.log("normalizing humidity")
          currenttemp = newstate           # convert floating point to integer.
          if currenttemp>=self.high_humidity:                     # handle temp Hi / Low state setting to on/off.
            tmpstate="on"
          elif currenttemp<=self.low_humidity:
            tmpstate="off"
          else:
            tmpstate= self.get_state(target)              # If new state is in between target points, just return current state of target so nothing changes.
        else:                                          # we have a number, but it's not a temperature so leave the value alone.
          self.log("newstate is a number, but not a temperature, so leave it alone : {}".format(newstate))
          tmpstate=newstate
      except:
        if newstate in ["home","house","Home","House"]:  # deal with having multiple versions of house and home to account for.
          tmpstate="home"
        else:
          tmpstate=newstate
    return tmpstate

  def check_override_active(self,target):
    override_active=False
    for override in self.targets[target]["overrides"]:
      if self.get_state(override)=="on":
        return True
 
  def bit_mask(self,target):
    state=0
    for trigger in self.targets[target]["triggers"]:      # loop through triggers
      t_dict=self.targets[target]["triggers"][trigger]
      t_state=str(self.normalize_state(target,trigger,self.get_state(trigger)))
      self.log("trigger={} onValue={} bit={} currentstate={}".format(trigger,t_dict["onValue"],t_dict["bit"],t_state))
      # or value for this trigger to existing state bits.
      state=state | (t_dict["bit"] if (t_state==t_dict["onValue"]) else 0)
      self.log("state={}".format(state))
    return state

