import my_appapi as appapi

##############
# 
#  By design light_control is run for each room or logical combination of lights so multiple instances of it may be running at the same time.
#  Each room has it's own section in the appdaemon.yaml file.
#  The primary data structure for the app is composed of a dictionary of targets devices.
#    Each target device has a dictionary of triggers that impact the state of the target device.
#    For example, the target office_light has triggers of (office_door, office_motion and office_tv, each of which are evaluated when deciding
#    whether office_light should be on/off/dim.
#
#    Each trigger has associated with it a bit value (0,1,2,4,8,16,32,64,128, etc)  Each bit value is unique within a room.
#    As the target is processed, each trigger is evaluated, if it is on, it's bit value is added together with other on triggers to create
#    a state value for the room.  
#
#    Each target has associated with it 4 lists (on_state,off_state,dim_state,ignore_state).  If the room state is in one of these lists, that
#    action is performed on the target.  
#
#    By bringing everything down to the bit level, the same application can be used for multiple rooms, since the if statements aren't specifying
#    the trigger entites, just the bit values associated with the states.
#
##############

class office_lights(appapi.my_appapi):

  def initialize(self):
    # self.LOGLEVEL="DEBUG"
    self.log("office_lights App")
    self.fan=["off",0]

    # Read appdaemon.yaml file

    # targets are a dictionary based structure of targets and one or more trigger that impact the state of the target.
    if "targets" in self.args:
      self.targets=eval(self.args["targets"])
    else:
      self.log("targets must be defined in appdaemon.yaml file")

    # for some rooms we don't want a light to turn on at full brightness, my office lights come on at 128 and dim to 50 when the tv is on for example.
    if "light_max" in self.args:
      self.light_max=self.args["light_max"]
    else:
      self.light_max=254

    if "light_dim" in self.args:
      self.light_dim = self.args["light_dim"]
    else:
      self.light_dim=128

    # In some cases especially with fans, the off value for the fan may still be technically on, just a slower setting.
    # I do this for my son's room, he has several computers in there that heat up the room so we keep the fan on at least a low setting all the time.
    if "light_off" in self.args:
      self.light_off=self.args["light_off"]
    else:
      self.light_off=0
    
    # in my office the fan is so close that setting the fan speed to 255 would blow all the papers off my desk, so the max is set lower than that.
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

    # these are set to account for the new "fan" device types that don't use a dimmer like above.
    self.fan_high_speed="high"
    self.fan_medium_speed="medium"
    self.fan_low_speed="low"

    # set value corresponding to the fan being off when compared to the new fan states
    if "fan_off" in self.args:
      self.fan_off=self.args["fan_off"]
    else:
      self.fan_off=0

    # the high and low temperatures that cause the fan to turn on or off, these are read from an input slider.  
    # these values are the names of the sliders that we read the value from for each occurance of the app.
    if "high_temp" in self.args:
      self.high_temp_slider=self.args["high_temp"]
    else:
      self.log("high_temp must be configured in appdaemon.yaml")
    if "low_temp" in self.args:
      self.low_temp_slider=self.args["low_temp"]
    else:
      self.log("low_temp must be configured in appdaemon.yaml")
    
    # humidity values to turn on/off the shower exhaust fans at.
    if "high_humidity" in self.args:
      self.high_humidity=self.args["high_humidity"]
    else:
      self.high_humidity=60
    if "low_humidity" in self.args:
      self.low_humidity=self.args["low_humidity"]
    else:
      self.low_humidity=59

    # deal with fan on speed depending on whether it's a high/low/med fan or a dimmer style
    if "fan_on_speed" in self.args:
      try:
        #see if we have a numeric value
        sfo=int(float(self.args["fan_on_speed"]))
        # it's numeric so find the appropriate hi/med/low text to go with it.
        if (self.fan_on>self.fan_medium):
          sfos=self.fan_high_speed
        elif (self.fan_on>self.fan_low):
          sfos=self.fan_medium_speed
        else:
          sfos=self.fan_low_speed
      except:
        # it's not numeric so it must be high/med/low so determine numeric values.
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

    # self.fan is an array that stores the text and the speed version of the fan speeds.
    self.fan[0]=sfos
    self.fan[1]=sfo

    # check the on_state/off_state/ignore_state lists to see if there is any overlap where we are telling
    # the app to turn something on and off based on the same room state.
    overlap=False
    for a in self.targets:
      for b in self.targets[a]["onState"]:
        if b>=0:
          if b in self.targets[a]["offState"]:
            self.log("onState overlaps offState in {} on element {}".format(a,b))
            overlap=True
          if b in self.targets[a]["ignoreState"]:
            self.log("onState overlaps ignoreState in {} on element {}".format(a,b))
            overlap=True
      for b in self.targets[a]["offState"]:
        if b>=0:
          if b in self.targets[a]["ignoreState"]:
            self.log("ignoreState overlaps offState in {} on element {}".format(a,b))
            overlap=True
    if overlap:
      self.log("Please fix configuration before continuing")
      exit

    # loop through the targets and setup listeners for the triggers.
    for ent in self.targets:

      # loop through the triggers.
      for ent_trigger in self.targets[ent]["triggers"]:

        self.log("registering callback for {} on {} for target {}".format(ent_trigger,self.targets[ent]["callback"],ent))
     
        # if we are using the sun for a trigger, we want to run a scheduled for sunup and sunset instead of an event trigger.
        if self.targets[ent]["triggers"][ent_trigger]["type"]=="sun":
          self.run_at_sunrise(self.process_sun,offset=5*60,target=ent)
          self.run_at_sunset(self.process_sun,offset=5*60,target=ent)
        else:
          # ok it's not sun so lets just setup an even trigger.
          self.listen_state(self.targets[ent]["callback"],ent_trigger,target=ent)
      # End of trigger loop

      # all callbacks have been setup.  
      # lets process the current state of each target as we start up just to make sure everything is in the right state now.
      self.process_light_state(ent)      # process each light as we register a callback for it's triggers rather than wait for a trigger to fire first.

   # End of target (ent) loop

  ########
  #
  # process_sun  - handler for sun schedule
  #
  def process_sun(self,kwargs):
    self.log("target={} trigger={}".format(kwargs["target"],"sunrise" if self.sun_up() else "sunset"))

    # a trigger based on sunup or sunset fired so check the target entity it was associated with.
    self.process_light_state(kwargs["target"])    # something changed so go evaluate the state of everything

