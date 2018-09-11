import appdaemon.plugins.hass.hassapi as hass
import datetime
import time
   
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

class office_lights(hass.Hass):

  def initialize(self):
    # self.LOGLEVEL="DEBUG"
    self.log("office_lights App")
    self.fan=["off",0]
#    exit(0)
    self.delay_handles={}
    # Read appdaemon.yaml file

    # targets are a dictionary based structure of targets and one or more trigger that impact the state of the target.
    if "targets" in self.args:
      self.targets=eval(self.args["targets"])
      self.log("self.targets={}".format(self.targets))
    else:
      self.log("targets must be defined in appdaemon.yaml file")

    # get time delay if lights turned on at night
    if "night_delay" in self.args:
      self.night_delay=self.args["night_delay"]
      self.log("night_delay = {}".format(self.night_delay))
    else:
      self.night_delay=15*60

    # for some rooms we don't want a light to turn on at full brightness, my office lights come on at 128 and dim to 50 when the tv is on for example.
    if "lights_max" in self.args:
      self.lights_max=self.args["lights_max"]
      self.log("lights_max={}".format(self.lights_max))
    else:
      self.lights_max=254

    if "lights_dim" in self.args:
      self.lights_dim = self.args["lights_dim"]
      self.log("self.lights_dim={}".format(self.lights_dim))
    else:
      self.lights_dim=128

    # In some cases especially with fans, the off value for the fan may still be technically on, just a slower setting.
    # I do this for my son's room, he has several computers in there that heat up the room so we keep the fan on at least a low setting all the time.
    if "light_off" in self.args:
      self.light_off=self.args["light_off"]
    else:
      self.light_off=0
    
    # in my office the fan is so close that setting the fan speed to 255 would blow all the papers off my desk, so the max is set lower than that.
    if "fan_max" in self.args:
      self.fan_high = self.args["fan_high"]
      self.log("self.fan_high={}".format(self.fan_hight))
    else:
      self.fan_high=254

    if "fan_med" in self.args:
      self.fan_med = self.args["fan_med"]
      self.log("self.fan_med={}".format(self.fan_med))
    else:
      self.fan_med=128

    if "fan_low" in self.args:
      self.fan_low=self.args["fan_low"]
      self.log("self.fan_low={}".format(self.fan_low))
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
      self.log("self.high_temp_slider={}".format(self.high_temp_slider))
    else:
      self.log("high_temp must be configured in appdaemon.yaml")
    if "low_temp" in self.args:
      self.low_temp_slider=self.args["low_temp"]
      self.log("self.low_temp_slider={}".format(self.low_temp_slider))
    else:
      self.log("low_temp must be configured in appdaemon.yaml")
    
    # humidity values to turn on/off the shower exhaust fans at.
    if "high_humidity" in self.args:
      self.high_humidity=self.args["high_humidity"]
      self.log("self.high_humidity={}".format(self.high_humidity))
    else:
      self.high_humidity=60
    if "low_humidity" in self.args:
      self.low_humidity=self.args["low_humidity"]
      self.log("self.low_humidity={}".format(self.low_humidity))
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
          if b in self.targets[a]["offState"] + self.targets[a]["dimState"] + self.targets[a]["ignoreState"] + self.targets[a]["offdelayState"] :
            self.log("onState overlaps in {}  on element {}".format(a,b))
            overlap=True

      for b in self.targets[a]["offState"]:
        if b>=0:
          if b in self.targets[a]["onState"] + self.targets[a]["dimState"] + self.targets[a]["ignoreState"] + self.targets[a]["offdelayState"] :
            self.log("offState overlaps in {} on element {}".format(a,b))
            overlap=True

      for b in self.targets[a]["dimState"]:
        if b>=0:
          if b in self.targets[a]["onState"] + self.targets[a]["offState"] + self.targets[a]["ignoreState"] + self.targets[a]["offdelayState"] :
            self.log("offState overlaps in {} on element {}".format(a,b))
            overlap=True

      for b in self.targets[a]["ignoreState"]:
        if b>=0:
          if b in self.targets[a]["onState"] + self.targets[a]["offState"] + self.targets[a]["dimState"] + self.targets[a]["offdelayState"] :
            self.log("offState overlaps in {} on element {}".format(a,b))
            overlap=True

      for b in self.targets[a]["offdelayState"]:
        if b>=0:
          if b in self.targets[a]["onState"] + self.targets[a]["offState"] + self.targets[a]["dimState"] + self.targets[a]["ignoreState"] :
            self.log("offState overlaps in {} on element {}".format(a,b))
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
        #self.log("targets[{}]['triggers'][{}]['type']={}".format(ent,ent_trigger,self.targets[ent]["triggers"][ent_trigger]["type"]))
        if self.targets[ent]["triggers"][ent_trigger]["type"]=="sun":
          self.log("registering sun triggers")
          self.run_at_sunrise(self.process_sun,offset=5*60,target=ent)
          self.log("sunrise trigger set")
          self.run_at_sunset(self.process_sun,offset=5*60,target=ent)
          self.log("sunset trigger set")
        else:
          # ok it's not sun so lets just setup an even trigger.
          self.log("registering normal state trigger")
          self.listen_state(self.targets[ent]["callback"],ent_trigger,target=ent)
      # End of trigger loop

      # all callbacks have been setup.  
      # lets process the current state of each target as we start up just to make sure everything is in the right state now.
      self.log("Lets process lights quickly for {} to make sure we are up to date".format(ent))
      self.process_light_state(ent)      # process each light as we register a callback for it's triggers rather than wait for a trigger to fire first.

    # End of target (ent) loop
    self.log("Office_lights End of initialization")

  ########
  #
  # process_sun  - handler for sun schedule
  #
  def process_sun(self,kwargs):
    self.log("target={} trigger={}".format(kwargs["target"],"sunrise" if self.sun_up() else "sunset"))

    # a trigger based on sunup or sunset fired so check the target entity it was associated with.
    self.process_light_state(kwargs["target"])    # something changed so go evaluate the state of everything

  ########
  #
  # state change handler.  All it does is call process_light_state all the work is done there.
  #
  def light_state_handler(self,trigger,attr,old,new,kwargs):
    self.log("trigger = {}, attr={}, old={}, new={}, kwargs={}".format(trigger,attr,old,new,kwargs))
    self.process_light_state(kwargs["target"])

  def notify_state_handler(self,trigger,attr,old,new,kwargs):
    self.log("trigger - {}, attr={}, old={}, new={}, kwargs={}".format(trigger,attr,old,new,kwargs))
    self.process_alert(kwargs["target"])

  def process_alert(self,target,**kwargs):
    self.log("In process_alert target-{}".format(target))
    state=0
    type_bits={}
    state=self.bit_mask(target)
    self.log("process_alert state={}".format(state))
    if(self.check_override_active(target)):
      self.log("Override Active")
    elif state in self.targets[target]["ignoreState"]:
      self.log("state={} ignoring state".format(state))
    elif state in self.targets[target]["offState"]:
      self.log("cannot turnoff notify ")
    elif state in self.targets[target]["offdelayState"]:
      self.log("Cannot turn off notify even with a delay")
    elif state in self.targets[target]["onState"]:
      self.log("target - {}, message - {} on - {}".format(target,self.targets[target]["notify_Message"],self.targets[target]["alexa_device"]))
      self.fire_event("SPEAK_EVENT",media_player=self.targets[target]["alexa_device"],message=self.targets[target]["notify_Message"])
    elif state in self.targets[target]["dimState"]:
      self.log("Cannot dim notify")
    else :
      self.log("unknown state {}".format(state))

  ########
  #
  # process_light_state.  All the light processing happens in here.
  #
  def process_light_state(self,target,**kwargs):
    # build current state binary flag.
    self.log("self.name={}".format(self.name))
    self.set_state("sensor."+self.name,state=self.time().strftime("%H:%M:%S"))
    state=0
    type_bits={}
    target_typ,target_name=self.split_entity(target)
   
    # create the room state bitmask. 
    state=self.bit_mask(target)

    # you thought that would be the hard part, that was the easy part.  Now we have to figure out how to turn on/off/dim the target.

    self.log("state={}".format(state))

    # first is an override that impacts the target in effect (input_booleans are used to represent overrides in HA)  
    if (self.check_override_active(target)):   # if the override bit is set, then don't evaluate anything else.  Think of it as manual mode
      self.log("Override active")

    elif state in self.targets[target]["ignoreState"]:
      # The light state is right where it is, so don't change it.
      self.log("state={} ignoring state".format(state))

    elif state in self.targets[target]["offState"]:
      # first lets clean up any remaining delay turnoffs
      self.stop_delay_listener(target)

      if target_typ=="light":     
        self.log("state {} dimmingf light {} to off state".format(state,target))
        # if the target is a light, turn the brightness to the off state before turning the light off.
        self.my_turn_on(target,brightness=self.light_off)
      # now regardless of the target type, turn it off.
      self.log("state {} turning device {} off".format(state,target))
      self.my_turn_off(target)

    elif state in self.targets[target]["offdelayState"]:
      self.log("delay_handles={}".format(self.delay_handles))
      if target in self.delay_handles:
        self.log("state={} delay for {} already active".format(state,target))
      else:
        self.log("state={} turn off delay activated for {}".format(state,target))
        self.delay_handles[target]=self.listen_state(self.delay_trigger, target, new = "on", duration = self.night_delay, immediate=True, oneshot=True, delay=True, source="appdaemon")

    elif state in self.targets[target]["onState"]:
      # Ok we are turning things on

      # first lets clean up any remaining delay turnoffs
      self.stop_delay_listener(target)

      if target_typ in ["light","fan"]:
        # Fans and lights have dimmer and speed qualities that we have to address

        if target_typ=="fan":
          # this is a fan, it doesn't matter what it thinks it is, it's a fan.
          self.log("state={} turning on fan {} at speed {}".format(state,target,self.fan[0]))
          self.my_turn_on(target,speed=self.fan[0])

        else:
          # this could be a light or a light that is controlling a fan
          if self.targets[target]["type"]=="fan":
            # this thinks it's a fan so treat it like a fan controlled by brightness instead of speed settings.
            self.log("state={} turning on fan {} at brightness {}".format(state,target,self.fan[1]))
            self.my_turn_on(target,brightness=self.fan[1])

          elif self.targets[target]["type"]=="light":
            # This thinks its a light so turn it on with brightness settings
            self.log("state={} turning on light {} at brightness {}".format(state,target,self.lights_max))
            self.my_turn_on(target,brightness=self.lights_max)
          else:
            self.log("this device doesn't know what it is trying to be : {}".format(self.targets[target]["type"]))
      else:
        # this isn't a light or a fan so just turn it on whatever it is
        self.log("state={} turning on {}".format(state,target))
        self.my_turn_on(target)

    elif state in self.targets[target]["dimState"]:
      # first lets clean up any remaining delay turnoffs
      self.stop_delay_listener(target)

      if target_typ in ["light"]:
          if self.targets[target]["type"]=="light": 
            # This thinks its a light so turn it on with brightness settings
            self.log("state={} turning on light {} at brightness {}".format(state,target,self.lights_dim))
            self.my_turn_on(target,brightness=self.lights_dim)
          else:
            self.log("{} cannot be dimmed".format(self.targets[target]["type"]))
      else:
        # this isn't a light so it can't be dimmed
        self.log("{} cannot be dimmed".format(target_typ))
    else:
      self.log("unknown state {}".format(state))

  ########
  #
  #  delay listen trigger
  #
  ########            
  def delay_trigger(self,entity,estate,old,new,kwargs):
    self.log("delay callback fired for {}".format(entity))
    self.my_turn_off(entity)

  ########
  #
  #  Stop delay listener - Removes delay listener from schedule
  #
  #######
  def stop_delay_listener(self,target):
    if target in self.delay_handles:
      try:
        self.cancel_listen_state(self.delay_handles[target])
      except:
        self.log("{} listener in dictionary but not in system continuing".format(target))
      self.delay_handles.pop(target)



  ########
  #
  #  turn off override, right now it doesn't do anything, but it might need to so I put it in just in case.
  #
  ########
  def my_turn_off(self,entity,**kwargs):
    #self.log("turning off {}".format(entity))
    etyp,ename=self.split_entity(entity)
    self.turn_off(entity)
    if etyp=="light":
      i=0
      while ((not self.get_state(entity)=="off") and (i<100)):
        self.log("waiting for {} to turn off brightness={}".format(entity,self.get_state(entity,attribute="brightness"))) 
        i=i+1

  #########
  #
  # My turn on
  #
  #########
  def my_turn_on(self,entity,**kwargs):
    self.log("entity={} kwargs={}".format(entity,kwargs))

    # were any additional arguements passed in through kwargs
    if not kwargs=={}:
      # get the entities current state
      if self.entity_exists(entity):
        cstate=self.get_state(entity,attribute="all")
        attributes=cstate["attributes"]
        current_state=cstate["state"]

        self.log("current_state={}, attributes={}".format(current_state,attributes))

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
        self.log("Entity {} does not exist in its entirity, HA may have just restarted".format(entity))
    else:
      # no kwargs passed in so no special handling required, just turn it on.
      devtyp,device=self.split_entity(entity)
      if devtyp=="lock":
        self.log("About to lock {}".format(entity))
        self.call_service("lock/lock",entity_id=entity)
      else:
        self.turn_on(entity)
    self.log("Done")

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
          self.low_humidity=self.get_state("sensor.master_relative_humidity")
          self.high_humidity=self.low_humidity+3
          self.log("resetting low_humidity to {} and high_humidity to {}".format(self.low_humidity,self.high_humidity))
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
      self.log("get_state({})={}".format(trigger,self.get_state(trigger)))
      t_state=str(self.normalize_state(target,trigger,self.get_state(trigger)))

      self.log("trigger={} onValue={} bit={} currentstate={}".format(trigger,t_dict["onValue"],t_dict["bit"],t_state))

      # bitwise or value for this trigger to existing state bits.
      # if the current state of the entity matches the expected on state from the dictionary use the bit value, otherwise use 0
      state=state | (t_dict["bit"] if (t_state==t_dict["onValue"]) else 0)
      self.log("state={}".format(state))
    return state