#    # either run_at_sunrise or run_at_sunset was triggered so re-register it.
#    if self.sun_up():
#      # there is currently an issue where when the sun schedule fires and we try to re-schedule an event that same second,
#      # the next time it's triggered, it triggers before sunset so it thinks the sun is still above the horizon. 
#      # so to account for that we are just triggering at 5 minutes past sunup or sunset.
#      self.run_at_sunrise(self.process_sun,offset=5*60,target=kwargs["target"])
#    else:
#      self.run_at_sunset(self.process_sun,offset=5*60,target=kwargs["target"])
  
   
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
   
    # create the room state bitmask. 
    state=self.bit_mask(target)

    # you thought that would be the hard part, that was the easy part.  Now we have to figure out how to turn on/off/dim the target.

    self.log("state={}".format(state))

    # first is an override that impacts the target in effect (input_booleans are used to represent overrides in HA)  
    if (not self.check_override_active(target)):   # if the override bit is set, then don't evaluate anything else.  Think of it as manual mode
     
      # ok, if we aren't turning the target on, or dimming it, then we must be either turning it off or ignoring it.
      if (not state in self.targets[target]["onState"]) and (not state in self.targets[target]["dimState"]):     # these states always result in light being turned off or ignored
        
        # are we ignoring the target at this time.
        if state in self.targets[target]["ignoreState"]:
          self.log("state={}, ignoring state".format(state))

        # if we aren't ignoring it, we must be turning it off
        else:
          self.log("state = {} turning off light".format(state))

          # lights and switches turn off slightly differently.
          if target_typ=="light":
            # because lights dim, we are going to tell it to dim to 0 
            self.my_turn_on(target,brightness=self.light_off)
          
          # now that we have handled lights, everything including lights responds to a turn_off signal
          self.turn_off(target)

      # ok, we were not turning the target off, or ignoring it, so we must be turning it on or dimming it.
      # because dimming uses the turn_on command we are handling them both here.
      elif state in self.targets[target]["onState"]:    # these states always result in light being turned on.
 
        # if it's not a light or a fan, then just turn it on.
        if target_typ not in ["light","fan"]:
          self.log("state={} turning on {}".format(state,target))
          self.my_turn_on(target)
        else:
         
          # we are dealing with a light or a fan (something with more than an on/off state
          # are we trying to dim it
          if state in self.targets[target]["dimState"]:                      # when turning on lights, media player determines whether to dim or not.
            
            # we are dimming it
            if target_typ=="light":
              # it is a light entity type.

              # this is a little confusing here.  Older fan switches, reported as lights, so here we are checking not on what the switch is reporting as
              # we know it's reporting as a light, but are we using it to control a light or a fan?
              if self.targets[target]["type"]=="fan":
                self.log("adjusting fan brightness")
                self.my_turn_on(target,brightness=self.fan_low)
              else:
                self.log("dim lights")
                self.my_turn_on(target,brightness=self.light_dim)
           
            # ok, this device is reporting as a fan, not a light so it's only got high/medium/low/off states.
            elif target_typ=="fan":
              self.log("adjusting fan speed")
              self.my_turn_on(target,speed=self.fan_low_speed)
            else:
              # we don't know what this is, so we are just going to treat it like a light and see what happens
              self.log("unknown type assuming light")
              self.my_turn_on(target,brightness=self.light_dim)
  
          # we aren't dimming anything, it's a true turn on situation
          else:                                                   
            # are we turning on a target we are using as a fan
            if self.targets[target]["type"]=="fan":

              # is it reporting as a fan  (not sure why we tested this in a different order than above, but who cares it does the same
              if target_typ=="fan":

                # we are using it as a fan and it is reporting as a fan so use the high/medium/low settings
                self.log("state={} turning on fan {} at speed {}".format(state,target,self.fan[0])) 
                self.my_turn_on(target,speed=self.fan[0])
              else:

                # we are treating it as a fan, but it's not reporting as a fan, so adjust the brightness
                self.log("state={} turning on fan {} at brightness {}".format(state,target,self.fan[1]))
                self.my_turn_on(target,brightness=self.fan[1])

            # it's not something we are treating as a fan, so is it something we think is a light?
            elif self.targets[target]["type"]=="light":

              # it something we are treating as a light, so turn it on and set it's brightness
              self.log("state={} turning on light {} at brightness={}".format(state,target,self.light_max))
              self.my_turn_on(target,brightness=self.light_max)

    
    else: # assicated with override check above 
      self.log("home override set so no automations performed")


  #########
  #
  # My turn on
  #
  #########
  def my_turn_on(self,entity,**kwargs):
    #self.log("entity={} kwargs={}".format(entity,kwargs))

    # were any additional arguements passed in through kwargs
    if not kwargs=={}:
      # get the entities current state
      current_state=self.get_state(entity,"all")
      attributes=current_state["attributes"]
      current_state=current_state["state"]

      #self.log("current_state={}, attributes={}".format(current_state,attributes))

      # was brightness passed in through kwargs
      if "brightness" in kwargs:

        # does the target respond to brightness
        if "brightness" in attributes:

          # did the brightness actually change or was it something else that triggered this
          if not attributes["brightness"]==kwargs["brightness"]:
            # brightness changed so send the change to the entity
            self.turn_on(entity,brightness=kwargs["brightness"])

          else:
            # the brightness didn't change it was something else, so don't do anything
            self.log("brightness unchanged")
        else:
          # brightness is not an attribute of this entity (or the entity is turned off )

          # is the entity turned off
          if current_state=="off":

            # the entity is turned off, so the brightness wouldn't have shown in the attributes, so we can turn it on.
            self.turn_on(entity,brightness=kwargs["brightness"])

      # did the high/medium/low type of speed get passed in, instead of brightness
      elif "speed" in kwargs:
        
        # does this entity support speed?
        if "speed" in attributes:
    
          # are the speeds the same
          if not attributes["speed"]==kwargs["speed"]:
            # no so turn on the fan
            self.turn_on(entity,speed=kwargs["speed"])
          else:
            # yes speeds are the same so something else changed nothing to do here
            self.log("no change in speed")
        else:  # speed is not in attributes
          self.turn_on(entity,speed=kwargs["speed"])

      # say what??
      else:
        self.log("unknown attributes {}".format(kwargs))
    else:
      # no special handling required, just turn it on.
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
      
      # lets see if we have a numeric or a string value
      try:
        #self.log("newstate={} {}*****************************".format(newstate,self.targets[target]["triggers"][trigger]["type"]))
        newstate=int(float(newstate))
        
        # if we got to here we have a numeric value
        # are we looking at a temperature trigger?
        if self.targets[target]["triggers"][trigger]["type"]=="temperature":     # is it a temperature.

          # we pull the high and low temp sliders again just in case they changed since the last time we ran.
          self.high_temp=int(float(self.get_state(self.high_temp_slider)))
          self.low_temp=int(float(self.get_state(self.low_temp_slider)))
          self.log("{}={}, {}={}".format(self.high_temp_slider,self.high_temp,self.low_temp_slider,self.low_temp))

          currenttemp = newstate
          # check current temperature against high and low temperatures
          # if the currenttemp is >= high temp, then we return on because the thermostat should be on
          if currenttemp>=self.high_temp: 
            tmpstate="on"
          # else if the current temp is lower than the low temp, then we are below the low temp, so thermostat shoudl be off
          elif currenttemp<=self.low_temp:
            tmpstate="off"
          # ok current temperature is in between so just leave the thermostat the way it is for now.
          else:
            tmpstate= self.get_state(target) 

        # ok we aren't dealing with temperature how about humidity
        elif self.targets[target]["triggers"][trigger]["type"]=="humidity":
          currenthumidity = newstate
          # if currenthumidity is > high set point, send back on
          if currenthumidity>=self.high_humidity:                     # handle temp Hi / Low state setting to on/off.
            tmpstate="on"
          # else if currenthumidity is below low humidity, then we want to turn off
          elif currenthumidity<=self.low_humidity:
            tmpstate="off"
          # we are somewhere in between so just leave the target the way it is for now.
          else:
            tmpstate= self.get_state(target)
        else:                                          
          # we have a number, but it's not a temperature so leave the value alone.  This might be a door, or motion detector
          tmpstate=newstate

      # ok if we got here, it wasn't a number so handle string normalization
      except:
        if newstate in ["home","house","Home","House"]:  # deal with having multiple versions of house and home to account for.
          tmpstate="home"
       
        # deal with time triggers, 
        elif self.targets[target]["triggers"][trigger]["type"]=="time":
          tbool=False
          # times are a dictionary of events with on and off keys so lets look through the possible events
          for event in self.targets[target]["triggers"][trigger]["time"]:

            # get the on and off times into variables just to shorten the if statement below.
            starttime=self.targets[target]["triggers"][trigger]["time"][event]["on"]
            endtime=self.targets[target]["triggers"][trigger]["time"][event]["off"]
            # if now is between starttime and endtime, return on 
            if self.now_is_between(starttime,endtime):
              tbool=True
          # end of loop

          tmpstate="on" if tbool else "off"

        else:
          # it's a string, but it wasn't home or time so just return the new state
          tmpstate=newstate

    self.log("Normalized {} to {}".format(newstate,tmpstate))
    return tmpstate

  ########
  #
  #  check_override
  #
  #######
  def check_override_active(self,target):
    override_active=False
    # check each override the the overrides key pair to see if it's turned on
    for override in self.targets[target]["overrides"]:

      if self.get_state(override)=="on":
        # override was turned on, so we are in an override situation
        override_active=True

    return override_active

  ##############
  #
  #  Bit_mask
  #
  ##############
  def bit_mask(self,target):
    state=0
    for trigger in self.targets[target]["triggers"]:      # loop through triggers
     
      # get the trigger dictionary for each trigger, this has the bit number and other stuff in it
      t_dict=self.targets[target]["triggers"][trigger]

      # get the current state of the trigger device to compare against the on_state from the dictionary above
      t_state=str(self.normalize_state(target,trigger,self.get_state(trigger)))

      self.log("trigger={} onValue={} bit={} currentstate={}".format(trigger,t_dict["onValue"],t_dict["bit"],t_state))

      # bitwise or value for this trigger to existing state bits.
      # if the current state of the entity matches the expected on state from the dictionary use the bit value, otherwise use 0
      state=state | (t_dict["bit"] if (t_state==t_dict["onValue"]) else 0)
      self.log("state={}".format(state))
    return state

